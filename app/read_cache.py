"""Bounded short-lived cache. Callers must authorize BEFORE accessing it."""
from threading import RLock
from time import monotonic

_lock = RLock()
_values = {}
_generation = 0


def invalidate_reads(data_only=False):
    global _generation
    with _lock:
        _generation += 1
        if data_only:
            for key in list(_values):
                if key[0] != "recipients":
                    _values.pop(key, None)
        else:
            _values.clear()


def cached_read(key, loader, ttl=15):
    with _lock:
        generation = _generation
        cached = _values.get(key)
        if cached and cached[0] > monotonic():
            return cached[1]
    # Never hold a cache lock while waiting for a database connection.
    value = loader()
    with _lock:
        if generation == _generation:
            if len(_values) >= 256:
                _values.pop(next(iter(_values)))
            _values[key] = (monotonic() + ttl, value)
    return value
