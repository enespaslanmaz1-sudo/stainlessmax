import uuid

import pytest
from flask import Flask, g, jsonify
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from lib.billing.http import install_billing_routes
from lib.billing.plans import PLAN_CATALOG, PlanSpec
from lib.billing.quotas import PlanLimitReachedError, consume_job_quota_or_raise
from lib.db.auth import hash_api_key, install_auth
from lib.db.models import ApiKey, Base, DEFAULT_TENANT_ID, Tenant, TenantPlanRequest, TenantSubscription


@pytest.fixture
def pg_session_factory(monkeypatch):
    database_url = (pytest.importorskip("os").getenv("DATABASE_URL") or "").strip()
    if not database_url.startswith("postgresql"):
        pytest.skip("DATABASE_URL must point to a PostgreSQL database")

    schema_name = f"test_auth_{uuid.uuid4().hex[:8]}"
    engine = create_engine(database_url, future=True)

    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection, _record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema_name}", public')

    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        conn.commit()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, autocommit=False, future=True)

    with session_factory() as session:
        session.add(
            Tenant(
                id=DEFAULT_TENANT_ID,
                name="Default Tenant",
                slug="default",
                plan="free",
                is_active=True,
            )
        )
        session.commit()

    try:
        yield session_factory
    finally:
        Base.metadata.drop_all(engine)
        with engine.connect() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            conn.commit()
        engine.dispose()


@pytest.fixture
def app_client(pg_session_factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    app = Flask(__name__)
    install_auth(app, pg_session_factory)
    install_billing_routes(app, pg_session_factory)

    @app.get("/api/protected/ping")
    def protected_ping():
        return jsonify({"ok": True, "tenant_id": str(g.tenant_id), "user_id": str(g.user_id) if g.user_id else None})

    @app.post("/api/protected/generate-lite")
    def protected_generate_lite():
        try:
            consume_job_quota_or_raise(pg_session_factory, tenant_id=g.tenant_id)
        except PlanLimitReachedError:
            return jsonify({"error": "plan_limit_reached"}), 429
        return jsonify({"status": "started"})

    return app.test_client(), pg_session_factory


def test_register_login_and_protected_me(app_client):
    client, _ = app_client

    register_res = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Acme",
            "tenant_slug": "acme",
            "email": "admin@acme.io",
            "password": "S3curePass!",
        },
    )
    assert register_res.status_code == 201

    login_res = client.post(
        "/api/auth/login",
        json={"email": "admin@acme.io", "password": "S3curePass!"},
    )
    assert login_res.status_code == 200
    token = login_res.get_json()["access_token"]

    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_json = me_res.get_json()
    assert me_json["auth_source"] == "jwt"
    assert me_json["user"]["email"] == "admin@acme.io"
    assert me_json["tenant"]["slug"] == "acme"


def test_api_key_access_path(app_client):
    client, session_factory = app_client

    register_res = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Beta",
            "tenant_slug": "beta",
            "email": "admin@beta.io",
            "password": "S3curePass!",
        },
    )
    assert register_res.status_code == 201
    tenant_id = uuid.UUID(register_res.get_json()["tenant"]["id"])

    raw_api_key = "sk_test_123"
    with session_factory() as session:
        session.add(
            ApiKey(
                tenant_id=tenant_id,
                name="server",
                key_hash=hash_api_key(raw_api_key),
            )
        )
        session.commit()

    me_res = client.get("/api/auth/me", headers={"X-API-Key": raw_api_key})
    assert me_res.status_code == 200
    me_json = me_res.get_json()
    assert me_json["auth_source"] == "api_key"
    assert me_json["user"] is None
    assert me_json["tenant"]["id"] == str(tenant_id)


def test_backward_compat_no_auth_uses_default_tenant(app_client):
    client, _ = app_client

    res = client.get("/api/protected/ping")
    assert res.status_code == 200
    data = res.get_json()
    assert data["tenant_id"] == str(DEFAULT_TENANT_ID)
    assert data["user_id"] is None


def test_tenant_context_is_reset_between_requests(app_client):
    client, _ = app_client

    register_res = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Gamma",
            "tenant_slug": "gamma",
            "email": "admin@gamma.io",
            "password": "S3curePass!",
        },
    )
    assert register_res.status_code == 201

    login_res = client.post(
        "/api/auth/login",
        json={"email": "admin@gamma.io", "password": "S3curePass!"},
    )
    assert login_res.status_code == 200
    login_json = login_res.get_json()
    token = login_json["access_token"]
    gamma_tenant_id = login_json["tenant"]["id"]

    first = client.get("/api/protected/ping", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 200
    first_json = first.get_json()
    assert first_json["tenant_id"] == gamma_tenant_id

    second = client.get("/api/protected/ping")
    assert second.status_code == 200
    second_json = second.get_json()
    assert second_json["tenant_id"] == str(DEFAULT_TENANT_ID)
    assert second_json["user_id"] is None


def test_free_plan_daily_limit_blocks_after_threshold(app_client):
    client, _ = app_client

    original_free = PLAN_CATALOG["free"]
    PLAN_CATALOG["free"] = PlanSpec(
        id=original_free.id,
        display_name=original_free.display_name,
        display_price=original_free.display_price,
        max_jobs_per_day=1,
        max_jobs_per_month=100,
        max_api_keys=original_free.max_api_keys,
        max_users=original_free.max_users,
        features=original_free.features,
    )

    try:
        first = client.post("/api/protected/generate-lite")
        assert first.status_code == 200

        second = client.post("/api/protected/generate-lite")
        assert second.status_code == 429
        assert second.get_json() == {"error": "plan_limit_reached"}
    finally:
        PLAN_CATALOG["free"] = original_free


def test_pro_plan_has_higher_limit_and_passes(app_client):
    client, session_factory = app_client

    original_pro = PLAN_CATALOG["pro"]
    PLAN_CATALOG["pro"] = PlanSpec(
        id=original_pro.id,
        display_name=original_pro.display_name,
        display_price=original_pro.display_price,
        max_jobs_per_day=2,
        max_jobs_per_month=100,
        max_api_keys=original_pro.max_api_keys,
        max_users=original_pro.max_users,
        features=original_pro.features,
    )

    register_res = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Quota Pro",
            "tenant_slug": f"quota-pro-{uuid.uuid4().hex[:8]}",
            "email": f"admin-pro-{uuid.uuid4().hex[:6]}@acme.io",
            "password": "S3curePass!",
        },
    )
    assert register_res.status_code == 201
    tenant_id = uuid.UUID(register_res.get_json()["tenant"]["id"])

    with session_factory() as session:
        tenant = session.get(Tenant, tenant_id)
        assert tenant is not None
        tenant.plan = "pro"
        session.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"email": register_res.get_json()["user"]["email"], "password": "S3curePass!"},
    )
    assert login_res.status_code == 200
    token = login_res.get_json()["access_token"]

    try:
        first = client.post("/api/protected/generate-lite", headers={"Authorization": f"Bearer {token}"})
        second = client.post("/api/protected/generate-lite", headers={"Authorization": f"Bearer {token}"})
        assert first.status_code == 200
        assert second.status_code == 200
    finally:
        PLAN_CATALOG["pro"] = original_pro


def test_subscription_endpoint_defaults_to_free_for_existing_tenant(app_client):
    client, _ = app_client

    register_res = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Sub Free",
            "tenant_slug": f"sub-free-{uuid.uuid4().hex[:8]}",
            "email": f"admin-subfree-{uuid.uuid4().hex[:6]}@acme.io",
            "password": "S3curePass!",
        },
    )
    assert register_res.status_code == 201

    login_res = client.post(
        "/api/auth/login",
        json={"email": register_res.get_json()["user"]["email"], "password": "S3curePass!"},
    )
    assert login_res.status_code == 200
    token = login_res.get_json()["access_token"]

    sub_res = client.get("/api/billing/subscription", headers={"Authorization": f"Bearer {token}"})
    assert sub_res.status_code == 200
    sub_json = sub_res.get_json()
    assert sub_json["tenant_id"] == register_res.get_json()["tenant"]["id"]
    assert sub_json["subscription"]["plan"] == "free"
    assert sub_json["subscription"]["status"] == "active"
    assert sub_json["subscription"]["cancel_at_period_end"] is False


def test_admin_can_update_own_tenant_plan_and_subscription(app_client):
    client, session_factory = app_client

    register_res = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Delta",
            "tenant_slug": f"delta-{uuid.uuid4().hex[:8]}",
            "email": f"admin-delta-{uuid.uuid4().hex[:6]}@acme.io",
            "password": "S3curePass!",
        },
    )
    assert register_res.status_code == 201
    tenant_id = register_res.get_json()["tenant"]["id"]

    login_res = client.post(
        "/api/auth/login",
        json={"email": register_res.get_json()["user"]["email"], "password": "S3curePass!"},
    )
    assert login_res.status_code == 200
    token = login_res.get_json()["access_token"]

    update_res = client.post(
        "/api/admin/tenant/plan",
        json={"plan": "pro"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_res.status_code == 200
    data = update_res.get_json()
    assert data["ok"] is True
    assert data["tenant_id"] == tenant_id
    assert data["plan"] == "pro"
    assert data["subscription"]["plan"] == "pro"
    assert data["subscription"]["status"] == "active"

    with session_factory() as session:
        tenant = session.get(Tenant, uuid.UUID(tenant_id))
        assert tenant is not None
        assert tenant.plan == "pro"
        sub = session.query(TenantSubscription).filter(TenantSubscription.tenant_id == uuid.UUID(tenant_id)).one_or_none()
        assert sub is not None
        assert sub.plan == "pro"
        assert sub.status == "active"


def test_anonymous_plan_request_with_tenant_slug_works(app_client):
    client, session_factory = app_client

    tenant_slug = f"lead-anon-{uuid.uuid4().hex[:8]}"
    register_res = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Lead Anonymous",
            "tenant_slug": tenant_slug,
            "email": f"admin-lead-anon-{uuid.uuid4().hex[:6]}@acme.io",
            "password": "S3curePass!",
        },
    )
    assert register_res.status_code == 201
    tenant_id = uuid.UUID(register_res.get_json()["tenant"]["id"])

    req_res = client.post(
        "/api/billing/plan-request",
        json={
            "requested_plan": "PRO",
            "tenant_slug": tenant_slug,
            "contact_email": "sales-contact@acme.io",
            "contact_phone": "+90-555-000-0000",
            "note": "Need upgrade details",
        },
    )
    assert req_res.status_code == 200
    payload = req_res.get_json()
    assert payload["ok"] is True
    request_id = uuid.UUID(payload["request_id"])

    with session_factory() as session:
        item = session.get(TenantPlanRequest, request_id)
        assert item is not None
        assert item.tenant_id == tenant_id
        assert item.requested_plan == "PRO"
        assert item.contact_email == "sales-contact@acme.io"
        assert item.status == "new"


def test_authenticated_plan_request_uses_context_tenant_without_slug(app_client):
    client, session_factory = app_client

    register_res = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Lead Auth",
            "tenant_slug": f"lead-auth-{uuid.uuid4().hex[:8]}",
            "email": f"admin-lead-auth-{uuid.uuid4().hex[:6]}@acme.io",
            "password": "S3curePass!",
        },
    )
    assert register_res.status_code == 201
    tenant_id = uuid.UUID(register_res.get_json()["tenant"]["id"])
    admin_email = register_res.get_json()["user"]["email"]

    login_res = client.post(
        "/api/auth/login",
        json={"email": admin_email, "password": "S3curePass!"},
    )
    assert login_res.status_code == 200
    token = login_res.get_json()["access_token"]

    req_res = client.post(
        "/api/billing/plan-request",
        json={
            "requested_plan": "BUSINESS",
            "note": "We need higher quotas",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert req_res.status_code == 200
    request_id = uuid.UUID(req_res.get_json()["request_id"])

    with session_factory() as session:
        item = session.get(TenantPlanRequest, request_id)
        assert item is not None
        assert item.tenant_id == tenant_id
        assert item.requested_plan == "BUSINESS"
        assert item.contact_email == admin_email


def test_admin_plan_request_list_and_update_are_tenant_scoped(app_client):
    client, _ = app_client

    reg_a = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Tenant A",
            "tenant_slug": f"tenant-a-{uuid.uuid4().hex[:8]}",
            "email": f"admin-a-{uuid.uuid4().hex[:6]}@acme.io",
            "password": "S3curePass!",
        },
    )
    assert reg_a.status_code == 201

    reg_b = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Tenant B",
            "tenant_slug": f"tenant-b-{uuid.uuid4().hex[:8]}",
            "email": f"admin-b-{uuid.uuid4().hex[:6]}@acme.io",
            "password": "S3curePass!",
        },
    )
    assert reg_b.status_code == 201

    slug_a = reg_a.get_json()["tenant"]["slug"]
    slug_b = reg_b.get_json()["tenant"]["slug"]

    req_a = client.post(
        "/api/billing/plan-request",
        json={"requested_plan": "PRO", "tenant_slug": slug_a, "note": "A request"},
    )
    assert req_a.status_code == 200
    req_a_id = req_a.get_json()["request_id"]

    req_b = client.post(
        "/api/billing/plan-request",
        json={"requested_plan": "BUSINESS", "tenant_slug": slug_b, "note": "B request"},
    )
    assert req_b.status_code == 200
    req_b_id = req_b.get_json()["request_id"]

    login_a = client.post(
        "/api/auth/login",
        json={"email": reg_a.get_json()["user"]["email"], "password": "S3curePass!"},
    )
    assert login_a.status_code == 200
    token_a = login_a.get_json()["access_token"]

    list_res = client.get("/api/admin/plan-requests", headers={"Authorization": f"Bearer {token_a}"})
    assert list_res.status_code == 200
    listed = list_res.get_json()
    listed_ids = {item["id"] for item in listed}
    assert req_a_id in listed_ids
    assert req_b_id not in listed_ids

    cross_update = client.patch(
        f"/api/admin/plan-requests/{req_b_id}",
        json={"status": "contacted"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert cross_update.status_code == 404
    assert cross_update.get_json() == {"error": "plan_request_not_found"}

    own_update = client.patch(
        f"/api/admin/plan-requests/{req_a_id}",
        json={"status": "contacted"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert own_update.status_code == 200
    assert own_update.get_json()["status"] == "contacted"
