"""Network-first alias discovery tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from osint_toolkit.ai.alias_discover import discover_aliases, heuristic_aliases, probe_network
from osint_toolkit.ai.query_expand import expand_query
from osint_toolkit.models.intel_item import IntelItem


def test_heuristic_aliases_from_titles():
    items = [
        IntelItem(
            source="bilibili",
            type="video",
            url="https://bilibili.com/1",
            title="【Mujica】丰川祥子名场面「小祥」合集",
            content="祥处梗解析",
        ),
        IntelItem(
            source="zhihu",
            type="answer",
            url="https://zhihu.com/2",
            title="如何评价 Ob一串字母女士",
            content="丰川祥子相关讨论",
        ),
    ]
    aliases = heuristic_aliases("丰川祥子", items)
    assert "小祥" in aliases or "Mujica" in aliases


def test_expand_query_prioritizes_network_aliases():
    result = expand_query(
        "丰川祥子",
        ["bilibili"],
        None,
        no_ai=True,
        discovered_aliases=["网络新梗", "小祥"],
    )
    queries = result["queries_used"]
    assert queries[0] == "丰川祥子"
    assert "网络新梗" in queries
    assert result["network_aliases"] == ["网络新梗", "小祥"]


@pytest.mark.asyncio
async def test_probe_network_aggregates(monkeypatch):
    async def fake_bili(q, limit):
        return [IntelItem(source="bilibili", type="video", url="u", title=q, content="")]

    async def fake_zhihu(q, limit):
        return []

    async def fake_web(q, limit):
        return []

    monkeypatch.setattr(
        "osint_toolkit.ai.alias_discover._probe_source",
        lambda name, q, limit: fake_bili(q, limit)
        if name == "bilibili"
        else (fake_zhihu(q, limit) if name == "zhihu" else fake_web(q, limit)),
    )
    items = await probe_network("test", ["bilibili", "zhihu", "web"], limit=3)
    assert len(items) >= 1


@pytest.mark.asyncio
async def test_discover_persists_aliases(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))

    async def fake_probe(query, sources=None, *, limit=5):
        return [
            IntelItem(
                source="v2ex",
                type="topic",
                url="https://v2ex.com/t/1",
                title="关于小祥的讨论",
                content="丰川祥子",
            )
        ]

    monkeypatch.setattr("osint_toolkit.ai.alias_discover.probe_network", fake_probe)
    monkeypatch.setattr(
        "osint_toolkit.ai.alias_discover.ai_extract_aliases",
        lambda *a, **k: (["小祥"], [{"term": "小祥", "type": "nickname"}]),
    )
    monkeypatch.setattr(
        "osint_toolkit.ai.alias_discover.heuristic_aliases",
        lambda *a, **k: ["小祥"],
    )

    result = await discover_aliases("丰川祥子", ["bilibili", "v2ex"], no_ai=False)
    assert "小祥" in result["discovered_aliases"]
    assert result["persist"]["saved"] is True
    assert (tmp_path / "entities" / "discovered.yaml").exists()


def test_ai_extract_requires_evidence_items():
    from osint_toolkit.ai.alias_discover import ai_extract_aliases

    terms, details = ai_extract_aliases("丰川祥子", [], no_ai=True)
    assert terms == []
    assert details == []


@pytest.mark.asyncio
async def test_discover_runs_heuristic_without_ai(monkeypatch):
    async def fake_probe(query, sources=None, *, limit=5):
        return [
            IntelItem(
                source="bilibili",
                type="video",
                url="https://bilibili.com/1",
                title="【小祥】丰川祥子剪辑",
                content="",
            )
        ]

    monkeypatch.setattr("osint_toolkit.ai.alias_discover.probe_network", fake_probe)
    result = await discover_aliases("丰川祥子", ["bilibili"], no_ai=True)
    assert result.get("probe_count", 0) >= 1
    assert result.get("discovered_aliases")
