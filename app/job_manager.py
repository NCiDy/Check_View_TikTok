from __future__ import annotations

import concurrent.futures
import threading
import time
import uuid
import random
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from core.checker import TikTokChecker
from core.proxy_manager import ProxyManager

from .config import settings as env_settings
from .database import db_session
from .models import AppSettings, CheckRun, Machine, TikTokAccount, User
from .check_queue import CheckQueue
from .read_cache import invalidate_reads


RETRYABLE_STATUSES = {"TIMEOUT", "HTTP_ERROR", "PARSE_ERROR", "EXCEPTION"}
MAX_CHECK_WORKERS = 5
MAX_WORKERS_PER_JOB = 3
logger = logging.getLogger(__name__)


def retryable_result(result):
    status = result.get("status")
    if status == "HTTP_ERROR":
        return result.get("status_code") in {408, 425, 429, 500, 502, 503, 504}
    return status in {"TIMEOUT", "PARSE_ERROR", "EXCEPTION"}


@dataclass
class InflightCheck:
    future: concurrent.futures.Future
    apply_lock: threading.Lock = field(default_factory=threading.Lock)
    latest_applied: bool = False
    auto_applied: bool = False
    cached_outcome: dict[str, Any] | None = None
    consumers: int = 1


class JobManager:
    """Runs independent jobs over one global checker pool.

    Different users can check at the same time. If jobs overlap on one account,
    the network request is shared and the latest database snapshot is written
    exactly once.
    """

    def __init__(self, event_callback: Callable[[str, dict[str, Any]], None] | None = None):
        self.event_callback = event_callback
        self.checker = TikTokChecker()
        self.proxy_manager = ProxyManager()
        self.proxy_manager.set_config(
            env_settings.proxy_mode,
            env_settings.proxy_list,
            env_settings.rotating_proxy_url,
        )
        worker_count = 10
        try:
            with db_session() as db:
                app_config = db.get(AppSettings, 1)
                if app_config:
                    worker_count = int(app_config.max_total_workers)
        except Exception:
            pass
        self.executor = CheckQueue(
            # Reserve database and CPU capacity for interactive web requests.
            max_workers=max(1, min(worker_count, MAX_CHECK_WORKERS)),
        )
        self.job_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=20,
            thread_name_prefix="tiktok-job",
        )
        self._registry_lock = threading.RLock()
        self._inflight: dict[uuid.UUID, InflightCheck] = {}
        self._stop_events: dict[uuid.UUID, threading.Event] = {}

    def shutdown(self) -> None:
        for event in list(self._stop_events.values()):
            event.set()

        self.job_executor.shutdown(
            wait=False,
            cancel_futures=False,
        )

        self.executor.shutdown(
            wait=False,
            cancel_futures=False,
        )

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self.event_callback:
            try:
                self.event_callback(event, payload)
            except Exception:
                pass

    @staticmethod
    def _runtime_settings(db) -> dict[str, Any]:
        row = db.get(AppSettings, 1)
        if row is None:
            raise RuntimeError("Không tìm thấy app_settings id=1")
        return {
            "max_workers_per_job": int(row.max_workers_per_job),
            "delay": float(row.request_delay_seconds),
            "timeout": int(row.request_timeout_seconds),
            "retry_count": int(row.retry_count),
            "dead_confirmations": int(row.dead_confirmation_attempts),
            "follower_threshold": int(row.follower_change_threshold),
            "notifications": bool(row.in_app_notifications_enabled),
            "voice_notifications": bool(row.voice_notifications_enabled),
        }

    @staticmethod
    def _account_ids_for_scope(db, scope_type: str, target_user_id, selected_ids):
        if scope_type == "SELECTED":
            if not selected_ids:
                return []
            return list(db.scalars(
                select(TikTokAccount.id).where(TikTokAccount.id.in_(selected_ids))
            ))

        query = select(TikTokAccount.id).join(
            Machine, Machine.id == TikTokAccount.machine_id
        )
        if scope_type == "USER":
            query = query.where(Machine.owner_id == target_user_id)
        elif scope_type == "LEADER_GROUP":
            member_ids = select(User.id).where(User.leader_id == target_user_id)
            query = query.where(
                Machine.owner_id.in_(member_ids.union(select(User.id).where(User.id == target_user_id)))
            )
        elif scope_type != "COMPANY":
            raise ValueError("Phạm vi check không hợp lệ")
        return list(db.scalars(query.order_by(TikTokAccount.created_at)))

    def start_job(
        self,
        requested_by: uuid.UUID | None,
        trigger_type: str,
        scope_type: str,
        requested_session_id: uuid.UUID | None = None,
        target_user_id: uuid.UUID | None = None,
        selected_ids: list[uuid.UUID] | None = None,
        priority: int = 10,
    ) -> dict[str, Any]:
        selected_ids = selected_ids or []
        if scope_type not in {"USER", "SELECTED"}:
            raise ValueError("Tạm thời chỉ check kênh của từng người")
        with db_session() as db:
            if requested_by:
                # Serialize starts for the same actor, including two sessions.
                db.execute(select(User.id).where(User.id == requested_by).with_for_update())
                active = db.scalar(select(CheckRun.id).where(
                    CheckRun.requested_by == requested_by,
                    CheckRun.status.in_(("QUEUED", "RUNNING")),
                ).limit(1))
                if active:
                    raise ValueError("Bạn đang có một lượt check chưa hoàn thành")
            if len(self._stop_events) >= 20:
                raise ValueError("Hệ thống đang xử lý nhiều lượt check, vui lòng thử lại sau")
            account_ids = self._account_ids_for_scope(
                db, scope_type, target_user_id, selected_ids
            )
            account_ids = list(dict.fromkeys(account_ids))
            if scope_type == "SELECTED" and set(account_ids) != set(selected_ids):
                raise ValueError("Một số kênh đã bị xóa hoặc không còn tồn tại; hãy tải lại danh sách")
            if not account_ids:
                raise ValueError("Phạm vi đã chọn chưa có kênh TikTok")

            run = CheckRun(
                requested_by=requested_by,
                requested_session_id=requested_session_id,
                trigger_type=trigger_type,
                scope_type=scope_type,
                target_user_id=target_user_id,
                selected_account_ids=account_ids,
                priority=priority,
                total_accounts=len(account_ids),
                status="QUEUED",
            )
            db.add(run)
            try:
                db.flush()
            except IntegrityError as exc:
                raise ValueError("Bạn đang có một job check khác chưa hoàn thành") from exc
            run_id = run.id

        stop_event = threading.Event()
        self._stop_events[run_id] = stop_event
        self.job_executor.submit(
            self._run_job,
            run_id,
            account_ids,
            trigger_type == "SCHEDULED",
            requested_by,
            requested_session_id,
            stop_event,
        )
        with db_session() as db:
            created = db.get(CheckRun, run_id)
            return self.serialize_run(created) if created else {
                "id": str(run_id),
                "status": "QUEUED",
                "total_accounts": len(account_ids),
            }

    def stop_job(self, run_id: uuid.UUID) -> bool:
        event = self._stop_events.get(run_id)
        if event is None:
            return False
        event.set()
        return True

    def _get_inflight(self, account_id: uuid.UUID, runtime: dict[str, Any]) -> InflightCheck:
        with self._registry_lock:
            existing = self._inflight.get(account_id)
            if existing and not existing.future.cancelled():
                existing.consumers += 1
                return existing

            future = self.executor.submit(self._network_check, account_id, runtime,
                                          priority=runtime.get("priority", 10))
            record = InflightCheck(future=future)
            self._inflight[account_id] = record

            return record

    def _release_inflight(self, account_id, record):
        # Keep the shared result until all jobs have persisted/consumed it,
        # not merely until the HTTP request finishes.
        with self._registry_lock:
            record.consumers -= 1
            if record.consumers <= 0 and self._inflight.get(account_id) is record:
                self._inflight.pop(account_id, None)

    def _network_check(self, account_id: uuid.UUID, runtime: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        with db_session() as db:
            username = db.scalar(select(TikTokAccount.username).where(TikTokAccount.id == account_id))
            if username is None:
                return {"status": "EXCEPTION", "error": "Kênh đã bị xóa", "account_id": str(account_id)}

        result: dict[str, Any] = {}
        for attempt in range(runtime["retry_count"] + 1):
            proxy = self.proxy_manager.get_proxy()
            result = self.checker.check(username, proxy=proxy, timeout=runtime["timeout"])
            result["attempt"] = attempt + 1
            if not retryable_result(result):
                break
            if attempt < runtime["retry_count"]:
                time.sleep(min(2 ** (attempt + 1), 15) + random.uniform(0, 1))
        result["account_id"] = str(account_id)
        logger.info("checker account=%s status=%s http=%s attempts=%s seconds=%.2f",
                    account_id, result.get("status"), result.get("status_code"),
                    result.get("attempt"), time.monotonic() - started)
        return result

    def _consume_result(
        self,
        record: InflightCheck,
        account_id: uuid.UUID,
        raw: dict[str, Any],
        scheduled: bool,
        requested_by: uuid.UUID | None,
        runtime: dict[str, Any],
    ) -> dict[str, Any]:
        with record.apply_lock:
            if not record.latest_applied:
                outcome = self._persist_result(
                    account_id, raw, scheduled, requested_by, runtime
                )
                record.latest_applied = True
                record.auto_applied = scheduled
                record.cached_outcome = outcome
                invalidate_reads(data_only=True)
                return outcome

            if scheduled and not record.auto_applied:
                outcome = self._persist_auto_only(account_id, raw, runtime)
                record.auto_applied = True
                return outcome

            return record.cached_outcome or {
                "account_id": str(account_id), "status": "ERROR", "error": "Không có kết quả"
            }

    @staticmethod
    def _rotate_auto_snapshot(
        account: TikTokAccount,
        final_status: str,
        raw: dict[str, Any],
        now: datetime,
        threshold: int,
        machine: Machine,
        owner: User,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        old_auto_status = account.auto_status
        old_auto_followers = account.auto_followers
        old_auto_time = account.auto_successful_checked_at

        account.previous_auto_status = account.auto_status
        account.previous_auto_checked_at = account.auto_checked_at
        account.auto_status = final_status
        account.auto_checked_at = now

        if raw.get("status") == "LIVE":
            new_followers = int(raw.get("followers") or 0)
            account.previous_auto_followers = account.auto_followers
            account.previous_auto_successful_checked_at = account.auto_successful_checked_at
            account.auto_followers = new_followers
            account.auto_successful_checked_at = now

            if old_auto_followers is not None:
                delta = new_followers - old_auto_followers
                if abs(delta) >= threshold:
                    direction = "tăng" if delta > 0 else "giảm"
                    minutes = 60
                    if old_auto_time:
                        minutes = max(1, round((now - old_auto_time).total_seconds() / 60))
                    message = (
                        f"Kênh số {account.slot_number}, máy {machine.machine_number} của "
                        f"{owner.full_name} {direction} từ {old_auto_followers:,} lên "
                        f"{new_followers:,} follow trong khoảng {minutes} phút"
                    ).replace(",", ".")
                    alerts.append({
                        "type": "FOLLOWER_CHANGE",
                        "message": message,
                        "delta": delta,
                    })

        if old_auto_status and old_auto_status != final_status:
            if final_status in {"DIE", "ERROR"} or old_auto_status == "DIE":
                alerts.append({
                    "type": "STATUS_CHANGE",
                    "message": (
                        f"Kênh số {account.slot_number}, máy {machine.machine_number} của "
                        f"{owner.full_name} đổi trạng thái {old_auto_status} → {final_status}"
                    ),
                })
        return alerts

    def _persist_result(
        self,
        account_id: uuid.UUID,
        raw: dict[str, Any],
        scheduled: bool,
        requested_by: uuid.UUID | None,
        runtime: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with db_session() as db:
            row = db.execute(
                select(TikTokAccount, Machine, User)
                .join(Machine, Machine.id == TikTokAccount.machine_id)
                .join(User, User.id == Machine.owner_id)
                .where(TikTokAccount.id == account_id)
                .with_for_update(of=TikTokAccount)
            ).one_or_none()
            if row is None:
                return {"account_id": str(account_id), "status": "ERROR", "error": "Kênh đã bị xóa"}
            account, machine, owner = row
            old_status = account.status
            old_followers = account.followers

            account.previous_status = account.status
            account.previous_checked_at = account.last_checked_at
            account.last_checked_at = now
            account.last_checked_by = requested_by

            raw_status = raw.get("status", "EXCEPTION")
            if raw_status == "LIVE":
                account.previous_followers = account.followers
                account.previous_successful_checked_at = account.last_successful_checked_at
                account.followers = int(raw.get("followers") or 0)
                account.following = int(raw.get("following") or 0)
                account.total_likes = int(raw.get("total_likes") or 0)
                account.total_sample_views = int(raw.get("total_sample_views") or 0)
                account.avg_sample_views = int(raw.get("avg_sample_views") or 0)
                account.video_count_sample = int(raw.get("video_count_sample") or 0)
                account.recent_videos = raw.get("videos") or []
                account.nickname = str(raw.get("nickname") or "")
                account.avatar_url = str(raw.get("avatar") or "")
                account.bio = str(raw.get("bio") or "")
                account.is_private = bool(raw.get("is_private"))
                account.is_verified = bool(raw.get("is_verified"))
                account.status = "LIVE"
                account.last_successful_checked_at = now
                account.last_error_code = None
                account.last_error_message = None
                account.last_http_status = raw.get("status_code")
                account.dead_confirmation_count = 0
            elif raw_status == "NOT_FOUND":
                account.dead_confirmation_count = min(account.dead_confirmation_count + 1, 10)
                account.status = (
                    "DIE" if account.dead_confirmation_count >= runtime["dead_confirmations"] else "ERROR"
                )
                account.last_error_code = "NOT_FOUND_PENDING" if account.status == "ERROR" else "NOT_FOUND"
                account.last_error_message = str(raw.get("error") or "Không tìm thấy tài khoản")
                account.last_http_status = raw.get("status_code")
            else:
                account.status = "ERROR"
                account.last_error_code = str(raw_status)
                account.last_error_message = str(raw.get("error") or "Không thể kiểm tra tài khoản")[:1000]
                account.last_http_status = raw.get("status_code")

            alerts: list[dict[str, Any]] = []
            if scheduled:
                alerts = self._rotate_auto_snapshot(
                    account,
                    account.status,
                    raw,
                    now,
                    runtime["follower_threshold"],
                    machine,
                    owner,
                )

            follower_delta = None
            if raw_status == "LIVE" and old_followers is not None:
                follower_delta = account.followers - old_followers
            new_problem = old_status == "LIVE" and account.status in {"DIE", "ERROR"}
            db.flush()
            return {
                "account_id": str(account.id),
                "owner_id": str(owner.id),
                "owner_name": owner.full_name,
                "machine_number": machine.machine_number,
                "slot_number": account.slot_number,
                "username": account.username,
                "status": account.status,
                "is_private": account.is_private,
                "followers": account.followers,
                "previous_followers": account.previous_followers,
                "follower_delta": follower_delta,
                "new_problem": new_problem,
                "error": account.last_error_message,
                "alerts": alerts if runtime["notifications"] else [],
                "last_checked_at": now.isoformat(),
                "nickname": account.nickname,
                "avatar_url": account.avatar_url,
                "following": account.following,
                "total_likes": account.total_likes,
                "total_sample_views": account.total_sample_views,
                "avg_sample_views": account.avg_sample_views,
                "video_count_sample": account.video_count_sample,
                "previous_status": account.previous_status,
                "last_successful_checked_at": account.last_successful_checked_at.isoformat() if account.last_successful_checked_at else None,
                "last_error_code": account.last_error_code,
                "last_error_message": account.last_error_message,
                "is_verified": account.is_verified,
                "leader_id": str(owner.leader_id) if owner.leader_id else None,
            }

    def _persist_auto_only(
        self,
        account_id: uuid.UUID,
        raw: dict[str, Any],
        runtime: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with db_session() as db:
            row = db.execute(
                select(TikTokAccount, Machine, User)
                .join(Machine, Machine.id == TikTokAccount.machine_id)
                .join(User, User.id == Machine.owner_id)
                .where(TikTokAccount.id == account_id)
                .with_for_update(of=TikTokAccount)
            ).one_or_none()
            if row is None:
                return {"account_id": str(account_id), "status": "ERROR", "error": "Kênh đã bị xóa"}
            account, machine, owner = row
            alerts = self._rotate_auto_snapshot(
                account,
                account.status,
                raw,
                now,
                runtime["follower_threshold"],
                machine,
                owner,
            )
            db.flush()
            return {
                "account_id": str(account.id),
                "owner_id": str(owner.id),
                "owner_name": owner.full_name,
                "machine_number": machine.machine_number,
                "slot_number": account.slot_number,
                "username": account.username,
                "status": account.status,
                "is_private": account.is_private,
                "followers": account.followers,
                "previous_followers": account.previous_followers,
                "follower_delta": (
                    account.auto_followers - account.previous_auto_followers
                    if account.auto_followers is not None and account.previous_auto_followers is not None
                    else None
                ),
                "new_problem": False,
                "error": account.last_error_message,
                "alerts": alerts if runtime["notifications"] else [],
                "last_checked_at": account.last_checked_at.isoformat() if account.last_checked_at else None,
            }

    @staticmethod
    def _update_run(run_id: uuid.UUID, outcome: dict[str, Any]) -> dict[str, Any]:
        with db_session() as db:
            run = db.get(CheckRun, run_id)
            if run is None:
                return {}
            run.processed_accounts += 1
            status = outcome.get("status")
            if status == "LIVE":
                run.live_count += 1
            elif status == "DIE":
                run.die_count += 1
            else:
                run.error_count += 1
            if outcome.get("follower_delta") not in (None, 0):
                run.follower_changed_count += 1
            if outcome.get("new_problem"):
                run.new_problem_count += 1
            db.flush()
            return JobManager.serialize_run(run)

    def _run_job(
        self,
        run_id: uuid.UUID,
        account_ids: list[uuid.UUID],
        scheduled: bool,
        requested_by: uuid.UUID | None,
        requested_session_id: uuid.UUID | None,
        stop_event: threading.Event,
    ) -> None:
        pending: dict[concurrent.futures.Future, tuple[uuid.UUID, InflightCheck]] = {}
        try:
            with db_session() as db:
                runtime = self._runtime_settings(db)
                run = db.get(CheckRun, run_id)
                if run is None:
                    return
                run.status = "RUNNING"
                run.started_at = datetime.now(timezone.utc)
                db.flush()
                run_payload = self.serialize_run(run)
                runtime["priority"] = run.priority
            event_identity = {
                "requested_by": str(requested_by) if requested_by else None,
                "requested_session_id": str(requested_session_id) if requested_session_id else None,
            }
            self._emit("job_started", {**event_identity, "run": run_payload, "scheduled": scheduled})

            queue = deque(account_ids)
            completed: set[uuid.UUID] = set()
            persistence_retries: dict[uuid.UUID, int] = {}
            counters = {key: 0 for key in ("processed_accounts", "live_count", "die_count",
                                         "error_count", "follower_changed_count", "new_problem_count")}
            last_saved = time.monotonic()
            per_job = max(
                1,
                min(runtime["max_workers_per_job"], 3 if runtime["priority"] == 0 else 2),
            )

            # On stop, drain already submitted work so completed requests are
            # persisted; do not silently drop the last in-flight results.
            while pending or (queue and not stop_event.is_set()):
                while queue and len(pending) < per_job and not stop_event.is_set():
                    account_id = queue.popleft()
                    record = self._get_inflight(account_id, runtime)
                    pending[record.future] = (account_id, record)
                    if runtime["delay"] > 0:
                        time.sleep(runtime["delay"])

                if not pending:
                    continue
                done, _ = concurrent.futures.wait(
                    pending.keys(), timeout=0.5, return_when=concurrent.futures.FIRST_COMPLETED
                )
                for future in done:
                    account_id, record = pending.pop(future)
                    try:
                        raw = future.result()
                    except Exception as exc:
                        raw = {"status": "EXCEPTION", "error": str(exc), "account_id": str(account_id)}
                    try:
                        outcome = self._consume_result(
                            record, account_id, raw, scheduled, requested_by, runtime
                        )
                    except Exception:
                        logger.exception("Cannot persist run=%s account=%s", run_id, account_id)
                        persistence_retries[account_id] = persistence_retries.get(account_id, 0) + 1
                        if persistence_retries[account_id] <= 1 and not stop_event.is_set():
                            queue.append(account_id)
                        continue
                    finally:
                        self._release_inflight(account_id, record)
                    completed.add(account_id)
                    counters["processed_accounts"] = len(completed)
                    result_status = outcome.get("status")
                    counters[{"LIVE": "live_count", "DIE": "die_count"}.get(result_status, "error_count")] += 1
                    counters["follower_changed_count"] += int(outcome.get("follower_delta") not in (None, 0))
                    counters["new_problem_count"] += int(bool(outcome.get("new_problem")))
                    run_payload = {**run_payload, **counters,
                                   "progress_percent": round(len(completed) * 100 / len(account_ids), 1)}
                    if len(completed) % 5 == 0 or time.monotonic() - last_saved >= 2:
                        try:
                            with db_session() as db:
                                run = db.get(CheckRun, run_id)
                                if run:
                                    for key, value in counters.items():
                                        setattr(run, key, value)
                        except Exception:
                            # Progress is advisory; a failed progress write must
                            # not discard remaining account work.
                            logger.exception("Could not checkpoint run=%s", run_id)
                        last_saved = time.monotonic()
                    self._emit("job_progress", {
                        **event_identity,
                        "run": run_payload,
                        "account": outcome,
                        "scheduled": scheduled,
                    })
                    for alert in outcome.get("alerts", []):
                        self._emit("alert", {
                            **event_identity,
                            "owner_id": outcome.get("owner_id"),
                            "account_id": outcome.get("account_id"),
                            "voice_enabled": runtime["voice_notifications"],
                            **alert,
                        })

            with db_session() as db:
                run = db.get(CheckRun, run_id)
                if run:
                    missing = set(account_ids) - completed
                    for key, value in counters.items():
                        setattr(run, key, value)
                    run.status = "STOPPED" if stop_event.is_set() else ("FAILED" if missing else "COMPLETED")
                    if missing:
                        run.message = (f"Đã lưu {len(completed)}/{len(account_ids)} kênh. Chưa xử lý: "
                                       + ", ".join(str(value) for value in sorted(missing, key=str)))[:1000]
                    elif counters["error_count"]:
                        run.message = f"Đã xử lý đủ {len(completed)} kênh; {counters['error_count']} kênh lỗi, có thể retry riêng."
                    run.finished_at = datetime.now(timezone.utc)
                    if scheduled and run.status == "COMPLETED":
                        config = db.get(AppSettings, 1)
                        if config:
                            config.last_auto_check_at = run.finished_at
                    db.flush()
                    payload = self.serialize_run(run)
                else:
                    payload = {"id": str(run_id), "status": "FAILED"}
            self._emit("job_failed" if payload["status"] == "FAILED" else "job_finished", {
                **event_identity,
                "run": payload,
                "scheduled": scheduled,
            })
            try:
                self._cleanup_old_runs(requested_by)
            except Exception:
                logger.exception("Could not clean old check runs")
        except Exception as exc:
            with db_session() as db:
                run = db.get(CheckRun, run_id)
                if run:
                    run.status = "FAILED"
                    run.message = str(exc)[:1000]
                    run.finished_at = datetime.now(timezone.utc)
                    db.flush()
                    payload = self.serialize_run(run)
                else:
                    payload = {"id": str(run_id), "status": "FAILED", "message": str(exc)}
            self._emit("job_failed", {
                "requested_by": str(requested_by) if requested_by else None,
                "requested_session_id": str(requested_session_id) if requested_session_id else None,
                "run": payload,
            })
        finally:
            for account_id, record in pending.values():
                self._release_inflight(account_id, record)
            self._stop_events.pop(run_id, None)

    @staticmethod
    def _cleanup_old_runs(requested_by: uuid.UUID | None) -> None:
        with db_session() as db:
            query = select(CheckRun.id).where(CheckRun.status.in_(("COMPLETED", "STOPPED", "FAILED")))
            if requested_by is None:
                query = query.where(CheckRun.requested_by.is_(None))
            else:
                query = query.where(CheckRun.requested_by == requested_by)
            old_ids = list(db.scalars(query.order_by(CheckRun.created_at.desc()).offset(20)))
            if old_ids:
                db.execute(delete(CheckRun).where(CheckRun.id.in_(old_ids)))

    @staticmethod
    def serialize_run(run: CheckRun) -> dict[str, Any]:
        total = int(run.total_accounts or 0)
        processed = int(run.processed_accounts or 0)
        return {
            "id": str(run.id),
            "requested_by": str(run.requested_by) if run.requested_by else None,
            "requested_session_id": str(run.requested_session_id) if run.requested_session_id else None,
            "trigger_type": run.trigger_type,
            "scope_type": run.scope_type,
            "target_user_id": str(run.target_user_id) if run.target_user_id else None,
            "status": run.status,
            "total_accounts": total,
            "processed_accounts": processed,
            "progress_percent": round(processed * 100 / total, 1) if total else 0,
            "live_count": int(run.live_count or 0),
            "die_count": int(run.die_count or 0),
            "error_count": int(run.error_count or 0),
            "follower_changed_count": int(run.follower_changed_count or 0),
            "new_problem_count": int(run.new_problem_count or 0),
            "message": run.message,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
