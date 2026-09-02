import asyncio
import time
import concurrent.futures
from typing import List, Dict, Any, Optional, Callable
from .checker import TikTokChecker
from .proxy_manager import ProxyManager

class WorkerPool:
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.checker = TikTokChecker()
        
        self.is_running = False
        self.is_paused = False
        self._stop_requested = False
        
        self.items_queue: List[str] = []
        self.results: List[Dict[str, Any]] = []
        
        # Statistics
        self.total_count = 0
        self.processed_count = 0
        self.live_count = 0
        self.dead_count = 0
        self.private_count = 0
        self.error_count = 0
        
        self.total_followers = 0
        self.total_likes = 0
        self.total_views = 0
        
        self.start_time = 0.0
        self.speed = 0.0  # accounts per second
        self.eta_seconds = 0
        
        self.concurrency = 10
        self.delay = 0.0
        self.timeout = 10
        
        self.callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.executor: Optional[concurrent.futures.ThreadPoolExecutor] = None

    def reset_stats(self):
        self.processed_count = 0
        self.live_count = 0
        self.dead_count = 0
        self.private_count = 0
        self.error_count = 0
        self.total_followers = 0
        self.total_likes = 0
        self.total_views = 0
        self.speed = 0.0
        self.eta_seconds = 0
        self.results.clear()

    def set_callback(self, cb: Callable[[str, Dict[str, Any]], None]):
        self.callback = cb

    def _emit(self, event: str, data: Dict[str, Any]):
        if self.callback:
            try:
                self.callback(event, data)
            except Exception:
                pass

    def get_summary(self) -> Dict[str, Any]:
        elapsed = time.time() - self.start_time if self.start_time > 0 and self.is_running else 0
        speed = round(self.processed_count / elapsed, 1) if elapsed > 1 else 0.0
        remaining = self.total_count - self.processed_count
        eta = int(remaining / speed) if speed > 0 else 0

        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "total": self.total_count,
            "processed": self.processed_count,
            "progress_percent": round((self.processed_count / self.total_count * 100), 1) if self.total_count > 0 else 0,
            "live": self.live_count,
            "dead": self.dead_count,
            "private": self.private_count,
            "error": self.error_count,
            "total_followers": self.total_followers,
            "total_likes": self.total_likes,
            "total_views": self.total_views,
            "speed": speed,
            "eta_seconds": eta,
            "elapsed_seconds": int(elapsed)
        }

    async def start(self, raw_items: List[str], concurrency: int = 10, delay: float = 0.0, timeout: int = 10):
        if self.is_running:
            return

        # Clean list
        valid_items = [item.strip() for item in raw_items if item.strip()]
        if not valid_items:
            self._emit("error", {"message": "Danh sách tài khoản trống!"})
            return

        self.reset_stats()
        self.items_queue = valid_items
        self.total_count = len(valid_items)
        self.concurrency = max(1, min(concurrency, 100))
        self.delay = delay
        self.timeout = timeout
        
        self.is_running = True
        self.is_paused = False
        self._stop_requested = False
        self.start_time = time.time()

        self._emit("started", self.get_summary())

        # Run background worker loop
        asyncio.create_task(self._process_queue())

    def pause(self):
        if self.is_running:
            self.is_paused = True
            self._emit("paused", self.get_summary())

    def resume(self):
        if self.is_running and self.is_paused:
            self.is_paused = False
            self._emit("resumed", self.get_summary())

    def stop(self):
        if self.is_running:
            self._stop_requested = True
            self.is_running = False
            self.is_paused = False
            self._emit("stopped", self.get_summary())

    def clear(self):
        self.stop()
        self.reset_stats()
        self.items_queue.clear()
        self.total_count = 0
        self._emit("cleared", self.get_summary())

    async def _process_queue(self):
        loop = asyncio.get_running_loop()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency)
        
        idx = 0
        active_tasks = set()

        while (idx < len(self.items_queue) or active_tasks) and not self._stop_requested:
            # Handle Pause
            while self.is_paused and not self._stop_requested:
                await asyncio.sleep(0.3)

            if self._stop_requested:
                break

            # Fill worker pool up to concurrency
            while len(active_tasks) < self.concurrency and idx < len(self.items_queue) and not self._stop_requested and not self.is_paused:
                item = self.items_queue[idx]
                idx += 1
                task = asyncio.create_task(self._check_single_item(item, idx, loop))
                active_tasks.add(task)
                if self.delay > 0:
                    await asyncio.sleep(self.delay)

            if active_tasks:
                # Wait for at least one task to complete
                done, active_tasks = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
                for d in done:
                    try:
                        res = await d
                        self._handle_result(res)
                    except Exception as e:
                        pass

            await asyncio.sleep(0.01)

        self.is_running = False
        self.is_paused = False
        if self.executor:
            self.executor.shutdown(wait=False)
        self._emit("finished", self.get_summary())

    async def _check_single_item(self, item: str, index: int, loop: asyncio.AbstractEventLoop) -> Dict[str, Any]:
        proxy = self.proxy_manager.get_proxy()
        # Run blocking curl_cffi in thread pool
        res = await loop.run_in_executor(
            self.executor,
            self.checker.check,
            item,
            proxy,
            self.timeout
        )
        res["index"] = index
        res["proxy_used"] = proxy or "Direct"
        return res

    def _handle_result(self, res: Dict[str, Any]):
        self.processed_count += 1
        self.results.append(res)
        
        status = res.get("status", "")
        if status == "LIVE":
            self.live_count += 1
            self.total_followers += res.get("followers", 0)
            self.total_likes += res.get("total_likes", 0)
            self.total_views += res.get("total_sample_views", 0)
        elif status == "PRIVATE":
            self.private_count += 1
            self.total_followers += res.get("followers", 0)
            self.total_likes += res.get("total_likes", 0)
        elif status in ["DEAD_OR_BANNED", "NOT_FOUND"]:
            self.dead_count += 1
        else:
            self.error_count += 1

        # Emit single result and updated summary
        self._emit("account_result", {
            "result": res,
            "summary": self.get_summary()
        })
