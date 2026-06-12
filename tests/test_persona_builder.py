"""Persona builder limits."""

from __future__ import annotations

import inspect

from osint_toolkit.persona.builder import build_persona_draft


def test_build_persona_default_limits():
    sig = inspect.signature(build_persona_draft)
    assert sig.parameters["event_limit"].default == 500
    assert sig.parameters["feedback_limit"].default == 500


def test_build_persona_review_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)
    (tmp_path / "persona").mkdir(parents=True, exist_ok=True)
    (tmp_path / "persona" / "persona_brief.md").write_text("old brief", encoding="utf-8")

    result = build_persona_draft(use_ai=False, review=True)

    assert "review_summary" in result
    assert result["review_summary"]["brief_before"] == "old brief"
    assert result["review_summary"]["brief_after"]
