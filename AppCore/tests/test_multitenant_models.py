import uuid

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from lib.db.models import Base, Job, JobStatus, Tenant


@pytest.fixture
def pg_session_factory():
    database_url = (pytest.importorskip("os").getenv("DATABASE_URL") or "").strip()
    if not database_url.startswith("postgresql"):
        pytest.skip("DATABASE_URL must point to a PostgreSQL database")

    schema_name = f"test_multitenant_{uuid.uuid4().hex[:8]}"
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


def test_create_tenant_and_job_under_tenant(pg_session_factory):
    with pg_session_factory() as session:
        tenant = Tenant(name="Acme", slug="acme", plan="pro", is_active=True)
        session.add(tenant)
        session.flush()

        job = Job(
            tenant_id=tenant.id,
            platform="youtube",
            account_id="acc-1",
            status=JobStatus.pending,
            payload={"topic": "test"},
        )
        session.add(job)
        session.commit()

        row = session.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert row.tenant_id == tenant.id


def test_tenant_id_required_for_job_when_no_default(pg_session_factory):
    with pg_session_factory() as session:
        tenant = Tenant(name="OnlyTenant", slug="only-tenant", plan="free", is_active=True)
        session.add(tenant)
        session.flush()

        session.execute(text("ALTER TABLE jobs ALTER COLUMN tenant_id DROP DEFAULT"))

        bad_job = Job(
            platform="tiktok",
            account_id="acc-2",
            status=JobStatus.pending,
            payload={"topic": "x"},
        )
        session.add(bad_job)

        with pytest.raises(IntegrityError):
            session.commit()
