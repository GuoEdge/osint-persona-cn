"""Entity store persistence tests."""

from __future__ import annotations

import yaml

from osint_toolkit.ai.entity_store import classify_slurs, merge_discovered_aliases


def test_merge_discovered_aliases_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    first = merge_discovered_aliases("丰川祥子", ["小祥", "祥子碳"], ["祥处"])
    assert first["saved"] is True
    assert "小祥" in first["added_aliases"]
    assert "祥处" in first["added_slurs"]

    second = merge_discovered_aliases("丰川祥子", ["小祥", "网络新梗"], [])
    assert second["saved"] is True
    assert second["added_aliases"] == ["网络新梗"]
    assert "小祥" not in second.get("added_aliases", [])

    path = tmp_path / "entities" / "discovered.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entry = data["entities"]["丰川祥子"]
    assert "小祥" in entry["aliases"]
    assert "网络新梗" in entry["aliases"]
    assert "祥处" in entry["slurs"]
    assert entry["meta"]["auto_discovered"] is True


def test_classify_slurs_from_ai_details():
    discovered = ["小祥", "祥处", "Sakiko"]
    details = [
        {"term": "祥处", "type": "slur"},
        {"term": "小祥", "type": "nickname"},
    ]
    aliases, slurs = classify_slurs(discovered, details, include_slurs=True)
    assert "祥处" in slurs
    assert "小祥" in aliases
    assert "Sakiko" in aliases
