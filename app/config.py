import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "TikTok Account Manager")
    database_url: str = os.getenv("DATABASE_URL", "").strip()
    session_secret: str = os.getenv("SESSION_SECRET", "").strip()
    environment: str = os.getenv("APP_ENV", "development").strip().lower()
    cookie_secure_override: str = os.getenv("COOKIE_SECURE", "").strip()
    port: int = _as_int(os.getenv("PORT"), 8088)
    
    supabase_url: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_service_role_key: str = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY", ""
    ).strip()

    proxy_mode: str = os.getenv("PROXY_MODE", "direct").strip().lower()
    proxy_list: str = os.getenv("PROXY_LIST", "")
    rotating_proxy_url: str = os.getenv("ROTATING_PROXY_URL", "").strip()

    @property
    def cookie_secure(self) -> bool:
        if self.cookie_secure_override:
            return _as_bool(self.cookie_secure_override)
        return self.environment == "production"

    @property
    def is_configured(self) -> bool:
        return bool(self.database_url and self.session_secret)


settings = Settings()

