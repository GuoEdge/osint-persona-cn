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


def test_per_query_limit_scales():
    assert per_query_limit(10, 3) >= 3
    assert per_query_limit(10, 1) == 6
