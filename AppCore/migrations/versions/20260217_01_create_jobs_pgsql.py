"""create jobs and related tables with uuid/jsonb indexes

Revision ID: 20260217_01_create_jobs_pgsql
Revises:
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260217_01_create_jobs_pgsql"
down_revision = None
branch_labels = None
depends_on = None


def _create_update_trigger() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_jobs_updated_at()
        RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs;
        CREATE TRIGGER trg_jobs_updated_at
        BEFORE UPDATE ON jobs
        FOR EACH ROW
        EXECUTE FUNCTION set_jobs_updated_at();
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # UUID generator support (pgcrypto/gen_random_uuid)
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Define and create enum consistently
    job_status = postgresql.ENUM(
        "pending",
        "generating",
        "ready",
        "uploading",
        "uploaded",
        "failed",
        "retrying",
        name="job_status",
        create_type=True,
    )
    job_status.create(bind, checkfirst=True)

    if not inspector.has_table("jobs"):
        op.create_table(
            "jobs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("platform", sa.String(length=16), nullable=False),
            sa.Column("account_id", sa.String(length=128), nullable=False),
            sa.Column("channel_id", sa.String(length=128), nullable=True),
            sa.Column("status", job_status, nullable=False, server_default=sa.text("'pending'::job_status")),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("video_path", sa.Text(), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("job_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    else:
        cols = {c["name"] for c in inspector.get_columns("jobs")}

        if "metadata" in cols and "job_metadata" not in cols:
            op.alter_column("jobs", "metadata", new_column_name="job_metadata")
        elif "job_metadata" not in cols:
            op.add_column("jobs", sa.Column("job_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

        op.execute("ALTER TABLE jobs ALTER COLUMN status SET DEFAULT 'pending'::job_status")
        op.execute("ALTER TABLE jobs ALTER COLUMN retry_count SET DEFAULT 0")
        op.execute("ALTER TABLE jobs ALTER COLUMN created_at SET DEFAULT now()")
        op.execute("ALTER TABLE jobs ALTER COLUMN updated_at SET DEFAULT now()")

    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_status_scheduled_time ON jobs (status, scheduled_time)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_platform_account_id ON jobs (platform, account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_status_created_at ON jobs (status, created_at)")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_idempotency_key_not_null
        ON jobs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )

    if not inspector.has_table("job_events"):
        op.create_table(
            "job_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("event_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_job_events_job_id_created_at ON job_events (job_id, created_at)")

    if not inspector.has_table("upload_attempts"):
        op.create_table(
            "upload_attempts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("platform", sa.String(length=16), nullable=False),
            sa.Column("account_id", sa.String(length=128), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False),
            sa.Column("proxy_ip", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error_code", sa.String(length=64), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_upload_attempts_job_id_attempt_no ON upload_attempts (job_id, attempt_no)")

    if not inspector.has_table("worker_heartbeats"):
        op.create_table(
            "worker_heartbeats",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("worker_type", sa.String(length=32), nullable=False),
            sa.Column("hostname", sa.String(length=128), nullable=False),
            sa.Column("worker_name", sa.String(length=128), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.UniqueConstraint("worker_name", name="uq_worker_heartbeats_worker_name"),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_worker_heartbeats_last_seen_at ON worker_heartbeats (last_seen_at)")

    _create_update_trigger()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs")
    op.execute("DROP FUNCTION IF EXISTS set_jobs_updated_at()")

    op.execute("DROP INDEX IF EXISTS ix_worker_heartbeats_last_seen_at")
    op.drop_table("worker_heartbeats")

    op.execute("DROP INDEX IF EXISTS ix_upload_attempts_job_id_attempt_no")
    op.drop_table("upload_attempts")

    op.execute("DROP INDEX IF EXISTS ix_job_events_job_id_created_at")
    op.drop_table("job_events")

    op.execute("DROP INDEX IF EXISTS uq_jobs_idempotency_key_not_null")
    op.execute("DROP INDEX IF EXISTS ix_jobs_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_jobs_platform_account_id")
    op.execute("DROP INDEX IF EXISTS ix_jobs_status_scheduled_time")
    op.drop_table("jobs")

    job_status = postgresql.ENUM(
        "pending",
        "generating",
        "ready",
        "uploading",
        "uploaded",
        "failed",
        "retrying",
        name="job_status",
    )
    job_status.drop(op.get_bind(), checkfirst=True)
