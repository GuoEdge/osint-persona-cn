"""Multi-query search collection tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import search as search_mod


@pytest.mark.asyncio
async def test_collect_uses_multiple_queries(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_collect(source: str, query: str, limit: int):
        calls.append((source, query))
        return [
            IntelItem(
                source=source,
                type="video",
                url=f"https://example.com/{source}/{query}",
                title=f"{query} title",
                content=query,
            )
        ]

    monkeypatch.setattr(search_mod, "_collect_source", fake_collect)
    monkeypatch.setattr(
        search_mod,
        "expand_query",
        lambda *a, **k: {
            "intent": "丰川祥子",
            "queries_used": ["丰川祥子", "祥子", "小祥"],
            "aliases": ["祥子", "小祥"],
            "recommended_sources": ["bilibili"],
            "expanded_queries": ["丰川祥子", "祥子", "小祥"],
        },
    )
    monkeypatch.setattr(search_mod, "maybe_load_persona_context", lambda: None)
    monkeypatch.setattr(search_mod, "summarize_batch", lambda *a, **k: [])
    monkeypatch.setattr(search_mod, "simulate_items", lambda *a, **k: [])
    monkeypatch.setattr(search_mod, "_mine_comments", AsyncMock(return_value=[]))

    with patch.object(search_mod, "sync_browser_cookies"):
        result = await search_mod.run_search(
            "丰川祥子",
            sources=["bilibili"],
            limit=10,
            no_ai=True,
            no_simulate=True,
            comment_mine_top=0,
        )

    assert len(calls) == 3
    queries_called = {q for _, q in calls}
    assert queries_called == {"丰川祥子", "祥子", "小祥"}
    items = result["items"]
    assert len(items) == 3
    for item in items:
        assert item.personal.get("matched_queries")


@pytest.mark.asyncio
async def test_run_search_discovers_when_no_ai(monkeypatch):
    discover_calls: list[bool] = []

    async def fake_discover(*args, **kwargs):
        discover_calls.append(kwargs.get("no_ai", False))
        return {"discovered_aliases": ["小祥"], "probe_count": 1}

    monkeypatch.setattr(search_mod, "discover_aliases", fake_discover)
    monkeypatch.setattr(search_mod, "_collect_source", AsyncMock(return_value=[]))
    monkeypatch.setattr(search_mod, "maybe_load_persona_context", lambda: None)
    monkeypatch.setattr(search_mod, "summarize_batch", lambda *a, **k: [])
    monkeypatch.setattr(search_mod, "simulate_items", lambda *a, **k: [])
    monkeypatch.setattr(search_mod, "_mine_comments", AsyncMock(return_value=[]))

    with patch.object(search_mod, "sync_browser_cookies"):
        await search_mod.run_search(
            "丰川祥子",
            sources=["bilibili"],
            limit=10,
            no_ai=True,
            no_simulate=True,
            comment_mine_top=0,
        )

    assert discover_calls == [True]
