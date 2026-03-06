import uuid
from contextvars import ContextVar

from lib.db.models import DEFAULT_TENANT_ID


_current_tenant_id: ContextVar[uuid.UUID] = ContextVar("current_tenant_id", default=DEFAULT_TENANT_ID)


def get_current_tenant_id() -> uuid.UUID:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: uuid.UUID) -> None:
    _current_tenant_id.set(tenant_id)


def reset_to_default_tenant() -> None:
    _current_tenant_id.set(DEFAULT_TENANT_ID)
