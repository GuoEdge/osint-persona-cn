"""Browser sync unit tests."""

from __future__ import annotations

import json

import pytest

from osint_toolkit.ingest.browser_sync import (
    CaptureAccumulator,
    build_sync_pages,
    edge_user_data_dir,
    should_capture_url,
)
from osint_toolkit.ingest.extension_events import parse_api_capture


def test_should_capture_bilibili_like_api():
    assert should_capture_url("https://api.bilibili.com/x/space/like/video?vmid=1")


def test_should_capture_zhihu_activities():
    assert should_capture_url("https://www.zhihu.com/api/v4/members/foo/activities")


def test_build_sync_pages_requires_ids():
    pages = build_sync_pages(platforms=("bilibili", "zhihu"), bilibili_mid="123", zhihu_token="abc")
    urls = [p["url"] for p in pages]
    assert any("space.bilibili.com/123" in u for u in urls)
    assert any("people/abc" in u for u in urls)
    assert "https://www.zhihu.com/recent-viewed" in urls


def test_capture_accumulator_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)

    acc = CaptureAccumulator()
    body = {
        "code": 0,
        "data": {"list": [{"title": "t", "bvid": "BV1111111111"}]},
    }
    rows = parse_api_capture("https://api.bilibili.com/x/space/like/video?vmid=1", body)
    acc.persist_rows(rows)
    acc.persist_rows(rows)
    assert acc.accepted == 1
    assert acc.skipped == 1


def test_edge_user_data_dir_windows(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\test\\AppData\\Local")
    path = edge_user_data_dir()
    assert path is not None
    assert "Edge" in str(path)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_browser_sync_integration():
    pytest.importorskip("playwright")
    from osint_toolkit.ingest.browser_sync import run_browser_sync

    result = await run_browser_sync(platforms=("zhihu",), headless=True)
    assert "accepted" in result
