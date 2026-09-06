from __future__ import annotations

import asyncio
from io import BytesIO
import json
import logging
import os
import secrets
import threading
import time
import uuid
from app.models import Department
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete, and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.audit import write_audit
from app.database import db_session, get_db, test_database_connection
from app.job_manager import JobManager
from app.models import Department, AuditLog, AppSettings, CheckRun, Machine, TikTokAccount, User, UserSession
from app.permissions import (
    ensure_can_manage_accounts,
    ensure_can_start_manual_check,
    ensure_can_view_user,
    machine_owner,
)
from app.security import (
    csrf_protect,
    end_user_session,
    get_current_session,
    get_current_user,
    hash_password,
    mark_login,
    require_roles,
    revoke_user_sessions,
    start_user_session,
    validate_login_username,
    validate_password,
    verify_password,
)
from core.checker import TikTokChecker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("tiktok-manager")
STATIC_DIR = Path(__file__).resolve().parent / "static"
REACT_DIST_DIR = STATIC_DIR / "react"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_uuid(value: str, field_name: str = "ID") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} không hợp lệ") from exc


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class LoginLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.attempts: dict[str, deque[float]] = defaultdict(deque)

    def ensure_allowed(self, key: str) -> None:
        now = time.time()
        with self.lock:
            history = self.attempts[key]
            while history and now - history[0] > 300:
                history.popleft()
            if len(history) >= 10:
                raise HTTPException(status_code=429, detail="Đăng nhập sai quá nhiều lần, thử lại sau 5 phút")

    def failed(self, key: str) -> None:
        with self.lock:
            self.attempts[key].append(time.time())

    def success(self, key: str) -> None:
        with self.lock:
            self.attempts.pop(key, None)


login_limiter = LoginLimiter()


class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = defaultdict(list)
        self.session_users: dict[str, str] = {}
        self.lock = asyncio.Lock()

    async def connect(self, session_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.connections[session_id].append(websocket)
            self.session_users[session_id] = user_id

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self.lock:
            if websocket in self.connections.get(session_id, []):
                self.connections[session_id].remove(websocket)
            if not self.connections.get(session_id):
                self.connections.pop(session_id, None)
                self.session_users.pop(session_id, None)

    async def send_sessions(self, session_ids: set[str], event: str, payload: dict[str, Any]) -> None:
        message = json.dumps({"type": event, "data": payload}, ensure_ascii=False, default=str)
        stale: list[tuple[str, WebSocket]] = []
        async with self.lock:
            targets = [(sid, ws) for sid in session_ids for ws in self.connections.get(sid, [])]
        for sid, websocket in targets:
            try:
                await websocket.send_text(message)
            except Exception:
                stale.append((sid, websocket))
        for sid, websocket in stale:
            await self.disconnect(sid, websocket)

    async def send_users(self, user_ids: set[str], event: str, payload: dict[str, Any]) -> None:
        async with self.lock:
            session_ids = {
                sid for sid, uid in self.session_users.items() if uid in user_ids
            }
        if session_ids:
            await self.send_sessions(session_ids, event, payload)

    async def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        async with self.lock:
            session_ids = set(self.connections)
        if session_ids:
            await self.send_sessions(session_ids, event, payload)

    async def dispatch_job_event(self, event: str, payload: dict[str, Any]) -> None:
        if event in {"job_started", "job_progress", "job_finished", "job_failed"}:
            requested_session_id = payload.get("requested_session_id")
            if requested_session_id:
                await self.send_sessions({str(requested_session_id)}, event, payload)
            elif payload.get("scheduled"):
                with db_session() as db:
                    boss_ids = {
                        str(value) for value in db.scalars(
                            select(User.id).where(User.role.in_(("BOSS", "MANAGER")), User.is_active.is_(True))
                        )
                    }
                await self.send_users(boss_ids, event, payload)

            # Other browsers receive only an invalidation after completion, never
            # somebody else's progress bar or stop button.
            if event in {"job_finished", "job_failed"}:
                await self.broadcast("data_updated", {"source": "check_run"})
            return

        if event == "alert":
            recipients: set[str] = set()
            owner_id = payload.get("owner_id")
            if owner_id:
                recipients.add(str(owner_id))
            try:
                with db_session() as db:
                    recipients.update(
                        str(value) for value in db.scalars(
                            select(User.id).where(User.role.in_(("BOSS", "MANAGER")), User.is_active.is_(True))
                        )
                    )
                    if owner_id:
                        owner = db.get(User, uuid.UUID(str(owner_id)))
                        if owner and owner.leader_id:
                            recipients.add(str(owner.leader_id))
            except Exception:
                pass
            if recipients:
                await self.send_users(recipients, event, payload)


ws_manager = ConnectionManager()


async def scheduler_loop(app: FastAPI) -> None:
    while True:
        try:
            await asyncio.sleep(15)
            if not getattr(app.state, "db_ready", False) or app.state.job_manager is None:
                continue
            should_start = False
            with db_session() as db:
                row = db.get(AppSettings, 1)
                if row and row.auto_check_enabled:
                    now = utcnow()
                    if row.next_auto_check_at is None:
                        row.next_auto_check_at = now + timedelta(minutes=row.check_interval_minutes)
                    elif row.next_auto_check_at <= now:
                        row.next_auto_check_at = now + timedelta(minutes=row.check_interval_minutes)
                        should_start = True
            if should_start:
                try:
                    app.state.job_manager.start_job(
                        requested_by=None,
                        trigger_type="SCHEDULED",
                        scope_type="COMPANY",
                        priority=20,
                    )
                except ValueError as exc:
                    logger.info("Không tạo auto job: %s", exc)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Scheduler gặp lỗi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_ready = False
    app.state.db_error = None
    app.state.job_manager = None
    app.state.scheduler_task = None
    event_loop = asyncio.get_running_loop()
    try:
        status = test_database_connection()
        if not status["tables_ok"]:
            raise RuntimeError(f"Thiếu bảng: {', '.join(status['missing_tables'])}")
        if not status.get("schema_ok", False):
            raise RuntimeError(
                "Database chưa chạy migration 002; thiếu cột: "
                + ", ".join(status.get("missing_columns", []))
            )

        # Bounded operational data: keep audit for 180 days and revoked sessions
        # for 30 days. Check history already keeps only the latest 20 runs/user.
        with db_session() as db:
            db.execute(delete(AuditLog).where(AuditLog.created_at < utcnow() - timedelta(days=180)))
            db.execute(delete(UserSession).where(
                UserSession.revoked_at.is_not(None),
                UserSession.revoked_at < utcnow() - timedelta(days=30),
            ))

        def event_bridge(event: str, payload: dict[str, Any]) -> None:
            asyncio.run_coroutine_threadsafe(
                ws_manager.dispatch_job_event(event, payload), event_loop
            )

        app.state.job_manager = JobManager(event_callback=event_bridge)
        app.state.db_ready = True
        app.state.scheduler_task = asyncio.create_task(scheduler_loop(app))
        logger.info("Đã kết nối database và khởi động JobManager")
    except Exception as exc:
        app.state.db_error = str(exc)
        logger.error("Ứng dụng chưa sẵn sàng kết nối database: %s", exc)
    yield
    if app.state.scheduler_task:
        app.state.scheduler_task.cancel()
    if app.state.job_manager:
        app.state.job_manager.shutdown()


app = FastAPI(
    title="TikTok Account Manager",
    version="4.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

session_secret = settings.session_secret or secrets.token_urlsafe(48)
if not settings.session_secret:
    logger.warning("SESSION_SECRET chưa cấu hình; phiên đăng nhập sẽ mất khi restart")

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    session_cookie="tiktok_manager_session",
    max_age=12 * 60 * 60,
    same_site="lax",
    https_only=settings.cookie_secure,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; connect-src 'self' ws: wss:; "
        "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/") or request.url.path in {"/", "/legacy"}:
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_request: Request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    full_name: str = Field(min_length=1, max_length=150)
    role: Literal["BOSS", "MANAGER", "LEADER", "MEMBER"]
    leader_id: str | None = None
    can_add_accounts: bool = False
    can_delete_accounts: bool = False
    can_run_checks: bool = True
    show_in_org_chart: bool = True


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    leader_id: str | None = None
    is_active: bool | None = None
    can_add_accounts: bool | None = None
    can_delete_accounts: bool | None = None
    can_run_checks: bool | None = None
    show_in_org_chart: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str


class MachineCreateRequest(BaseModel):
    owner_id: str
    machine_number: int = Field(ge=1, le=32767)
    note: str | None = Field(default=None, max_length=200)


class BulkAccountsRequest(BaseModel):
    machine_id: str
    items: list[str] = Field(min_length=1, max_length=100)


class TransferAccountRequest(BaseModel):
    machine_id: str
    slot_number: int = Field(ge=1, le=10)


class CheckStartRequest(BaseModel):
    scope_type: Literal["SELECTED", "USER", "LEADER_GROUP", "COMPANY"]
    target_user_id: str | None = None
    account_ids: list[str] = Field(default_factory=list, max_length=1000)


class SettingsUpdateRequest(BaseModel):
    auto_check_enabled: bool | None = None
    check_interval_minutes: int | None = Field(default=None, ge=15, le=1440)
    max_total_workers: int | None = Field(default=None, ge=1, le=50)
    max_workers_per_job: int | None = Field(default=None, ge=1, le=20)
    request_delay_seconds: float | None = Field(default=None, ge=0, le=60)
    request_timeout_seconds: int | None = Field(default=None, ge=3, le=120)
    retry_count: int | None = Field(default=None, ge=0, le=5)
    dead_confirmation_attempts: int | None = Field(default=None, ge=2, le=5)
    follower_change_threshold: int | None = Field(default=None, ge=1)
    in_app_notifications_enabled: bool | None = None
    voice_notifications_enabled: bool | None = None


class SessionRevokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=100)

class DepartmentUpdateRequest(BaseModel):
    leader_collaboration_enabled: bool


def serialize_user(db: Session, user: User) -> dict[str, Any]:
    machine_count = db.scalar(select(func.count()).select_from(Machine).where(Machine.owner_id == user.id)) or 0
    account_count = db.scalar(
        select(func.count()).select_from(TikTokAccount)
        .join(Machine, Machine.id == TikTokAccount.machine_id)
        .where(Machine.owner_id == user.id)
    ) or 0
    active_session = db.scalar(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utcnow(),
        )
        .order_by(UserSession.last_seen_at.desc())
    )
    return {
        "id": str(user.id),
        "username": user.username,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "is_system_owner": user.is_system_owner,
        "is_technical_account": user.is_technical_account,
        "show_in_org_chart": user.show_in_org_chart,
        "leader_id": str(user.leader_id) if user.leader_id else None,
        "department_id": str(user.department_id) if user.department_id else None,
        "is_active": user.is_active,
        "can_add_accounts": user.can_add_accounts,
        "can_delete_accounts": user.can_delete_accounts,
        "can_run_checks": user.can_run_checks,
        "machine_count": int(machine_count),
        "account_count": int(account_count),
        "last_login_at": iso(user.last_login_at),
        "last_seen_at": iso(active_session.last_seen_at) if active_session else None,
        "is_online": bool(
            active_session and active_session.last_seen_at >= utcnow() - timedelta(minutes=2)
        ),
        "updated_at": iso(user.updated_at),
        "created_at": iso(user.created_at),
    }


def serialize_machine(db: Session, machine: Machine) -> dict[str, Any]:
    account_count = db.scalar(
        select(func.count()).select_from(TikTokAccount).where(TikTokAccount.machine_id == machine.id)
    ) or 0
    return {
        "id": str(machine.id),
        "owner_id": str(machine.owner_id),
        "machine_number": machine.machine_number,
        "note": machine.note,
        "account_count": int(account_count),
        "created_at": iso(machine.created_at),
    }


def serialize_account(account: TikTokAccount, machine: Machine, owner: User) -> dict[str, Any]:
    follower_delta = None
    if account.followers is not None and account.previous_followers is not None:
        follower_delta = account.followers - account.previous_followers
    auto_delta = None
    if account.auto_followers is not None and account.previous_auto_followers is not None:
        auto_delta = account.auto_followers - account.previous_auto_followers
    return {
        "id": str(account.id),
        "machine_id": str(machine.id),
        "machine_number": machine.machine_number,
        "slot_number": account.slot_number,
        "owner_id": str(owner.id),
        "owner_name": owner.full_name,
        "owner_role": owner.role,
        "username": account.username,
        "nickname": account.nickname,
        "avatar_url": account.avatar_url,
        "bio": account.bio,
        "followers": account.followers,
        "previous_followers": account.previous_followers,
        "follower_delta": follower_delta,
        "following": account.following,
        "total_likes": account.total_likes,
        "total_sample_views": account.total_sample_views,
        "avg_sample_views": account.avg_sample_views,
        "video_count_sample": account.video_count_sample,
        "recent_videos": account.recent_videos or [],
        "status": account.status,
        "previous_status": account.previous_status,
        "is_private": account.is_private,
        "is_verified": account.is_verified,
        "last_error_code": account.last_error_code,
        "last_error_message": account.last_error_message,
        "last_checked_at": iso(account.last_checked_at),
        "last_successful_checked_at": iso(account.last_successful_checked_at),
        "auto_followers": account.auto_followers,
        "previous_auto_followers": account.previous_auto_followers,
        "auto_delta": auto_delta,
        "auto_status": account.auto_status,
        "previous_auto_status": account.previous_auto_status,
        "auto_checked_at": iso(account.auto_checked_at),
        "created_at": iso(account.created_at),
    }


def visible_users_query(current: User):
    if current.role in {"BOSS", "MANAGER"}:
        return select(User).order_by(User.role, User.full_name)

    if current.role == "LEADER":
        conditions = [
            User.id == current.id,
            User.leader_id == current.id,
        ]

        if current.department_id:
            collaboration_enabled = exists(
                select(Department.id).where(
                    Department.id == current.department_id,
                    Department.is_active.is_(True),
                    Department.leader_collaboration_enabled.is_(True),
                )
            )

            conditions.append(
                and_(
                    collaboration_enabled,
                    User.department_id == current.department_id,
                    User.role.in_(("LEADER", "MEMBER")),
                )
            )

        return (
            select(User)
            .where(
                or_(*conditions),
                User.is_active.is_(True),
            )
            .order_by(User.role, User.full_name)
        )

    return select(User).where(User.id == current.id)


def visible_owner_ids(
    db: Session,
    current: User,
) -> list[uuid.UUID]:
    query = (
        visible_users_query(current)
        .with_only_columns(User.id)
        .order_by(None)
    )

    return list(db.scalars(query))


def ensure_can_manage_user(
    actor: User,
    target: User | None = None,
    creating_role: str | None = None,
) -> None:
    role = creating_role or (target.role if target else None)

    if actor.role not in {"BOSS", "MANAGER"}:
        raise HTTPException(
            status_code=403,
            detail="Bạn không có quyền quản lý nhân sự",
        )

    # Chỉ BOSS chính được quản lý BOSS hoặc MANAGER.
    if role in {"BOSS", "MANAGER"} and not actor.is_system_owner:
        raise HTTPException(
            status_code=403,
            detail="Chỉ BOSS chính được quản lý BOSS hoặc MANAGER",
        )

    if target is not None and target.is_system_owner and target.id != actor.id:
        raise HTTPException(
            status_code=403,
            detail="Không được thay đổi BOSS chính",
        )


def serialize_session(db: Session, row: UserSession, current_session_id: uuid.UUID) -> dict[str, Any]:
    user = db.get(User, row.user_id)
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "user_name": user.full_name if user else "Tài khoản đã xóa",
        "username": user.username if user else None,
        "role": user.role if user else None,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "created_at": iso(row.created_at),
        "last_seen_at": iso(row.last_seen_at),
        "expires_at": iso(row.expires_at),
        "revoked_at": iso(row.revoked_at),
        "revoked_reason": row.revoked_reason,
        "is_current": row.id == current_session_id,
        "is_online": (
            row.revoked_at is None
            and row.expires_at > utcnow()
            and row.last_seen_at >= utcnow() - timedelta(minutes=2)
        ),
    }


def active_boss_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(User.id)).where(User.role.in_(("BOSS", "MANAGER")), User.is_active.is_(True))
        )
        or 0
    )


def get_job_manager(request: Request) -> JobManager:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail=request.app.state.db_error or "JobManager chưa sẵn sàng")
    return manager


@app.get("/api/health")
def health(request: Request):
    return {
        "status": "ok" if request.app.state.db_ready else "setup_required",
        "database": "connected" if request.app.state.db_ready else "not_connected",
        "detail": request.app.state.db_error,
        "version": app.version,
    }


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    key = f"{ip}:{payload.username.lower()}"
    login_limiter.ensure_allowed(key)
    try:
        username = validate_login_username(payload.username).lower()
    except ValueError:
        login_limiter.failed(key)
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")
    user = db.scalar(select(User).where(User.username_normalized == username))
    if user is None or not user.is_active:
        login_limiter.failed(key)
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")
    valid, replacement = verify_password(payload.password, user.password_hash)
    if not valid:
        login_limiter.failed(key)
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")
    if replacement:
        user.password_hash = replacement
    mark_login(db, user)
    forwarded_ip = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    ip_address = forwarded_ip or (request.client.host if request.client else None)
    csrf_token, user_session, revoked_ids = start_user_session(
        request,
        db,
        user,
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
    )
    write_audit(db, request, user, "AUTH_LOGIN", "SESSION", user_session.id)
    db.commit()
    if revoked_ids:
        await ws_manager.send_sessions(
            set(revoked_ids),
            "session_revoked",
            {"reason": "Tài khoản vừa đăng nhập trên thiết bị khác"},
        )
    login_limiter.success(key)
    return {
        "success": True,
        "user": serialize_user(db, user),
        "session_id": str(user_session.id),
        "csrf_token": csrf_token,
    }


@app.post("/api/auth/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
    current_session: UserSession = Depends(get_current_session),
):
    write_audit(db, request, current, "AUTH_LOGOUT", "SESSION", current_session.id)
    end_user_session(request, db)
    db.commit()
    return {"success": True}


@app.get("/api/auth/me")
def me(
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
):
    return {
        "user": serialize_user(db, current),
        "session_id": str(current_session.id),
        "csrf_token": request.session.get("csrf_token"),
    }


@app.post("/api/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
    current_session: UserSession = Depends(get_current_session),
):
    valid, _ = verify_password(payload.current_password, current.password_hash)
    if not valid:
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")
    try:
        current.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    current.password_changed_at = utcnow()
    revoked_ids = revoke_user_sessions(
        db,
        current.id,
        "PASSWORD_CHANGED",
        except_session_id=current_session.id,
    )
    write_audit(db, request, current, "PASSWORD_CHANGED", "USER", current.id)
    db.commit()
    if revoked_ids:
        await ws_manager.send_sessions(
            set(revoked_ids), "session_revoked", {"reason": "Mật khẩu đã được thay đổi"}
        )
    return {"success": True}


@app.get("/api/users")
def list_users(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    query = (
        visible_users_query(current)
        .where(User.is_technical_account.is_(False))
    )

    users = list(db.scalars(query))

    return {
        "users": [
            serialize_user(db, user)
            for user in users
            if not user.is_technical_account
        ]
    }


@app.post("/api/users")
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    ensure_can_manage_user(current, creating_role=payload.role)
    if payload.role == "BOSS" and active_boss_count(db) >= 3:
        raise HTTPException(status_code=409, detail="Đã đủ 3 tài khoản BOSS đang hoạt động")
    try:
        username = validate_login_username(payload.username)
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    leader_id = None
    if payload.role == "MEMBER":
        if not payload.leader_id:
            raise HTTPException(status_code=422, detail="Member phải thuộc một Leader")
        leader_id = parse_uuid(payload.leader_id, "Leader ID")
        leader = db.get(User, leader_id)
        if leader is None or leader.role != "LEADER" or not leader.is_active:
            raise HTTPException(status_code=422, detail="Leader không hợp lệ")

    user = User(
        username=username,
        password_hash=password_hash,
        full_name=payload.full_name.strip(),
        role=payload.role,
        leader_id=leader_id,
        can_add_accounts=True if payload.role in {"BOSS", "MANAGER"} else payload.can_add_accounts,
        can_delete_accounts=True if payload.role in {"BOSS", "MANAGER"} else payload.can_delete_accounts,
        can_run_checks=True if payload.role in {"BOSS", "MANAGER"} else payload.can_run_checks,
        show_in_org_chart=payload.show_in_org_chart,
        is_system_owner=False,
    )
    db.add(user)
    try:
        write_audit(
            db,
            request,
            current,
            "USER_CREATED",
            "USER",
            user.id,
            {"username": user.username, "role": user.role},
        )
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại") from exc
    await ws_manager.broadcast("directory_updated", {"user_id": str(user.id)})
    return {"user": serialize_user(db, user)}


@app.patch("/api/users/{user_id}")
async def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    target = db.get(User, parse_uuid(user_id, "User ID"))
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    ensure_can_manage_user(current, target=target)
    values = payload.model_dump(exclude_unset=True)
    if target.is_system_owner and values.get("is_active") is False:
        raise HTTPException(status_code=422, detail="Không thể khóa tài khoản BOSS chính")
    if "leader_id" in values:
        if target.role != "MEMBER":
            raise HTTPException(status_code=422, detail="Chỉ Member mới được gán Leader")
        if not values["leader_id"]:
            raise HTTPException(status_code=422, detail="Member bắt buộc phải có Leader")
        leader = db.get(User, parse_uuid(values.pop("leader_id"), "Leader ID"))
        if leader is None or leader.role != "LEADER" or not leader.is_active:
            raise HTTPException(status_code=422, detail="Leader không hợp lệ")
        target.leader_id = leader.id
    for field, value in values.items():
        setattr(target, field, value.strip() if field == "full_name" and value else value)
    revoked_ids: list[str] = []
    if values.get("is_active") is False:
        revoked_ids = revoke_user_sessions(db, target.id, "ACCOUNT_DISABLED")
    try:
        write_audit(
            db,
            request,
            current,
            "USER_UPDATED",
            "USER",
            target.id,
            {"fields": sorted(values)},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc.orig)) from exc
    if revoked_ids:
        await ws_manager.send_sessions(
            set(revoked_ids), "session_revoked", {"reason": "Tài khoản đã bị khóa"}
        )
    await ws_manager.broadcast("directory_updated", {"user_id": str(target.id)})
    await ws_manager.send_users(
        {str(target.id)}, "permissions_updated", {"user_id": str(target.id)}
    )
    return {"user": serialize_user(db, target)}


@app.post("/api/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    target = db.get(User, parse_uuid(user_id, "User ID"))
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    ensure_can_manage_user(current, target=target)
    if target.id == current.id:
        raise HTTPException(status_code=422, detail="Hãy dùng chức năng Đổi mật khẩu cho tài khoản hiện tại")
    try:
        target.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target.password_changed_at = utcnow()
    revoked_ids = revoke_user_sessions(db, target.id, "PASSWORD_RESET")
    write_audit(db, request, current, "PASSWORD_RESET", "USER", target.id)
    db.commit()
    if revoked_ids:
        await ws_manager.send_sessions(
            set(revoked_ids), "session_revoked", {"reason": "BOSS đã đặt lại mật khẩu"}
        )
    return {"success": True}

@app.post("/api/users/{user_id}/avatar")
async def upload_user_avatar(
    user_id: str,
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    target = db.get(User, parse_uuid(user_id, "User ID"))

    if target is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )

    # Mỗi người chỉ được đổi ảnh của mình.
    # BOSS được đổi ảnh cho tất cả mọi người.
    if current.role not in {"BOSS", "MANAGER"} and current.id != target.id:
        if (
            current.role == "MANAGER"
            and target.role == "BOSS"
            and current.id != target.id
        ):
            raise HTTPException(
                status_code=403,
                detail="QUẢN LÝ không được thay đổi tài khoản BOSS",
            )
        raise HTTPException(
            status_code=403,
            detail="Bạn không được đổi ảnh của người khác"
        )
    if target.role == "BOSS" and current.id != target.id:
        ensure_can_manage_user(current, target=target)

    allowed_formats = {"JPEG", "PNG", "WEBP"}
    if avatar.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(
            status_code=422,
            detail="Chỉ chấp nhận ảnh JPG, PNG hoặc WebP"
        )

    # Đọc tối đa 2 MB + 1 byte để kiểm tra vượt giới hạn.
    image_data = await avatar.read(2 * 1024 * 1024 + 1)

    if not image_data:
        raise HTTPException(
            status_code=422,
            detail="File ảnh trống"
        )

    if len(image_data) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Ảnh đại diện không được vượt quá 2 MB"
        )

    # Verify actual image bytes, resize and strip metadata before public storage.
    try:
        with Image.open(BytesIO(image_data)) as source:
            if source.format not in allowed_formats:
                raise ValueError("unsupported format")
            if source.width * source.height > 20_000_000:
                raise ValueError("image dimensions too large")
            source.load()
            source.thumbnail((512, 512), Image.Resampling.LANCZOS)
            normalized = source.convert("RGBA" if "A" in source.getbands() else "RGB")
            output = BytesIO()
            normalized.save(output, format="WEBP", quality=86, method=4)
            image_data = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=422, detail="Nội dung file không phải ảnh hợp lệ")

    if (
        not settings.supabase_url
        or not settings.supabase_service_role_key
    ):
        raise HTTPException(
            status_code=503,
            detail="Server chưa cấu hình Supabase Storage"
        )

    object_name = f"{target.id}.webp"

    upload_url = (
        f"{settings.supabase_url}"
        f"/storage/v1/object/avatars/{object_name}"
    )

    storage_request = UrlRequest(
        upload_url,
        data=image_data,
        method="POST",
        headers={
            "Authorization": (
                f"Bearer {settings.supabase_service_role_key}"
            ),
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "image/webp",
            "x-upsert": "true",
        },
    )

    try:
        with urlopen(storage_request, timeout=30) as response:
            response.read()
    except HTTPError as exc:
        error_content = exc.read().decode(
            "utf-8",
            errors="ignore"
        )

        logger.error(
            "Supabase Storage HTTP %s: %s",
            exc.code,
            error_content,
        )

        raise HTTPException(
            status_code=502,
            detail="Supabase không nhận được ảnh"
        ) from exc
    except URLError as exc:
        logger.error("Supabase Storage error: %s", exc)

        raise HTTPException(
            status_code=502,
            detail="Không kết nối được Supabase Storage"
        ) from exc

    # Thêm phiên bản vào URL để trình duyệt không giữ ảnh cũ.
    avatar_url = (
        f"{settings.supabase_url}"
        f"/storage/v1/object/public/avatars/{object_name}"
        f"?v={int(time.time())}"
    )

    target.avatar_url = avatar_url
    write_audit(db, request, current, "AVATAR_UPDATED", "USER", target.id)
    db.commit()
    db.refresh(target)
    await ws_manager.broadcast("directory_updated", {"user_id": str(target.id)})

    return {
        "success": True,
        "user": serialize_user(db, target),
    }

@app.get("/api/machines")
def list_machines(
    owner_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    owner_uuid = parse_uuid(owner_id, "Owner ID")
    ensure_can_view_user(db, current, owner_uuid)
    machines = db.scalars(
        select(Machine).where(Machine.owner_id == owner_uuid).order_by(Machine.machine_number)
    )
    return {"machines": [serialize_machine(db, machine) for machine in machines]}


@app.post("/api/machines")
async def create_machine(
    payload: MachineCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    owner_id = parse_uuid(payload.owner_id, "Owner ID")
    owner = db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise HTTPException(status_code=404, detail="Không tìm thấy người sở hữu")
    ensure_can_manage_accounts(db, current, owner_id, "can_add_accounts")

    machine_count = db.scalar(
        select(func.count(Machine.id)).where(Machine.owner_id == owner_id)
    ) or 0

    if machine_count >= 10:
        raise HTTPException(
            status_code=400,
            detail="Mỗi người chỉ được thêm tối đa 10 máy"
        )

    machine = Machine(
        owner_id=owner_id,
        machine_number=payload.machine_number,
        note=payload.note
    )
    db.add(machine)
    try:
        db.flush()
        write_audit(
            db, request, current, "MACHINE_CREATED", "MACHINE", machine.id,
            {"owner_id": str(owner_id), "machine_number": machine.machine_number},
        )
        db.commit()
        db.refresh(machine)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Số máy này đã tồn tại") from exc
    await ws_manager.broadcast("data_updated", {"source": "machine", "owner_id": str(owner_id)})
    return {"machine": serialize_machine(db, machine)}


@app.delete("/api/machines/{machine_id}")
async def delete_machine(
    machine_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    machine_uuid = parse_uuid(machine_id, "Machine ID")
    machine = db.get(Machine, machine_uuid)
    if machine is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy máy")
    ensure_can_manage_accounts(
    db, current, machine.owner_id, "can_delete_accounts"
)
    owner_id = machine.owner_id
    machine_number = machine.machine_number
    write_audit(
        db, request, current, "MACHINE_DELETED", "MACHINE", machine.id,
        {"owner_id": str(owner_id), "machine_number": machine_number},
    )
    db.delete(machine)
    db.commit()
    await ws_manager.broadcast("data_updated", {"source": "machine", "owner_id": str(owner_id)})
    return {"success": True, "message": "Đã xóa máy và toàn bộ kênh thuộc máy"}


@app.post("/api/accounts/bulk")
async def add_accounts_bulk(
    payload: BulkAccountsRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    machine_id = parse_uuid(payload.machine_id, "Machine ID")
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy máy")
    ensure_can_manage_accounts(
    db, current, machine.owner_id, "can_add_accounts"
)

    occupied = set(db.scalars(select(TikTokAccount.slot_number).where(TikTokAccount.machine_id == machine.id)))
    available = deque(slot for slot in range(1, 11) if slot not in occupied)
    seen: set[str] = set()
    added: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for raw in payload.items:
        username = TikTokChecker.clean_username(raw)
        normalized = username.lower()
        if not username:
            rejected.append({"input": raw, "reason": "Username không hợp lệ"})
            continue
        if normalized in seen:
            rejected.append({"input": raw, "reason": "Trùng trong danh sách vừa dán"})
            continue
        seen.add(normalized)
        existing = db.execute(
            select(TikTokAccount, Machine, User)
            .join(Machine, Machine.id == TikTokAccount.machine_id)
            .join(User, User.id == Machine.owner_id)
            .where(TikTokAccount.username_normalized == normalized)
        ).one_or_none()
        if existing:
            _account, _machine, owner = existing
            reason = "Username đã có trong công ty"
            if current.role == "BOSS":
                reason += f" và thuộc {owner.full_name}"
            rejected.append({"input": raw, "reason": reason})
            continue
        if not available:
            rejected.append({"input": raw, "reason": "Máy đã đủ 10 kênh"})
            continue
        account = TikTokAccount(
            machine_id=machine.id,
            slot_number=available.popleft(),
            username=username,
            status="UNCHECKED",
            recent_videos=[],
        )
        db.add(account)
        db.flush()
        added.append({"id": str(account.id), "username": username, "slot_number": account.slot_number})
    try:
        write_audit(
            db, request, current, "ACCOUNTS_ADDED", "MACHINE", machine.id,
            {"owner_id": str(machine.owner_id), "count": len(added)},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Có username hoặc vị trí kênh bị trùng") from exc
    await ws_manager.broadcast(
        "data_updated", {"source": "accounts", "owner_id": str(machine.owner_id)}
    )
    return {"added": added, "rejected": rejected}


@app.get("/api/accounts")
def list_accounts(
    owner_id: str,
    machine_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    query = (
        select(TikTokAccount, Machine, User)
        .join(Machine, Machine.id == TikTokAccount.machine_id)
        .join(User, User.id == Machine.owner_id)
    )
    if owner_id == "ALL":
        allowed_ids = visible_owner_ids(db, current)
        query = query.where(Machine.owner_id.in_(allowed_ids))
    else:
        owner_uuid = parse_uuid(owner_id, "Owner ID")
        ensure_can_view_user(db, current, owner_uuid)
        query = query.where(Machine.owner_id == owner_uuid)
    if machine_id:
        query = query.where(Machine.id == parse_uuid(machine_id, "Machine ID"))
    if status and status != "ALL":
        query = query.where(TikTokAccount.status == status)
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.where(TikTokAccount.username_normalized.ilike(pattern))
    rows = db.execute(query.order_by(Machine.machine_number, TikTokAccount.slot_number)).all()
    return {"accounts": [serialize_account(*row) for row in rows]}


@app.delete("/api/accounts/{account_id}")
async def delete_account(
    account_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    account = db.get(TikTokAccount, parse_uuid(account_id, "Account ID"))
    if account is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh")
    owner_id = machine_owner(db, account.machine_id)
    ensure_can_manage_accounts(db, current, owner_id, "can_delete_accounts")
    username = account.username
    write_audit(
        db, request, current, "ACCOUNT_DELETED", "TIKTOK_ACCOUNT", account.id,
        {"owner_id": str(owner_id), "username": username},
    )
    db.delete(account)
    db.commit()
    await ws_manager.broadcast("data_updated", {"source": "account", "owner_id": str(owner_id)})
    return {"success": True}


@app.patch("/api/accounts/{account_id}/transfer")
async def transfer_account(
    account_id: str,
    payload: TransferAccountRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    if current.role not in {"BOSS", "MANAGER"}:
        raise HTTPException(
            status_code=403,
            detail="Chỉ BOSS hoặc QUẢN LÝ được chuyển kênh",
        )
    account = db.get(TikTokAccount, parse_uuid(account_id, "Account ID"))
    target_machine = db.get(Machine, parse_uuid(payload.machine_id, "Machine ID"))
    if account is None or target_machine is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh hoặc máy đích")
    occupied = db.scalar(select(TikTokAccount.id).where(
        TikTokAccount.machine_id == target_machine.id,
        TikTokAccount.slot_number == payload.slot_number,
        TikTokAccount.id != account.id,
    ))
    if occupied:
        raise HTTPException(status_code=409, detail="Vị trí kênh trên máy đích đã được sử dụng")
    old_owner_id = machine_owner(db, account.machine_id)
    account.machine_id = target_machine.id
    account.slot_number = payload.slot_number
    write_audit(
        db, request, current, "ACCOUNT_TRANSFERRED", "TIKTOK_ACCOUNT", account.id,
        {
            "username": account.username,
            "from_owner_id": str(old_owner_id),
            "to_owner_id": str(target_machine.owner_id),
            "slot_number": payload.slot_number,
        },
    )
    db.commit()
    await ws_manager.broadcast("data_updated", {"source": "account_transfer"})
    return {"success": True}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    owner_ids = visible_owner_ids(db, current)
    rows = db.execute(
        select(TikTokAccount, Machine, User)
        .join(Machine, Machine.id == TikTokAccount.machine_id)
        .join(User, User.id == Machine.owner_id)
        .where(Machine.owner_id.in_(owner_ids))
    ).all() if owner_ids else []
    accounts = [row[0] for row in rows]
    last_checked = max((a.last_checked_at for a in accounts if a.last_checked_at), default=None)
    recent_changes = []
    for account, machine, owner in rows:
        if account.auto_followers is not None and account.previous_auto_followers is not None:
            delta = account.auto_followers - account.previous_auto_followers
            if delta:
                recent_changes.append({
                    "account_id": str(account.id),
                    "owner_id": str(owner.id),
                    "username": account.username,
                    "owner_name": owner.full_name,
                    "machine_number": machine.machine_number,
                    "slot_number": account.slot_number,
                    "before": account.previous_auto_followers,
                    "after": account.auto_followers,
                    "delta": delta,
                    "checked_at": iso(account.auto_checked_at),
                })
    recent_changes.sort(key=lambda item: item["checked_at"] or "", reverse=True)
    return {
        "total": len(accounts),
        "live": sum(a.status == "LIVE" for a in accounts),
        "die": sum(a.status == "DIE" for a in accounts),
        "error": sum(a.status in {"ERROR", "UNCHECKED"} for a in accounts),
        "unchecked": sum(a.status == "UNCHECKED" for a in accounts),
        "new_problem": sum(a.previous_status == "LIVE" and a.status in {"DIE", "ERROR"} for a in accounts),
        "last_checked_at": iso(last_checked),
        "recent_changes": recent_changes[:30],
    }

@app.patch("/api/departments/{department_id}")
async def update_department(
    department_id: str,
    payload: DepartmentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
):
    if current.role not in {"BOSS", "MANAGER"}:
        raise HTTPException(
            status_code=403,
            detail="Bạn không có quyền cấu hình phòng",
        )

    department = db.get(
        Department,
        parse_uuid(department_id, "Department ID"),
    )

    if department is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy phòng",
        )

    department.leader_collaboration_enabled = (
        payload.leader_collaboration_enabled
    )
    department.updated_at = utcnow()

    write_audit(
        db,
        request,
        current,
        "DEPARTMENT_UPDATED",
        "DEPARTMENT",
        department.id,
        {
            "leader_collaboration_enabled":
                department.leader_collaboration_enabled
        },
    )

    db.commit()

    await ws_manager.broadcast(
        "directory_updated",
        {"department_id": str(department.id)},
    )

    return {
        "department": {
            "id": str(department.id),
            "name": department.name,
            "leader_collaboration_enabled":
                department.leader_collaboration_enabled,
        }
    }

@app.get("/api/search")
def global_search(
    q: str,
    db: Session = Depends(get_db),
    _boss: User = Depends(require_roles("BOSS", "MANAGER")),
):
    clean = TikTokChecker.clean_username(q) or q.strip().lstrip("@").lower()
    rows = db.execute(
        select(TikTokAccount, Machine, User)
        .join(Machine, Machine.id == TikTokAccount.machine_id)
        .join(User, User.id == Machine.owner_id)
        .where(TikTokAccount.username_normalized.ilike(f"%{clean.lower()}%"))
        .order_by(TikTokAccount.username_normalized)
        .limit(30)
    ).all()
    results = []
    for account, machine, owner in rows:
        leader_name = None
        if owner.leader_id:
            leader = db.get(User, owner.leader_id)
            leader_name = leader.full_name if leader else None
        item = serialize_account(account, machine, owner)
        item["leader_name"] = leader_name
        results.append(item)
    return {"results": results}


@app.post("/api/check-runs")
async def start_check(
    payload: CheckStartRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
    current_session: UserSession = Depends(get_current_session),
):
    manager = get_job_manager(request)
    target_id = parse_uuid(payload.target_user_id, "Target User ID") if payload.target_user_id else None
    selected_ids = [parse_uuid(value, "Account ID") for value in payload.account_ids]

    if payload.scope_type == "USER":
        if target_id is None:
            raise HTTPException(status_code=422, detail="Thiếu người cần check")
        ensure_can_start_manual_check(db, current, target_id)
    elif payload.scope_type == "SELECTED":
        if not selected_ids:
            raise HTTPException(status_code=422, detail="Chưa chọn kênh")
        owner_ids = set(db.scalars(
            select(Machine.owner_id)
            .join(TikTokAccount, TikTokAccount.machine_id == Machine.id)
            .where(TikTokAccount.id.in_(selected_ids))
        ))
        if len(owner_ids) != 1 and current.role not in {"BOSS", "MANAGER"}:
            raise HTTPException(status_code=403, detail="Mỗi lần chỉ được check kênh của một người")
        for owner_id in owner_ids:
            ensure_can_start_manual_check(db, current, owner_id)
    elif payload.scope_type == "LEADER_GROUP":
        if current.role not in {"BOSS", "MANAGER"} or target_id is None:
            raise HTTPException(status_code=403, detail="Chỉ BOSS được check cả nhóm Leader")
        target = db.get(User, target_id)
        if target is None or target.role != "LEADER":
            raise HTTPException(status_code=422, detail="Leader không hợp lệ")
    elif payload.scope_type == "COMPANY":
        if current.role not in {"BOSS", "MANAGER"}:
            raise HTTPException(status_code=403, detail="Chỉ BOSS được check toàn công ty")

    try:
        run = manager.start_job(
            requested_by=current.id,
            requested_session_id=current_session.id,
            trigger_type="MANUAL",
            scope_type=payload.scope_type,
            target_user_id=target_id,
            selected_ids=selected_ids,
            priority=0 if current.role in {"BOSS", "MANAGER"} else 10,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_audit(
        db,
        request,
        current,
        "CHECK_STARTED",
        "CHECK_RUN",
        run["id"],
        {"scope_type": payload.scope_type, "target_user_id": payload.target_user_id},
    )
    db.commit()
    return {"run": run}


@app.get("/api/check-runs/current")
def current_check_run(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
):
    query = select(CheckRun).where(
        CheckRun.status.in_(("QUEUED", "RUNNING")),
        CheckRun.requested_session_id == current_session.id,
    )
    if current.role in {"BOSS", "MANAGER"}:
        query = select(CheckRun).where(
            CheckRun.status.in_(("QUEUED", "RUNNING")),
            or_(CheckRun.requested_session_id == current_session.id, CheckRun.trigger_type == "SCHEDULED"),
        )
    runs = db.scalars(query.order_by(CheckRun.created_at.desc()))
    return {"runs": [JobManager.serialize_run(run) for run in runs]}


@app.post("/api/check-runs/{run_id}/stop")
async def stop_check_run(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
    current_session: UserSession = Depends(get_current_session),
):
    run_uuid = parse_uuid(run_id, "Run ID")
    run = db.get(CheckRun, run_uuid)
    if run is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    if run.trigger_type == "MANUAL" and run.requested_session_id != current_session.id:
        raise HTTPException(status_code=403, detail="Chỉ thiết bị khởi tạo mới được dừng job này")
    if run.trigger_type == "SCHEDULED" and current.role != "BOSS":
        raise HTTPException(status_code=403, detail="Chỉ BOSS được dừng lịch check tự động")
    if not get_job_manager(request).stop_job(run_uuid):
        raise HTTPException(status_code=409, detail="Job đã kết thúc")
    write_audit(db, request, current, "CHECK_STOP_REQUESTED", "CHECK_RUN", run.id)
    db.commit()
    return {"success": True}


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    row = db.get(AppSettings, 1)
    if row is None:
        raise HTTPException(status_code=500, detail="Thiếu app_settings")
    public = {
        "auto_check_enabled": row.auto_check_enabled,
        "check_interval_minutes": row.check_interval_minutes,
        "timezone": row.timezone,
        "next_auto_check_at": iso(row.next_auto_check_at),
        "last_auto_check_at": iso(row.last_auto_check_at),
        "follower_change_threshold": row.follower_change_threshold,
        "voice_notifications_enabled": row.voice_notifications_enabled,
    }
    if current.role == "BOSS":
        public.update({
            "max_total_workers": row.max_total_workers,
            "max_workers_per_job": row.max_workers_per_job,
            "request_delay_seconds": float(row.request_delay_seconds),
            "request_timeout_seconds": row.request_timeout_seconds,
            "retry_count": row.retry_count,
            "dead_confirmation_attempts": row.dead_confirmation_attempts,
            "in_app_notifications_enabled": row.in_app_notifications_enabled,
        })
    return {"settings": public}


@app.patch("/api/settings")
async def update_settings(
    payload: SettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    boss: User = Depends(require_roles("BOSS", "MANAGER")),
    _csrf: User = Depends(csrf_protect),
):
    row = db.get(AppSettings, 1)
    if row is None:
        raise HTTPException(status_code=500, detail="Thiếu app_settings")
    values = payload.model_dump(exclude_unset=True)
    new_total = int(values.get("max_total_workers", row.max_total_workers))
    new_per_job = int(values.get("max_workers_per_job", row.max_workers_per_job))
    if new_per_job > new_total:
        raise HTTPException(status_code=422, detail="Luồng mỗi job không được lớn hơn tổng luồng")
    was_enabled = row.auto_check_enabled
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_by = boss.id
    if row.auto_check_enabled and (not was_enabled or row.next_auto_check_at is None):
        row.next_auto_check_at = utcnow() + timedelta(minutes=row.check_interval_minutes)
    elif not row.auto_check_enabled:
        row.next_auto_check_at = None
    write_audit(db, request, boss, "SETTINGS_UPDATED", "APP_SETTINGS", 1, {"fields": sorted(values)})
    db.commit()
    await ws_manager.broadcast("settings_updated", {"updated_by": str(boss.id)})
    return {
        "success": True,
        "message": "Đã lưu. Thay đổi tổng worker có hiệu lực hoàn toàn sau khi restart server.",
    }


@app.get("/api/organization")
def organization(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    users = list(
        db.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.show_in_org_chart.is_(True),
                User.is_technical_account.is_(False),
            )
            .order_by(User.role, User.full_name)
        )
    )

    department_ids = {
        user.department_id
        for user in users
        if user.department_id is not None
    }

    departments = []

    if department_ids:
        rows = list(
            db.scalars(
                select(Department)
                .where(
                    Department.id.in_(department_ids),
                    Department.is_active.is_(True),
                )
                .order_by(Department.name)
            )
        )

        departments = [
            {
                "id": str(item.id),
                "name": item.name,

                # Không công khai cấu hình quyền cho Member.
                "leader_collaboration_enabled":
                    item.leader_collaboration_enabled
                    if current.role in {"BOSS", "MANAGER", "LEADER"}
                    else False,
            }
            for item in rows
        ]

    return {
        "users": [
            serialize_user(db, user)
            for user in users
        ],
        "departments": departments,
    }


@app.get("/api/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
):
    query = select(UserSession)
    if current.role not in {"BOSS", "MANAGER"}:
        query = query.where(UserSession.user_id == current.id)
    rows = db.scalars(query.order_by(UserSession.created_at.desc()).limit(100))
    return {"sessions": [serialize_session(db, row, current_session.id) for row in rows]}


@app.delete("/api/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(csrf_protect),
    current_session: UserSession = Depends(get_current_session),
):
    target = db.get(UserSession, parse_uuid(session_id, "Session ID"))
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên đăng nhập")
    target_user = db.get(User, target.user_id)
    if (
        target_user
        and target_user.role == "BOSS"
        and target.user_id != current.id
        and not current.is_system_owner
    ):
        raise HTTPException(
            status_code=403,
            detail="Không được thu hồi phiên đăng nhập của BOSS",
        )
    if target.user_id != current.id and current.role not in {"BOSS", "MANAGER"}:
        raise HTTPException(status_code=403, detail="Không được đăng xuất phiên của người khác")
    if target_user and target_user.is_system_owner and target.user_id != current.id:
        raise HTTPException(status_code=403, detail="Không được đăng xuất BOSS chính")
    if target.revoked_at is None:
        target.revoked_at = utcnow()
        target.revoked_reason = "FORCE_LOGOUT" if target.id != current_session.id else "LOGOUT"
    write_audit(db, request, current, "SESSION_REVOKED", "SESSION", target.id)
    is_current = target.id == current_session.id
    if is_current:
        request.session.clear()
    db.commit()
    await ws_manager.send_sessions(
        {str(target.id)}, "session_revoked", {"reason": "Phiên đăng nhập đã được thu hồi"}
    )
    return {"success": True, "current_session_revoked": is_current}


@app.get("/api/audit-logs")
def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _boss: User = Depends(require_roles("BOSS", "MANAGER")),
):
    safe_limit = max(1, min(limit, 200))
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(safe_limit))
    result = []
    for row in rows:
        actor = db.get(User, row.actor_user_id) if row.actor_user_id else None
        result.append({
            "id": row.id,
            "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
            "actor_name": actor.full_name if actor else "Hệ thống",
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "details": row.details or {},
            "ip_address": row.ip_address,
            "created_at": iso(row.created_at),
        })
    return {"logs": result}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session = websocket.scope.get("session", {})
    user_id = session.get("user_id")
    session_id = session.get("session_id")
    if not user_id or not session_id:
        await websocket.close(code=4401)
        return
    try:
        with db_session() as db:
            user = db.get(User, uuid.UUID(user_id))
            active_session = db.get(UserSession, uuid.UUID(session_id))
            if (
                user is None
                or not user.is_active
                or active_session is None
                or active_session.user_id != user.id
                or active_session.revoked_at is not None
                or active_session.expires_at <= utcnow()
            ):
                await websocket.close(code=4401)
                return
    except Exception:
        await websocket.close(code=1011)
        return
    await ws_manager.connect(session_id, user_id, websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "data": {"user_id": user_id, "session_id": session_id},
        }))
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                with db_session() as db:
                    active_session = db.get(UserSession, uuid.UUID(session_id))
                    if active_session is None or active_session.revoked_at is not None:
                        await websocket.close(code=4401)
                        return
                    active_session.last_seen_at = utcnow()
                await websocket.send_text('{"type":"pong","data":{}}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(session_id, websocket)
    finally:
        await ws_manager.disconnect(session_id, websocket)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if (REACT_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(REACT_DIST_DIR / "assets")), name="react-assets")


@app.get("/legacy", response_class=HTMLResponse)
def legacy():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def root():
    react_index = REACT_DIST_DIR / "index.html"
    if react_index.exists():
        return HTMLResponse(react_index.read_text(encoding="utf-8"))
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/{full_path:path}", response_class=HTMLResponse)
def frontend(full_path: str):
    if full_path.startswith(("api/", "ws")):
        raise HTTPException(status_code=404, detail="Không tìm thấy API")
    react_index = REACT_DIST_DIR / "index.html"
    if react_index.exists():
        return HTMLResponse(react_index.read_text(encoding="utf-8"))
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", str(settings.port))),
        reload=False,
    )
