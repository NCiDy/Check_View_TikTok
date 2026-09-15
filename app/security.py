import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserSession


password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")


def hash_password(password: str) -> str:
    validate_password(password)
    return password_hasher.hash(password)


def validate_password(password: str) -> None:
    if len(password) < 8 or len(password) > 128:
        raise ValueError("Mật khẩu phải có từ 8 đến 128 ký tự")


def validate_login_username(username: str) -> str:
    clean = username.strip()
    if not USERNAME_PATTERN.fullmatch(clean):
        raise ValueError("Tên đăng nhập gồm 3-50 ký tự: chữ, số, _, . hoặc -")
    return clean


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    try:
        valid = password_hasher.verify(password_hash, password)
        replacement = password_hasher.hash(password) if password_hasher.check_needs_rehash(password_hash) else None
        return bool(valid), replacement
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, None


SESSION_LIFETIME = timedelta(hours=12)
SESSION_TOUCH_INTERVAL = timedelta(seconds=60)


def start_user_session(
    request: Request,
    db: Session,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, UserSession, list[str]]:
    """Create the only active session for a user and revoke older devices."""
    now = datetime.now(timezone.utc)
    # Serialize simultaneous logins for the same account before touching the
    # partial unique index. The project uses PostgreSQL/Supabase exclusively.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"user-session:{user.id}"},
    )
    active_sessions = list(
        db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
            .order_by(UserSession.created_at.desc(), UserSession.id.desc())
        )
    )
    
    max_sessions = max(1, min(int(user.max_active_sessions or 1), 5))
    
    # Giữ lại số phiên mới nhất theo giới hạn.
    # Chừa một slot cho phiên sắp tạo.
    sessions_to_revoke = active_sessions[max_sessions - 1:]
    
    revoked_ids: list[str] = []
    
    for active in sessions_to_revoke:
        active.revoked_at = now
        active.revoked_reason = "SESSION_LIMIT_EXCEEDED"
        revoked_ids.append(str(active.id))
    
    if sessions_to_revoke:
        db.flush()

    csrf_token = secrets.token_urlsafe(32)
    user_session = UserSession(
        user_id=user.id,
        ip_address=(ip_address or "")[:100] or None,
        user_agent=(user_agent or "")[:500] or None,
        expires_at=now + SESSION_LIFETIME,
    )
    db.add(user_session)
    db.flush()
    request.session.clear()
    request.session.update(
        {
            "user_id": str(user.id),
            "session_id": str(user_session.id),
            "csrf_token": csrf_token,
        }
    )
    return csrf_token, user_session, revoked_ids


def end_user_session(request: Request, db: Session, reason: str = "LOGOUT") -> str | None:
    raw_session_id = request.session.get("session_id")
    if raw_session_id:
        try:
            user_session = db.get(UserSession, uuid.UUID(str(raw_session_id)))
        except (ValueError, TypeError):
            user_session = None
        if user_session is not None and user_session.revoked_at is None:
            user_session.revoked_at = datetime.now(timezone.utc)
            user_session.revoked_reason = reason[:100]
    request.session.clear()
    return str(raw_session_id) if raw_session_id else None


def revoke_user_sessions(
    db: Session,
    user_id: uuid.UUID,
    reason: str,
    except_session_id: uuid.UUID | None = None,
) -> list[str]:
    query = select(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    )
    if except_session_id is not None:
        query = query.where(UserSession.id != except_session_id)
    now = datetime.now(timezone.utc)
    revoked: list[str] = []
    for user_session in db.scalars(query):
        user_session.revoked_at = now
        user_session.revoked_reason = reason[:100]
        revoked.append(str(user_session.id))
    return revoked


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession:
    raw_session_id = request.session.get("session_id")
    raw_user_id = request.session.get("user_id")
    if not raw_session_id or not raw_user_id:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa đăng nhập")
    try:
        session_id = uuid.UUID(str(raw_session_id))
        user_id = uuid.UUID(str(raw_user_id))
    except (ValueError, TypeError):
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ")

    user_session = db.scalar(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
        )
    )
    now = datetime.now(timezone.utc)
    if user_session is None or user_session.revoked_at is not None or user_session.expires_at <= now:
        request.session.clear()
        detail = "Tài khoản đã đăng nhập trên thiết bị khác"
        if user_session is None or user_session.revoked_reason != "SIGNED_IN_ELSEWHERE":
            detail = "Phiên đăng nhập đã hết hạn"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    if now - user_session.last_seen_at >= SESSION_TOUCH_INTERVAL:
        user_session.last_seen_at = now
        db.commit()
    return user_session


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    user_session: UserSession = Depends(get_current_session),
) -> User:
    user = db.scalar(select(User).where(User.id == user_session.user_id, User.is_active.is_(True)))
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản đã bị khóa")
    return user


def csrf_protect(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    expected = str(request.session.get("csrf_token", ""))
    supplied = request.headers.get("X-CSRF-Token", "")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="CSRF token không hợp lệ")
    return current_user


def require_roles(*roles: str) -> Callable:
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này")
        return current_user
    return dependency


def mark_login(db: Session, user: User) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    db.flush()
