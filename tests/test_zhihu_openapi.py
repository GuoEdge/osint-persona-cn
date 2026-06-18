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
        lambda: {"openapi": {"search_count": 10, "access_secret": "x", "base_url": "https://developer.zhihu.com"}},
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
async def test_hot_list(monkeypatch):
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
        lambda: {"openapi": {"hot_list_count": 30, "base_url": "https://developer.zhihu.com"}},
    )

    items = await zhihu_openapi.hot_list(limit=5, client=client)
    assert len(items) == 1
    assert items[0].personal.get("hot_list") is True
