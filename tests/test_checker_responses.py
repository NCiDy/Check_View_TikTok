import json
from html import escape
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.checker import TikTokChecker
from core.embed_parser import metric
from curl_cffi.requests.exceptions import Timeout, ConnectionError


def response(info=None, videos=None, extra=None, tag='id="__FRONTITY_CONNECT_STATE__"'):
    entry = {"userInfo": info if info is not None else {
        "uniqueId": "sample", "followerCount": 123, "heartCount": 15,
    }, "videoList": videos if videos is not None else []}
    entries = dict(extra or {})
    entries["/embed/@sample"] = entry
    state = json.dumps({"source": {"data": entries}})
    return f"<script {tag}>{state}</script>"


def check(html, status=200):
    checker = TikTokChecker()
    session = Mock()
    session.get.return_value = SimpleNamespace(status_code=status, text=html)
    checker._session = lambda: session
    result = checker.check("sample")
    assert session.get.call_count == 1  # All recovery is in the original response.
    return result, session


@pytest.mark.parametrize("tag", [
    'id="__FRONTITY_CONNECT_STATE__"', "id='__FRONTITY_CONNECT_STATE__'",
    'ID = "__FRONTITY_CONNECT_STATE__"', 'id=__FRONTITY_CONNECT_STATE__',
])
def test_script_attributes(tag):
    result, _ = check(response(tag=tag))
    assert result["status"] == "LIVE"
    assert result["followers"] == 123


def test_multiple_profiles_selects_requested_username():
    result, _ = check(response(extra={"/embed/@other": {
        "userInfo": {"uniqueId": "other", "followerCount": 999},
    }}))
    assert result["followers"] == 123


def test_escaped_json_and_malformed_previous_script():
    html = response()
    body = html.split(">", 1)[1].rsplit("<", 1)[0]
    html = '<script id="__FRONTITY_CONNECT_STATE__">bad</script>' + (
        '<script id="__FRONTITY_CONNECT_STATE__">' + escape(body) + '</script>')
    assert check(html)[0]["status"] == "LIVE"


def test_numeric_strings_and_nested_video_stats():
    result, _ = check(response(
        info={"uniqueId": "sample", "followerCount": "123", "heartCount": "-1"},
        videos=[{"id": "1", "playCount": "100"}, {"id": "2", "stats": {"playCount": 50}}],
    ))
    assert result["status"] == "LIVE"
    assert result["total_sample_views"] == 150
    assert result["total_likes"] == 2**32 - 1
    assert len(result["videos"]) == 2


def test_nested_profile_stats():
    result, _ = check(response(info={"user": {"uniqueId": "sample"}, "stats": {"followerCount": 8}}))
    assert result["followers"] == 8


@pytest.mark.parametrize("info", [
    {}, {"followerCount": None}, {"followerCount": "1.2K"},
    {"followerCount": -1}, {"followerCount": True},
    {"followerCount": 42, "uniqueId": "someone_else"},
])
def test_incomplete_or_wrong_profile_never_overwrites_metrics(info):
    assert check(response(info=info))[0]["status"] == "PARSE_ERROR"


@pytest.mark.parametrize("status", [403, 429, 500, 503, 404])
def test_upstream_failure_is_not_hidden(status):
    result, _ = check("unavailable", status)
    assert result["status"] == ("NOT_FOUND" if status == 404 else "HTTP_ERROR")
    assert result["status_code"] == status


def test_missing_video_views_not_saved_as_zero():
    assert check(response(videos=[{"id": "1"}]))[0]["status"] == "PARSE_ERROR"


def test_profile_headers_follow_library_browser_version():
    _, session = check(response())
    kwargs = session.get.call_args.kwargs
    assert kwargs["impersonate"] == "chrome"
    assert "User-Agent" not in kwargs["headers"]


def test_invalid_numeric_value_is_explicit():
    with pytest.raises(ValueError):
        metric("12K", "views")


@pytest.mark.parametrize("exc,status", [(Timeout("timed out"), "TIMEOUT"),
                                        (ConnectionError("closed"), "EXCEPTION")])
def test_transport_error_resets_worker_session_without_extra_request(exc, status):
    checker = TikTokChecker()
    session = Mock()
    session.get.side_effect = exc
    checker._thread_local.session = session
    result = checker.check("sample")
    assert result["status"] == status
    session.get.assert_called_once()
    session.close.assert_called_once()
    assert checker._thread_local.session is None
