import json
import uuid
from contextlib import contextmanager
from unittest.mock import Mock
import pytest
from core.profile_parser import parse_profile, ProfileDataError


def html(followers=2744, username="sample", stats_v2=None, extra_user=None, status=0):
    info = {"user": {"uniqueId": username, **(extra_user or {})},
            "stats": {"followerCount": followers}, "statsV2": stats_v2 or {}}
    state = {"__DEFAULT_SCOPE__": {"webapp.user-detail": {
        "statusCode": status, "userInfo": info}}}
    return '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">' + json.dumps(state) + '</script>'


def test_stats_v2_preferred_with_stats_fallback():
    assert parse_profile(html(stats_v2={"followerCount": "3000"}), "sample")["followers"] == 3000
    assert parse_profile(html(stats_v2={"followerCount": "invalid"}), "sample")["followers"] == 2744


def test_wrong_username_never_uses_other_profiles_followers():
    with pytest.raises(ProfileDataError):
        parse_profile(html(username="other"), "sample")


def test_follow_only_result_clears_stale_videos_and_error_in_database(monkeypatch):
    import app.job_manager as module
    from app.models import TikTokAccount, Machine, User
    raw = parse_profile(html(), "sample")
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


def test_waf_200_page_is_reported_truthfully_not_as_missing_profile():
    body = '<html><script id="slardar-config">{"slardarClient":"SlardarWAF"}</script>Please wait...</html>'
    with pytest.raises(ProfileDataError, match="upstream_waf_challenge"):
        parse_profile(body, "sample")


def test_profile_error_diagnosis_distinguishes_missing_json_from_status():
    with pytest.raises(ProfileDataError, match="profile_json_missing"):
        parse_profile("<html>empty</html>", "sample")
    with pytest.raises(ProfileDataError, match="profile_status=10201"):
        parse_profile(html(status=10201), "sample")
