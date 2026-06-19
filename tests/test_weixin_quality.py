"""Weixin engagement parsing and quality filter tests."""

from __future__ import annotations

import pytest

from osint_toolkit.collectors.weixin import WeixinCollector
from osint_toolkit.ingest.weixin_engagement import parse_weixin_engagement, weixin_engagement_relevance_boost
from osint_toolkit.ingest.weixin_sogou import parse_weixin_sogou_html

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

MP_HTML_HIGH_READS = """
<html><body>
<script>var read_num = '12000'; var like_num = '88';</script>
var msg_title = "高质量文章"
</body></html>
"""

MP_HTML_LOW_READS = """
<html><body>
<script>var read_num = '42';</script>
var msg_title = "低阅读量文章"
</body></html>
"""


def test_parse_weixin_engagement():
    data = parse_weixin_engagement(MP_HTML_HIGH_READS)
    assert data["views"] == 12000
    assert data["likes"] == 88


def test_weixin_engagement_relevance_boost():
    assert weixin_engagement_relevance_boost(0) == 0.0
    assert weixin_engagement_relevance_boost(1000) > weixin_engagement_relevance_boost(100)


@pytest.mark.asyncio
async def test_weixin_quality_filter_drops_low_reads(monkeypatch):
    col = WeixinCollector()

    monkeypatch.setattr(
        col,
        "cfg",
        {
            "min_snippet_chars": 0,
            "fetch_read_count_top": 1,
            "fetch_read_delay_ms": 0,
            "min_read_count": 500,
            "drop_unknown_read_count": False,
            "playwright_on_block": False,
            "serp_fallback": False,
        },
    )

    async def fake_http(_client, _query, limit=10):
        return parse_weixin_sogou_html(SAMPLE_HTML, "test", limit=limit), None

    async def fake_engagement(_url: str):
        return {"views": 42, "likes": 0}

    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_http", fake_http)
    monkeypatch.setattr(col, "_fetch_engagement", fake_engagement)

    async def fake_article_url(_item):
        return "https://mp.weixin.qq.com/s/fake"

    monkeypatch.setattr(col, "_article_url_for_item", fake_article_url)

    items = await col.search("test", limit=3)
    assert items == []


@pytest.mark.asyncio
async def test_weixin_quality_filter_keeps_high_reads(monkeypatch):
    col = WeixinCollector()

    monkeypatch.setattr(
        col,
        "cfg",
        {
            "min_snippet_chars": 0,
            "fetch_read_count_top": 1,
            "fetch_read_delay_ms": 0,
            "min_read_count": 500,
            "drop_unknown_read_count": False,
            "playwright_on_block": False,
            "serp_fallback": False,
        },
    )

    async def fake_http(_client, _query, limit=10):
        return parse_weixin_sogou_html(SAMPLE_HTML, "test", limit=limit), None

    async def fake_engagement(_url: str):
        return {"views": 8000, "likes": 12}

    monkeypatch.setattr("osint_toolkit.collectors.weixin.search_weixin_sogou_http", fake_http)
    monkeypatch.setattr(col, "_fetch_engagement", fake_engagement)

    async def fake_article_url(_item):
        return "https://mp.weixin.qq.com/s/fake"

    monkeypatch.setattr(col, "_article_url_for_item", fake_article_url)

    items = await col.search("test", limit=3)
    assert len(items) == 1
    assert items[0].metrics.views == 8000
