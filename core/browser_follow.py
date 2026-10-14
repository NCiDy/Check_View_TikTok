"""One headless Chromium per checker, shared by bounded asynchronous tabs.

No TikTok login, personal browser profile, stealth scripts or CAPTCHA solver.
Only validated, exact profile statistics may produce a successful result.
"""
import asyncio
import concurrent.futures
import os
import threading
import time

from core.profile_parser import parse_profile, ProfileDataError


class BrowserFollowers:
    def __init__(self):
        self._lock = threading.Lock()
        self._loop = None
        self._thread = None
        self._browser = None
        self._playwright = None
        self._slots = None
        self._closed = False

    def _ensure_loop(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("Checker đã dừng")
            if self._loop is None:
                ready = threading.Event()
                try:
                    tab_count = max(1, min(5, int(os.getenv("TIKTOK_BROWSER_TABS", "3"))))
                except ValueError:
                    tab_count = 3
                def serve():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    self._loop = loop
                    self._slots = asyncio.Semaphore(tab_count)
                    ready.set()
                    loop.run_forever()
                    loop.close()
                self._thread = threading.Thread(target=serve, name="tiktok-browser", daemon=True)
                self._thread.start()
                if not ready.wait(10):
                    raise RuntimeError("Không khởi động được browser worker")
            return self._loop

    async def _get_browser(self):
        # All access runs on the same loop; startup lock avoids parallel launches.
        if not hasattr(self, "_launch_lock"):
            self._launch_lock = asyncio.Lock()
        async with self._launch_lock:
            if self._browser is None or not self._browser.is_connected():
                from playwright.async_api import async_playwright
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True, args=["--disable-dev-shm-usage"],
                )
            return self._browser

    async def _read(self, username, timeout, proxy):
        context = None
        acquired = False
        last_reason = "Chưa nhận được dữ liệu follow"
        http = None
        try:
            # Deadline includes waiting for a tab, navigation and hydration.
            async with asyncio.timeout(timeout):
                await self._slots.acquire()
                acquired = True
                browser = await self._get_browser()
                options = {"locale": "en-US", "viewport": {"width": 1280, "height": 720}}
                if proxy:
                    from urllib.parse import urlsplit, unquote
                    parsed = urlsplit(proxy if "://" in proxy else "http://" + proxy)
                    options["proxy"] = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}"}
                    if parsed.username:
                        options["proxy"].update(username=unquote(parsed.username), password=unquote(parsed.password or ""))
                context = await browser.new_context(**options)
                # Keep document, scripts, fetch/XHR and styles operational.
                async def route_request(route):
                    if route.request.resource_type in {"image", "media", "font"}:
                        await route.abort()
                    else:
                        await route.continue_()
                await context.route("**/*", route_request)
                page = await context.new_page()
                response = await page.goto(f"https://www.tiktok.com/@{username}", wait_until="domcontentloaded", timeout=timeout * 1000)
                http = response.status if response else None
                if http is not None and http >= 400:
                    return {"status": "HTTP_ERROR", "status_code": http, "error": f"Profile HTTP {http}"}
                while True:
                    try:
                        result = parse_profile(await page.content(), username)
                        result.update(source="BROWSER_PROFILE", status_code=http)
                        return result
                    except ProfileDataError as exc:
                        last_reason = str(exc)
                    except Exception as exc:
                        # page.content() can race a document replacement after
                        # DOMContentLoaded. Continue on the same page/deadline;
                        # do not repeat goto or hide unrelated browser errors.
                        message = str(exc)
                        if not any(marker in message for marker in (
                            "Unable to retrieve content because the page is navigating",
                            "Execution context was destroyed",
                            "Cannot find context with specified id",
                        )):
                            raise
                        last_reason = "Trang đang chuyển hướng; chưa đọc được follow"
                    # Allow ordinary page scripts to finish. Never solve CAPTCHA.
                    await asyncio.sleep(0.2)
        except TimeoutError:
            return {"status": "TIMEOUT", "status_code": http, "error": last_reason + "; browser deadline exceeded"}
        except Exception as exc:
            return {"status": "EXCEPTION", "status_code": http,
                    "error": "Browser checker: " + type(exc).__name__ + ": " + str(exc)[:400]}
        finally:
            if context is not None:
                try:
                    await asyncio.wait_for(context.close(), timeout=2)
                except Exception:
                    pass
            if acquired:
                self._slots.release()

    def check(self, username, timeout=12, proxy=None):
        started = time.monotonic()
        try:
            loop = self._ensure_loop()
            future = asyncio.run_coroutine_threadsafe(self._read(username, max(1, float(timeout)), proxy), loop)
            try:
                result = future.result(timeout=max(1, float(timeout)) + 5)
            except concurrent.futures.TimeoutError:
                future.cancel()
                result = {"status": "TIMEOUT", "error": "Browser worker quá thời gian chờ"}
        except Exception as exc:
            result = {"status": "EXCEPTION", "error": str(exc)[:400]}
        result.update(username=username, latency_ms=round((time.monotonic() - started) * 1000, 1))
        return result

    async def _close(self):
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    def close(self):
        with self._lock:
            self._closed = True
            loop = self._loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._close(), loop).result(timeout=5)
            except Exception:
                # Browser failure must not prevent application shutdown.
                pass
            finally:
                loop.call_soon_threadsafe(loop.stop)
