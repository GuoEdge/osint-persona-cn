"""Bilibili article search tests."""

import pytest

from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.ingest import bilibili_sdk


@pytest.mark.asyncio
async def test_search_type_uses_wbi(monkeypatch):
    col = BilibiliCollector()
    captured: dict = {}

    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_sdk.sdk_enabled",
        lambda _feature: False,
    )

    async def fake_wbi_get(_client, base, params):
        captured["base"] = base
        captured["params"] = params
        return {
            "code": 0,
            "data": {
                "result": [
                    {
                        "bvid": "BV1111111111",
                        "title": "测试视频",
                        "description": "desc",
                        "author": "up",
                        "play": 10,
                        "like": 1,
                    }
                ]
            },
        }

    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_wbi.wbi_get",
        fake_wbi_get,
    )

    rows = await col._search_type("关键词", "video", 3)
    assert len(rows) == 1
    assert "wbi/search/type" in captured["base"]
    assert captured["params"]["search_type"] == "video"
    assert captured["params"]["keyword"] == "关键词"


@pytest.mark.asyncio
async def test_search_serp_fallback(monkeypatch):
    col = BilibiliCollector()

    async def fail_search(*_a, **_k):
        raise RuntimeError("wbi blocked")

    async def fake_serp(_query, _limit):
        from osint_toolkit.models.intel_item import IntelItem

        return [
            IntelItem(
                source="bilibili",
                type="video",
                url="https://www.bilibili.com/video/BV1",
                title="兜底",
                content="",
            )
        ]

    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_sdk.configured_search_types",
        lambda: ["video"],
    )
    monkeypatch.setattr(col, "_search_type", fail_search)
    monkeypatch.setattr(col, "_serp_site_search", fake_serp)

    items = await col.search("测试", limit=2)
    assert len(items) == 1
    assert items[0].title == "兜底"


def test_configured_search_types_normalizes_aliases(monkeypatch):
    monkeypatch.setattr(
        bilibili_sdk,
        "get_search_config",
        lambda: {"types": ["video", "user", "bangumi"]},
    )
    assert bilibili_sdk.configured_search_types() == ["video", "bili_user", "media_bangumi"]


def test_comment_type_from_url():
    col = BilibiliCollector()
    assert col._comment_type_from_url("https://www.bilibili.com/read/cv1") == 12
    assert col._comment_type_from_url("https://www.bilibili.com/opus/2") == 17
    assert col._comment_type_from_url("https://www.bilibili.com/video/BV1") == 1


@pytest.mark.asyncio
async def test_resolve_oid_cv():
    col = BilibiliCollector()
    oid = await col._resolve_oid("https://www.bilibili.com/read/cv12345678")
    assert oid == "12345678"


@pytest.mark.asyncio
async def test_resolve_oid_opus():
    col = BilibiliCollector()
    oid = await col._resolve_oid("https://www.bilibili.com/opus/7654321")
    assert oid == "7654321"


def test_parse_article():
    col = BilibiliCollector()
    item = col._parse_article({"id": 99, "title": "测试专栏", "desc": "摘要"})
    assert item is not None
    assert item.type == "article"
    assert "cv99" in item.url


def test_parse_user():
    col = BilibiliCollector()
    item = col._parse_user({"mid": 123, "uname": "测试UP", "usign": "签名", "fans": 1000})
    assert item is not None
    assert item.type == "user"
    assert item.url.endswith("/123")
    assert item.metrics.views == 1000


@pytest.mark.asyncio
async def test_search_type_prefers_sdk(monkeypatch):
    col = BilibiliCollector()
    calls: list[str] = []

    async def fake_sdk_entries(query: str, search_type: str, *, limit: int = 10, page: int = 1):
        calls.append(search_type)
        return [{"mid": 9, "uname": "sdk-user", "usign": "hi", "fans": 3}]

    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_sdk.sdk_enabled",
        lambda feature: feature == "search",
    )
    monkeypatch.setattr("osint_toolkit.ingest.bilibili_sdk.search_entries", fake_sdk_entries)
    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_sdk.configured_search_types",
        lambda: ["bili_user"],
    )

    rows = await col._search_type("关键词", "bili_user", 2)
    assert calls == ["bili_user"]
    assert rows[0]["uname"] == "sdk-user"


@pytest.mark.asyncio
async def test_search_merges_configured_types(monkeypatch):
    col = BilibiliCollector()

    async def fake_search_type(query: str, search_type: str, limit: int):
        if search_type == "video":
            return [{"bvid": "BV1111111111", "title": "v", "description": "", "author": "a", "play": 1, "like": 0}]
        if search_type == "bili_user":
            return [{"mid": 7, "uname": "u", "usign": "", "fans": 0}]
        return []

    monkeypatch.setattr(
        "osint_toolkit.ingest.bilibili_sdk.configured_search_types",
        lambda: ["video", "bili_user"],
    )
    monkeypatch.setattr(col, "_search_type", fake_search_type)

    items = await col.search("测试", limit=3)
    types = {item.type for item in items}
    assert types == {"video", "user"}

