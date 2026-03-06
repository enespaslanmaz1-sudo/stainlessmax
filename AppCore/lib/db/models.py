import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_TENANT_ID_SQL = "'00000000-0000-0000-0000-000000000001'::uuid"


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    ready = "ready"
    uploading = "uploading"
    uploaded = "uploaded"
    failed = "failed"
    retrying = "retrying"


job_status_enum = Enum(
    JobStatus,
    name="job_status",
    values_callable=lambda x: [e.value for e in x],
)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'free'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="tenant")
    subscription: Mapped["TenantSubscription | None"] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        uselist=False,
    )
    plan_requests: Mapped[list["TenantPlanRequest"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'member'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="users")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="api_keys")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="audit_logs")
    user: Mapped[User | None] = relationship(back_populates="audit_logs")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        server_default=text(DEFAULT_TENANT_ID_SQL),
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        job_status_enum,
        nullable=False,
        default=JobStatus.pending,
        server_default=text("'pending'::job_status"),
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    job_metadata: Mapped[dict | None] = mapped_column("job_metadata", JSONB, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="jobs")
    events: Mapped[list["JobEvent"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    upload_attempts: Mapped[list["UploadAttempt"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    @classmethod
    def due_filter(cls):
        return (cls.scheduled_time.is_(None)) | (cls.scheduled_time <= func.now())


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        server_default=text(DEFAULT_TENANT_ID_SQL),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="events")


class UploadAttempt(Base):
    __tablename__ = "upload_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        server_default=text(DEFAULT_TENANT_ID_SQL),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    proxy_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship(back_populates="upload_attempts")


class TenantUsageQuota(Base):
    __tablename__ = "tenant_usage_quotas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    usage_day: Mapped[date] = mapped_column(Date, nullable=False)
    usage_month: Mapped[date] = mapped_column(Date, nullable=False)
    jobs_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    uploads_started: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TenantSubscription(Base):
    __tablename__ = "tenant_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'free'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'active'"))
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="subscription")


class TenantPlanRequest(Base):
    __tablename__ = "tenant_plan_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_plan: Mapped[str] = mapped_column(String(16), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'new'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="plan_requests")


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Tenant-scoped by design: isolation for worker fleets and observability in SaaS mode.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        server_default=text(DEFAULT_TENANT_ID_SQL),
    )
    worker_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hostname: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


Index("ix_tenants_slug", Tenant.slug, unique=True)
Index("ix_users_tenant_id_email", User.tenant_id, User.email)
Index("ix_api_keys_tenant_id_created_at", ApiKey.tenant_id, ApiKey.created_at)
Index("ix_audit_logs_tenant_id_created_at", AuditLog.tenant_id, AuditLog.created_at)
Index("ix_audit_logs_tenant_id_resource", AuditLog.tenant_id, AuditLog.resource_type, AuditLog.resource_id)

Index("ix_jobs_tenant_status_scheduled_time", Job.tenant_id, Job.status, Job.scheduled_time)
Index("ix_jobs_tenant_created_at", Job.tenant_id, Job.created_at)
Index("ix_jobs_platform_account_id", Job.platform, Job.account_id)
Index("ix_jobs_status_created_at", Job.status, Job.created_at)
Index(
    "uq_jobs_idempotency_key_not_null",
    Job.idempotency_key,
    unique=True,
    postgresql_where=Job.idempotency_key.isnot(None),
)

Index("ix_job_events_tenant_job_created_at", JobEvent.tenant_id, JobEvent.job_id, JobEvent.created_at)
Index("ix_upload_attempts_tenant_job_attempt", UploadAttempt.tenant_id, UploadAttempt.job_id, UploadAttempt.attempt_no)
Index("ix_worker_heartbeats_tenant_last_seen_at", WorkerHeartbeat.tenant_id, WorkerHeartbeat.last_seen_at)
Index("ix_tenant_usage_quotas_tenant_month", TenantUsageQuota.tenant_id, TenantUsageQuota.usage_month)
Index("uq_tenant_usage_quotas_tenant_day", TenantUsageQuota.tenant_id, TenantUsageQuota.usage_day, unique=True)
Index("uq_tenant_subscriptions_tenant_id", TenantSubscription.tenant_id, unique=True)
Index("ix_tenant_plan_requests_tenant_created_at", TenantPlanRequest.tenant_id, TenantPlanRequest.created_at)
Index("ix_tenant_plan_requests_tenant_status", TenantPlanRequest.tenant_id, TenantPlanRequest.status)
