"""Strict, tolerant parsing of public embed responses without network retries."""
import json
import re
from html import unescape
from html.parser import HTMLParser


_SCRIPT = re.compile(
    r'<script\b[^>]*\bid\s*=\s*[\'\"]__FRONTITY_CONNECT_STATE__[\'\"][^>]*>(.*?)</script\s*>',
    re.DOTALL | re.IGNORECASE,
)


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.parts = []
        self.states = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("id") == "__FRONTITY_CONNECT_STATE__"
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.states.append("".join(self.parts))
            self.active = False


def metric(value, name, default=None, signed=False):
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"Missing {name}")
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name}")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        result = int(value)
    else:
        raise ValueError(f"Invalid {name}")
    if result < 0 and not signed:
        raise ValueError(f"Negative {name}")
    return result


def parse_embed(html, username):
    states = _SCRIPT.findall(html)
    if not states:
        parser = _Scripts()
        parser.feed(html)
        states = parser.states
    for text in states:
        try:
            try:
                data = json.loads(text.strip())
            except json.JSONDecodeError:
                data = json.loads(unescape(text.strip()))
            entries = data.get("source", {}).get("data", {})
            if not isinstance(entries, dict):
                continue
        except (ValueError, TypeError, AttributeError):
            continue
        for key, entry in entries.items():
            if not key.startswith("/embed/@") or not isinstance(entry, dict):
                continue
            key_user = key[len("/embed/@"):].split("?")[0].rstrip("/")
            if key_user.casefold() != username.casefold() or entry.get("isError"):
                continue
            info = entry.get("userInfo")
            if not isinstance(info, dict):
                continue
            if isinstance(info.get("user"), dict):
                stats = info.get("stats")
                if not isinstance(stats, dict):
                    continue
                info = {**info["user"], **stats}
            actual = info.get("uniqueId")
            if actual and str(actual).casefold() != username.casefold():
                continue
            try:
                metric(info.get("followerCount"), "followerCount")
            except ValueError:
                continue
            # Preserve all videos; never substitute an unrelated profile or
            # silently accept a missing follower metric as zero.
            return {**entry, "userInfo": info}
    raise ValueError("Không tìm thấy dữ liệu embed hợp lệ cho đúng username")
