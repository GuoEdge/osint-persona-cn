"""PersonaContext tests."""

from __future__ import annotations

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
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)

    from osint_toolkit.storage.sqlite import connect

    conn = connect()
    conn.execute("INSERT INTO events (event_type, data_json) VALUES ('ext_page_visit', '{}')")
    conn.commit()
    conn.close()

    mark_persona_built()
    assert is_persona_stale() is False

    conn = connect()
    for _ in range(55):
        conn.execute("INSERT INTO events (event_type, data_json) VALUES ('ext_page_visit', '{}')")
    conn.commit()
    conn.close()

    assert is_persona_stale() is True


def test_persona_context_dataclass():
    ctx = PersonaContext(brief="test", recent_topics=["ai"])
    assert ctx.brief == "test"
    assert ctx.stale is False
