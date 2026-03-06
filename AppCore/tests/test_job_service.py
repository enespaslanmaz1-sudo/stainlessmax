import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from lib.db.job_service import IdempotencyKeyMismatchError, InvalidTransitionError, JobRepository
from lib.db.models import Base, DEFAULT_TENANT_ID, Job, JobEvent, JobStatus, Tenant, UploadAttempt


class FakeClock:
    def __init__(self, initial: datetime):
        self._now = initial

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now = self._now + delta


@pytest.fixture
def pg_session_factory(monkeypatch):
    database_url = (pytest.importorskip("os").getenv("DATABASE_URL") or "").strip()
    if not database_url.startswith("postgresql"):
        pytest.skip("DATABASE_URL must point to a PostgreSQL database for claim/locking tests")

    schema_name = f"test_job_service_{uuid.uuid4().hex[:8]}"
    engine = create_engine(database_url, future=True)

    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute(f'SET search_path TO "{schema_name}"')
        cur.close()

    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    try:
        yield SessionLocal
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        engine.dispose()


@pytest.fixture
def fake_clock():
    return FakeClock(datetime(2026, 2, 17, 12, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def repo(pg_session_factory, fake_clock):
    return JobRepository(
        pg_session_factory,
        max_retries=3,
        retry_cooldown_seconds=300,
        now_provider=fake_clock.now,
    )


def _create_job(session_factory, *, status: JobStatus, scheduled_time=None, job_metadata=None):
    with session_factory() as session:
        job = Job(
            platform="tiktok",
            account_id="acc-1",
            status=status,
            scheduled_time=scheduled_time,
            payload={"x": 1},
            job_metadata=job_metadata,
        )
        session.add(job)
        session.commit()
        return job.id


def _create_tenant(session_factory, *, name: str, slug: str) -> uuid.UUID:
    with session_factory() as session:
        tenant = Tenant(name=name, slug=slug, plan="pro", is_active=True)
        session.add(tenant)
        session.commit()
        return tenant.id


def _run_claim_workers(
    claim_func,
    *,
    tenant_id: uuid.UUID = DEFAULT_TENANT_ID,
    worker_count: int = 10,
    limit: int = 10,
) -> list[uuid.UUID]:
    barrier = threading.Barrier(worker_count)
    results: list[list[uuid.UUID]] = []
    lock = threading.Lock()

    def worker(i: int):
        barrier.wait()
        jobs = claim_func(worker_name=f"w{i}", limit=limit, tenant_id=tenant_id)
        with lock:
            results.append([j.id for j in jobs])

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(worker_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    return [job_id for batch in results for job_id in batch]


def test_no_double_pick_under_concurrent_workers_pending_bulk(repo, pg_session_factory, fake_clock):
    for _ in range(30):
        _create_job(
            pg_session_factory,
            status=JobStatus.pending,
            scheduled_time=fake_clock.now() - timedelta(minutes=1),
        )

    claimed = _run_claim_workers(repo.claim_for_generation, worker_count=10, limit=10)

    assert len(claimed) == 30
    assert len(set(claimed)) == 30


def test_no_double_pick_under_concurrent_workers_retrying_upload_bulk(repo, pg_session_factory, fake_clock):
    for _ in range(30):
        _create_job(
            pg_session_factory,
            status=JobStatus.retrying,
            scheduled_time=fake_clock.now() - timedelta(minutes=1),
            job_metadata={"retry_target": "upload"},
        )

    claimed = _run_claim_workers(repo.claim_for_upload, worker_count=10, limit=10)

    assert len(claimed) == 30
    assert len(set(claimed)) == 30


def test_scheduled_time_is_respected_for_pending_and_retrying(repo, pg_session_factory, fake_clock):
    due_pending_id = _create_job(
        pg_session_factory,
        status=JobStatus.pending,
        scheduled_time=fake_clock.now() - timedelta(minutes=1),
    )
    _create_job(
        pg_session_factory,
        status=JobStatus.pending,
        scheduled_time=fake_clock.now() + timedelta(hours=2),
    )

    due_retrying_upload_id = _create_job(
        pg_session_factory,
        status=JobStatus.retrying,
        scheduled_time=fake_clock.now() - timedelta(minutes=1),
        job_metadata={"retry_target": "upload"},
    )
    _create_job(
        pg_session_factory,
        status=JobStatus.retrying,
        scheduled_time=fake_clock.now() + timedelta(hours=2),
        job_metadata={"retry_target": "upload"},
    )

    gen_claimed = repo.claim_for_generation(worker_name="gen-worker", limit=10, tenant_id=DEFAULT_TENANT_ID)
    gen_ids = {job.id for job in gen_claimed}
    assert due_pending_id in gen_ids
    assert len(gen_ids) == 1

    upload_claimed = repo.claim_for_upload(worker_name="upload-worker", limit=10, tenant_id=DEFAULT_TENANT_ID)
    upload_ids = {job.id for job in upload_claimed}
    assert due_retrying_upload_id in upload_ids
    assert len(upload_ids) == 1


def test_claim_event_from_retrying_is_correct(repo, pg_session_factory, fake_clock):
    job_id = _create_job(
        pg_session_factory,
        status=JobStatus.retrying,
        scheduled_time=fake_clock.now() - timedelta(minutes=1),
        job_metadata={"retry_target": "upload"},
    )

    claimed = repo.claim_for_upload(worker_name="upload-worker", limit=1, tenant_id=DEFAULT_TENANT_ID)
    assert [j.id for j in claimed] == [job_id]

    with pg_session_factory() as session:
        latest_event = session.execute(
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.created_at.desc())
        ).scalar_one()

    assert latest_event.event_type == "claimed_upload"
    assert latest_event.event_payload["from"] == "retrying"
    assert latest_event.event_payload["to"] == "uploading"


def test_orphan_retrying_job_is_failed_with_event(repo, pg_session_factory, fake_clock):
    job_id = _create_job(
        pg_session_factory,
        status=JobStatus.retrying,
        scheduled_time=fake_clock.now() - timedelta(minutes=1),
        job_metadata={},
    )

    claimed = repo.claim_for_upload(worker_name="upload-worker", limit=10, tenant_id=DEFAULT_TENANT_ID)
    assert claimed == []

    with pg_session_factory() as session:
        job = session.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert job.status == JobStatus.failed
        assert "missing retry_target" in (job.error_message or "")

        event = session.execute(
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.created_at.desc())
        ).scalar_one()
        assert event.event_type == "retry_orphan_failed"
        assert event.event_payload["reason"] == "missing_retry_target"


def test_invalid_transition_is_rejected(repo, pg_session_factory):
    job_id = _create_job(pg_session_factory, status=JobStatus.ready)

    with pytest.raises(InvalidTransitionError):
        repo.transition_status(
            job_id=job_id,
            expected_from=JobStatus.pending,
            to_status=JobStatus.generating,
            event_type="invalid",
            tenant_id=DEFAULT_TENANT_ID,
        )


def test_retry_cooldown_requeue_and_eventual_failed_without_manual_status_toggle(repo, pg_session_factory, fake_clock):
    job_id = _create_job(
        pg_session_factory,
        status=JobStatus.ready,
        scheduled_time=fake_clock.now() - timedelta(minutes=1),
    )

    first_claim = repo.claim_for_upload(worker_name="upload-worker", limit=1, tenant_id=DEFAULT_TENANT_ID)
    assert [j.id for j in first_claim] == [job_id]

    state1 = repo.mark_upload_failed(
        job_id=job_id,
        platform="tiktok",
        account_id="acc-1",
        error_message="e1",
        error_code="E1",
        tenant_id=DEFAULT_TENANT_ID,
    )
    assert state1.status == JobStatus.retrying
    assert state1.retry_count == 1
    assert state1.scheduled_time == fake_clock.now() + timedelta(seconds=300)

    second_claim_too_early = repo.claim_for_upload(worker_name="upload-worker", limit=1, tenant_id=DEFAULT_TENANT_ID)
    assert second_claim_too_early == []

    fake_clock.advance(timedelta(seconds=301))

    second_claim = repo.claim_for_upload(worker_name="upload-worker", limit=1, tenant_id=DEFAULT_TENANT_ID)
    assert [j.id for j in second_claim] == [job_id]

    state2 = repo.mark_upload_failed(
        job_id=job_id,
        platform="tiktok",
        account_id="acc-1",
        error_message="e2",
        error_code="E2",
        tenant_id=DEFAULT_TENANT_ID,
    )
    assert state2.status == JobStatus.retrying
    assert state2.retry_count == 2

    fake_clock.advance(timedelta(seconds=301))

    third_claim = repo.claim_for_upload(worker_name="upload-worker", limit=1, tenant_id=DEFAULT_TENANT_ID)
    assert [j.id for j in third_claim] == [job_id]

    state3 = repo.mark_upload_failed(
        job_id=job_id,
        platform="tiktok",
        account_id="acc-1",
        error_message="e3",
        error_code="E3",
        tenant_id=DEFAULT_TENANT_ID,
    )
    assert state3.status == JobStatus.failed
    assert state3.retry_count == 3

    with pg_session_factory() as session:
        attempts = session.execute(
            select(UploadAttempt).where(UploadAttempt.job_id == job_id).order_by(UploadAttempt.attempt_no.asc())
        ).scalars().all()
        assert [a.attempt_no for a in attempts] == [1, 2, 3]

        events = session.execute(select(JobEvent).where(JobEvent.job_id == job_id)).scalars().all()
        assert len(events) >= 6


def test_idempotency_key_set_and_verify(repo, pg_session_factory):
    job_id = _create_job(pg_session_factory, status=JobStatus.pending)

    key = repo.ensure_idempotency_key(job_id=job_id, idempotency_key="idem-1", tenant_id=DEFAULT_TENANT_ID)
    assert key == "idem-1"

    same_key = repo.ensure_idempotency_key(job_id=job_id, idempotency_key="idem-1", tenant_id=DEFAULT_TENANT_ID)
    assert same_key == "idem-1"

    with pytest.raises(IdempotencyKeyMismatchError):
        repo.ensure_idempotency_key(job_id=job_id, idempotency_key="idem-2", tenant_id=DEFAULT_TENANT_ID)


def test_tenant_a_cannot_access_tenant_b_job(repo, pg_session_factory, fake_clock):
    tenant_a = _create_tenant(pg_session_factory, name="Tenant A", slug=f"tenant-a-{uuid.uuid4().hex[:8]}")
    tenant_b = _create_tenant(pg_session_factory, name="Tenant B", slug=f"tenant-b-{uuid.uuid4().hex[:8]}")

    job_b = _create_job(
        pg_session_factory,
        status=JobStatus.pending,
        scheduled_time=fake_clock.now() - timedelta(minutes=1),
        job_metadata={"from": "tenant_b"},
    )

    with pg_session_factory() as session:
        session.execute(
            text("UPDATE jobs SET tenant_id = :tenant_id WHERE id = :job_id"),
            {"tenant_id": tenant_b, "job_id": job_b},
        )
        session.commit()

    claimed_by_a = repo.claim_for_generation(worker_name="worker-a", limit=10, tenant_id=tenant_a)
    assert [j.id for j in claimed_by_a] == []

    claimed_by_b = repo.claim_for_generation(worker_name="worker-b", limit=10, tenant_id=tenant_b)
    assert [j.id for j in claimed_by_b] == [job_b]

    with pytest.raises(InvalidTransitionError):
        repo.transition_status(
            job_id=job_b,
            expected_from=JobStatus.generating,
            to_status=JobStatus.ready,
            event_type="tenant_a_try_update",
            tenant_id=tenant_a,
        )

    with pytest.raises(IdempotencyKeyMismatchError):
        repo.ensure_idempotency_key(job_id=job_b, idempotency_key="idem-a", tenant_id=tenant_a)
