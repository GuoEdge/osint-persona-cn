"""Extension event ingestion tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.ingest.extension_events import normalize_extension_payload, parse_api_capture
from osint_toolkit.web.app import create_app


def test_parse_bilibili_comment_like_action():
    body = {
        "code": 0,
        "_osint_reply_action": {
            "type": "1",
            "oid": "123",
            "rpid": "456",
            "action": "1",
        },
    }
    rows = parse_api_capture("https://api.bilibili.com/x/v2/reply/action", body)
    assert len(rows) == 1
    assert rows[0][0] == "bilibili_comment_like"


def test_parse_bilibili_likes():
    body = {
        "code": 0,
        "data": {
            "list": [
                {"title": "测试视频", "bvid": "BV1xx411c7mD"},
            ]
        },
    }
    rows = parse_api_capture("https://api.bilibili.com/x/space/like/video?vmid=1", body)
    assert len(rows) == 1
    assert rows[0][0] == "bilibili_like"
    assert "BV1xx411c7mD" in rows[0][1]["url"]


def test_parse_zhihu_activities_dict_data():
    """Zhihu activities API may return data as a paging object, not a bare list."""
    body = {
        "data": {
            "data": [
                {
                    "verb": "赞同了回答",
                    "type": "ANSWER",
                    "target": {
                        "question": {"title": "测试问题", "id": 99},
                        "id": 100,
                    },
                }
            ],
            "paging": {"is_end": True},
        }
    }
    rows = parse_api_capture("https://www.zhihu.com/api/v4/members/me/activities", body)
    assert len(rows) == 1
    assert rows[0][0] == "zhihu_vote"


def test_parse_github_starred_graphql():
    body = {
        "data": {
            "viewer": {
                "starredRepositories": {
                    "nodes": [
                        {
                            "nameWithOwner": "octocat/Hello-World",
                            "url": "https://github.com/octocat/Hello-World",
                            "description": "My first repo",
                        }
                    ]
                }
            }
        }
    }
    rows = parse_api_capture("https://api.github.com/graphql", body)
    assert len(rows) == 1
    assert rows[0][0] == "github_star"
    assert rows[0][1]["url"] == "https://github.com/octocat/Hello-World"


def test_parse_zhihu_voteanswers():
    body = {
        "data": [
            {
                "target": {
                    "question": {"title": "如何学习 Python", "id": 123},
                    "id": 456,
                }
            }
        ]
    }
    rows = parse_api_capture("https://www.zhihu.com/api/v4/members/me/voteanswers", body)
    assert len(rows) == 1
    assert rows[0][0] == "zhihu_vote"
    assert "question/123/answer/456" in rows[0][1]["url"]


def test_page_session_min_duration():
    rows = normalize_extension_payload(
        {"kind": "page_session", "url": "https://www.bilibili.com/video/BV1", "title": "t", "duration_ms": 1000}
    )
    assert rows == []


def test_page_session_ok():
    rows = normalize_extension_payload(
        {"kind": "page_session", "url": "https://www.zhihu.com/question/1", "title": "t", "duration_ms": 5000}
    )
    assert len(rows) == 1
    assert rows[0][0] == "ext_page_dwell"


def test_page_visit_github():
    rows = normalize_extension_payload(
        {
            "kind": "page_visit",
            "url": "https://github.com/octocat/Hello-World",
            "title": "repo",
            "platform": "github",
        }
    )
    assert len(rows) == 1
    assert rows[0][0] == "ext_page_visit"
    assert rows[0][1]["source"] == "github"


@pytest.fixture
def client():
    return TestClient(create_app())


def test_extension_events_api(client, tmp_path, monkeypatch):
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)

    payload = {
        "events": [
            {
                "kind": "api_capture",
                "url": "https://api.bilibili.com/x/space/like/video?vmid=1",
                "body": {"code": 0, "data": {"list": [{"title": "A", "bvid": "BV1111111111"}]}},
            }
        ],
        "version": "0.1.0",
    }
    r = client.post("/api/extension/events", json=payload)
    assert r.status_code == 200
    assert r.json()["accepted"] == 1

    r2 = client.post("/api/extension/events", json=payload)
    assert r2.json()["skipped"] == 1

    status = client.get("/api/extension/status").json()
    assert status["extension_event_count"] == 1

    import sqlite3

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT event_type, data_json FROM events").fetchone()
    conn.close()
    assert row[0] == "bilibili_like"
    assert json.loads(row[1])["via"] == "extension"


@pytest.mark.asyncio
async def test_extension_batch_skips_bad_payload(tmp_path, monkeypatch):
    from osint_toolkit.services.extension import ingest_extension_batch

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)

    result = await ingest_extension_batch(
        [
            {"kind": "page_visit", "url": "https://github.com/a/b", "title": "ok", "platform": "github"},
            {
                "kind": "api_capture",
                "url": "https://www.zhihu.com/api/v4/members/x/activities",
                "body": {"data": {"paging": {"is_end": True}}},
            },
        ]
    )
    assert result["accepted"] >= 1
    assert not result.get("parse_errors")


def test_extension_ping(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    r = client.post("/api/extension/ping", json={"version": "0.1.0", "enabled": True})
    assert r.status_code == 200
    assert r.json()["ok"] is True
