"""Tests for Zhihu OpenAPI rate-limit retry behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osint_toolkit.ingest import zhihu_openapi


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    zhihu_openapi._reset_rate_limiter_for_tests()
    yield
    zhihu_openapi._reset_rate_limiter_for_tests()


@pytest.mark.asyncio
async def test_api_get_refreshes_timestamp_on_retry(monkeypatch):
    monkeypatch.setattr(
        zhihu_openapi,
        "_openapi_cfg",
        lambda: {
            "base_url": "https://developer.zhihu.com",
            "enabled": True,
            "min_request_interval_sec": 0,
            "rate_limit_retry_max": 2,
            "rate_limit_retry_base_sec": 0.01,
        },
    )
    monkeypatch.setattr(zhihu_openapi, "access_secret", lambda: "test-secret")

    timestamps: list[str] = []
    clock = iter([1000.0, 2000.0, 3000.0])
    monkeypatch.setattr(zhihu_openapi.time, "time", lambda: next(clock))

    async def fake_get(url, headers=None, **kwargs):
        timestamps.append(str((headers or {}).get("X-Request-Timestamp")))
        resp = MagicMock()
        resp.status_code = 200
        if len(timestamps) == 1:
            resp.json.return_value = {"Code": 30001, "Message": "second limit exceeded"}
        else:
            resp.json.return_value = {"Code": 0, "Data": {"Items": []}}
        return resp

    http = MagicMock()
    http.get = AsyncMock(side_effect=fake_get)

    data = await zhihu_openapi._api_get("/api/v1/content/zhihu_search", {"Query": "x", "Count": 1}, client=http)
    assert data == {"Items": []}
    assert len(timestamps) == 2
    assert timestamps[0] != timestamps[1]
