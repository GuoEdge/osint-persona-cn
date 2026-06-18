"""Bilibili ingest likes tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ingest_likes_sdk_first(monkeypatch):
    from osint_toolkit.ingest import bilibili_account

    sdk_rows = [
        {
            "source": "bilibili",
            "title": "SDK 点赞",
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
    monkeypatch.setattr(bilibili_account, "log_event", lambda et, entry: logged.append((et, entry)))

    rows = await bilibili_account.ingest_likes(limit=5)
    assert rows == sdk_rows
    assert logged == [("bilibili_like", sdk_rows[0])]
