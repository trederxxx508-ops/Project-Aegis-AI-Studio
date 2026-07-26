"""Cache TTL sederhana untuk membatasi panggilan API pasar.

Dipakai agar pemindaian watchlist tidak menembak yfinance berulang kali
untuk ticker yang sama dalam rentang waktu singkat.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def get(key: str, ttl_seconds: float) -> Any | None:
    """Ambil nilai jika masih segar, selain itu None."""
    with _lock:
        entry = _store.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if time.time() - stored_at > ttl_seconds:
        return None
    return value


def set(key: str, value: Any) -> None:  # noqa: A001 - meniru API cache biasa
    with _lock:
        _store[key] = (time.time(), value)


def get_or_compute(key: str, ttl_seconds: float, compute: Callable[[], Any]) -> Any:
    """Kembalikan nilai ter-cache, atau hitung lalu simpan."""
    cached = get(key, ttl_seconds)
    if cached is not None:
        return cached
    value = compute()
    set(key, value)
    return value


def clear() -> None:
    with _lock:
        _store.clear()


def stats() -> dict:
    with _lock:
        return {"entries": len(_store), "keys": sorted(_store.keys())}
