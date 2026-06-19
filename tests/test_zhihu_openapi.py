"""Zhihu Data Open Platform client tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from osint_toolkit.collectors.zhihu import ZhihuCollector
from osint_toolkit.ingest import zhihu_openapi


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def test_openapi_configured(monkeypatch):
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "test-secret")
    monkeypatch.setattr(
        zhihu_openapi,
        "get_zhihu_config",
        lambda: {
            "openapi": {
                "enabled": True,
                "access_secret": "test-secret",
                "features": {"search": True},
            }
        },
    )
    assert zhihu_openapi.openapi_configured() is True
    assert zhihu_openapi.openapi_enabled("search") is True


def test_openapi_item_to_intel_article():
    item = zhihu_openapi.openapi_item_to_intel(
        {
            "Title": "测试文章 - 知乎",
            "ContentType": "Article",
            "ContentID": "123",
            "ContentText": "正文摘要",
            "Url": "https://zhuanlan.zhihu.com/p/123?utm_medium=openapi",
            "VoteUpCount": 5,
            "CommentCount": 2,
            "AuthorName": "作者",
            "CommentInfoList": [{"Content": "热评一条"}],
        }
    )
    assert item is not None
    assert item.type == "article"
    assert item.url == "https://zhuanlan.zhihu.com/p/123"
    assert item.title == "测试文章"
    assert item.personal.get("openapi_comments")


@pytest.mark.asyncio
async def test_openapi_search(monkeypatch):
    zhihu_openapi._reset_rate_limiter_for_tests()
    client = MagicMock()
    client.get = AsyncMock(
        return_value=_mock_response(
            {
                "Code": 0,
                "Message": "success",
                "Data": {
                    "Items": [
                        {
                            "Title": "如何学习 Python - 知乎",
                            "ContentType": "Question",
                            "Url": "https://www.zhihu.com/question/42",
                            "ContentText": "想系统入门",
                        }
                    ]
                },
            }
        )
    )
    monkeypatch.setattr(zhihu_openapi, "openapi_enabled", lambda _f: True)
    monkeypatch.setattr(
        zhihu_openapi,
        "get_zhihu_config",
        lambda: {
            "openapi": {
                "search_count": 10,
                "access_secret": "x",
                "base_url": "https://developer.zhihu.com",
                "min_request_interval_sec": 0,
            }
        },
    )
    monkeypatch.setattr(zhihu_openapi, "access_secret", lambda: "x")

    items = await zhihu_openapi.search("python", limit=5, client=client)
    assert len(items) == 1
    assert items[0].type == "question"
    assert "Authorization" in client.get.await_args.kwargs["headers"]


@pytest.mark.asyncio
async def test_collector_prefers_openapi(monkeypatch):
    col = ZhihuCollector(client=MagicMock())

    async def fake_openapi(q, limit, client=None):
        return [
            zhihu_openapi.openapi_item_to_intel(
                {
                    "Title": "OpenAPI 命中",
                    "ContentType": "Answer",
                    "Url": "https://www.zhihu.com/question/1/answer/2",
                    "ContentText": "内容",
                }
            )
        ]

    monkeypatch.setattr(
        "osint_toolkit.collectors.zhihu.get_search_config",
        lambda: {
            "zhihu_aggressive": False,
            "zhihu_expand_answers": False,
        },
    )
    monkeypatch.setattr(
        zhihu_openapi,
        "get_zhihu_config",
        lambda: {"openapi": {"prefer_search": True, "merge_search_v3": False}},
    )
    monkeypatch.setattr(zhihu_openapi, "openapi_enabled", lambda _f: True)
    monkeypatch.setattr(zhihu_openapi, "search", fake_openapi)

    async def fail_v3(*_a, **_k):
        raise RuntimeError("should not call search_v3")

    monkeypatch.setattr(col, "_search_v3", fail_v3)

    items = await col.search("test", limit=5)
    assert len(items) == 1
    assert items[0].title == "OpenAPI 命中"


@pytest.mark.asyncio
async def test_openapi_retries_on_second_limit(monkeypatch):
    zhihu_openapi._reset_rate_limiter_for_tests()
    client = MagicMock()
    rate_limited = _mock_response(
        {"Code": 30001, "Message": "second limit exceeded", "Data": None}
    )
    ok = _mock_response(
        {
            "Code": 0,
            "Data": {
                "Items": [
                    {
                        "Title": "重试成功",
                        "ContentType": "Answer",
                        "Url": "https://www.zhihu.com/question/1/answer/1",
                        "ContentText": "ok",
                    }
                ]
            },
        }
    )
    client.get = AsyncMock(side_effect=[rate_limited, ok])
    monkeypatch.setattr(zhihu_openapi, "openapi_enabled", lambda _f: True)
    monkeypatch.setattr(zhihu_openapi, "access_secret", lambda: "x")
    monkeypatch.setattr(
        zhihu_openapi,
        "get_zhihu_config",
        lambda: {
            "openapi": {
                "base_url": "https://developer.zhihu.com",
                "min_request_interval_sec": 0,
                "rate_limit_retry_max": 2,
                "rate_limit_retry_base_sec": 0.01,
            }
        },
    )

    items = await zhihu_openapi.search("python", limit=1, client=client)
    assert len(items) == 1
    assert items[0].title == "重试成功"
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_openapi_serializes_parallel_calls(monkeypatch):
    zhihu_openapi._reset_rate_limiter_for_tests()
    call_times: list[float] = []

    async def tracked_get(*_args, **_kwargs):
        import time

        call_times.append(time.monotonic())
        return _mock_response({"Code": 0, "Data": {"Items": []}})

    client = MagicMock()
    client.get = AsyncMock(side_effect=tracked_get)
    monkeypatch.setattr(zhihu_openapi, "openapi_enabled", lambda _f: True)
    monkeypatch.setattr(zhihu_openapi, "access_secret", lambda: "x")
    monkeypatch.setattr(
        zhihu_openapi,
        "get_zhihu_config",
        lambda: {
            "openapi": {
                "base_url": "https://developer.zhihu.com",
                "min_request_interval_sec": 0.05,
                "rate_limit_retry_max": 0,
            }
        },
    )

    import asyncio

    await asyncio.gather(
        zhihu_openapi.search("a", limit=1, client=client),
        zhihu_openapi.search("b", limit=1, client=client),
    )
    assert len(call_times) == 2
    assert call_times[1] - call_times[0] >= 0.04


@pytest.mark.asyncio
async def test_hot_list(monkeypatch):
    zhihu_openapi._reset_rate_limiter_for_tests()
    client = MagicMock()
    client.get = AsyncMock(
        return_value=_mock_response(
            {
                "Code": 0,
                "Data": {
                    "Items": [
                        {
                            "Title": "今日热点",
                            "Url": "https://www.zhihu.com/question/99",
                            "Summary": "摘要",
                        }
                    ]
                },
            }
        )
    )
    monkeypatch.setattr(zhihu_openapi, "openapi_enabled", lambda _f: True)
    monkeypatch.setattr(zhihu_openapi, "access_secret", lambda: "x")
    monkeypatch.setattr(
        zhihu_openapi,
        "get_zhihu_config",
        lambda: {
            "openapi": {
                "hot_list_count": 30,
                "base_url": "https://developer.zhihu.com",
                "min_request_interval_sec": 0,
            }
        },
    )

    items = await zhihu_openapi.hot_list(limit=5, client=client)
    assert len(items) == 1
    assert items[0].personal.get("hot_list") is True


@pytest.mark.asyncio
async def test_global_search(monkeypatch):
    zhihu_openapi._reset_rate_limiter_for_tests()
    client = MagicMock()
    client.get = AsyncMock(
        return_value=_mock_response(
            {
                "Code": 0,
                "Data": {
                    "Items": [
                        {
                            "Title": "知乎回答",
                            "Url": "https://www.zhihu.com/question/1/answer/2",
                            "ContentType": "Answer",
                            "ContentText": "站内",
                        },
                        {
                            "Title": "站外文章",
                            "Url": "https://example.com/post",
                            "ContentText": "站外",
                        },
                    ]
                },
            }
        )
    )
    monkeypatch.setattr(zhihu_openapi, "openapi_enabled", lambda feature: feature == "global_search")
    monkeypatch.setattr(zhihu_openapi, "access_secret", lambda: "x")
    monkeypatch.setattr(
        zhihu_openapi,
        "get_zhihu_config",
        lambda: {
            "openapi": {
                "base_url": "https://developer.zhihu.com",
                "min_request_interval_sec": 0,
            }
        },
    )

    items = await zhihu_openapi.global_search("test", limit=5, client=client)
    assert len(items) == 2
    assert items[0].source == "zhihu"
    assert items[1].source == "web"
    assert items[0].personal.get("via") == "zhihu_openapi_global"


def test_global_search_disabled(monkeypatch):
    monkeypatch.setattr(zhihu_openapi, "openapi_enabled", lambda _f: False)

    import asyncio

    items = asyncio.run(zhihu_openapi.global_search("test"))
    assert items == []
