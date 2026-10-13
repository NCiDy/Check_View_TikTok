"""Parse public profile metrics; followers determine check success."""
import json
from html import unescape
from html.parser import HTMLParser

from core.embed_parser import metric


class ProfileDataError(ValueError):
    pass


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = None
        self.parts = []
        self.states = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            ident = dict(attrs).get("id")
            self.active = ident if ident in {
                "__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE",
            } else None
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.states.append((self.active, "".join(self.parts)))
            self.active = None


def _optional_count(stats, stats_v2, key):
    for source in (stats_v2, stats):
        try:
            return metric(source.get(key), key)
        except ValueError:
            pass
    return 0


def _normalize(user, stats, stats_v2, username):
    actual = user.get("uniqueId")
    if not isinstance(actual, str) or actual.casefold() != username.casefold():
        raise ProfileDataError("Trang hồ sơ không trả đúng username")
    followers = None
    for source in (stats_v2, stats):
        try:
            followers = metric(source.get("followerCount"), "followerCount")
            break
        except ValueError:
            pass
    if followers is None:
        raise ProfileDataError("Trang hồ sơ thiếu số follow hợp lệ")
    def text(key):
        value = user.get(key)
        return value if isinstance(value, str) else ""
    return {
        "username": actual, "status": "LIVE", "followers": followers,
        "following": _optional_count(stats, stats_v2, "followingCount"),
        "total_likes": _optional_count(stats, stats_v2, "heartCount"),
        "nickname": text("nickname"), "avatar": text("avatarThumb") or text("avatarMedium"),
        "bio": text("signature"), "is_private": user.get("privateAccount") is True,
        "is_verified": user.get("verified") is True,
        "videos": [], "video_count_sample": 0, "total_sample_views": 0,
        "avg_sample_views": 0, "latest_5_views": [], "error": "",
    }


def parse_profile(html, username):
    parser = _Scripts()
    parser.feed(html)
    if not parser.states and ("SlardarWAF" in html or "_wafchallengeid" in html):
        raise ProfileDataError("upstream_waf_challenge: TikTok trả trang xác minh JavaScript, không có follow")
    reasons = []
    for ident, text in parser.states:
        try:
            try:
                data = json.loads(text)
            except ValueError:
                data = json.loads(unescape(text))
            if ident == "__UNIVERSAL_DATA_FOR_REHYDRATION__":
                detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
                if detail.get("statusCode") not in (0, "0"):
                    reasons.append(f"profile_status={detail.get('statusCode')}")
                    continue
                info = detail.get("userInfo") or {}
                user = info.get("user") or {}
                stats = info.get("stats") or {}
                stats_v2 = info.get("statsV2") or {}
            else:
                module = data.get("UserModule") or {}
                users = module.get("users") or {}
                user = next((u for u in users.values() if isinstance(u, dict)
                             and str(u.get("uniqueId", "")).casefold() == username.casefold()), {})
                stats = (module.get("stats") or {}).get(user.get("uniqueId"), {})
                stats_v2 = {}
            if not isinstance(user, dict):
                reasons.append("invalid_user_object")
                continue
            stats = stats if isinstance(stats, dict) else {}
            stats_v2 = stats_v2 if isinstance(stats_v2, dict) else {}
            return _normalize(user, stats, stats_v2, username)
        except (ValueError, TypeError, AttributeError) as exc:
            reasons.append(str(exc)[:160])
            continue
    reason = "; ".join(reasons[:3]) if reasons else "profile_json_missing"
    raise ProfileDataError(f"Không lấy được follow: {reason}")
