import re
import json
import time
from typing import Dict, Any, Optional, List
from curl_cffi import requests

class TikTokChecker:
    """
    High-performance, zero-cookie, 100% account-safe TikTok profile and video metrics extractor.
    Uses public embed SSR endpoints with TLS Chrome impersonation.
    """
    
    BASE_EMBED_URL = "https://www.tiktok.com/embed/@{username}"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.tiktok.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

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

    def check(self, username: str, proxy: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
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

        start_time = time.time()
        try:
            r = requests.get(
                url,
                headers=self.DEFAULT_HEADERS,
                impersonate="chrome124",
                proxies=proxies,
                timeout=timeout
            )
            elapsed = round((time.time() - start_time) * 1000, 1)

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
                return {
                    "raw_input": username,
                    "username": clean_user,
                    "status": "HTTP_ERROR",
                    "status_code": r.status_code,
                    "latency_ms": elapsed,
                    "error": f"Lỗi HTTP {r.status_code}"
                }

            # Parse FRONTITY SSR JSON
            match = re.search(r'<script[^>]+id=[\'"]__FRONTITY_CONNECT_STATE__[\'"][^>]*>(.*?)</script>', r.text, re.DOTALL)
            if not match:
                # Check for alternative script tags or WAF
                return {
                    "raw_input": username,
                    "username": clean_user,
                    "status": "PARSE_ERROR",
                    "latency_ms": elapsed,
                    "error": "Không thể phân tích dữ liệu SSR (Có thể IP bị hạn chế)"
                }

            data = json.loads(match.group(1))
            source = data.get("source", {})
            data_dict = source.get("data", {})
            
            # Key is usually /embed/@username (in lower or exact case)
            embed_key = None
            for k in data_dict.keys():
                if k.startswith("/embed/@"):
                    embed_key = k
                    break
            
            if not embed_key:
                return {
                    "raw_input": username,
                    "username": clean_user,
                    "status": "PARSE_ERROR",
                    "latency_ms": elapsed,
                    "error": "Không tìm thấy khóa dữ liệu Embed; không kết luận DIE"
                }

            embed_data = data_dict.get(embed_key, {})
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
            raw_hearts = user_info.get("heartCount", 0)
            if isinstance(raw_hearts, int) and raw_hearts < 0:
                raw_hearts = raw_hearts + (1 << 32)

            follower_count = user_info.get("followerCount", 0)
            following_count = user_info.get("followingCount", 0)
            is_private = user_info.get("privateAccount", False)
            is_verified = user_info.get("verified", False)
            nickname = user_info.get("nickname", "")
            avatar = user_info.get("avatarThumbUrl", "")
            bio = user_info.get("signature", "")
            unique_id = user_info.get("uniqueId", clean_user)

            # Process video list
            # Do not try to process videos for a private account.
            raw_videos = [] if is_private else (embed_data.get("videoList", []) or [])
            parsed_videos: List[Dict[str, Any]] = []
            total_views = 0
            latest_views = []

            for vid in raw_videos[:10]:
                play_count = vid.get("playCount", 0)
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

        except requests.errors.Timeout:
            return {
                "raw_input": username,
                "username": clean_user,
                "status": "TIMEOUT",
                "latency_ms": round((time.time() - start_time) * 1000, 1),
                "error": "Quá thời gian chờ (Timeout)"
            }
        except Exception as e:
            return {
                "raw_input": username,
                "username": clean_user,
                "status": "EXCEPTION",
                "latency_ms": round((time.time() - start_time) * 1000, 1),
                "error": str(e)
            }
