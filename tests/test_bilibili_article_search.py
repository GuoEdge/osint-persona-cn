"""Bilibili article search tests."""

import pytest

from osint_toolkit.collectors.bilibili import BilibiliCollector


@pytest.mark.asyncio
async def test_search_type_uses_wbi(monkeypatch):
    col = BilibiliCollector()
    captured: dict = {}

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

    monkeypatch.setattr(col, "_search_type", fail_search)
    monkeypatch.setattr(col, "_serp_site_search", fake_serp)

    items = await col.search("测试", limit=2)
    assert len(items) == 1
    assert items[0].title == "兜底"


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
