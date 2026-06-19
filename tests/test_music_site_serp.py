"""Music site collectors use SERP snippets only (no login-gated page fetch)."""

from __future__ import annotations

import pytest

from osint_toolkit.collectors.registry import COLLECTORS
from osint_toolkit.collectors.serp.models import SerpHit


@pytest.mark.asyncio
async def test_netease_music_skips_content_fetch(monkeypatch):
    collector_cls = COLLECTORS["netease_music"]
    collector = collector_cls()

    async def fake_site(self, domain, query, limit=10):
        return (
            [SerpHit(title="Song", url="https://music.163.com/song/1", snippet="lyrics", engine="bing_html", query=query)],
            ["bing_html: ok (1)"],
        )

    fetch_called = {"n": 0}

    async def fake_fetch(self, url):
        fetch_called["n"] += 1
        raise AssertionError("should not fetch music page")

    monkeypatch.setattr(collector_cls, "search", collector_cls.search)
    from osint_toolkit.collectors.serp.engine import SerpEngine

    monkeypatch.setattr(SerpEngine, "site_search", fake_site)
    from osint_toolkit.collectors.web import WebCollector

    monkeypatch.setattr(WebCollector, "fetch", fake_fetch)

    items = await collector.search("晴天", limit=3)
    assert len(items) == 1
    assert fetch_called["n"] == 0
    assert items[0].personal.get("content_fetched") is not True
