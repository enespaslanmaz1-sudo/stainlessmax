"""add tenant subscriptions table and backfill free subscriptions

Revision ID: 20260218_04_tenant_subscriptions
Revises: 20260218_03_tenant_usage_quotas
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260218_04_tenant_subscriptions"
down_revision = "20260218_03_tenant_usage_quotas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("tenant_subscriptions"):
        op.create_table(
            "tenant_subscriptions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("plan", sa.Text(), nullable=False, server_default=sa.text("'free'")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
            sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_subscriptions_tenant_id ON tenant_subscriptions (tenant_id)"
    )

    op.execute(
        """
        INSERT INTO tenant_subscriptions (
            tenant_id,
            plan,
            status,
            current_period_start,
            current_period_end,
            cancel_at_period_end
        )
        SELECT
            t.id,
            LOWER(COALESCE(NULLIF(t.plan, ''), 'free')),
            'active',
            now(),
            NULL,
            false
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1
            FROM tenant_subscriptions ts
            WHERE ts.tenant_id = t.id
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenant_subscriptions_tenant_id")
    op.drop_table("tenant_subscriptions")
