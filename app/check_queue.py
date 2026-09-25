"""Small bounded, aging priority executor for network work (no database access)."""
from concurrent.futures import Future
from threading import Condition, Thread
from time import monotonic


class CheckQueue:
    def __init__(self, max_workers=5):
        self._condition = Condition()
        self._items = []
        self._closed = False
        self._sequence = 0
        self._threads = [Thread(target=self._work, daemon=True, name=f"checker-{i}")
                         for i in range(max_workers)]
        for thread in self._threads:
            thread.start()

    def submit(self, fn, *args, priority=10):
        future = Future()
        with self._condition:
            if self._closed:
                raise RuntimeError("Checker đang dừng")
            self._sequence += 1
            self._items.append((priority, monotonic(), self._sequence, future, fn, args))
            self._condition.notify()
        return future

    def _work(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._items)
                if not self._items:
                    return
                now = monotonic()
                # A normal task waiting 50s overtakes a newly queued priority-0
                # task. Priority never preempts work or starves other users.
                index = min(range(len(self._items)), key=lambda i: (
                    self._items[i][0] - (now - self._items[i][1]) / 5,
                    self._items[i][2],
                ))
                _, _, _, future, fn, args = self._items.pop(index)
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(fn(*args))
                except BaseException as exc:
                    future.set_exception(exc)

    def shutdown(self, wait=False, cancel_futures=False):
        with self._condition:
            self._closed = True
            if cancel_futures:
                for item in self._items:
                    item[3].cancel()
                self._items.clear()
            self._condition.notify_all()
        if wait:
            for thread in self._threads:
                thread.join()
