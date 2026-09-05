import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    leader_collaboration_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    username: Mapped[str] = mapped_column(Text, nullable=False)
    username_normalized: Mapped[str] = mapped_column(
        Text, Computed("lower(btrim(username))", persisted=True)
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_system_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_in_org_chart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    leader_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    can_add_accounts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete_accounts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_run_checks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    machine_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class TikTokAccount(Base):
    __tablename__ = "tiktok_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    machine_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )
    slot_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    username_normalized: Mapped[str] = mapped_column(
        Text,
        Computed("lower(trim(leading '@' FROM btrim(username)))", persisted=True),
    )
    nickname: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    followers: Mapped[int | None] = mapped_column(BigInteger)
    previous_followers: Mapped[int | None] = mapped_column(BigInteger)
    following: Mapped[int | None] = mapped_column(BigInteger)
    total_likes: Mapped[int | None] = mapped_column(BigInteger)
    total_sample_views: Mapped[int | None] = mapped_column(BigInteger)
    avg_sample_views: Mapped[int | None] = mapped_column(BigInteger)
    video_count_sample: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_videos: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="UNCHECKED")
    previous_status: Mapped[str | None] = mapped_column(Text)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error_code: Mapped[str | None] = mapped_column(Text)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    last_http_status: Mapped[int | None] = mapped_column(Integer)
    dead_confirmation_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    last_successful_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_successful_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_followers: Mapped[int | None] = mapped_column(BigInteger)
    previous_auto_followers: Mapped[int | None] = mapped_column(BigInteger)
    auto_status: Mapped[str | None] = mapped_column(Text)
    previous_auto_status: Mapped[str | None] = mapped_column(Text)
    auto_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_auto_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_successful_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_auto_successful_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CheckRun(Base):
    __tablename__ = "check_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    requested_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_sessions.id", ondelete="SET NULL")
    )
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    selected_account_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="QUEUED")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=10)
    total_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    live_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    die_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    follower_changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_problem_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    auto_check_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Asia/Ho_Chi_Minh")
    next_auto_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_auto_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_total_workers: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=10)
    max_workers_per_job: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    request_delay_seconds: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0.3)
    request_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    dead_confirmation_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    follower_change_threshold: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    in_app_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    voice_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
