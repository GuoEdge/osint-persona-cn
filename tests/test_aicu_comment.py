"""AICU ingest and Bilibili comment event tests."""

from __future__ import annotations

import json

import pytest

from osint_toolkit.ingest.aicu import (
    extract_replies_from_payload,
    ingest_aicu_from_json,
    parent_url_from_dyn,
    parse_aicu_page,
    parse_aicu_reply,
)
from osint_toolkit.ingest.extension_events import parse_api_capture
from osint_toolkit.storage.sqlite import connect


def test_parent_url_from_dyn_video_with_bvid():
    url = parent_url_from_dyn({"oid": "12345", "type": 1}, aid_bvid={"12345": "BV1test000"})
    assert url == "https://www.bilibili.com/video/BV1test000"


def test_parent_url_from_dyn_video_fallback_av():
    url = parent_url_from_dyn({"oid": "999", "type": 1})
    assert url == "https://www.bilibili.com/video/av999"


def test_parent_url_from_dyn_article():
    url = parent_url_from_dyn({"oid": "12357091", "type": 12})
    assert url == "https://www.bilibili.com/read/cv12357091"


def test_parse_aicu_reply():
    entry = parse_aicu_reply(
        {
            "rpid": "272676426369",
            "message": "在ae里调用的哪个效果啊",
            "time": 1756125884,
            "dyn": {"oid": "115055295270376", "type": 1},
        },
        aid_bvid={"115055295270376": "BV1xx411c7mD"},
    )
    assert entry is not None
    assert entry["rpid"] == "272676426369"
    assert entry["event_kind"] == "comment_post"
    assert entry["via"] == "aicu"
    assert "BV1xx411c7mD" in entry["url"]


def test_parse_aicu_page():
    body = {
        "code": 0,
        "data": {
            "cursor": {"is_end": False, "all_count": 2},
            "replies": [{"rpid": "1", "message": "hi", "dyn": {"oid": "1", "type": 1}}],
        },
    }
    replies, is_end, all_count = parse_aicu_page(body)
    assert len(replies) == 1
    assert is_end is False
    assert all_count == 2


def test_parse_reply_action_like():
    body = {
        "code": 0,
        "_osint_reply_action": {
            "type": "1",
            "oid": "243322853",
            "rpid": "3039053308",
            "action": "1",
        },
    }
    rows = parse_api_capture("https://api.bilibili.com/x/v2/reply/action", body)
    assert len(rows) == 1
    assert rows[0][0] == "bilibili_comment_like"
    assert rows[0][1]["rpid"] == "3039053308"
    assert "av243322853" in rows[0][1]["url"]


def test_parse_reply_action_unlike_skipped():
    body = {
        "code": 0,
        "_osint_reply_action": {"type": "1", "oid": "1", "rpid": "2", "action": "0"},
    }
    rows = parse_api_capture("https://api.bilibili.com/x/v2/reply/action", body)
    assert rows == []


def test_parse_reply_main_liked_comments():
    body = {
        "code": 0,
        "data": {
            "replies": [
                {
                    "rpid": 100,
                    "oid": 200,
                    "type": 1,
                    "action": 1,
                    "content": {"message": "好评论"},
                },
                {
                    "rpid": 101,
                    "oid": 200,
                    "type": 1,
                    "action": 0,
                    "content": {"message": "未赞"},
                },
            ]
        },
    }
    rows = parse_api_capture("https://api.bilibili.com/x/v2/reply/wbi/main?oid=200", body)
    assert len(rows) == 1
    assert rows[0][1]["message"] == "好评论"


def test_ingest_aicu_from_json(tmp_path, monkeypatch):
    import asyncio

    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "osint_toolkit.ingest.aicu.load_config",
        lambda: {"ingest": {"aicu_enabled": True}},
    )

    payload = {
        "code": 0,
        "data": {
            "replies": [
                {"rpid": "j1", "message": "from json", "time": 1, "dyn": {"oid": "1", "type": 12}}
            ]
        },
    }
    result = asyncio.run(ingest_aicu_from_json(payload))
    assert result["ok"] is True
    assert result["count"] == 1


def test_extract_replies_from_payload_list():
    pages = [{"code": 0, "data": {"replies": [{"rpid": "1", "message": "a", "dyn": {}}]}}]
    assert len(extract_replies_from_payload(pages)) == 1


def test_aicu_dedup_on_import(tmp_path, monkeypatch):
    import asyncio

    from osint_toolkit.ingest import aicu as aicu_mod

    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)

    async def fake_page(*_args, **_kwargs):
        return {
            "code": 0,
            "data": {
                "cursor": {"is_end": True, "all_count": 1},
                "replies": [
                    {
                        "rpid": "dup1",
                        "message": "same",
                        "time": 1,
                        "dyn": {"oid": "1", "type": 1},
                    }
                ],
            },
        }

    async def fake_nav(_client):
        return 32823281

    async def noop_resolve(*_args, **_kwargs):
        return None

    monkeypatch.setattr(aicu_mod, "_fetch_aicu_page", fake_page)
    monkeypatch.setattr(aicu_mod, "_nav_mid", fake_nav)
    monkeypatch.setattr(aicu_mod, "_resolve_bvid", noop_resolve)

    cfg = {"ingest": {"aicu_enabled": True, "aicu_page_size": 10, "aicu_delay_sec": 0}}
    monkeypatch.setattr(aicu_mod, "load_config", lambda: cfg)

    first = asyncio.run(aicu_mod.ingest_aicu_comments())
    second = asyncio.run(aicu_mod.ingest_aicu_comments())

    assert first["count"] == 1
    assert second["count"] == 0
    assert second["skipped"] == 1

    conn = connect()
    rows = conn.execute(
        "SELECT COUNT(*) AS c FROM events WHERE event_type = ?",
        ("bilibili_comment_post",),
    ).fetchone()
    conn.close()
    assert rows["c"] == 1
