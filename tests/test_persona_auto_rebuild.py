"""Persona auto-rebuild tests."""

from __future__ import annotations

import pytest

from osint_toolkit.persona.auto_rebuild import get_auto_rebuild_mode, maybe_auto_rebuild_persona
from osint_toolkit.persona.context import is_persona_stale
from osint_toolkit.storage.sqlite import connect


def test_first_build_stale_at_ten_events(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)
    (tmp_path / "persona").mkdir(parents=True, exist_ok=True)

    conn = connect()
    for _ in range(9):
        conn.execute("INSERT INTO events (event_type, data_json) VALUES ('ext_page_visit', '{}')")
    conn.commit()
    conn.close()
    assert is_persona_stale() is False

    conn = connect()
    conn.execute("INSERT INTO events (event_type, data_json) VALUES ('ext_page_visit', '{}')")
    conn.commit()
    conn.close()
    from osint_toolkit.persona.context import get_event_count

    assert get_event_count() == 10
    assert is_persona_stale() is True


@pytest.mark.asyncio
async def test_prompt_mode_suggests_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)
    (tmp_path / "persona").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "osint_toolkit.persona.auto_rebuild.load_config",
        lambda: {"ai": {"auto_persona_rebuild": "prompt", "auto_persona_rebuild_threshold": 50}},
    )

    conn = connect()
    for _ in range(12):
        conn.execute("INSERT INTO events (event_type, data_json) VALUES ('ext_page_visit', '{}')")
    conn.commit()
    conn.close()

    result = await maybe_auto_rebuild_persona()
    assert result.get("action") == "suggested"
    assert result.get("persona_rebuild_suggested") is True
    assert get_auto_rebuild_mode() == "prompt"
