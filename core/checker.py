import re
import time
import threading
from typing import Dict, Any, Optional, List
from curl_cffi import requests
from curl_cffi.requests.exceptions import Timeout
from core.embed_parser import parse_embed, metric
from core.profile_parser import parse_profile, ProfileDataError

class TikTokChecker:
    """
    Public, login-free TikTok profile and video metrics extractor.
    Reads profile followers first; embed video metrics are best effort.
    """
    
    BASE_EMBED_URL = "https://www.tiktok.com/embed/@{username}"
    BASE_PROFILE_URL = "https://www.tiktok.com/@{username}"
    VIDEO_TIMEOUT_SECONDS = 1
    DEFAULT_HEADERS = {
        "Referer": "https://www.tiktok.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    def __init__(self):
        # A curl_cffi Session reuses DNS/TLS/TCP connections. Keep one session
        # per checker thread because Session objects are not shared across
        # workers safely.
        self._thread_local = threading.local()

    def _session(self):
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    @staticmethod
    def _profile_session():
        # Match the successful Render probe: a separate cookie jar and curl
        # connection for each profile. Embed responses cannot affect it.
        return requests.Session()

    def reset_session(self) -> None:
        """Drop the current worker's connection before a deferred retry."""
        session = getattr(self._thread_local, "session", None)
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
            self._thread_local.session = None

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

    def _optional_video_metrics(self, result, proxy, timeout=None):
        if result["is_private"]:
            return
        try:
            videos = self._check_embed(result["username"], proxy=proxy,
                                       timeout=self.VIDEO_TIMEOUT_SECONDS if timeout is None else timeout)
            if videos.get("status") == "LIVE":
                fields = {key: videos[key] for key in (
                    "videos", "video_count_sample", "total_sample_views",
                    "avg_sample_views", "latest_5_views")}
                result.update(fields)
        except Exception:
            # A successful follower result cannot be demoted by video errors.
            pass

    def check(self, username: str, proxy: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
        started = time.monotonic()
        profile = self._check_profile(username, proxy=proxy, timeout=timeout)
        if profile.get("status") == "LIVE" or profile.get("status") == "INVALID_INPUT":
            return profile
        # Recover channels still served by the original embed endpoint instead
        # of making the new profile parser the only route to success. Spend
        # at most the remaining original timeout, capped at two seconds.
        remaining = float(timeout) - (time.monotonic() - started)
        if remaining <= 0:
            return profile
        try:
            embed = self._check_embed(username, proxy=proxy, timeout=min(remaining, 2.0))
            if embed.get("status") == "LIVE":
                embed["source"] = "EMBED_FALLBACK"
                return embed
            profile["error"] = (str(profile.get("error", ""))
                                + "; embed=" + str(embed.get("status"))
                                + "/" + str(embed.get("status_code")))[:1000]
        except Exception as exc:
            profile["error"] = (str(profile.get("error", "")) + "; embed=" + type(exc).__name__)[:1000]
        return profile

    def _check_profile(self, username: str, proxy: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
        clean_user = self.clean_username(username)
        if not clean_user:
            return {"raw_input": username, "username": "", "status": "INVALID_INPUT",
                    "error": "Tên người dùng không hợp lệ"}
        started = time.monotonic()
        response = None
        try:
            options = {}
            if proxy:
                p = proxy.strip()
                if not p.startswith(("http://", "https://", "socks5://")):
                    p = "http://" + p
                options["proxies"] = {"http": p, "https": p}
            with self._profile_session() as session:
                response = session.get(
                    self.BASE_PROFILE_URL.format(username=clean_user),
                    headers=self.DEFAULT_HEADERS, impersonate="chrome", timeout=timeout,
                    **options,
                )
            if response.status_code != 200:
                return {"raw_input": username, "username": clean_user,
                        "status": "NOT_FOUND" if response.status_code == 404 else "HTTP_ERROR",
                        "status_code": response.status_code,
                        "latency_ms": round((time.monotonic() - started) * 1000, 1),
                        "error": f"Trang hồ sơ trả HTTP {response.status_code}"}
            result = parse_profile(response.text, clean_user)
            result.update(raw_input=username, status_code=response.status_code,
                          source="PROFILE", latency_ms=round((time.monotonic() - started) * 1000, 1))
            remaining = float(timeout) - (time.monotonic() - started)
            if remaining > 0:
                self._optional_video_metrics(result, proxy,
                                             timeout=min(remaining, self.VIDEO_TIMEOUT_SECONDS))
            result["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            return result
        except Timeout:
            self.reset_session()
            status, error = "TIMEOUT", "Quá thời gian chờ lấy follow"
        except ProfileDataError as exc:
            status = "PARSE_ERROR"
            error = f"{exc}; bytes={len(response.content)}" if response is not None else str(exc)
        except Exception as exc:
            self.reset_session()
            status, error = "EXCEPTION", str(exc)
        return {"raw_input": username, "username": clean_user, "status": status,
                "status_code": getattr(response, "status_code", None), "error": error,
                "latency_ms": round((time.monotonic() - started) * 1000, 1)}

    def _check_embed(self, username: str, proxy: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
        """
        Check a single TikTok account.
        Returns detailed dict with status, followers, following, likes, views, videos, etc.
        """
        clean_user = self.clean_username(username)
        if not clean_user:
            return {
                "raw_input": username,
                "username": "",
                "status": "INVALID_INPUT",
                "error": "Tên người dùng không hợp lệ"
            }

        url = self.BASE_EMBED_URL.format(username=clean_user)
        proxies = None
        if proxy:
            # Format proxy for curl_cffi
            p = proxy.strip()
            if not p.startswith("http://") and not p.startswith("https://") and not p.startswith("socks5://"):
                p = f"http://{p}"
            proxies = {"http": p, "https": p}

        start_time = time.monotonic()
        try:
            r = self._session().get(
                url,
                headers=self.DEFAULT_HEADERS,
                impersonate="chrome",
                proxies=proxies,
                timeout=timeout
            )
            elapsed = round((time.monotonic() - start_time) * 1000, 1)

            # Only an explicit 404 is a dead candidate. The database layer
            # requires repeated confirmation before changing status to DIE.
            if r.status_code == 404:
                return {
                    "raw_input": username,
                    "username": clean_user,
                    "nickname": "",
                    "avatar": "",
                    "status": "NOT_FOUND",
                    "status_code": r.status_code,
                    "latency_ms": elapsed,
                    "error": "TikTok trả về 404; cần check xác nhận thêm trước khi kết luận DIE"
                }

            if r.status_code != 200:
                # A 503 can leave this worker reusing the same failing edge
                # connection or response cookies for its next account. Retire
                # only that worker's session. This does not retry the account
                # or alter first-pass concurrency.
                if r.status_code == 503:
                    self.reset_session()
                return {
                    "raw_input": username,
                    "username": clean_user,
                    "status": "HTTP_ERROR",
                    "status_code": r.status_code,
                    "latency_ms": elapsed,
                    "error": f"Lỗi HTTP {r.status_code}"
                }

            # Parse the response already received; never add a second request.
            embed_data = parse_embed(r.text, clean_user)
            user_info = embed_data.get("userInfo")
            is_error = embed_data.get("isError", False)

            if not user_info or is_error:
                return {
                    "raw_input": username,
                    "username": clean_user,
                    "nickname": "",
                    "avatar": "",
                    "status": "PARSE_ERROR",
                    "latency_ms": elapsed,
                    "error": "Embed không trả về thông tin người dùng; không kết luận DIE"
                }

            # Correct 32-bit signed integer overflow for large heartCount
            try:
                raw_hearts = metric(user_info.get("heartCount"), "heartCount", default=0, signed=True)
            except ValueError:
                raw_hearts = 0
            if isinstance(raw_hearts, int) and raw_hearts < 0:
                raw_hearts = raw_hearts + (1 << 32)

            follower_count = metric(user_info.get("followerCount"), "followerCount")
            try:
                following_count = metric(user_info.get("followingCount"), "followingCount", default=0)
            except ValueError:
                following_count = 0
            is_private = user_info.get("privateAccount", False)
            is_verified = user_info.get("verified", False)
            nickname = user_info.get("nickname", "")
            avatar = user_info.get("avatarThumbUrl") or user_info.get("avatarThumb", "")
            bio = user_info.get("signature", "")
            unique_id = user_info.get("uniqueId", clean_user)

            # Process video list
            # Do not try to process videos for a private account.
            raw_videos = [] if is_private else (embed_data.get("videoList", []) or [])
            if not isinstance(raw_videos, list):
                raw_videos = []
            parsed_videos: List[Dict[str, Any]] = []
            total_views = 0
            latest_views = []

            for vid in raw_videos[:10]:
                if not isinstance(vid, dict):
                    continue
                stats = vid.get("stats") or {}
                stats = stats if isinstance(stats, dict) else {}
                try:
                    play_count = metric(vid.get("playCount", stats.get("playCount")), "playCount")
                except ValueError:
                    continue
                total_views += play_count
                if len(latest_views) < 5:
                    latest_views.append(play_count)

                parsed_videos.append({
                    "id": vid.get("id", ""),
                    "desc": vid.get("desc", ""),
                    "play_count": play_count,
                    "cover_url": vid.get("coverUrl", "") or vid.get("originCoverUrl", ""),
                    "video_url": f"https://www.tiktok.com/@{unique_id}/video/{vid.get('id', '')}" if vid.get('id') else "",
                    "ratio": vid.get("ratio", "720p")
                })

            avg_views = (total_views // len(parsed_videos)) if parsed_videos else 0

            return {
                "raw_input": username,
                "username": unique_id,
                "nickname": nickname,
                "avatar": avatar,
                "status": "LIVE",
                "status_code": r.status_code,
                "followers": follower_count,
                "following": following_count,
                "total_likes": raw_hearts,
                "is_verified": is_verified,
                "is_private": is_private,
                "bio": bio,
                "video_count_sample": len(parsed_videos),
                "total_sample_views": total_views,
                "avg_sample_views": avg_views,
                "latest_5_views": latest_views,
                "videos": parsed_videos,
                "latency_ms": elapsed,
                "error": ""
            }

        except Timeout:
            self.reset_session()
            return {
                "raw_input": username,
                "username": clean_user,
                "status": "TIMEOUT",
                "latency_ms": round((time.monotonic() - start_time) * 1000, 1),
                "error": "Quá thời gian chờ (Timeout)"
            }
        except (ValueError, TypeError, AttributeError) as e:
            return {
                "raw_input": username, "username": clean_user,
                "status": "PARSE_ERROR", "error": str(e),
                "status_code": getattr(locals().get("r"), "status_code", None),
                "latency_ms": round((time.monotonic() - start_time) * 1000, 1),
            }
        except Exception as e:
            self.reset_session()
            return {
                "raw_input": username,
                "username": clean_user,
                "status": "EXCEPTION",
                "latency_ms": round((time.monotonic() - start_time) * 1000, 1),
                "error": str(e)
            }
