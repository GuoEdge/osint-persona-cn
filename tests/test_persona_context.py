"""PersonaContext tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from osint_toolkit.persona.context import (
    PersonaContext,
    extract_topics,
    is_persona_stale,
    mark_persona_built,
)


def test_extract_topics_from_hints():
    hints = [
        {"title": "Python 异步编程实战"},
        {"title": "Python 类型系统入门"},
        {"title": "MCP 协议解析"},
    ]
    topics = extract_topics(hints, limit=5)
    assert "python" in topics or "异步" in topics or "python" in [t.lower() for t in topics]


def test_persona_stale_detection(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "osint_toolkit.persona.context.load_config",
        lambda: {"ai": {"auto_persona_rebuild_threshold": 10}},
    )
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)
    from osint_toolkit.storage import sqlite as sqlite_mod

    sqlite_mod._reset_pool_if_path_changed(db)

    counts = {"n": 5}
    monkeypatch.setattr("osint_toolkit.persona.context.get_event_count", lambda: counts["n"])

    mark_persona_built()
    assert is_persona_stale() is False

    counts["n"] = 17
    assert is_persona_stale() is True


def test_persona_context_dataclass():
    ctx = PersonaContext(brief="test", recent_topics=["ai"], structured={"interest_domains": []})
    assert ctx.brief == "test"
    assert "interest_domains" in ctx.structured
    assert ctx.stale is False


def test_persona_stale_detection_by_age(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "osint_toolkit.persona.context.load_config",
        lambda: {
            "ai": {
                "auto_persona_rebuild_threshold": 500,
                "auto_persona_rebuild_max_age_hours": 24,
            }
        },
    )

    from osint_toolkit.persona.store import load_mental_model, save_mental_model

    counts = {"n": 25}
    monkeypatch.setattr("osint_toolkit.persona.context.get_event_count", lambda: counts["n"])
    mark_persona_built()
    model = load_mental_model()
    model["built_at"] = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    save_mental_model(model)

    assert is_persona_stale() is True
