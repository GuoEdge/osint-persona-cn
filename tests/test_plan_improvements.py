"""搜索审查计划相关回归测试."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from osint_toolkit.ai.query_expand import expand_query, per_query_limit
from osint_toolkit.ai.step_registry import normalize_disabled_steps, normalize_step_id
from osint_toolkit.ai.steering import is_step_enabled
from osint_toolkit.collectors.comment_mine_registry import supports_comment_mine
from osint_toolkit.collectors.registry import COLLECTORS
from osint_toolkit.collectors.source_catalog import get_catalog_grouped
from osint_toolkit.collectors.source_resolve import _apply_source_overrides
from osint_toolkit.services.runs import show_run


def test_step_id_aliases():
    assert normalize_step_id("ai_summarize") == "summarize"
    assert normalize_step_id("summarize") == "summarize"
    assert "summarize" in normalize_disabled_steps(["ai_summarize", "summarize"])


def test_disabled_summarize_step():
    assert not is_step_enabled("summarize", disabled_steps=["ai_summarize"])
    assert is_step_enabled("summarize", disabled_steps=["report"])


def test_source_overrides_force_block():
    active, skipped = _apply_source_overrides(
        ["zhihu", "web"],
        ["bilibili"],
        overrides={"force": ["bilibili"], "block": ["web"]},
    )
    assert "bilibili" in active
    assert "web" not in active
    assert "zhihu" in active


def test_catalog_depth_metadata():
    groups = get_catalog_grouped()
    assert len(groups) == 6
    hub = next(g for g in groups if g["id"] == "community_hub")
    hub_ids = {s["id"] for s in hub["sources"]}
    assert {"v2ex", "weibo", "nga"}.issubset(hub_ids)
    assert groups[0]["tier"] == "primary"
    flat = [s for g in groups for s in g["sources"]]
    zh = next(s for s in flat if s["id"] == "zhihu")
    gh = next(s for s in flat if s["id"] == "github")
    weibo = next(s for s in flat if s["id"] == "weibo")
    assert zh["depth"] == "hybrid"
    assert gh["kind"] == "native"
    assert weibo["depth"] == "serp"


def test_github_native_collector_registered():
    assert "github" in COLLECTORS
    assert COLLECTORS["github"].__name__ == "GithubCollector"


def test_comment_mine_registry():
    assert supports_comment_mine("zhihu")
    assert supports_comment_mine("v2ex")
    assert not supports_comment_mine("web")


def test_expand_query_respects_profile(monkeypatch, tmp_path):
    monkeypatch.setattr("osint_toolkit.pipeline.context.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "osint_toolkit.ai.query_expand.get_search_config",
        lambda: {"max_expanded_queries": 5, "include_slurs": True, "discover_aliases": False},
    )
    monkeypatch.setattr(
        "osint_toolkit.collectors.source_resolve.resolve_search_sources",
        lambda *a, **k: (["zhihu"], [], {}),
    )
    monkeypatch.setattr(
        "osint_toolkit.ai.query_expand.apply_source_routing",
        lambda *a, **k: {"active_sources": ["zhihu"], "score_breakdown": {}, "hint": ""},
    )
    result = expand_query("测试话题", ["zhihu"], None, no_ai=True, profile="zhihu_deep")
    assert result["active_sources"] == ["zhihu"]


def test_show_run_merges_source_plan(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-e1f2a3b4"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "command": "search", "query": "q", "status": "done"}),
        encoding="utf-8",
    )
    (run_dir / "source_plan.json").write_text(
        json.dumps(
            {
                "step": "ai_source_plan",
                "data": {
                    "source_plan": {"topic_summary": "测试", "reasoning_chain": []},
                    "source_routing": {"active_sources": ["zhihu"], "score_breakdown": {}},
                    "active_sources": ["zhihu"],
                },
            }
        ),
        encoding="utf-8",
    )
    data = show_run(run_id)
    assert data["source_plan"]["topic_summary"] == "测试"
    assert data["collect_sources"] == ["zhihu"]


@pytest.mark.asyncio
async def test_disabled_comment_mine_skips(monkeypatch, tmp_path):
    from osint_toolkit.models.intel_item import IntelItem
    from osint_toolkit.services import search as search_service

    monkeypatch.setattr("osint_toolkit.pipeline.context.get_data_dir", lambda: tmp_path)
    items = [
        IntelItem(source="zhihu", type="answer", url="https://zhihu.com/a/1", title="t", content="c"),
    ]
    mined = await search_service._mine_comments(
        items, top=5, no_ai=False, disabled_steps=["comment_mine"]
    )
    assert mined == []


def test_summarize_batch_respects_disabled(monkeypatch):
    from osint_toolkit.ai.summarize import summarize_batch
    from osint_toolkit.models.intel_item import IntelItem

    called = {"n": 0}

    def fake_client(*args, **kwargs):
        called["n"] += 1
        return MagicMock()

    monkeypatch.setattr("osint_toolkit.ai.summarize.DeepSeekClient", fake_client)
    items = [IntelItem(source="web", type="t", url="https://x", title="a", content="b")]
    out = summarize_batch(items, no_ai=False, disabled_steps=["ai_summarize"])
    assert len(out) == 1
    assert out[0]["meta"]["ai_invoked"] is False
    assert called["n"] == 0
