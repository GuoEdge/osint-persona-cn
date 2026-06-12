"""Query analyze tests."""

from __future__ import annotations

from osint_toolkit.ai.query_analyze import analyze_query


def test_analyze_query_no_ai_fallback():
    result = analyze_query("MCP 协议", ["zhihu", "web"], None, no_ai=True)
    assert result["expanded_queries"] == ["MCP 协议"]
    assert result["recommended_sources"] == ["zhihu", "web"]


def test_analyze_query_disabled_step():
    result = analyze_query(
        "test",
        ["bilibili"],
        None,
        disabled_steps=["query_analyze"],
    )
    assert result["intent"] == "test"
