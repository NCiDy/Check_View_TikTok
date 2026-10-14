"""Legacy embed parsing contract; the checker no longer calls embed."""
import json
import pytest
from core.embed_parser import parse_embed, metric


def test_embed_parser_retained_for_legacy_imports():
    state = {"source": {"data": {"/embed/@sample": {
        "userInfo": {"uniqueId": "sample", "followerCount": 123}, "videoList": []}}}}
    body = '<script id="__FRONTITY_CONNECT_STATE__">' + json.dumps(state) + '</script>'
    assert parse_embed(body, "sample")["userInfo"]["followerCount"] == 123


def test_invalid_numeric_value_is_explicit():
    with pytest.raises(ValueError):
        metric("12K", "views")
