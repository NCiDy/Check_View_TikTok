from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def normalize_database_url(raw_url: str) -> str:
    """Convert a Supabase/Postgres URI to the psycopg SQLAlchemy dialect."""
    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgresql+psycopg://") and "sslmode=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"
    return url


def configure_database(raw_url: str | None = None) -> Engine:
    global _engine, _session_factory
    url = normalize_database_url(raw_url or settings.database_url)
    if not url:
        raise RuntimeError("DATABASE_URL chưa được cấu hình trong file .env")

    if _engine is not None:
        return _engine

    engine_kwargs = {
        "pool_pre_ping": True,
        "future": True,
    }

    if url.startswith("postgresql"):
        engine_kwargs.update({
            # Keep the application pool deliberately below Supabase's shared
            # pool limit so checker work cannot starve interactive requests.
            "pool_size": 5,
            "max_overflow": 0,
            "pool_timeout": 10,
            "pool_recycle": 120,
            "pool_use_lifo": True,
            "pool_reset_on_return": "rollback",
            # Supabase transaction pooling (port 6543) does not support
            # prepared statements. This is also safe in session mode.
            "connect_args": {"prepare_threshold": None, "connect_timeout": 5},
        })

    _engine = create_engine(url, **engine_kwargs)
    _session_factory = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    return _engine


def get_engine() -> Engine:
    return configure_database()


def get_session_factory() -> sessionmaker:
    if _session_factory is None:
        configure_database()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_database_connection() -> dict:
    engine = get_engine()
    required = {
        "users",
        "machines",
        "tiktok_accounts",
        "check_runs",
        "app_settings",
        "user_sessions",
        "audit_logs",
    }
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        rows = connection.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        ))
        found = {row[0] for row in rows}
        column_rows = connection.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        ))
        found_columns = {(row[0], row[1]) for row in column_rows}
    missing = sorted(required - found)
    required_columns = {
        ("users", "max_active_sessions"),
        ("users", "is_system_owner"),
        ("users", "show_in_org_chart"),
        ("check_runs", "requested_session_id"),
    }
    missing_columns = sorted(f"{table}.{column}" for table, column in required_columns - found_columns)
    return {
        "connected": True,
        "tables_ok": not missing,
        "schema_ok": not missing and not missing_columns,
        "missing_tables": missing,
        "missing_columns": missing_columns,
    }
