import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Machine, User


def can_view_user(db: Session, actor: User, target_id: uuid.UUID) -> bool:
    if actor.role == "BOSS" or actor.id == target_id:
        return True
    if actor.role == "LEADER":
        return db.scalar(
            select(User.id).where(
                User.id == target_id,
                User.leader_id == actor.id,
                User.role == "MEMBER",
                User.is_active.is_(True),
            )
        ) is not None
    return False


def ensure_can_view_user(db: Session, actor: User, target_id: uuid.UUID) -> None:
    if not can_view_user(db, actor, target_id):
        raise HTTPException(status_code=403, detail="Không được xem dữ liệu của người này")


def can_manage_accounts(
    db: Session,
    actor: User,
    owner_id: uuid.UUID,
    permission: str,
) -> bool:
    # BOSS quản lý toàn công ty.
    if actor.role == "BOSS":
        return True

    # Tài khoản phải được BOSS cấp đúng quyền.
    if not bool(getattr(actor, permission, False)):
        return False

    # Leader hoặc Member quản lý kênh của chính mình.
    if actor.id == owner_id:
        return True

    # Leader được quản lý Member trực thuộc.
    if actor.role == "LEADER":
        member_id = db.scalar(
            select(User.id).where(
                User.id == owner_id,
                User.role == "MEMBER",
                User.leader_id == actor.id,
                User.is_active.is_(True),
            )
        )
        return member_id is not None

    return False


def ensure_can_manage_accounts(
    db: Session,
    actor: User,
    owner_id: uuid.UUID,
    permission: str,
) -> None:
    if not can_manage_accounts(db, actor, owner_id, permission):
        raise HTTPException(
            status_code=403,
            detail="Bạn không có quyền quản lý máy hoặc kênh của người này",
        )


def machine_owner(db: Session, machine_id: uuid.UUID) -> uuid.UUID:
    owner_id = db.scalar(select(Machine.owner_id).where(Machine.id == machine_id))
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy máy")
    return owner_id


def ensure_can_start_manual_check(db: Session, actor: User, target_id: uuid.UUID) -> None:
    if actor.role != "BOSS" and not actor.can_run_checks:
        raise HTTPException(status_code=403, detail="BOSS đã tắt quyền check của bạn")
    ensure_can_view_user(db, actor, target_id)

