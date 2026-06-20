"""Bilibili followings ingest tests."""

from __future__ import annotations

import pytest

from osint_toolkit.ingest import bilibili_account


@pytest.mark.asyncio
async def test_ingest_followings_parses_list(monkeypatch):
    class FakeClient:
        async def get(self, url: str):
            class Resp:
                def json(self):
                    return {
                        "code": 0,
                        "data": {
                            "list": [
                                {"mid": 1, "uname": "up-a"},
                                {"mid": 2, "uname": "up-b"},
                            ]
                        },
                    }

            return Resp()

    monkeypatch.setattr(bilibili_account, "HttpClient", lambda: FakeClient())
    async def _fake_mid(_c):
        return 99

    monkeypatch.setattr(bilibili_account, "_nav_mid", _fake_mid)
    monkeypatch.setattr(bilibili_account, "log_events_batch", lambda *_a, **_k: None)
    monkeypatch.setattr(
        bilibili_account.sync_state,
        "load_account_sync_state",
        lambda: {},
    )
    monkeypatch.setattr(
        bilibili_account.sync_state,
        "save_account_sync_state",
        lambda _s: None,
    )

    rows = await bilibili_account.ingest_followings(limit=10)
    assert len(rows) == 2
    assert rows[0]["event_kind"] == "following"
    assert "space.bilibili.com" in rows[0]["url"]


@pytest.mark.asyncio
async def test_ingest_followings_incremental_skips_known(monkeypatch, tmp_path):
    state: dict = {"bilibili": {"following_mids": ["1"]}}

    class FakeClient:
        async def get(self, url: str):
            class Resp:
                def json(self):
                    return {
                        "code": 0,
                        "data": {
                            "list": [
                                {"mid": 1, "uname": "up-a"},
                                {"mid": 2, "uname": "up-b"},
                            ]
                        },
                    }

            return Resp()

    monkeypatch.setattr(bilibili_account, "HttpClient", lambda: FakeClient())

    async def _fake_mid(_c):
        return 99

    monkeypatch.setattr(bilibili_account, "_nav_mid", _fake_mid)
    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_sdk.sdk_enabled",
        lambda _k: False,
    )
    monkeypatch.setattr(bilibili_account, "log_events_batch", lambda *_a, **_k: None)
    monkeypatch.setattr(
        bilibili_account.sync_state,
        "load_account_sync_state",
        lambda: state,
    )

    def _save(s: dict) -> None:
        state.clear()
        state.update(s)

    monkeypatch.setattr(bilibili_account.sync_state, "save_account_sync_state", _save)

    rows = await bilibili_account.ingest_followings(limit=10)
    assert len(rows) == 1
    assert rows[0]["uid"] == 2
