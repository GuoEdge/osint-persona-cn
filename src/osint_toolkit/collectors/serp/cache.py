"""SERP 结果内存缓存 / In-memory SERP result cache."""

from __future__ import annotations

import time
from typing import Any

from osint_toolkit.collectors.serp.models import SerpHit

_store: dict[str, tuple[float, list[SerpHit], list[str]]] = {}


def get_cached(key: str, ttl_sec: int) -> tuple[list[SerpHit], list[str]] | None:
    if ttl_sec <= 0:
        return None
    entry = _store.get(key)
    if not entry:
        return None
    if time.time() - entry[0] > ttl_sec:
        _store.pop(key, None)
        return None
    return entry[1], entry[2]


def set_cached(key: str, hits: list[SerpHit], attempts: list[str]) -> None:
    _store[key] = (time.time(), hits, attempts)


def clear_cache() -> None:
    _store.clear()


def cache_stats() -> dict[str, Any]:
    return {"entries": len(_store)}
