"""add tenant usage quota table for plan limits

Revision ID: 20260218_03_tenant_usage_quotas
Revises: 20260217_02_multitenant_foundation
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260218_03_tenant_usage_quotas"
down_revision = "20260217_02_multitenant_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("tenant_usage_quotas"):
        op.create_table(
            "tenant_usage_quotas",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("usage_day", sa.Date(), nullable=False),
            sa.Column("usage_month", sa.Date(), nullable=False),
            sa.Column("jobs_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("uploads_started", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_usage_quotas_tenant_day ON tenant_usage_quotas (tenant_id, usage_day)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenant_usage_quotas_tenant_month ON tenant_usage_quotas (tenant_id, usage_month)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tenant_usage_quotas_tenant_month")
    op.execute("DROP INDEX IF EXISTS uq_tenant_usage_quotas_tenant_day")
    op.drop_table("tenant_usage_quotas")
