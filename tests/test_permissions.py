import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import User
from app.permissions import can_manage_accounts
from server import ensure_can_manage_user


def make_user(
    role: str,
    *,
    system_owner: bool = False,
    leader_id: uuid.UUID | None = None,
) -> User:
    return User(
        id=uuid.uuid4(),
        username=f"user-{uuid.uuid4().hex[:8]}",
        password_hash="$argon2id$test-placeholder-hash",
        full_name="Test User",
        role=role,
        leader_id=leader_id,
        is_system_owner=system_owner,
        show_in_org_chart=True,
        is_technical_account=False,
        is_active=True,
        can_add_accounts=True,
        can_delete_accounts=True,
        can_run_checks=True,
    )


def test_leader_can_manage_own_channels():
    leader = make_user("LEADER")
    db = MagicMock(spec=Session)

    assert can_manage_accounts(
        db,
        leader,
        leader.id,
        "can_add_accounts",
    ) is True


def test_leader_can_manage_direct_member():
    leader = make_user("LEADER")
    member = make_user(
        "MEMBER",
        leader_id=leader.id,
    )

    db = MagicMock(spec=Session)
    db.scalar.return_value = member.id

    assert can_manage_accounts(
        db,
        leader,
        member.id,
        "can_add_accounts",
    ) is True


def test_leader_cannot_manage_member_of_another_team():
    leader = make_user("LEADER")
    other_member = make_user(
        "MEMBER",
        leader_id=uuid.uuid4(),
    )

    db = MagicMock(spec=Session)
    db.scalar.return_value = None

    assert can_manage_accounts(
        db,
        leader,
        other_member.id,
        "can_delete_accounts",
    ) is False


def test_member_permission_flag_is_enforced():
    member = make_user("MEMBER")
    member.can_delete_accounts = False

    db = MagicMock(spec=Session)

    assert can_manage_accounts(
        db,
        member,
        member.id,
        "can_delete_accounts",
    ) is False


def test_member_cannot_manage_another_member():
    member = make_user("MEMBER")
    other_member = make_user("MEMBER")

    db = MagicMock(spec=Session)

    assert can_manage_accounts(
        db,
        member,
        other_member.id,
        "can_add_accounts",
    ) is False


def test_boss_can_manage_company_accounts():
    boss = make_user("BOSS")
    member = make_user("MEMBER")

    db = MagicMock(spec=Session)

    assert can_manage_accounts(
        db,
        boss,
        member.id,
        "can_delete_accounts",
    ) is True


def test_manager_can_manage_company_accounts():
    manager = make_user("MANAGER")
    member = make_user("MEMBER")

    db = MagicMock(spec=Session)

    assert can_manage_accounts(
        db,
        manager,
        member.id,
        "can_add_accounts",
    ) is True


def test_only_system_owner_can_manage_another_boss():
    system_owner = make_user(
        "BOSS",
        system_owner=True,
    )
    secondary_boss = make_user("BOSS")

    ensure_can_manage_user(
        system_owner,
        target=secondary_boss,
    )

    with pytest.raises(HTTPException) as exc:
        ensure_can_manage_user(
            secondary_boss,
            target=system_owner,
        )

    assert exc.value.status_code == 403


def test_secondary_boss_can_manage_member():
    secondary_boss = make_user("BOSS")
    member = make_user("MEMBER")

    ensure_can_manage_user(
        secondary_boss,
        target=member,
    )