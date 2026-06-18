"""Browser history ingest tests."""

from __future__ import annotations

from osint_toolkit.ingest.browser import _should_skip_url
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.storage.sqlite import connect


def test_should_skip_local_urls():
    assert _should_skip_url("http://127.0.0.1:8787/") is True
    assert _should_skip_url("https://www.bilibili.com/video/BV1") is False


def test_log_event_deduped_for_browser_visit():
    from uuid import uuid4

    from osint_toolkit.storage.knowledge import log_event_deduped

    entry = {
        "source": "browser",
        "url": "https://example.com/a",
        "title": "A",
        "visited_at": "2026-06-13T10:00:00+00:00",
    }
    key = f"browser_visit:test-{uuid4().hex}"
    assert log_event_deduped("browser_visit", entry, key) is True
    assert log_event_deduped("browser_visit", entry, key) is False

    conn = connect()
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM events WHERE event_type='browser_visit' AND data_json LIKE ?",
        (f'%{entry["url"]}%',),
    ).fetchone()["c"]
    conn.close()
    assert count >= 1


def test_browser_visit_scores_for_persona():
    generic = score_event("browser_visit", {"url": "https://example.com/post"})
    interest = score_event(
        "browser_visit",
        {"url": "https://www.bilibili.com/video/BV1", "title": "AI"},
    )
    assert generic >= 8
    assert interest > generic
