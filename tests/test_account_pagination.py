"""Exercise real SQL/ORM filtering with an isolated SQLite test schema.

Production uses PostgreSQL. Only DDL types/defaults are adapted here; endpoint
queries, authorization, serializers and deferred loading are the real ones.
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, JSON, MetaData, Table, create_engine, event, insert
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session

from app.models import Department, Machine, TikTokAccount, User
from app.read_cache import invalidate_reads
from server import account_detail, list_accounts, dashboard


@pytest.fixture
def data():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for model in (Department, User, Machine, TikTokAccount):
        Table(model.__tablename__, metadata, *[
            Column(c.name, JSON() if isinstance(c.type, (ARRAY, JSONB)) else c.type,
                   primary_key=c.primary_key, nullable=True)
            for c in model.__table__.columns
        ])
    metadata.create_all(engine)
    db = Session(engine)
    owner_id, other_id = uuid.uuid4(), uuid.uuid4()
    for owner, role in ((owner_id, "BOSS"), (other_id, "MEMBER")):
        db.execute(insert(User), {"id": owner, "username": str(owner), "full_name": role,
                                "role": role, "is_active": True, "password_hash": "not-a-secret"})
    machine_id = uuid.uuid4()
    db.execute(insert(Machine), {"id": machine_id, "owner_id": owner_id,
                                "machine_number": 1, "machine_type": "NORMAL"})
    ids = []
    for i in range(125):
        account_id = uuid.uuid4()
        ids.append(account_id)
        db.execute(insert(TikTokAccount), {
            "id": account_id, "machine_id": machine_id, "slot_number": i + 1,
            "username": f"channel{i:03}", "username_normalized": f"channel{i:03}",
            "followers": i, "previous_followers": 0, "status": "LIVE" if i % 2 else "ERROR",
            "recent_videos": [{"id": str(i), "desc": "v" * 1000}], "is_monetized": False,
        })
    db.commit()
    invalidate_reads()
    yield db, db.get(User, owner_id), db.get(User, other_id), ids, engine
    db.close()
    engine.dispose()


def query(db, actor, owner_id, **kwargs):
    return list_accounts(owner_id=str(owner_id), page=kwargs.pop("page", 1),
                         page_size=50, db=db, current=actor, **kwargs)


def test_pages_cover_all_accounts_once_and_keep_full_scope_summary(data):
    db, boss, _, ids, engine = data
    statements = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, sql, *a: statements.append(sql))
    pages = [query(db, boss, boss.id, page=p) for p in (1, 2, 3)]
    assert [len(page["accounts"]) for page in pages] == [50, 50, 25]
    assert {a["id"] for page in pages for a in page["accounts"]} == set(map(str, ids))
    assert all(page["summary"]["total"] == 125 for page in pages)
    assert pages[0]["accounts"][0]["followers"] == 124
    assert all("recent_videos" not in sql for sql in statements)
    assert all(a["recent_videos"] == [] for page in pages for a in page["accounts"])
    detail = account_detail(str(ids[0]), db, boss)
    assert detail["account"]["recent_videos"][0]["desc"] == "v" * 1000


def test_filters_apply_before_pagination(data):
    db, boss, _, _, _ = data
    result = query(db, boss, boss.id, status="LIVE", page=2)
    assert result["total"] == 62
    assert len(result["accounts"]) == 12
    assert result["summary"]["total"] == 125
    assert all(a["status"] == "LIVE" for a in result["accounts"])
    result = query(db, boss, boss.id, search="channel12")
    assert result["total"] == 5


def test_member_cannot_read_another_owner_or_video(data):
    db, boss, member, ids, _ = data
    with pytest.raises(HTTPException) as denied:
        query(db, member, boss.id)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException):
        account_detail(str(ids[0]), db, member)
    result = query(db, member, "ALL")
    assert result["total"] == 0


def test_dashboard_aggregates_and_masks_other_owners(data):
    db, boss, member, _, _ = data
    result = dashboard(db, boss)
    assert result["total"] == 125
    assert result["live"] == 62
    assert result["error"] == 63
    assert sum(result["composition"].values()) == 125
    assert len(result["breakthrough_channels"]) == 5
    other = dashboard(db, member)
    assert other["total"] == 0
    assert all("*" in channel["username"] for channel in other["breakthrough_channels"])
