"""Bilibili ingest likes tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ingest_likes_sdk_first(monkeypatch):
    from osint_toolkit.ingest import bilibili_account

    sdk_rows = [
        {
            "source": "bilibili",
            "title": "SDK 鐐硅禐",
            "url": "https://www.bilibili.com/video/BV1",
            "event_kind": "like",
        }
    ]

    async def fake_sdk_likes(limit):
        return sdk_rows

    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_sdk.sdk_enabled",
        lambda feature: feature == "ingest_likes",
    )
    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_sdk.ingest_likes",
        fake_sdk_likes,
    )
    monkeypatch.setattr(bilibili_account, "log_events_batch", lambda entries: logged.extend([(et, entry) for et, entry, _ in entries]))
    monkeypatch.setattr(bilibili_account, "_bilibili_section", lambda: {})
    monkeypatch.setattr(bilibili_account, "_persist_bilibili", lambda **_k: None)
    monkeypatch.setattr(
        "osint_toolkit.ingest.account_sync_state.filter_new_by_bvids",
        lambda entries, _seen: entries,
    )

    rows = await bilibili_account.ingest_likes(limit=5)
    assert rows == sdk_rows
    assert logged == [("bilibili_like", sdk_rows[0])]
