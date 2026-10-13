import json
import threading
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock

import pytest
from curl_cffi.requests.exceptions import Timeout

from core.checker import TikTokChecker
from core.profile_parser import parse_profile, ProfileDataError


def html(followers=2744, username="sample", stats_v2=None, extra_user=None, status=0):
    info = {"user": {"uniqueId": username, **(extra_user or {})},
            "stats": {"followerCount": followers}, "statsV2": stats_v2 or {}}
    state = {"__DEFAULT_SCOPE__": {"webapp.user-detail": {
        "statusCode": status, "userInfo": info}}}
    return '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">' + json.dumps(state) + '</script>'


def checker_for(body=None, status=200):
    checker = TikTokChecker()
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value = SimpleNamespace(status_code=status, text=body or html(), content=(body or html()).encode())
    checker._thread_local.session = session
    checker._session = lambda: session
    checker._profile_session = lambda: session
    checker._check_embed = Mock(return_value={"status": "HTTP_ERROR", "status_code": 503})
    return checker, session


def test_profile_followers_succeed_despite_embed_overload():
    checker, session = checker_for()
    raw = checker.check("sample")
    assert raw["status"] == "LIVE"
    assert raw["followers"] == 2744
    assert raw["videos"] == [] and raw["total_sample_views"] == 0
    assert raw["error"] == "" and raw["status_code"] == 200
    assert "/embed/" not in session.get.call_args.args[0]
    # Following channels keep checking followers; failed video endpoint is
    # suspended rather than called again for every channel.
    assert checker.check("sample")["status"] == "LIVE"
    checker._check_embed.assert_called_once()


@pytest.mark.parametrize("exc", [Timeout("timeout"), ValueError("bad videos"), RuntimeError("network")])
def test_optional_failure_cannot_demote_followers(exc):
    checker, _ = checker_for()
    checker._check_embed.side_effect = exc
    assert checker.check("sample")["status"] == "LIVE"


def test_zero_followers_valid_and_private_does_not_fetch_video():
    checker, _ = checker_for(html(0, extra_user={"privateAccount": True}))
    raw = checker.check("sample")
    assert raw["status"] == "LIVE" and raw["followers"] == 0
    checker._check_embed.assert_not_called()


def test_stats_v2_preferred_with_stats_fallback():
    assert parse_profile(html(stats_v2={"followerCount": "3000"}), "sample")["followers"] == 3000
    assert parse_profile(html(stats_v2={"followerCount": "invalid"}), "sample")["followers"] == 2744


@pytest.mark.parametrize("followers", [None, -1, True, "2.7K", ""])
def test_missing_invalid_followers_never_success(followers):
    checker, _ = checker_for(html(followers))
    assert checker.check("sample")["status"] == "PARSE_ERROR"
    checker._check_embed.assert_not_called()


def test_wrong_username_never_uses_other_profiles_followers():
    with pytest.raises(ProfileDataError):
        parse_profile(html(username="other"), "sample")


def test_nonzero_profile_status_not_treated_as_dead_account():
    checker, _ = checker_for(html(status=10201))
    assert checker.check("sample")["status"] == "PARSE_ERROR"


def test_valid_video_metrics_are_copied_without_overwriting_followers():
    checker, _ = checker_for()
    checker._check_embed.return_value = {
        "status": "LIVE", "followers": 1, "videos": [{"id": "123"}],
        "video_count_sample": 1, "total_sample_views": 88,
        "avg_sample_views": 88, "latest_5_views": [88],
    }
    raw = checker.check("sample")
    assert raw["followers"] == 2744 and raw["total_sample_views"] == 88
    assert raw["videos"] == [{"id": "123"}]


def test_optional_video_timeout_is_bounded_and_no_parallel_probe():
    checker, _ = checker_for()
    gate, entered = threading.Event(), threading.Event()
    def block(*args, **kwargs):
        assert kwargs["timeout"] == 1
        entered.set()
        assert gate.wait(2)
        return {"status": "TIMEOUT"}
    checker._check_embed.side_effect = block
    thread = threading.Thread(target=checker.check, args=("sample",))
    thread.start()
    try:
        assert entered.wait(2)
        assert checker.check("sample")["status"] == "LIVE"
        assert checker._check_embed.call_count == 1
    finally:
        gate.set()
        thread.join(2)
    assert not thread.is_alive()


@pytest.mark.parametrize("status", [404, 429, 503])
def test_profile_http_failure_is_reported(status):
    checker, _ = checker_for(status=status)
    raw = checker.check("sample")
    assert raw["status"] == ("NOT_FOUND" if status == 404 else "HTTP_ERROR")
    checker._check_embed.assert_not_called()


def test_follow_only_result_clears_stale_videos_and_error_in_database(monkeypatch):
    import app.job_manager as module
    from app.models import TikTokAccount, Machine, User
    checker, _ = checker_for()
    raw = checker.check("sample")
    account = TikTokAccount(id=uuid.uuid4(), username="sample", status="ERROR",
                            followers=100, total_sample_views=500,
                            recent_videos=[{"id": "old"}], slot_number=1,
                            dead_confirmation_count=1)
    machine = Machine(machine_number=42)
    owner = User(id=uuid.uuid4(), full_name="Owner")
    db = Mock()
    db.execute.return_value.one_or_none.return_value = (account, machine, owner)
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(module, "db_session", session)
    manager = module.JobManager.__new__(module.JobManager)
    outcome = manager._persist_result(account.id, raw, False, owner.id,
                                      {"notifications": False, "dead_confirmations": 2})
    assert outcome["status"] == "LIVE"
    assert account.followers == 2744 and account.previous_followers == 100
    assert account.total_sample_views == 0 and account.recent_videos == []
    assert account.last_error_message is None and account.last_error_code is None
    assert account.last_successful_checked_at is not None


def test_missing_optional_counts_do_not_discard_followers():
    body = html(stats_v2={"followerCount": "2744", "heartCount": "bad"})
    result = parse_profile(body, "sample")
    assert result["followers"] == 2744 and result["total_likes"] == 0


def test_sigi_profile_shape_is_supported():
    data = {"UserModule": {"users": {"sample": {"uniqueId": "sample"}},
                           "stats": {"sample": {"followerCount": 5}}}}
    body = '<script id="SIGI_STATE">' + json.dumps(data) + '</script>'
    assert parse_profile(body, "sample")["followers"] == 5


def test_batch_of_50_uses_fresh_profile_sessions_and_closes_all(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import core.checker as module
    created = []
    lock = threading.Lock()
    class SingleUseSession:
        def __init__(self):
            self.used = False
            self.closed = False
            with lock:
                created.append(self)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.closed = True
        def get(self, url, **kwargs):
            assert not self.used, "Profile cookie jar must not cross accounts"
            self.used = True
            username = url.rsplit("/", 1)[1][1:]
            return SimpleNamespace(status_code=200, text=html(50, username), content=b"profile")
    monkeypatch.setattr(module.requests, "Session", SingleUseSession)
    checker = TikTokChecker()
    checker._check_embed = Mock(return_value={"status": "HTTP_ERROR", "status_code": 503})
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(checker.check, [f"account{i}" for i in range(50)]))
    assert len(created) == 50 and all(s.closed for s in created)
    assert all(r["status"] == "LIVE" and r["followers"] == 50 for r in results)
    assert checker._check_embed.call_count == 1


def test_profile_error_diagnosis_distinguishes_missing_json_from_status():
    with pytest.raises(ProfileDataError, match="profile_json_missing"):
        parse_profile("<html>empty</html>", "sample")
    with pytest.raises(ProfileDataError, match="profile_status=10201"):
        parse_profile(html(status=10201), "sample")
