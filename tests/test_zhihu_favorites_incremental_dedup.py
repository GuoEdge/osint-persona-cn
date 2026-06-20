"""Cross-sync Zhihu favorites dedup tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_zhihu_favorites_second_sync_logs_nothing_new(monkeypatch, tmp_path):
    from osint_toolkit.ingest import account_sync_state as sync_state
    from osint_toolkit.ingest import zhihu_account
    from osint_toolkit.storage import sqlite as sqlite_mod

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(sqlite_mod, "get_db_path", lambda: tmp_path / "knowledge.db")

    logged: list[str] = []

    def track_dedup(event_type, data, key):
        logged.append(key)
        from osint_toolkit.storage.knowledge import log_event

        log_event(event_type, data)
        return True

    class FakeResp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    favlists = {"data": [{"id": 1, "title": "默认"}], "paging": {"is_end": True}}
    items_page = {
        "data": [
            {
                "content": {
                    "type": "article",
                    "id": 42,
                    "title": "文章",
                    "url": "https://api.zhihu.com/articles/42",
                }
            }
        ],
        "paging": {"is_end": True},
    }

    class FakeClient:
        async def get(self, url, headers=None):
            if "favlists" in url:
                return FakeResp(favlists)
            if "/collections/" in url:
                return FakeResp(items_page)
            raise AssertionError(url)

    async def fake_token(_c):
        return "token"

    monkeypatch.setattr(zhihu_account, "_url_token", fake_token)
    monkeypatch.setattr(zhihu_account, "HttpClient", lambda: FakeClient())
    monkeypatch.setattr(zhihu_account, "log_event_deduped", track_dedup)
    first = await zhihu_account.ingest_favorites(limit=5)
    assert len(first) == 1
    assert len(logged) == 1

    logged.clear()
    second = await zhihu_account.ingest_favorites(limit=5)
    assert len(second) == 0
    assert logged == []

    state = sync_state.load_account_sync_state()
    assert "https://zhuanlan.zhihu.com/p/42" in state["zhihu"]["favorite_urls"]
