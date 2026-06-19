"""SERP 结果内存缓存 / In-memory SERP result cache."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from osint_toolkit.collectors.serp.models import SerpHit

_MAX_ENTRIES = 300
_store: OrderedDict[str, tuple[float, list[SerpHit], list[str]]] = OrderedDict()


def get_cached(key: str, ttl_sec: int) -> tuple[list[SerpHit], list[str]] | None:
    if ttl_sec <= 0:
        return None
    entry = _store.get(key)
    if not entry:
        return None
    if time.time() - entry[0] > ttl_sec:
        _store.pop(key, None)
        return None
    _store.move_to_end(key)
    return entry[1], entry[2]


def set_cached(key: str, hits: list[SerpHit], attempts: list[str]) -> None:
    _store[key] = (time.time(), hits, attempts)
    _store.move_to_end(key)
    while len(_store) > _MAX_ENTRIES:
        _store.popitem(last=False)


def clear_cache() -> None:
    _store.clear()


def cache_stats() -> dict[str, Any]:
    return {"entries": len(_store), "max_entries": _MAX_ENTRIES}
