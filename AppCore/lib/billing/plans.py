from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlanSpec:
    id: str
    display_name: str
    display_price: str
    max_jobs_per_day: int
    max_jobs_per_month: int
    max_api_keys: int
    max_users: int
    features: tuple[str, ...]


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(parsed, 0)


PLAN_ORDER: tuple[str, ...] = ("free", "pro", "business")

PLAN_CATALOG: dict[str, PlanSpec] = {
    "free": PlanSpec(
        id="free",
        display_name="Free",
        display_price="$0",
        max_jobs_per_day=_env_int("PLAN_FREE_MAX_JOBS_PER_DAY", 10),
        max_jobs_per_month=_env_int("PLAN_FREE_MAX_JOBS_PER_MONTH", 100),
        max_api_keys=_env_int("PLAN_FREE_MAX_API_KEYS", 1),
        max_users=_env_int("PLAN_FREE_MAX_USERS", 1),
        features=(),
    ),
    "pro": PlanSpec(
        id="pro",
        display_name="Pro",
        display_price="$29",
        max_jobs_per_day=_env_int("PLAN_PRO_MAX_JOBS_PER_DAY", 200),
        max_jobs_per_month=_env_int("PLAN_PRO_MAX_JOBS_PER_MONTH", 3000),
        max_api_keys=_env_int("PLAN_PRO_MAX_API_KEYS", 10),
        max_users=_env_int("PLAN_PRO_MAX_USERS", 5),
        features=("automation", "team_members"),
    ),
    "business": PlanSpec(
        id="business",
        display_name="Business",
        display_price="$99",
        max_jobs_per_day=_env_int("PLAN_BUSINESS_MAX_JOBS_PER_DAY", 2000),
        max_jobs_per_month=_env_int("PLAN_BUSINESS_MAX_JOBS_PER_MONTH", 50000),
        max_api_keys=_env_int("PLAN_BUSINESS_MAX_API_KEYS", 100),
        max_users=_env_int("PLAN_BUSINESS_MAX_USERS", 50),
        features=("automation", "team_members", "priority_queue"),
    ),
}


def get_plan_spec(plan_id: str | None) -> PlanSpec:
    normalized = (plan_id or "").strip().lower() or "free"
    return PLAN_CATALOG.get(normalized, PLAN_CATALOG["free"])


def list_public_plans() -> list[dict[str, object]]:
    plans: list[dict[str, object]] = []
    for key in PLAN_ORDER:
        plan = PLAN_CATALOG[key]
        plans.append(
            {
                "id": plan.id,
                "display_name": plan.display_name,
                "display_price": plan.display_price,
                "limits": {
                    "max_jobs_per_day": plan.max_jobs_per_day,
                    "max_jobs_per_month": plan.max_jobs_per_month,
                    "max_api_keys": plan.max_api_keys,
                    "max_users": plan.max_users,
                },
                "features": list(plan.features),
            }
        )
    return plans
