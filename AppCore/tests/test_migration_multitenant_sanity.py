from pathlib import Path


def test_multitenant_migration_file_exists_and_has_expected_markers():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20260217_02_multitenant_foundation.py"
    )
    content = migration_path.read_text(encoding="utf-8")

    assert "revision = \"20260217_02_multitenant_foundation\"" in content
    assert "down_revision = \"20260217_01_create_jobs_pgsql\"" in content
    assert "create_table(\n            \"tenants\"" in content
    assert "UPDATE {table_name} SET tenant_id" in content
    assert "ix_jobs_tenant_status_scheduled_time" in content
