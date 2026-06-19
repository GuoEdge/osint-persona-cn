"""Persona version history and rollback tests."""

from __future__ import annotations

from osint_toolkit.persona.store import (
    archive_brief_version,
    list_version_entries,
    load_persona_brief,
    persona_brief_path,
    rollback_version,
    save_mental_model,
    save_persona_brief,
)


def test_list_version_entries_uses_file_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    persona = tmp_path / "persona"
    persona.mkdir(parents=True)
    save_mental_model({"version": 2, "built_at": "2026-06-19T06:00:00+00:00", "events_at_last_build": 99})
    (persona / "mental_model.v1.yaml").write_text("version: 1\nevents_at_last_build: 10\n", encoding="utf-8")

    entries = list_version_entries(current_version=2)
    versions = {int(e["version"]) for e in entries}
    assert versions == {1, 2}
    current = next(e for e in entries if e["is_current"])
    assert current["version"] == 2
    assert current["events_at_last_build"] == 99


def test_rollback_restores_brief_archive(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    persona = tmp_path / "persona"
    persona.mkdir(parents=True)
    (persona / "mental_model.v3.yaml").write_text("version: 3\nsummary: old model\n", encoding="utf-8")
    (persona / "persona_brief.v3.md").write_text("# old brief\n", encoding="utf-8")
    save_mental_model({"version": 5, "summary": "new model"})
    save_persona_brief("# new brief\n")

    assert rollback_version(3) is True
    assert "old model" in (persona / "mental_model.yaml").read_text(encoding="utf-8")
    assert load_persona_brief().startswith("# old brief")


def test_archive_brief_version_copies_once(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    (tmp_path / "persona").mkdir(parents=True)
    save_persona_brief("hello")
    archive_brief_version(1)
    archive_brief_version(1)
    assert (tmp_path / "persona" / "persona_brief.v1.md").read_text(encoding="utf-8") == "hello"
    assert persona_brief_path().read_text(encoding="utf-8") == "hello"
