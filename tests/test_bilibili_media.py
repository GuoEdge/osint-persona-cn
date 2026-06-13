"""Bilibili subtitle/danmaku enrichment tests."""

from __future__ import annotations

import pytest

from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.ingest import bilibili_sdk
from osint_toolkit.models.intel_item import IntelItem


@pytest.mark.asyncio
async def test_enrich_video_adds_subtitle_and_danmaku(monkeypatch):
    item = IntelItem(
        source="bilibili",
        type="video",
        url="https://www.bilibili.com/video/BV1test",
        title="t",
        content="desc",
    )

    async def fake_subtitle(url: str):
        return {
            "text": "字幕正文",
            "track": {"lan_doc": "中文（自动生成）"},
            "source": "sdk",
        }

    async def fake_danmaku(url: str, *, max_lines: int | None = None):
        return ["哈哈哈", "哈哈哈", "前方高能"]

    async def fake_summary(top, *, no_ai: bool = False):
        return "弹幕摘要"

    monkeypatch.setattr(bilibili_sdk, "sdk_enabled", lambda feature: feature in {"subtitle", "danmaku"})
    monkeypatch.setattr(bilibili_sdk, "fetch_subtitle_for_url", fake_subtitle)
    monkeypatch.setattr(bilibili_sdk, "fetch_danmaku_lines", fake_danmaku)
    monkeypatch.setattr("osint_toolkit.analyzers.danmaku.summarize_danmaku", fake_summary)

    await bilibili_sdk.enrich_video_item(item)
    assert item.layers["subtitle"]["kind"] == "ai"
    assert "字幕正文" in item.content
    assert item.layers["danmaku_count"] == 3
    assert item.layers["danmaku_summary"] == "弹幕摘要"


def test_default_comment_mine_top_is_twelve():
    from osint_toolkit.utils.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["search"]["comment_mine_top"] == 12


@pytest.mark.asyncio
async def test_search_mine_enriches_bilibili_video(monkeypatch):
    from osint_toolkit.services import search as search_mod

    enriched: list[str] = []

    class FakeBili:
        async def enrich_video(self, item):
            enriched.append(item.url)
            item.layers["danmaku_summary"] = "dm"

        async def fetch_comments(self, url, limit=None):
            return [{"author": "u", "content": "c", "likes": 1, "rpid": 1}]

    class FakeZhihu:
        async def fetch_comments(self, url, limit=None):
            return []

    async def fake_summary(comments, no_ai=False):
        return "sum"

    monkeypatch.setattr(search_mod, "BilibiliCollector", FakeBili)
    monkeypatch.setattr(search_mod, "ZhihuCollector", FakeZhihu)
    monkeypatch.setattr(search_mod, "summarize_comments", fake_summary)

    items = [
        IntelItem(
            source="bilibili",
            type="video",
            url="https://www.bilibili.com/video/BV1",
            title="v",
            content="",
        )
    ]
    items[0].signals.relevance = 1.0

    mined = await search_mod._mine_comments(items, top=1, no_ai=True)
    assert enriched == ["https://www.bilibili.com/video/BV1"]
    assert mined[0]["danmaku_summary"] == "dm"
