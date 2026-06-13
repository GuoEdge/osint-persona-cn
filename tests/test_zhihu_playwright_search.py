"""Zhihu Playwright search tier tests."""

from __future__ import annotations

import pytest

from osint_toolkit.collectors.zhihu import ZhihuCollector


@pytest.mark.asyncio
async def test_zhihu_search_playwright_fallback(monkeypatch):
    col = ZhihuCollector()

    async def fail_api(_query, _limit):
        raise RuntimeError("api blocked")

    sample = {
        "data": [
            {
                "object": {
                    "type": "answer",
                    "id": 99,
                    "excerpt": "摘要",
                    "voteup_count": 1,
                    "comment_count": 0,
                    "author": {"name": "作者"},
                    "question": {"id": 1, "title": "问题标题"},
                }
            }
        ]
    }

    async def ok_pw(_query, _limit):
        return [
            col._parse_object(sample["data"][0]["object"]),
        ]

    monkeypatch.setattr(col, "_api_search", fail_api)
    monkeypatch.setattr(col, "_playwright_search", ok_pw)

    items = await col.search("测试", limit=5)
    assert len(items) == 1
    assert items[0].type == "answer"
    assert "问题标题" in items[0].title


@pytest.mark.asyncio
async def test_zhihu_playwright_search_parses_payload(monkeypatch):
    col = ZhihuCollector()
    payload = {
        "data": [
            {
                "object": {
                    "type": "article",
                    "url": "https://zhuanlan.zhihu.com/p/1",
                    "title": "文章",
                    "excerpt": "内容",
                    "author": {"name": "A"},
                    "voteup_count": 2,
                }
            }
        ]
    }

    async def fake_fetch(_query, limit=10):
        assert limit == 3
        return payload

    monkeypatch.setattr(
        "osint_toolkit.ingest.zhihu_playwright.fetch_search_v3",
        fake_fetch,
    )
    monkeypatch.setattr(
        "osint_toolkit.ingest.playwright_session.playwright_available",
        lambda: True,
    )

    items = await col._playwright_search("关键词", limit=3)
    assert len(items) == 1
    assert items[0].type == "article"
    assert items[0].title == "文章"
