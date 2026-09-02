import threading
import time
from typing import List, Optional, Dict, Any
from curl_cffi import requests

class ProxyManager:
    def __init__(self):
        self.proxies: List[str] = []
        self.rotating_url: Optional[str] = None
        self.lock = threading.Lock()
        self.index = 0
        self.mode = "direct"  # "direct", "list", "rotating"
        self.last_rotating_ip = ""
        self.last_rotating_time = 0

    def set_config(self, mode: str, proxy_text: str = "", rotating_url: str = ""):
        with self.lock:
            self.mode = mode
            self.rotating_url = rotating_url.strip() if rotating_url else None
            self.proxies = []
            self.index = 0

            if proxy_text:
                lines = [l.strip() for l in proxy_text.splitlines() if l.strip()]
                for line in lines:
                    formatted = self._format_proxy(line)
                    if formatted:
                        self.proxies.append(formatted)

    def _format_proxy(self, raw: str) -> Optional[str]:
        p = raw.strip()
        if not p:
            return None
        
        # Check scheme
        scheme = "http"
        if "://" in p:
            parts = p.split("://", 1)
            scheme = parts[0].lower()
            p = parts[1]

        # Handle ip:port:user:pass
        segments = p.split(":")
        if len(segments) == 4:
            ip, port, user, pwd = segments
            return f"{scheme}://{user}:{pwd}@{ip}:{port}"
        elif len(segments) == 2:
            ip, port = segments
            return f"{scheme}://{ip}:{port}"
        elif "@" in p:
            return f"{scheme}://{p}"
        
        return f"{scheme}://{p}"

    def get_proxy(self) -> Optional[str]:
        rotating_url = None
        with self.lock:
            if self.mode == "direct" or not self.mode:
                return None
            
            if self.mode == "list":
                if not self.proxies:
                    return None
                proxy = self.proxies[self.index % len(self.proxies)]
                self.index += 1
                return proxy
            
            if self.mode == "rotating":
                if not self.rotating_url:
                    return None
                # Never perform a network request while holding the shared
                # proxy lock; otherwise all checker threads are serialized.
                rotating_url = self.rotating_url

        if rotating_url:
            return self._fetch_rotating_proxy(rotating_url)
        return None

    def _fetch_rotating_proxy(self, rotating_url: str) -> Optional[str]:
        # For rotating URLs that return an IP:PORT or JSON
        try:
            r = requests.get(rotating_url, timeout=5)
            if r.status_code == 200:
                body = r.text.strip()
                # Check if JSON
                try:
                    data = r.json()
                    # e.g., TMProxy, Tinsoft, KingProxy formats
                    if isinstance(data, dict):
                        p = data.get("data", {}).get("proxy") or data.get("proxy") or data.get("httpProxy") or data.get("ip_port")
                        if p:
                            return self._format_proxy(str(p))
                except Exception:
                    pass
                # plain text
                return self._format_proxy(body.splitlines()[0])
        except Exception:
            pass
        return None

    def test_proxy(self, proxy_str: str) -> Dict[str, Any]:
        formatted = self._format_proxy(proxy_str)
        if not formatted:
            return {"success": False, "error": "Định dạng Proxy không hợp lệ"}

        start = time.time()
        try:
            proxies = {"http": formatted, "https": formatted}
            r = requests.get(
                "https://api.ipify.org?format=json",
                proxies=proxies,
                impersonate="chrome124",
                timeout=8
            )
            elapsed = round((time.time() - start) * 1000)
            if r.status_code == 200:
                ip = r.json().get("ip", "Unknown")
                return {"success": True, "ip": ip, "latency_ms": elapsed, "proxy": formatted}
            else:
                return {"success": False, "error": f"HTTP {r.status_code}", "latency_ms": elapsed}
        except Exception as e:
            return {"success": False, "error": str(e), "latency_ms": round((time.time() - start) * 1000)}
