"""High-dwell auto-save tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.ingest.dwell_save import collect_dwell_save_urls, is_saveable_content_url
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.web.app import create_app


def test_is_saveable_video():
    assert is_saveable_content_url("https://www.bilibili.com/video/BV1xx411c7mD")
    assert not is_saveable_content_url("https://www.bilibili.com/account/history")


def test_collect_dwell_urls():
    payloads = [
        {
            "kind": "page_session",
            "url": "https://www.zhihu.com/question/123456/answer/789",
            "duration_ms": 120_000,
        },
        {
            "kind": "page_session",
            "url": "https://www.bilibili.com/",
            "duration_ms": 200_000,
        },
    ]
    urls = collect_dwell_save_urls(payloads)
    assert len(urls) == 1
    assert "zhihu.com" in urls[0]


def test_score_high_dwell():
    assert score_event("ext_page_dwell", {"duration_ms": 120_000}) > score_event(
        "ext_page_visit", {"url": "https://x.com"}
    )


@pytest.fixture
def client():
    return TestClient(create_app())


def test_dwell_triggers_knowledge_save(client, tmp_path, monkeypatch):
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)

    mock_item = type("Item", (), {"url": "https://www.bilibili.com/video/BV1111111111"})()
    with patch("osint_toolkit.services.save.save_url", new_callable=AsyncMock) as mock_save:
        mock_save.return_value = {"item": mock_item, "card_path": "/tmp/x.md"}
        payload = {
            "events": [
                {
                    "kind": "page_session",
                    "url": "https://www.bilibili.com/video/BV1111111111",
                    "title": "长视频",
                    "duration_ms": 100_000,
                    "platform": "bilibili",
                }
            ],
        }
        r = client.post("/api/extension/events", json=payload)
        assert r.status_code == 200
        assert r.json().get("saved_to_knowledge", 0) >= 1
        mock_save.assert_called()
