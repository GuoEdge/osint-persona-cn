"""Weixin (Sogou) search tests."""

from __future__ import annotations

import pytest

from osint_toolkit.collectors.weixin import WeixinCollector
from osint_toolkit.ingest.weixin_sogou import (
    is_weixin_blocked,
    parse_weixin_sogou_html,
    search_weixin_sogou_http,
)

SAMPLE_HTML = """
<ul class="news-list">
  <li>
    <div class="txt-box">
      <h3><a href="/link?url=abc&type=2&query=test"><em>Python</em> 入门指南</a></h3>
      <p class="txt-info">这是一段摘要内容</p>
      <div class="s-p"><span class="all-time-y2">测试公众号</span></div>
    </div>
  </li>
</ul>
"""


def test_parse_weixin_sogou_html():
    rows = parse_weixin_sogou_html(SAMPLE_HTML, "test", limit=5)
    assert len(rows) == 1
    assert rows[0]["title"] == "Python 入门指南"
    assert rows[0]["author"] == "测试公众号"
    assert rows[0]["url"].startswith("https://weixin.sogou.com/link?")


def test_is_weixin_blocked():
    assert is_weixin_blocked("", url="https://weixin.sogou.com/antispider/")
    assert not is_weixin_blocked(SAMPLE_HTML)


@pytest.mark.asyncio
async def test_weixin_collector_search(monkeypatch):
    col = WeixinCollector()

    async def fake_http(_client, _query, limit=10):
        return parse_weixin_sogou_html(SAMPLE_HTML, "test", limit=limit), None

    async def noop_pw(_query, limit=10):
        return [], None

    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_http", fake_http)
    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_playwright", noop_pw)

    items = await col.search("test", limit=3)
    assert len(items) == 1
    assert items[0].source == "weixin"
    assert items[0].author == "测试公众号"


@pytest.mark.asyncio
async def test_weixin_collector_playwright_fallback(monkeypatch):
    col = WeixinCollector()

    async def fail_http(_client, _query, limit=10):
        return [], "weixin_sogou: 检测到验证码/风控页面"

    async def ok_pw(_query, limit=10):
        return parse_weixin_sogou_html(SAMPLE_HTML, "test", limit=limit), None

    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_http", fail_http)
    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_playwright", ok_pw)

    items = await col.search("test", limit=3)
    assert len(items) == 1
