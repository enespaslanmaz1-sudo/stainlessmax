"""add tenant plan request leads table

Revision ID: 20260218_05_tenant_plan_requests
Revises: 20260218_04_tenant_subscriptions
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260218_05_tenant_plan_requests"
down_revision = "20260218_04_tenant_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("tenant_plan_requests"):
        op.create_table(
            "tenant_plan_requests",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("requested_plan", sa.String(length=16), nullable=False),
            sa.Column("contact_email", sa.String(length=320), nullable=True),
            sa.Column("contact_phone", sa.String(length=64), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'new'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenant_plan_requests_tenant_created_at ON tenant_plan_requests (tenant_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenant_plan_requests_tenant_status ON tenant_plan_requests (tenant_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tenant_plan_requests_tenant_status")
    op.execute("DROP INDEX IF EXISTS ix_tenant_plan_requests_tenant_created_at")
    op.drop_table("tenant_plan_requests")
