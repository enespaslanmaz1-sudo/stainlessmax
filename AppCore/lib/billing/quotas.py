from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from lib.billing.plans import get_plan_spec
from lib.db.models import Tenant, TenantUsageQuota
from lib.db.session import session_scope


class PlanLimitReachedError(Exception):
    pass


def _utc_today_and_month_start(now: datetime | None = None) -> tuple[date, date]:
    current = now or datetime.now(UTC)
    current_utc = current.astimezone(UTC)
    day = current_utc.date()
    month_start = day.replace(day=1)
    return day, month_start


def _ensure_row(session: Session, *, tenant_id: uuid.UUID, usage_day: date, usage_month: date) -> None:
    stmt = insert(TenantUsageQuota).values(
        tenant_id=tenant_id,
        usage_day=usage_day,
        usage_month=usage_month,
        jobs_created=0,
        uploads_started=0,
    )
    session.execute(stmt.on_conflict_do_nothing(index_elements=["tenant_id", "usage_day"]))


def _current_month_total(session: Session, *, tenant_id: uuid.UUID, usage_month: date) -> int:
    total = session.execute(
        sa.select(sa.func.coalesce(sa.func.sum(TenantUsageQuota.jobs_created), 0)).where(
            TenantUsageQuota.tenant_id == tenant_id,
            TenantUsageQuota.usage_month == usage_month,
        )
    ).scalar_one()
    return int(total or 0)


def _consume_one(session: Session, *, tenant_id: uuid.UUID, now: datetime | None = None) -> bool:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None or not bool(tenant.is_active):
        return False

    plan = get_plan_spec(tenant.plan)
    day, month_start = _utc_today_and_month_start(now)
    _ensure_row(session, tenant_id=tenant_id, usage_day=day, usage_month=month_start)

    month_total = _current_month_total(session, tenant_id=tenant_id, usage_month=month_start)
    if month_total >= plan.max_jobs_per_month:
        return False

    day_updated = session.execute(
        sa.update(TenantUsageQuota)
        .where(
            TenantUsageQuota.tenant_id == tenant_id,
            TenantUsageQuota.usage_day == day,
            TenantUsageQuota.jobs_created < plan.max_jobs_per_day,
        )
        .values(jobs_created=TenantUsageQuota.jobs_created + 1)
        .returning(TenantUsageQuota.jobs_created)
    ).first()
    if not day_updated:
        return False

    month_after = _current_month_total(session, tenant_id=tenant_id, usage_month=month_start)
    if month_after > plan.max_jobs_per_month:
        session.execute(
            sa.update(TenantUsageQuota)
            .where(
                TenantUsageQuota.tenant_id == tenant_id,
                TenantUsageQuota.usage_day == day,
                TenantUsageQuota.jobs_created > 0,
            )
            .values(jobs_created=TenantUsageQuota.jobs_created - 1)
        )
        return False

    return True


def consume_job_quota_or_raise(
    session_factory: sessionmaker[Session] | None,
    *,
    tenant_id: uuid.UUID,
    now: datetime | None = None,
) -> None:
    if session_factory is None:
        return

    with session_scope(session_factory) as session:
        allowed = _consume_one(session, tenant_id=tenant_id, now=now)
        if not allowed:
            raise PlanLimitReachedError("plan_limit_reached")
