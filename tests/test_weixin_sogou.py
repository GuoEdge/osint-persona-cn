"""Weixin (Sogou) search tests."""

from __future__ import annotations

import pytest

from osint_toolkit.collectors.weixin import WeixinCollector
from osint_toolkit.ingest.weixin_sogou import (
    is_weixin_blocked,
    parse_weixin_sogou_html,
)

SAMPLE_HTML = """
<ul class="news-list">
  <li>
    <div class="txt-box">
      <h3><a href="/link?url=abc&type=2&query=test"><em>Python</em> 入门指南</a></h3>
      <p class="txt-info">这是一段足够长的摘要内容，用于通过搜狗微信搜索的质量预筛门槛，避免低质空摘要进入后续流程。</p>
      <div class="s-p">
        <span class="all-time-y2">测试公众号</span>
        <span class="s2"><script>document.write(timeConvert('1700000000'))</script></span>
      </div>
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
    assert rows[0]["published_at"] == "2023-11-14"


def test_is_weixin_blocked():
    assert is_weixin_blocked("", url="https://weixin.sogou.com/antispider/")
    assert not is_weixin_blocked(SAMPLE_HTML)


@pytest.mark.asyncio
async def test_weixin_collector_search(monkeypatch):
    col = WeixinCollector()
    monkeypatch.setattr(col, "cfg", {**col.cfg, "min_snippet_chars": 0, "fetch_read_count_top": 0})

    async def fake_http(_client, _query, limit=10):
        return parse_weixin_sogou_html(SAMPLE_HTML, "test", limit=limit), None

    async def fail_pw(*_a, **_k):
        return [], "unused"

    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_http", fake_http)
    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_playwright", fail_pw)
    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_serp", fail_pw)

    items = await col.search("test", limit=3)
    assert len(items) == 1
    assert items[0].source == "weixin"
    assert items[0].author == "测试公众号"
    assert items[0].personal.get("published_at") == "2023-11-14"


@pytest.mark.asyncio
async def test_weixin_collector_playwright_fallback(monkeypatch):
    col = WeixinCollector()
    monkeypatch.setattr(col, "cfg", {**col.cfg, "min_snippet_chars": 0, "fetch_read_count_top": 0})

    async def fail_http(_client, _query, limit=10):
        return [], "weixin_sogou: 检测到验证码/风控页面"

    async def ok_pw(_query, limit=10, resolve_mp=True):
        return parse_weixin_sogou_html(SAMPLE_HTML, "test", limit=limit), None

    async def fail_serp(*_a, **_k):
        return [], "unused"

    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_http", fail_http)
    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_playwright", ok_pw)
    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_serp", fail_serp)

    items = await col.search("test", limit=3)
    assert len(items) == 1


@pytest.mark.asyncio
async def test_weixin_collector_serp_fallback(monkeypatch):
    col = WeixinCollector()
    monkeypatch.setattr(col, "cfg", {**col.cfg, "min_snippet_chars": 0, "fetch_read_count_top": 0})

    async def fail_http(_client, _query, limit=10):
        return [], "blocked"

    async def fail_pw(*_a, **_k):
        return [], "blocked"

    async def ok_serp(_client, _query, limit=10):
        return [
            {
                "title": "SERP 文章",
                "url": "https://mp.weixin.qq.com/s/abc",
                "snippet": "摘要",
                "author": "",
                "via": "serp",
            }
        ], None

    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_http", fail_http)
    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_playwright", fail_pw)
    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_serp", ok_serp)

    items = await col.search("test", limit=3)
    assert len(items) == 1
    assert items[0].url.startswith("https://mp.weixin.qq.com/")
    assert items[0].personal.get("weixin_via") == "serp"
