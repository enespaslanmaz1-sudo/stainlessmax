from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from flask import Flask, g, jsonify, request
from sqlalchemy.orm import Session, sessionmaker

from lib.billing.plans import PLAN_CATALOG, get_plan_spec, list_public_plans
from lib.db.auth import require_authenticated
from lib.db.models import Tenant, TenantPlanRequest, TenantSubscription, User
from lib.db.session import session_scope


ALLOWED_REQUESTED_PLANS = {"PRO", "BUSINESS"}
ALLOWED_PLAN_REQUEST_STATUSES = {"new", "contacted", "closed"}


def _period_end_from_now(now: datetime) -> datetime:
    return now + timedelta(days=30)


def _is_authenticated_request() -> bool:
    return getattr(g, "auth_source", "default") in {"jwt", "token", "api_key"}


def _get_or_create_subscription(session: Session, *, tenant: Tenant) -> TenantSubscription:
    subscription = session.execute(
        sa.select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if subscription is not None:
        return subscription

    now = datetime.now(UTC)
    plan = get_plan_spec(tenant.plan).id
    subscription = TenantSubscription(
        tenant_id=tenant.id,
        plan=plan,
        status="active",
        current_period_start=now,
        current_period_end=_period_end_from_now(now),
        cancel_at_period_end=False,
    )
    session.add(subscription)
    session.flush()
    return subscription


def install_billing_routes(app: Flask, session_factory: sessionmaker[Session] | None) -> None:
    @app.route("/api/billing/plans", methods=["GET"])
    def billing_plans():
        return jsonify(list_public_plans())

    @app.route("/api/billing/plan-request", methods=["POST"])
    def billing_plan_request():
        if session_factory is None:
            return jsonify({"error": "database_not_configured"}), 503

        data: dict[str, Any] = request.get_json(silent=True) or {}
        requested_plan = str(data.get("requested_plan", "")).strip().upper()
        tenant_slug = str(data.get("tenant_slug", "")).strip().lower()
        contact_email = str(data.get("contact_email", "")).strip() or None
        contact_phone = str(data.get("contact_phone", "")).strip() or None
        note = str(data.get("note", "")).strip() or None

        if requested_plan not in ALLOWED_REQUESTED_PLANS:
            return jsonify({"error": "invalid_requested_plan"}), 400

        with session_scope(session_factory) as session:
            tenant: Tenant | None
            user: User | None = None

            if _is_authenticated_request():
                tenant = session.get(Tenant, g.tenant_id)
                if tenant is None:
                    return jsonify({"error": "tenant_not_found"}), 404

                if g.user_id is not None:
                    user = session.get(User, g.user_id)
                    if user is None or not bool(user.is_active):
                        return jsonify({"error": "inactive_user"}), 403
                    if not contact_email:
                        contact_email = user.email
            else:
                if not tenant_slug:
                    return jsonify({"error": "tenant_slug_required"}), 400
                tenant = session.execute(sa.select(Tenant).where(Tenant.slug == tenant_slug)).scalar_one_or_none()
                if tenant is None:
                    return jsonify({"error": "tenant_not_found"}), 404

            if not bool(tenant.is_active):
                return jsonify({"error": "inactive_tenant"}), 403

            plan_request = TenantPlanRequest(
                tenant_id=tenant.id,
                requested_plan=requested_plan,
                contact_email=contact_email,
                contact_phone=contact_phone,
                note=note,
                status="new",
            )
            session.add(plan_request)
            session.flush()

            return jsonify({"ok": True, "request_id": str(plan_request.id)})

    @app.route("/api/billing/subscription", methods=["GET"])
    @require_authenticated(allow_api_key=True)
    def billing_subscription():
        if session_factory is None:
            return jsonify({"error": "database_not_configured"}), 503

        with session_scope(session_factory) as session:
            tenant = session.get(Tenant, g.tenant_id)
            if tenant is None or not bool(tenant.is_active):
                return jsonify({"error": "inactive_tenant"}), 403

            subscription = _get_or_create_subscription(session, tenant=tenant)
            plan_spec = get_plan_spec(subscription.plan)

            return jsonify(
                {
                    "tenant_id": str(tenant.id),
                    "subscription": {
                        "plan": plan_spec.id,
                        "status": subscription.status,
                        "current_period_start": subscription.current_period_start.isoformat(),
                        "current_period_end": subscription.current_period_end.isoformat()
                        if subscription.current_period_end
                        else None,
                        "cancel_at_period_end": bool(subscription.cancel_at_period_end),
                    },
                }
            )

    @app.route("/api/admin/plan-requests", methods=["GET"])
    @require_authenticated(allow_api_key=False)
    def admin_list_plan_requests():
        if session_factory is None:
            return jsonify({"error": "database_not_configured"}), 503

        if g.user_id is None:
            return jsonify({"error": "authentication_required"}), 401

        with session_scope(session_factory) as session:
            user = session.get(User, g.user_id)
            if user is None or not bool(user.is_active):
                return jsonify({"error": "inactive_user"}), 403
            if user.role != "admin":
                return jsonify({"error": "forbidden"}), 403

            items = session.execute(
                sa.select(TenantPlanRequest)
                .where(TenantPlanRequest.tenant_id == g.tenant_id)
                .order_by(TenantPlanRequest.created_at.desc())
            ).scalars().all()

            return jsonify(
                [
                    {
                        "id": str(item.id),
                        "tenant_id": str(item.tenant_id),
                        "requested_plan": item.requested_plan,
                        "contact_email": item.contact_email,
                        "contact_phone": item.contact_phone,
                        "note": item.note,
                        "status": item.status,
                        "created_at": item.created_at.isoformat(),
                        "updated_at": item.updated_at.isoformat(),
                    }
                    for item in items
                ]
            )

    @app.route("/api/admin/plan-requests/<request_id>", methods=["PATCH"])
    @require_authenticated(allow_api_key=False)
    def admin_update_plan_request(request_id: str):
        if session_factory is None:
            return jsonify({"error": "database_not_configured"}), 503

        if g.user_id is None:
            return jsonify({"error": "authentication_required"}), 401

        data: dict[str, Any] = request.get_json(silent=True) or {}
        status = str(data.get("status", "")).strip().lower()
        if status not in ALLOWED_PLAN_REQUEST_STATUSES:
            return jsonify({"error": "invalid_status"}), 400

        with session_scope(session_factory) as session:
            user = session.get(User, g.user_id)
            if user is None or not bool(user.is_active):
                return jsonify({"error": "inactive_user"}), 403
            if user.role != "admin":
                return jsonify({"error": "forbidden"}), 403

            try:
                request_uuid = uuid.UUID(request_id)
            except ValueError:
                return jsonify({"error": "invalid_request_id"}), 400

            item = session.execute(
                sa.select(TenantPlanRequest).where(
                    TenantPlanRequest.id == request_uuid,
                    TenantPlanRequest.tenant_id == g.tenant_id,
                )
            ).scalar_one_or_none()
            if item is None:
                return jsonify({"error": "plan_request_not_found"}), 404

            item.status = status
            session.flush()

            return jsonify({"ok": True, "request_id": str(item.id), "status": item.status})

    @app.route("/api/admin/tenant/plan", methods=["POST"])
    @require_authenticated(allow_api_key=False)
    def admin_update_tenant_plan():
        if session_factory is None:
            return jsonify({"error": "database_not_configured"}), 503

        data: dict[str, Any] = request.get_json(silent=True) or {}
        plan = str(data.get("plan", "")).strip().lower()
        if not plan:
            return jsonify({"error": "plan_required"}), 400
        if plan not in PLAN_CATALOG:
            return jsonify({"error": "invalid_plan"}), 400

        if g.user_id is None:
            return jsonify({"error": "authentication_required"}), 401

        with session_scope(session_factory) as session:
            user = session.get(User, g.user_id)
            if user is None or not bool(user.is_active):
                return jsonify({"error": "inactive_user"}), 403
            if user.role != "admin":
                return jsonify({"error": "forbidden"}), 403

            tenant = session.get(Tenant, g.tenant_id)
            if tenant is None or not bool(tenant.is_active):
                return jsonify({"error": "inactive_tenant"}), 403

            subscription = _get_or_create_subscription(session, tenant=tenant)
            now = datetime.now(UTC)

            tenant.plan = plan
            subscription.plan = plan
            subscription.status = "active"
            subscription.current_period_start = now
            subscription.current_period_end = _period_end_from_now(now)
            subscription.cancel_at_period_end = False
            session.flush()

            return jsonify(
                {
                    "ok": True,
                    "tenant_id": str(tenant.id),
                    "plan": plan,
                    "subscription": {
                        "plan": subscription.plan,
                        "status": subscription.status,
                        "current_period_start": subscription.current_period_start.isoformat(),
                        "current_period_end": subscription.current_period_end.isoformat()
                        if subscription.current_period_end
                        else None,
                        "cancel_at_period_end": bool(subscription.cancel_at_period_end),
                    },
                }
            )
