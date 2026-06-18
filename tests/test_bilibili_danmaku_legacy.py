"""Bilibili legacy danmaku fallback tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_fetch_danmaku_lines_legacy_parses_xml(monkeypatch):
    from osint_toolkit.ingest import bilibili_sdk

    monkeypatch.setattr(
        bilibili_sdk,
        "resolve_video_aid_cid",
        AsyncMock(return_value=(123, 456)),
    )

    class FakeResp:
        status_code = 200
        text = '<i><d p="1">hello</d><d p="2">world</d></i>'

    class FakeClient:
        async def get(self, url):
            assert url == "https://comment.bilibili.com/456.xml"
            return FakeResp()

    lines = await bilibili_sdk.fetch_danmaku_lines_legacy(
        "https://www.bilibili.com/video/BV1",
        client=FakeClient(),
    )
    assert lines == ["hello", "world"]


@pytest.mark.asyncio
async def test_fetch_danmaku_lines_falls_back_when_sdk_disabled(monkeypatch):
    from osint_toolkit.ingest import bilibili_sdk

    monkeypatch.setattr(bilibili_sdk, "sdk_enabled", lambda _f: False)
    monkeypatch.setattr(
        bilibili_sdk,
        "fetch_danmaku_lines_legacy",
        AsyncMock(return_value=["fallback"]),
    )
    lines = await bilibili_sdk.fetch_danmaku_lines("https://www.bilibili.com/video/BV1")
    assert lines == ["fallback"]
