from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_enterprise_migration_contains_required_tables_and_indexes():
    sql = (ROOT / "database" / "002_enterprise_sessions.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS public.user_sessions" in sql
    assert "CREATE TABLE IF NOT EXISTS public.audit_logs" in sql
    assert "ux_user_sessions_one_active_per_user" in sql
    assert "ux_check_runs_one_active_per_session" in sql


def test_example_environment_has_placeholders_only():
    value = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "YOUR_DATABASE_PASSWORD" in value
    assert "YOUR_SERVICE_ROLE_KEY" in value
    assert "wpotbxp" not in value.lower()
