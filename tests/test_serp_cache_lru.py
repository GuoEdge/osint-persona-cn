"""SERP 缓存 LRU 测试."""

from __future__ import annotations

from osint_toolkit.collectors.serp import cache as serp_cache
from osint_toolkit.collectors.serp.models import SerpHit


def test_serp_cache_evicts_oldest(monkeypatch):
    serp_cache.clear_cache()
    monkeypatch.setattr(serp_cache, "_MAX_ENTRIES", 2)
    hit = SerpHit(title="t", url="https://example.com", snippet="s", engine="web")
    serp_cache.set_cached("a", [hit], [])
    serp_cache.set_cached("b", [hit], [])
    serp_cache.set_cached("c", [hit], [])
    stats = serp_cache.cache_stats()
    assert stats["entries"] == 2
    assert serp_cache.get_cached("a", ttl_sec=600) is None
    assert serp_cache.get_cached("c", ttl_sec=600) is not None
