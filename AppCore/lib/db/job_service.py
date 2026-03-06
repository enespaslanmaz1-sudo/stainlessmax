import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

import sqlalchemy as sa
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from lib.db.models import Job, JobEvent, JobStatus, UploadAttempt
from lib.db.session import session_scope


class JobServiceError(Exception):
    pass


class InvalidTransitionError(JobServiceError):
    pass


class IdempotencyKeyMismatchError(JobServiceError):
    pass


class JobRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        max_retries: int = 3,
        retry_cooldown_seconds: int = 300,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.session_factory = session_factory
        self.max_retries = max_retries
        self.retry_cooldown_seconds = retry_cooldown_seconds
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        now = self.now_provider()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    def claim_for_generation(self, worker_name: str, *, tenant_id: uuid.UUID, limit: int = 1) -> list[Job]:
        return self._claim_jobs(
            from_status=JobStatus.pending,
            retry_target="generation",
            to_status=JobStatus.generating,
            event_type="claimed_generation",
            event_payload={"worker": worker_name},
            limit=limit,
            tenant_id=tenant_id,
        )

    def claim_for_upload(self, worker_name: str, *, tenant_id: uuid.UUID, limit: int = 1) -> list[Job]:
        return self._claim_jobs(
            from_status=JobStatus.ready,
            retry_target="upload",
            to_status=JobStatus.uploading,
            event_type="claimed_upload",
            event_payload={"worker": worker_name},
            limit=limit,
            tenant_id=tenant_id,
        )

    def _claim_jobs(
        self,
        *,
        from_status: JobStatus,
        retry_target: str,
        to_status: JobStatus,
        event_type: str,
        event_payload: dict[str, Any] | None,
        limit: int,
        tenant_id: uuid.UUID,
    ) -> list[Job]:
        if limit <= 0:
            return []

        now_ts = self._now()
        tenant_scope = tenant_id

        with session_scope(self.session_factory) as session:
            self._fail_orphan_retrying_jobs(session=session, now_ts=now_ts, tenant_id=tenant_scope)

            claim_sql = text(
                """
                WITH picked AS (
                    SELECT id, status AS previous_status
                    FROM jobs
                    WHERE tenant_id = :tenant_id
                      AND (
                            status = :from_status
                         OR (
                                status = :retrying_status
                            AND COALESCE(job_metadata->>'retry_target', '') = :retry_target
                         )
                      )
                      AND (scheduled_time IS NULL OR scheduled_time <= :now_ts)
                    ORDER BY scheduled_time NULLS FIRST, created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT :limit
                )
                UPDATE jobs j
                SET status = :to_status,
                    updated_at = :now_ts
                FROM picked
                WHERE j.id = picked.id
                RETURNING j.id, picked.previous_status
                """
            )

            rows = session.execute(
                claim_sql,
                {
                    "tenant_id": tenant_scope,
                    "from_status": from_status.value,
                    "retrying_status": JobStatus.retrying.value,
                    "retry_target": retry_target,
                    "to_status": to_status.value,
                    "limit": limit,
                    "now_ts": now_ts,
                },
            ).all()

            if not rows:
                return []

            claimed_ids = [row[0] for row in rows]
            previous_status_by_id = {row[0]: row[1] for row in rows}

            for job_id in claimed_ids:
                previous_status = previous_status_by_id[job_id]
                self._insert_events(
                    session,
                    [job_id],
                    tenant_id=tenant_scope,
                    event_type=event_type,
                    event_payload={
                        "from": previous_status,
                        "to": to_status.value,
                        **(event_payload or {}),
                    },
                )

            return (
                session.execute(
                    select(Job)
                    .where(Job.tenant_id == tenant_scope, Job.id.in_(claimed_ids))
                    .order_by(Job.created_at.asc())
                )
                .scalars()
                .all()
            )

    def _fail_orphan_retrying_jobs(self, *, session: Session, now_ts: datetime, tenant_id: uuid.UUID) -> None:
        enum_type = sa.Enum(JobStatus, name="job_status", values_callable=lambda x: [e.value for e in x])
        orphan_error = "retrying job missing retry_target metadata"

        stmt = (
            sa.update(Job)
            .where(
                Job.tenant_id == tenant_id,
                Job.status == JobStatus.retrying,
                sa.or_(
                    Job.job_metadata.is_(None),
                    func.coalesce(Job.job_metadata["retry_target"].astext, "") == "",
                ),
                sa.or_(Job.scheduled_time.is_(None), Job.scheduled_time <= now_ts),
            )
            .values(
                status=sa.cast(JobStatus.failed.value, enum_type),
                error_message=orphan_error,
                updated_at=now_ts,
            )
            .returning(Job.id)
        )

        rows = session.execute(stmt).all()
        if not rows:
            return

        for (job_id,) in rows:
            self._insert_events(
                session,
                [job_id],
                tenant_id=tenant_id,
                event_type="retry_orphan_failed",
                event_payload={
                    "from": JobStatus.retrying.value,
                    "to": JobStatus.failed.value,
                    "reason": "missing_retry_target",
                },
            )

    def transition_status(
        self,
        *,
        job_id: uuid.UUID,
        expected_from: JobStatus,
        to_status: JobStatus,
        event_type: str,
        event_payload: dict[str, Any] | None = None,
        tenant_id: uuid.UUID,
    ) -> Job:
        now_ts = self._now()
        tenant_scope = tenant_id

        values: dict[str, Any] = {
            "status": to_status,
            "updated_at": now_ts,
        }

        if to_status in {JobStatus.ready, JobStatus.uploaded}:
            values["job_metadata"] = sa.case(
                (Job.job_metadata.is_(None), None),
                else_=Job.job_metadata - "retry_target",
            )

        update_stmt = (
            sa.update(Job)
            .where(Job.id == job_id, Job.tenant_id == tenant_scope, Job.status == expected_from)
            .values(**values)
            .returning(Job.id)
        )

        with session_scope(self.session_factory) as session:
            row = session.execute(update_stmt).first()
            if not row:
                raise InvalidTransitionError(
                    f"invalid transition for job={job_id}: expected {expected_from.value} -> {to_status.value}"
                )

            self._insert_events(
                session,
                [job_id],
                tenant_id=tenant_scope,
                event_type=event_type,
                event_payload={
                    "from": expected_from.value,
                    "to": to_status.value,
                    **(event_payload or {}),
                },
            )

            return session.execute(select(Job).where(Job.id == job_id, Job.tenant_id == tenant_scope)).scalar_one()

    def ensure_idempotency_key(self, *, job_id: uuid.UUID, idempotency_key: str, tenant_id: uuid.UUID) -> str:
        if not idempotency_key:
            raise ValueError("idempotency_key must not be empty")
        now_ts = self._now()
        tenant_scope = tenant_id

        with session_scope(self.session_factory) as session:
            stmt = (
                sa.update(Job)
                .where(Job.id == job_id, Job.tenant_id == tenant_scope)
                .where(sa.or_(Job.idempotency_key.is_(None), Job.idempotency_key == idempotency_key))
                .values(idempotency_key=func.coalesce(Job.idempotency_key, idempotency_key), updated_at=now_ts)
                .returning(Job.idempotency_key)
            )
            row = session.execute(stmt).first()
            if row:
                return row[0]

            existing = session.execute(select(Job.idempotency_key).where(Job.id == job_id, Job.tenant_id == tenant_scope)).first()
            if not existing:
                raise JobServiceError(f"job not found: {job_id}")
            raise IdempotencyKeyMismatchError(
                f"job={job_id} already has a different idempotency_key"
            )

    def mark_generation_failed(
        self,
        *,
        job_id: uuid.UUID,
        error_message: str,
        max_retries: int | None = None,
        tenant_id: uuid.UUID,
    ) -> Job:
        return self._mark_failed_with_retry(
            job_id=job_id,
            expected_from=JobStatus.generating,
            event_type="generation_failed",
            error_message=error_message,
            max_retries=max_retries,
            retry_target="generation",
            tenant_id=tenant_id,
        )

    def mark_upload_failed(
        self,
        *,
        job_id: uuid.UUID,
        platform: str,
        account_id: str,
        error_message: str,
        error_code: str | None = None,
        proxy_ip: str | None = None,
        max_retries: int | None = None,
        tenant_id: uuid.UUID,
    ) -> Job:
        final_max = max_retries or self.max_retries
        tenant_scope = tenant_id

        with session_scope(self.session_factory) as session:
            updated = self._transition_to_retry_or_failed(
                session=session,
                job_id=job_id,
                expected_from=JobStatus.uploading,
                error_message=error_message,
                max_retries=final_max,
                retry_target="upload",
                tenant_id=tenant_scope,
            )

            attempt_no = session.execute(
                select(func.coalesce(func.max(UploadAttempt.attempt_no), 0) + 1).where(
                    UploadAttempt.tenant_id == tenant_scope,
                    UploadAttempt.job_id == job_id,
                )
            ).scalar_one()

            session.add(
                UploadAttempt(
                    tenant_id=tenant_scope,
                    job_id=job_id,
                    platform=platform,
                    account_id=account_id,
                    attempt_no=int(attempt_no),
                    proxy_ip=proxy_ip,
                    status="failed",
                    error_code=error_code,
                    error_message=error_message,
                )
            )

            self._insert_events(
                session,
                [job_id],
                tenant_id=tenant_scope,
                event_type="upload_failed",
                event_payload={
                    "from": JobStatus.uploading.value,
                    "to": updated.status.value,
                    "retry_count": updated.retry_count,
                    "max_retries": final_max,
                    "error_code": error_code,
                    "error_message": error_message,
                    "cooldown_seconds": self.retry_cooldown_seconds,
                },
            )

            return updated

    def _mark_failed_with_retry(
        self,
        *,
        job_id: uuid.UUID,
        expected_from: JobStatus,
        event_type: str,
        error_message: str,
        max_retries: int | None,
        retry_target: str,
        tenant_id: uuid.UUID,
    ) -> Job:
        final_max = max_retries or self.max_retries
        tenant_scope = tenant_id

        with session_scope(self.session_factory) as session:
            updated = self._transition_to_retry_or_failed(
                session=session,
                job_id=job_id,
                expected_from=expected_from,
                error_message=error_message,
                max_retries=final_max,
                retry_target=retry_target,
                tenant_id=tenant_scope,
            )

            self._insert_events(
                session,
                [job_id],
                tenant_id=tenant_scope,
                event_type=event_type,
                event_payload={
                    "from": expected_from.value,
                    "to": updated.status.value,
                    "retry_count": updated.retry_count,
                    "max_retries": final_max,
                    "error_message": error_message,
                    "cooldown_seconds": self.retry_cooldown_seconds,
                },
            )

            return updated

    def _transition_to_retry_or_failed(
        self,
        *,
        session: Session,
        job_id: uuid.UUID,
        expected_from: JobStatus,
        error_message: str,
        max_retries: int,
        retry_target: str,
        tenant_id: uuid.UUID,
    ) -> Job:
        now_ts = self._now()
        retry_expr = Job.retry_count + 1
        retry_at = now_ts + timedelta(seconds=self.retry_cooldown_seconds)

        enum_type = sa.Enum(JobStatus, name="job_status", values_callable=lambda x: [e.value for e in x])
        next_status_expr = sa.case(
            (retry_expr >= max_retries, JobStatus.failed.value),
            else_=JobStatus.retrying.value,
        )

        retry_meta_expr = func.coalesce(Job.job_metadata, sa.cast(sa.literal("{}"), JSONB)).op("||")(
            func.jsonb_build_object("retry_target", retry_target)
        )

        stmt = (
            sa.update(Job)
            .where(Job.id == job_id, Job.tenant_id == tenant_id, Job.status == expected_from)
            .values(
                retry_count=retry_expr,
                status=sa.cast(next_status_expr, enum_type),
                scheduled_time=sa.case(
                    (retry_expr >= max_retries, Job.scheduled_time),
                    else_=sa.bindparam("retry_at"),
                ),
                job_metadata=sa.case(
                    (retry_expr >= max_retries, sa.case((Job.job_metadata.is_(None), None), else_=Job.job_metadata - "retry_target")),
                    else_=retry_meta_expr,
                ),
                error_message=error_message,
                updated_at=now_ts,
            )
            .returning(Job.id)
        )

        row = session.execute(stmt, {"retry_at": retry_at}).first()
        if not row:
            raise InvalidTransitionError(
                f"invalid retry transition for job={job_id}: expected {expected_from.value}"
            )

        return session.execute(select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)).scalar_one()

    @staticmethod
    def _insert_events(
        session: Session,
        job_ids: Iterable[uuid.UUID],
        *,
        tenant_id: uuid.UUID,
        event_type: str,
        event_payload: dict[str, Any] | None,
    ) -> None:
        for job_id in job_ids:
            session.add(
                JobEvent(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    event_type=event_type,
                    event_payload=event_payload,
                )
            )
