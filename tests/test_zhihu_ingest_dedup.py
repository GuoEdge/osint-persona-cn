"""Zhihu ingest dedup tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ingest_activities_stub_returns_empty():
    from osint_toolkit.ingest import zhihu_account

    rows, endpoint = await zhihu_account.ingest_activities(limit=5)
    assert rows == []
    assert endpoint is None


@pytest.mark.asyncio
async def test_ingest_voteanswers_stub_returns_empty():
    from osint_toolkit.ingest import zhihu_account

    rows, endpoint = await zhihu_account.ingest_voteanswers(limit=5)
    assert rows == []
    assert endpoint is None
