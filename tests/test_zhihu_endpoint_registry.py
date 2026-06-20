"""Zhihu endpoint registry tests."""

from __future__ import annotations

import pytest

from osint_toolkit.ingest.zhihu_endpoint_registry import (
    layer_status_from_count,
    paginate_member_api,
    VOTE_ENDPOINTS,
)


def test_layer_status_from_count():
    assert layer_status_from_count(3) == "ok"
    assert layer_status_from_count(0) == "empty"
    assert layer_status_from_count(0, attempted=False) == "skip"


@pytest.mark.asyncio
async def test_paginate_member_api_first_working_endpoint(monkeypatch):
    from osint_toolkit.ingest import zhihu_endpoint_registry as reg

    calls: list[str] = []

    class FakeResp:
        def __init__(self, status: int, data: list):
            self.status_code = status
            self._data = data

        def json(self):
            return {"data": self._data, "paging": {"is_end": True}}

    class FakeClient:
        async def get(self, url, headers=None):
            calls.append(url)
            if "voteanswers" in url:
                return FakeResp(404, [])
            if "vote_answers" in url:
                return FakeResp(
                    200,
                    [{"target": {"question": {"title": "Q"}, "url": "https://www.zhihu.com/question/1/answer/2"}}],
                )
            return FakeResp(404, [])

    items, key = await paginate_member_api(FakeClient(), "tok", VOTE_ENDPOINTS, limit=5)
    assert key == "vote_answers"
    assert len(items) == 1
    assert any("vote_answers" in u for u in calls)
