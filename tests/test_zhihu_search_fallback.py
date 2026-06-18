"""Zhihu search fallback tests."""

from __future__ import annotations

import json

import pytest

from osint_toolkit.collectors.zhihu import ZhihuCollector
from osint_toolkit.models.intel_item import IntelItem


@pytest.mark.asyncio
async def test_site_search_type_inference(monkeypatch):
    col = ZhihuCollector()

    async def fake_site_search(self, _domain, _query, limit=10):
        from osint_toolkit.collectors.serp.models import SerpHit

        return [
            SerpHit(url="https://www.zhihu.com/question/1/answer/2", title="A"),
            SerpHit(url="https://zhuanlan.zhihu.com/p/3", title="B"),
            SerpHit(url="https://www.zhihu.com/question/4", title="Q"),
        ], []

    monkeypatch.setattr(
        "osint_toolkit.collectors.serp.engine.SerpEngine.site_search",
        fake_site_search,
    )

    items = await col._site_search("python", 5)
    types = {item.type for item in items}
    assert types == {"answer", "article", "question"}


@pytest.mark.asyncio
async def test_local_event_search_matches_tokens(monkeypatch, tmp_path):
    from osint_toolkit.storage import sqlite as sqlite_mod

    db_path = tmp_path / "events.db"
    monkeypatch.setattr(sqlite_mod, "get_db_path", lambda: db_path)

    conn = sqlite_mod.connect()
    conn.execute(
        "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
        (
            "zhihu_vote",
            json.dumps(
                {
                    "title": "Python 入门指南",
                    "url": "https://www.zhihu.com/question/1/answer/9",
                }
            ),
        ),
    )
    conn.commit()
    conn.close()

    col = ZhihuCollector()
    items = await col._local_event_search("Python", 5)
    assert len(items) == 1
    assert items[0].type == "answer"


@pytest.mark.asyncio
async def test_fallback_chain_playwright_then_serp(monkeypatch):
    col = ZhihuCollector()

    async def fail_playwright(*_a, **_k):
        raise RuntimeError("playwright blocked")

    async def ok_serp(_query, _limit):
        return [
            IntelItem(
                source="zhihu",
                type="answer",
                url="https://www.zhihu.com/question/1/answer/2",
                title="SERP 兜底",
                content="",
            )
        ]

    monkeypatch.setattr(col, "_playwright_search", fail_playwright)
    monkeypatch.setattr(col, "_site_search", ok_serp)

    items = await col._run_search_fallbacks("test", 3)
    assert len(items) == 1
    assert items[0].title == "SERP 兜底"
