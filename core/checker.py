"""Follower-only checker using a server-side headless browser."""
import re
from core.browser_follow import BrowserFollowers


class TikTokChecker:
    def __init__(self):
        self._browser = BrowserFollowers()

    @staticmethod
    def clean_username(raw_input: str) -> str:
        """
        Extract clean username from raw input:
        - raw: @username -> username
        - raw: username -> username
        - raw: https://www.tiktok.com/@username?lang=vi -> username
        - raw: username|password|email -> username
        - raw: username:password -> username
        """
        text = raw_input.strip()
        if not text:
            return ""
        
        # Check if URL
        if "tiktok.com/@" in text.lower():
            m = re.search(r'tiktok\.com/@([a-zA-Z0-9_\.\-]+)', text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        
        # Check if separated by | or : or ; or tab or space
        for sep in ['|', ':', ';', '\t', ',']:
            if sep in text:
                parts = text.split(sep)
                text = parts[0].strip()
                break
                
        # Some legacy lists use whitespace between username and credentials.
        text = text.split()[0] if text.split() else ""

        # Remove leading @
        text = text.lstrip('@').strip()
        
        # Remove any query params or slashes
        text = text.split('?')[0].split('/')[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", text):
            return ""
        return text

    def check(self, username, proxy=None, timeout=12):
        clean = self.clean_username(username)
        if not clean:
            return {"raw_input": username, "username": "", "status": "INVALID_INPUT",
                    "error": "Tên người dùng không hợp lệ"}
        result = self._browser.check(clean, timeout=timeout, proxy=proxy)
        result["raw_input"] = username
        return result

    def reset_session(self):
        # Each request has an isolated context; no shared TikTok cookies.
        pass

    def close(self):
        self._browser.close()
