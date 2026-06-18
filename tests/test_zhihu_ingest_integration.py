"""Zhihu ingest integration tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ingest_favorites_normalizes_api_urls(monkeypatch, tmp_path):
    from osint_toolkit.ingest import zhihu_account
    from osint_toolkit.storage import sqlite as sqlite_mod

    monkeypatch.setattr(sqlite_mod, "get_db_path", lambda: tmp_path / "knowledge.db")

    class FakeResp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    favlists = {
        "data": [{"id": 1, "title": "默认"}],
        "paging": {"is_end": True},
    }
    items_page = {
        "data": [
            {
                "content": {
                    "type": "article",
                    "id": 42,
                    "title": "文章标题",
                    "url": "https://api.zhihu.com/articles/42",
                }
            }
        ],
        "paging": {"is_end": True},
    }

    class FakeClient:
        async def get(self, url):
            if "favlists" in url:
                return FakeResp(favlists)
            if "/collections/" in url:
                return FakeResp(items_page)
            raise AssertionError(url)

    logged: list[tuple[str, dict]] = []
    async def fake_token(_c):
        return "token"

    monkeypatch.setattr(zhihu_account, "_url_token", fake_token)
    monkeypatch.setattr(zhihu_account, "HttpClient", lambda: FakeClient())
    monkeypatch.setattr(zhihu_account, "log_event", lambda et, entry: logged.append((et, entry)))
    monkeypatch.setattr(zhihu_account, "save_endorsement", lambda **_k: None)

    rows = await zhihu_account.ingest_favorites(limit=5)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://zhuanlan.zhihu.com/p/42"
    assert logged[0][0] == "zhihu_fav"
