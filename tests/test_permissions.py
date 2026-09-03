import uuid

import pytest
from fastapi import HTTPException

from app.models import User
from app.permissions import can_manage_own_accounts
from server import ensure_can_manage_user


def make_user(role: str, *, system_owner: bool = False) -> User:
    return User(
        id=uuid.uuid4(),
        username=f"user-{uuid.uuid4().hex[:8]}",
        password_hash="$argon2id$test-placeholder-hash",
        full_name="Test User",
        role=role,
        is_system_owner=system_owner,
        is_active=True,
        can_add_accounts=True,
        can_delete_accounts=True,
        can_run_checks=True,
    )


def test_leader_can_manage_only_own_channels():
    leader = make_user("LEADER")
    member = make_user("MEMBER")
    assert can_manage_own_accounts(leader, leader.id, "can_add_accounts") is True
    assert can_manage_own_accounts(leader, member.id, "can_add_accounts") is False


def test_member_permission_flag_is_enforced():
    member = make_user("MEMBER")
    member.can_delete_accounts = False
    assert can_manage_own_accounts(member, member.id, "can_delete_accounts") is False


def test_only_system_owner_can_manage_another_boss():
    system_owner = make_user("BOSS", system_owner=True)
    secondary_boss = make_user("BOSS")
    ensure_can_manage_user(system_owner, target=secondary_boss)
    with pytest.raises(HTTPException) as exc:
        ensure_can_manage_user(secondary_boss, target=system_owner)
    assert exc.value.status_code == 403


def test_secondary_boss_can_manage_member():
    secondary_boss = make_user("BOSS")
    member = make_user("MEMBER")
    ensure_can_manage_user(secondary_boss, target=member)
