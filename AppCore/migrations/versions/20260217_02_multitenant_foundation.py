"""add multi-tenant foundation and tenant isolation columns

Revision ID: 20260217_02_multitenant_foundation
Revises: 20260217_01_create_jobs_pgsql
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260217_02_multitenant_foundation"
down_revision = "20260217_01_create_jobs_pgsql"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TENANT_ID_SQL = f"'{DEFAULT_TENANT_ID}'::uuid"


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def _fk_exists(inspector: sa.Inspector, table_name: str, fk_name: str) -> bool:
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, idx_name: str) -> bool:
    return any(idx.get("name") == idx_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    if not inspector.has_table("tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("plan", sa.Text(), nullable=False, server_default=sa.text("'free'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        )

    op.execute(
        f"""
        INSERT INTO tenants (id, name, slug, plan, is_active)
        VALUES ({DEFAULT_TENANT_ID_SQL}, 'Default Tenant', 'default', 'free', true)
        ON CONFLICT (slug) DO NOTHING
        """
    )

    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False, server_default=sa.text("'member'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )

    if not inspector.has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("key_hash", sa.String(length=255), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
        )

    if not inspector.has_table("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("action", sa.String(length=128), nullable=False),
            sa.Column("resource_type", sa.String(length=64), nullable=False),
            sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    tenantized_tables = [
        ("jobs", "fk_jobs_tenant_id_tenants", True),
        ("job_events", "fk_job_events_tenant_id_tenants", True),
        ("upload_attempts", "fk_upload_attempts_tenant_id_tenants", True),
        # worker_heartbeats is tenant-scoped for SaaS worker observability and isolation.
        ("worker_heartbeats", "fk_worker_heartbeats_tenant_id_tenants", True),
    ]

    inspector = sa.inspect(bind)
    for table_name, fk_name, required in tenantized_tables:
        if not inspector.has_table(table_name):
            continue

        if not _has_column(inspector, table_name, "tenant_id"):
            op.add_column(
                table_name,
                sa.Column(
                    "tenant_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                    server_default=sa.text(DEFAULT_TENANT_ID_SQL),
                ),
            )

        op.execute(f"UPDATE {table_name} SET tenant_id = {DEFAULT_TENANT_ID_SQL} WHERE tenant_id IS NULL")

        inspector = sa.inspect(bind)
        if not _fk_exists(inspector, table_name, fk_name):
            op.create_foreign_key(
                fk_name,
                source_table=table_name,
                referent_table="tenants",
                local_cols=["tenant_id"],
                remote_cols=["id"],
                ondelete="CASCADE",
            )

        if required:
            op.alter_column(table_name, "tenant_id", nullable=False)

    op.execute("CREATE INDEX IF NOT EXISTS ix_tenants_slug ON tenants (slug)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_tenant_id_email ON users (tenant_id, email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_tenant_id_created_at ON api_keys (tenant_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id_created_at ON audit_logs (tenant_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id_resource ON audit_logs (tenant_id, resource_type, resource_id)")

    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_tenant_status_scheduled_time ON jobs (tenant_id, status, scheduled_time)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_tenant_created_at ON jobs (tenant_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_job_events_tenant_job_created_at ON job_events (tenant_id, job_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_upload_attempts_tenant_job_attempt ON upload_attempts (tenant_id, job_id, attempt_no)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_worker_heartbeats_tenant_last_seen_at ON worker_heartbeats (tenant_id, last_seen_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_worker_heartbeats_tenant_last_seen_at")
    op.execute("DROP INDEX IF EXISTS ix_upload_attempts_tenant_job_attempt")
    op.execute("DROP INDEX IF EXISTS ix_job_events_tenant_job_created_at")
    op.execute("DROP INDEX IF EXISTS ix_jobs_tenant_created_at")
    op.execute("DROP INDEX IF EXISTS ix_jobs_tenant_status_scheduled_time")

    op.execute("DROP INDEX IF EXISTS ix_audit_logs_tenant_id_resource")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_tenant_id_created_at")
    op.execute("DROP INDEX IF EXISTS ix_api_keys_tenant_id_created_at")
    op.execute("DROP INDEX IF EXISTS ix_users_tenant_id_email")
    op.execute("DROP INDEX IF EXISTS ix_tenants_slug")

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("worker_heartbeats") and _has_column(inspector, "worker_heartbeats", "tenant_id"):
        if _fk_exists(inspector, "worker_heartbeats", "fk_worker_heartbeats_tenant_id_tenants"):
            op.drop_constraint("fk_worker_heartbeats_tenant_id_tenants", "worker_heartbeats", type_="foreignkey")
        op.drop_column("worker_heartbeats", "tenant_id")

    inspector = sa.inspect(bind)
    if inspector.has_table("upload_attempts") and _has_column(inspector, "upload_attempts", "tenant_id"):
        if _fk_exists(inspector, "upload_attempts", "fk_upload_attempts_tenant_id_tenants"):
            op.drop_constraint("fk_upload_attempts_tenant_id_tenants", "upload_attempts", type_="foreignkey")
        op.drop_column("upload_attempts", "tenant_id")

    inspector = sa.inspect(bind)
    if inspector.has_table("job_events") and _has_column(inspector, "job_events", "tenant_id"):
        if _fk_exists(inspector, "job_events", "fk_job_events_tenant_id_tenants"):
            op.drop_constraint("fk_job_events_tenant_id_tenants", "job_events", type_="foreignkey")
        op.drop_column("job_events", "tenant_id")

    inspector = sa.inspect(bind)
    if inspector.has_table("jobs") and _has_column(inspector, "jobs", "tenant_id"):
        if _fk_exists(inspector, "jobs", "fk_jobs_tenant_id_tenants"):
            op.drop_constraint("fk_jobs_tenant_id_tenants", "jobs", type_="foreignkey")
        op.drop_column("jobs", "tenant_id")

    op.drop_table("audit_logs")
    op.drop_table("api_keys")
    op.drop_table("users")

    # Keep tenants table only if no dependent tenantized data remains.
    op.drop_table("tenants")
