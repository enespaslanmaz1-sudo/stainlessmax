import os
import sys
from pathlib import Path


def _add_system_to_syspath() -> None:
    root = Path(__file__).resolve().parents[2]
    system_dir = root / "System"
    if str(system_dir) not in sys.path:
        sys.path.insert(0, str(system_dir))


def test_shared_factory_registers_auth_and_billing_routes_without_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SAAS_MODE", "1")

    _add_system_to_syspath()

    from app import create_app

    app, _socketio = create_app()

    rule_paths = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/api/auth/login" in rule_paths
    assert "/api/billing/plans" in rule_paths
    assert "/api/billing/plan-request" in rule_paths
