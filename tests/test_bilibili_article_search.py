"""Bilibili article search tests."""

import pytest

from osint_toolkit.collectors.bilibili import BilibiliCollector


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
