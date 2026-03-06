import hashlib
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any, Callable

import bcrypt
import jwt
import sqlalchemy as sa
from flask import Flask, g, jsonify, request
from sqlalchemy.orm import Session, sessionmaker

from lib.db.models import ApiKey, AuditLog, DEFAULT_TENANT_ID, Tenant, User
from lib.db.session import session_scope
from lib.db.tenant_context import reset_to_default_tenant, set_current_tenant_id


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(slots=True)
class AuthIdentity:
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    source: str


class InMemoryLoginRateLimiter:
    def __init__(self, *, max_attempts: int = 10, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._bucket: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_limited(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            attempts = [ts for ts in self._bucket.get(key, []) if now - ts <= self.window_seconds]
            self._bucket[key] = attempts
            return len(attempts) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        now = time.time()
        with self._lock:
            attempts = [ts for ts in self._bucket.get(key, []) if now - ts <= self.window_seconds]
            attempts.append(now)
            self._bucket[key] = attempts

    def clear(self, key: str) -> None:
        with self._lock:
            self._bucket.pop(key, None)


_login_limiter = InMemoryLoginRateLimiter()
_auth_secret_warning_emitted = False
_auth_secret_warning_lock = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip() or os.getenv("FLASK_SECRET_KEY", "").strip()
    if not secret and _is_production_mode():
        return ""
    return secret or "change-me-in-production"


def _is_production_mode() -> bool:
    markers = (
        os.getenv("FLASK_ENV", ""),
        os.getenv("APP_ENV", ""),
        os.getenv("ENV", ""),
    )
    if any((m or "").strip().lower() == "production" for m in markers):
        return True
    return os.getenv("SAAS_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _is_auth_secret_configured() -> bool:
    return bool(os.getenv("JWT_SECRET", "").strip() or os.getenv("FLASK_SECRET_KEY", "").strip())


def _auth_secret_unavailable_for_auth_endpoints() -> bool:
    return _is_production_mode() and not _is_auth_secret_configured()


def _warn_missing_auth_secret(app: Flask) -> None:
    global _auth_secret_warning_emitted
    with _auth_secret_warning_lock:
        if _auth_secret_warning_emitted:
            return
        app.logger.warning(
            "JWT_SECRET/FLASK_SECRET_KEY is missing in production mode; auth endpoints are disabled"
        )
        _auth_secret_warning_emitted = True


def _jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256"


def _jwt_exp_minutes() -> int:
    try:
        return int(os.getenv("JWT_EXP_MINUTES", "120"))
    except ValueError:
        return 120


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def hash_api_key(raw_api_key: str) -> str:
    return hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or f"tenant-{uuid.uuid4().hex[:8]}"


def create_access_token(*, user: User) -> str:
    now = _utc_now()
    exp = now + timedelta(minutes=_jwt_exp_minutes())
    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "email": user.email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_jwt_algorithm()])
    except jwt.PyJWTError as exc:
        raise AuthError("invalid_or_expired_token", 401) from exc


def _append_audit(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    meta: dict[str, Any] | None,
    ip: str | None,
    user_agent: str | None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            meta=meta,
            ip=ip,
            user_agent=user_agent,
        )
    )


def register_tenant_admin(
    session_factory: sessionmaker[Session],
    *,
    tenant_name: str,
    tenant_slug: str | None,
    email: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    tenant_name = (tenant_name or "").strip()
    email = (email or "").strip().lower()
    password = (password or "").strip()
    tenant_slug = (tenant_slug or "").strip() or _slugify(tenant_name)

    if not tenant_name or not email or not password:
        raise AuthError("tenant_name_email_password_required", 400)
    if len(password) < 8:
        raise AuthError("password_too_short", 400)

    with session_scope(session_factory) as session:
        if session.scalar(sa.select(Tenant.id).where(Tenant.slug == tenant_slug)) is not None:
            raise AuthError("tenant_slug_already_exists", 409)
        if session.scalar(sa.select(User.id).where(User.email == email)) is not None:
            raise AuthError("email_already_exists", 409)

        tenant = Tenant(name=tenant_name, slug=tenant_slug, plan="free", is_active=True)
        session.add(tenant)
        session.flush()

        user = User(
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
        session.add(user)
        session.flush()

        _append_audit(
            session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="auth.register",
            resource_type="user",
            resource_id=user.id,
            meta={"email": email},
            ip=ip,
            user_agent=user_agent,
        )

        token = create_access_token(user=user)

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role,
                "is_active": bool(user.is_active),
            },
            "tenant": {
                "id": str(tenant.id),
                "name": tenant.name,
                "slug": tenant.slug,
                "is_active": bool(tenant.is_active),
            },
        }


def login_user(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    email = (email or "").strip().lower()
    password = (password or "").strip()
    if not email or not password:
        raise AuthError("email_password_required", 400)

    limiter_key = f"{ip or 'unknown'}:{email}"
    if _login_limiter.is_limited(limiter_key):
        raise AuthError("too_many_login_attempts", 429)

    with session_scope(session_factory) as session:
        row = session.execute(
            sa.select(User, Tenant)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(User.email == email)
        ).first()

        if row is None:
            _login_limiter.record_failure(limiter_key)
            raise AuthError("invalid_credentials", 401)

        user, tenant = row
        if not bool(user.is_active):
            raise AuthError("inactive_user", 403)
        if not bool(tenant.is_active):
            raise AuthError("inactive_tenant", 403)
        if not verify_password(password, user.password_hash):
            _login_limiter.record_failure(limiter_key)
            raise AuthError("invalid_credentials", 401)

        _login_limiter.clear(limiter_key)
        token = create_access_token(user=user)

        _append_audit(
            session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="auth.login",
            resource_type="user",
            resource_id=user.id,
            meta={"email": user.email},
            ip=ip,
            user_agent=user_agent,
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role,
                "is_active": bool(user.is_active),
            },
            "tenant": {
                "id": str(tenant.id),
                "name": tenant.name,
                "slug": tenant.slug,
                "is_active": bool(tenant.is_active),
            },
        }


def _resolve_from_token(session_factory: sessionmaker[Session], token: str) -> AuthIdentity:
    if _auth_secret_unavailable_for_auth_endpoints():
        raise AuthError("auth_secret_not_configured", 503)

    payload = decode_access_token(token)
    tenant_id_raw = payload.get("tenant_id")
    user_id_raw = payload.get("sub")
    if not tenant_id_raw or not user_id_raw:
        raise AuthError("invalid_token_payload", 401)

    tenant_id = uuid.UUID(str(tenant_id_raw))
    user_id = uuid.UUID(str(user_id_raw))

    with session_scope(session_factory) as session:
        row = session.execute(
            sa.select(User, Tenant)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(User.id == user_id, User.tenant_id == tenant_id)
        ).first()

        if row is None:
            raise AuthError("user_not_found", 401)

        user, tenant = row
        if not bool(user.is_active):
            raise AuthError("inactive_user", 403)
        if not bool(tenant.is_active):
            raise AuthError("inactive_tenant", 403)

        return AuthIdentity(tenant_id=tenant.id, user_id=user.id, source="jwt")


def _resolve_from_api_key(
    session_factory: sessionmaker[Session],
    *,
    raw_api_key: str,
    ip: str | None,
    user_agent: str | None,
) -> AuthIdentity:
    key_hash = hash_api_key(raw_api_key)
    now = _utc_now()

    with session_scope(session_factory) as session:
        row = session.execute(
            sa.select(ApiKey, Tenant)
            .join(Tenant, Tenant.id == ApiKey.tenant_id)
            .where(ApiKey.key_hash == key_hash)
        ).first()

        if row is None:
            raise AuthError("invalid_api_key", 401)

        api_key, tenant = row
        if not bool(tenant.is_active):
            raise AuthError("inactive_tenant", 403)

        api_key.last_used_at = now
        _append_audit(
            session,
            tenant_id=tenant.id,
            user_id=None,
            action="auth.api_key_used",
            resource_type="api_key",
            resource_id=api_key.id,
            meta={"name": api_key.name},
            ip=ip,
            user_agent=user_agent,
        )

        return AuthIdentity(tenant_id=tenant.id, user_id=None, source="api_key")


def resolve_request_identity(
    session_factory: sessionmaker[Session] | None,
    *,
    authorization_header: str | None,
    api_key_header: str | None,
    ip: str | None,
    user_agent: str | None,
) -> AuthIdentity:
    if session_factory and authorization_header and authorization_header.startswith("Bearer "):
        token = authorization_header.removeprefix("Bearer ").strip()
        if token:
            return _resolve_from_token(session_factory, token)

    if session_factory and api_key_header:
        raw_api_key = api_key_header.strip()
        if raw_api_key:
            return _resolve_from_api_key(
                session_factory,
                raw_api_key=raw_api_key,
                ip=ip,
                user_agent=user_agent,
            )

    if session_factory:
        with session_scope(session_factory) as session:
            tenant = session.get(Tenant, DEFAULT_TENANT_ID)
            if tenant is None or not bool(tenant.is_active):
                raise AuthError("inactive_tenant", 403)

    return AuthIdentity(tenant_id=DEFAULT_TENANT_ID, user_id=None, source="default")


def require_authenticated(allow_api_key: bool = True) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            source = getattr(g, "auth_source", "default")
            if source in {"jwt", "token"}:
                return func(*args, **kwargs)
            if allow_api_key and source == "api_key":
                return func(*args, **kwargs)
            return jsonify({"error": "authentication_required"}), 401

        return wrapper

    return decorator


def install_auth(app: Flask, session_factory: sessionmaker[Session] | None) -> None:
    @app.before_request
    def _resolve_auth_context():
        path = request.path or ""
        if path.startswith("/api/auth/") and _auth_secret_unavailable_for_auth_endpoints():
            _warn_missing_auth_secret(app)
            return jsonify({"error": "auth_secret_not_configured"}), 503

        try:
            identity = resolve_request_identity(
                session_factory,
                authorization_header=request.headers.get("Authorization"),
                api_key_header=request.headers.get("X-API-Key"),
                ip=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )
        except AuthError as exc:
            return jsonify({"error": exc.message}), exc.status_code

        g.tenant_id = identity.tenant_id
        g.user_id = identity.user_id
        g.auth_source = identity.source
        set_current_tenant_id(identity.tenant_id)
        return None

    @app.teardown_request
    def _reset_tenant_context(_error):
        try:
            reset_to_default_tenant()
        except Exception:
            app.logger.exception("failed_to_reset_tenant_context_in_teardown")

    @app.route("/api/auth/register", methods=["POST"])
    def auth_register():
        if session_factory is None:
            return jsonify({"error": "database_not_configured"}), 503

        data = request.get_json(silent=True) or {}
        try:
            result = register_tenant_admin(
                session_factory,
                tenant_name=str(data.get("tenant_name", "")),
                tenant_slug=str(data.get("tenant_slug", "")) or None,
                email=str(data.get("email", "")),
                password=str(data.get("password", "")),
                ip=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )
            return jsonify(result), 201
        except AuthError as exc:
            return jsonify({"error": exc.message}), exc.status_code

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        if session_factory is None:
            return jsonify({"error": "database_not_configured"}), 503

        data = request.get_json(silent=True) or {}
        try:
            result = login_user(
                session_factory,
                email=str(data.get("email", "")),
                password=str(data.get("password", "")),
                ip=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )
            return jsonify(result)
        except AuthError as exc:
            response = jsonify({"error": exc.message})
            if exc.status_code == 429:
                response.headers["Retry-After"] = str(_login_limiter.window_seconds)
                response.headers["X-RateLimit-Limit"] = str(_login_limiter.max_attempts)
                response.headers["X-RateLimit-Window"] = str(_login_limiter.window_seconds)
            return response, exc.status_code

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        return jsonify({"ok": True})

    @app.route("/api/auth/me", methods=["GET"])
    @require_authenticated(allow_api_key=True)
    def auth_me():
        if session_factory is None:
            return jsonify({"error": "database_not_configured"}), 503

        with session_scope(session_factory) as session:
            tenant = session.get(Tenant, g.tenant_id)
            if tenant is None or not bool(tenant.is_active):
                return jsonify({"error": "inactive_tenant"}), 403

            user_payload: dict[str, Any] | None = None
            if g.user_id is not None:
                user = session.get(User, g.user_id)
                if user is None or not bool(user.is_active):
                    return jsonify({"error": "inactive_user"}), 403
                user_payload = {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role,
                    "is_active": bool(user.is_active),
                }

            return jsonify(
                {
                    "auth_source": g.auth_source,
                    "user": user_payload,
                    "tenant": {
                        "id": str(tenant.id),
                        "name": tenant.name,
                        "slug": tenant.slug,
                        "is_active": bool(tenant.is_active),
                    },
                }
            )
