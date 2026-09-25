import threading
import uuid
from concurrent.futures import Future
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.check_queue import CheckQueue
from app.job_manager import InflightCheck, JobManager, retryable_result, selected_ids_for_run
from app.models import CheckRun, TikTokAccount
from app.read_cache import cached_read, invalidate_reads


def test_priority_queue_and_worker_limit():
    queue = CheckQueue(1)
    gate, started = threading.Event(), threading.Event()
    order = []
    def block():
        started.set()
        assert gate.wait(2)
    first = queue.submit(block)
    assert started.wait(2)
    normal = queue.submit(lambda: order.append("normal"), priority=10)
    manager = queue.submit(lambda: order.append("manager"), priority=0)
    gate.set()
    for future in (first, normal, manager):
        future.result(timeout=2)
    queue.shutdown(wait=True)
    assert order == ["manager", "normal"]


def test_priority_aging_prevents_starvation(monkeypatch):
    import app.check_queue as module
    now = [0.0]
    monkeypatch.setattr(module, "monotonic", lambda: now[0])
    queue = CheckQueue(1)
    gate, started = threading.Event(), threading.Event()
    order = []
    first = queue.submit(lambda: (started.set(), gate.wait(2)))
    assert started.wait(2)
    old = queue.submit(lambda: order.append("old"), priority=10)
    now[0] = 60
    boss = queue.submit(lambda: order.append("boss"), priority=0)
    gate.set()
    for future in (first, old, boss):
        future.result(timeout=2)
    queue.shutdown(wait=True)
    assert order == ["old", "boss"]


@pytest.mark.parametrize("status,http,expected", [
    ("LIVE", 200, False), ("NOT_FOUND", 404, False),
    ("HTTP_ERROR", 403, False), ("HTTP_ERROR", 429, True),
    ("HTTP_ERROR", 503, True), ("TIMEOUT", None, True),
])
def test_retry_classifies_errors(status, http, expected):
    assert retryable_result({"status": status, "status_code": http}) is expected


def test_only_selected_scope_persists_selected_account_ids():
    account_ids = [uuid.uuid4(), uuid.uuid4()]
    assert selected_ids_for_run("SELECTED", account_ids) == account_ids
    assert selected_ids_for_run("USER", account_ids) == []


def test_list_orm_does_not_read_video_json():
    sql = str(select(TikTokAccount).compile(dialect=postgresql.dialect()))
    assert "recent_videos" not in sql


def test_cache_invalidation_and_scope():
    invalidate_reads()
    assert cached_read(("summary", "a"), lambda: 1) == 1
    assert cached_read(("summary", "b"), lambda: 2) == 2
    assert cached_read(("summary", "a"), lambda: 3) == 1
    invalidate_reads()
    assert cached_read(("summary", "a"), lambda: 3) == 3


def test_immediately_finished_future_does_not_deadlock():
    manager = JobManager.__new__(JobManager)
    manager._registry_lock = threading.RLock()
    manager._inflight = {}
    future = Future()
    future.set_result({"status": "LIVE"})
    manager.executor = MagicMock()
    manager.executor.submit.return_value = future
    assert manager._get_inflight(uuid.uuid4(), {}).future is future


@pytest.mark.parametrize("failure", [None, "transient", "permanent", "stop"])
def test_run_reconciles_every_account_and_drains_on_stop(monkeypatch, failure):
    import app.job_manager as module
    manager = JobManager.__new__(JobManager)
    ids = [uuid.uuid4() for _ in range(100)]
    run_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    run = CheckRun(id=run_id, requested_by=uuid.uuid4(), requested_session_id=None,
                   trigger_type="MANUAL", scope_type="USER", target_user_id=None,
                   priority=10, total_accounts=100, status="QUEUED", created_at=now,
                   processed_accounts=0, live_count=0, die_count=0, error_count=0,
                   follower_changed_count=0, new_problem_count=0)
    db = MagicMock()
    db.get.return_value = run
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(module, "db_session", session)
    manager._runtime_settings = lambda _: {
        "max_workers_per_job": 2, "delay": 0, "voice_notifications": False,
    }
    manager._cleanup_old_runs = lambda _: None
    manager._release_inflight = lambda *args: None
    stop = threading.Event()
    manager._stop_events = {run_id: stop}
    attempts, stored, events = {}, set(), []
    manager._emit = lambda name, payload: events.append((name, payload))
    def check(account_id, runtime):
        future = Future()
        future.set_result({"status": "LIVE"})
        return InflightCheck(future)
    manager._get_inflight = check
    def consume(record, account_id, *args):
        attempts[account_id] = attempts.get(account_id, 0) + 1
        if account_id == ids[27] and (failure == "permanent" or (failure == "transient" and attempts[account_id] == 1)):
            raise RuntimeError("temporary database failure")
        assert account_id not in stored
        stored.add(account_id)
        if failure == "stop" and len(stored) == 1:
            stop.set()
        return {"account_id": str(account_id), "status": "LIVE"}
    manager._consume_result = consume
    manager._run_job(run_id, ids, False, run.requested_by, None, stop)
    assert run.processed_accounts == len(stored)
    if failure == "permanent":
        assert run.status == "FAILED"
        assert len(stored) == 99
        assert str(ids[27]) in run.message
        assert events[-1][0] == "job_failed"
    elif failure == "stop":
        assert run.status == "STOPPED"
        assert len(stored) == 2  # Already submitted results are saved.
    else:
        assert run.status == "COMPLETED"
        assert stored == set(ids)
        assert run.processed_accounts == 100


def test_shared_result_is_persisted_once():
    manager = JobManager.__new__(JobManager)
    manager._persist_result = MagicMock(return_value={"status": "LIVE"})
    record = InflightCheck(Future())
    account_id = uuid.uuid4()
    for _ in range(2):
        manager._consume_result(record, account_id, {}, False, None, {})
    assert manager._persist_result.call_count == 1
