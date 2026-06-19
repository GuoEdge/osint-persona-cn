"""Query expansion tests."""

from __future__ import annotations

import textwrap

import yaml

from osint_toolkit.ai.query_expand import (
    _entity_aliases_for_query,
    _rule_expand,
    expand_query,
    per_query_limit,
)


def test_rule_expand_chinese_name():
    aliases = _rule_expand("丰川祥子")
    assert "祥子" in aliases
    assert "小祥" in aliases
    assert "祥子酱" not in aliases


def test_rule_expand_skips_when_enough_existing():
    aliases = _rule_expand("丰川祥子", existing_aliases=["祥子", "小祥", "网络梗"])
    assert aliases == []


def test_entity_partial_match(tmp_path, monkeypatch):
    entities_dir = tmp_path / "entities"
    entities_dir.mkdir()
    (entities_dir / "test.yaml").write_text(
        yaml.safe_dump(
            {"entities": {"丰川祥子": {"aliases": ["祥子", "Sakiko"], "slurs": []}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    aliases = _entity_aliases_for_query("祥子", include_slurs=False)
    assert "丰川祥子" in aliases
    assert "Sakiko" not in aliases


def test_entity_aliases_with_slurs(tmp_path, monkeypatch):
    entities_dir = tmp_path / "entities"
    entities_dir.mkdir()
    (entities_dir / "test.yaml").write_text(
        yaml.safe_dump(
            {
                "entities": {
                    "丰川祥子": {
                        "aliases": ["祥子", "Ob一串字母女士"],
                        "slurs": ["祥处"],
                    }
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    with_slurs = _entity_aliases_for_query("丰川祥子", include_slurs=True)
    without_slurs = _entity_aliases_for_query("丰川祥子", include_slurs=False)
    assert "祥子" in with_slurs
    assert "祥处" in with_slurs
    assert "祥处" not in without_slurs


def test_expand_query_no_ai_merges_rules(tmp_path, monkeypatch):
    entities_dir = tmp_path / "entities"
    entities_dir.mkdir()
    (entities_dir / "bd.yaml").write_text(
        textwrap.dedent(
            """
            entities:
              丰川祥子:
                aliases: [祥子]
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    result = expand_query("丰川祥子", ["bilibili"], None, no_ai=True)
    queries = result["queries_used"]
    assert queries[0] == "丰川祥子"
    assert "祥子" in queries
    assert len(queries) >= 2


def test_expand_query_aliases_respect_max_queries(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.ai.query_expand.get_search_config",
        lambda: {"max_expanded_queries": 2, "include_slurs": True},
    )
    result = expand_query(
        "丰川祥子",
        ["bilibili"],
        None,
        no_ai=True,
        discovered_aliases=["祥子", "小祥", "字幕:ai"],
    )
    assert result["queries_used"] == ["丰川祥子", "祥子"]
    assert result["aliases"] == ["祥子"]
    assert "字幕:ai" not in result["aliases"]


def test_expand_query_filters_noisy_entity_aliases(tmp_path, monkeypatch):
    entities_dir = tmp_path / "entities"
    entities_dir.mkdir()
    (entities_dir / "mcp.yaml").write_text(
        yaml.safe_dump(
            {
                "entities": {
                    "MCP": {
                        "aliases": ["zhihu.comhttps:", "LLM", "MCP的前景如何？"],
                        "slurs": [],
                    }
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    result = expand_query("MCP", ["zhihu"], None, no_ai=True)
    queries = result["queries_used"]
    assert queries[0] == "MCP"
    assert "zhihu.comhttps:" not in queries
    assert "MCP的前景如何？" not in queries


def test_per_query_limit_scales(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.ai.query_expand.get_search_config",
        lambda: {"per_query_limit_ratio": 0.6, "zhihu_aggressive": False},
    )
    assert per_query_limit(10, 3) >= 3
    assert per_query_limit(10, 1) == 6


def test_per_query_limit_aggressive_floor(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.ai.query_expand.get_search_config",
        lambda: {"per_query_limit_ratio": 0.6, "zhihu_aggressive": True, "zhihu_per_query_limit_min": 20},
    )
    assert per_query_limit(25, 1) == 20
    assert per_query_limit(10, 1) == 10


def test_expand_query_glm52_stays_tight(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.ai.query_expand.get_search_config",
        lambda: {
            "max_expanded_queries": 8,
            "max_expanded_queries_narrow": 4,
            "include_slurs": True,
            "rule_expand_enabled": True,
        },
    )
    result = expand_query(
        "glm5.2",
        ["bilibili", "zhihu"],
        None,
        no_ai=True,
        discovered_aliases=["GLM-5.2", "字幕:ai", "论文精读", "康奈尔笔记法"],
    )
    queries = result["queries_used"]
    assert queries[0] == "glm5.2"
    assert "GLM-5.2" in queries
    assert "字幕:ai" not in queries
    assert "论文精读" not in queries
    assert "康奈尔笔记法" not in queries
    assert len(queries) <= 4
