import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User


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


def start_user_session(request: Request, user: User) -> str:
    csrf_token = secrets.token_urlsafe(32)
    request.session.clear()
    request.session.update({"user_id": str(user.id), "csrf_token": csrf_token})
    return csrf_token


def end_user_session(request: Request) -> None:
    request.session.clear()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    raw_id = request.session.get("user_id")
    if not raw_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa đăng nhập")
    try:
        user_id = uuid.UUID(raw_id)
    except (ValueError, TypeError):
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ")

    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
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
    db.commit()

