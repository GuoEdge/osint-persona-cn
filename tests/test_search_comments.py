"""Search comment mining pipeline tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import search as search_mod


@pytest.mark.asyncio
async def test_mine_comments_before_summarize(monkeypatch):
    order: list[str] = []
    bili_item = IntelItem(
        source="bilibili",
        type="video",
        url="https://www.bilibili.com/video/BV1test",
        title="test video",
        content="about 祥子",
    )
    bili_item.signals.relevance = 0.9

    async def fake_collect(source: str, query: str, limit: int):
        return [bili_item] if source == "bilibili" else []

    async def fake_mine(items, *, top, no_ai):
        order.append("mine")
        items[0].layers["comments_summary"] = "社区观点测试"
        return [{"item_id": items[0].id, "comments_summary": "社区观点测试"}]

    def fake_summarize(*args, **kwargs):
        order.append("summarize")
        return []

    monkeypatch.setattr(search_mod, "_collect_source", fake_collect)
    monkeypatch.setattr(
        search_mod,
        "expand_query",
        lambda *a, **k: {
            "queries_used": ["test"],
            "aliases": [],
            "recommended_sources": ["bilibili"],
            "expanded_queries": ["test"],
            "intent": "test",
        },
    )
    monkeypatch.setattr(search_mod, "maybe_load_persona_context", lambda: None)
    monkeypatch.setattr(search_mod, "_mine_comments", fake_mine)
    monkeypatch.setattr(search_mod, "summarize_batch", fake_summarize)
    monkeypatch.setattr(search_mod, "simulate_items", lambda *a, **k: [])

    with patch.object(search_mod, "sync_browser_cookies"):
        result = await search_mod.run_search(
            "test",
            sources=["bilibili"],
            limit=5,
            no_ai=True,
            no_simulate=True,
            comment_mine_top=1,
        )

    assert order == ["mine", "summarize"]
    assert result["items"][0].layers.get("comments_summary") == "社区观点测试"


def test_report_payload_includes_comments_summary():
    from osint_toolkit.ai.report import _fallback_report

    item = IntelItem(
        source="bilibili",
        type="video",
        url="https://example.com",
        title="t",
        content="c",
    )
    item.layers["comments_summary"] = "热评归纳"
    text = _fallback_report("q", [item], "run-1")
    assert "社区观点" in text
    assert "热评归纳" in text
