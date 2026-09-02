from core.checker import TikTokChecker
from app.database import normalize_database_url
from app.security import hash_password, verify_password


def test_clean_username_legacy_formats():
    cases = {
        "@hello.world": "hello.world",
        "https://www.tiktok.com/@Hello_123?lang=vi": "Hello_123",
        "username|password|email|2fa": "username",
        "username:password": "username",
        "username password": "username",
    }
    for raw, expected in cases.items():
        assert TikTokChecker.clean_username(raw) == expected


def test_clean_username_rejects_invalid_input():
    assert TikTokChecker.clean_username("") == ""
    assert TikTokChecker.clean_username("not valid / value") == "not"
    assert TikTokChecker.clean_username("@@@") == ""


def test_password_hash_is_argon2_and_verifies():
    password_hash = hash_password("mat-khau-demo-123")
    assert password_hash.startswith("$argon2id$")
    assert verify_password("mat-khau-demo-123", password_hash)[0] is True
    assert verify_password("sai-mat-khau", password_hash)[0] is False


def test_supabase_url_uses_psycopg_and_ssl():
    value = normalize_database_url(
        "postgresql://postgres.project:password@host.pooler.supabase.com:5432/postgres"
    )
    assert value.startswith("postgresql+psycopg://")
    assert "sslmode=require" in value

