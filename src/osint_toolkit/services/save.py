"""收录服务 / Save service."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from osint_toolkit.analyzers.comments import summarize_comments
from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.collectors.web import WebCollector
from osint_toolkit.collectors.weixin import WeixinCollector
from osint_toolkit.collectors.zhihu import ZhihuCollector
from osint_toolkit.exporters.card import export_card
from osint_toolkit.storage.knowledge import save_item


async def save_url(
    url: str,
    *,
    with_comments: bool = False,
    no_ai: bool = False,
) -> dict[str, Any]:
    host = urlparse(url).hostname or ""
    if "zhihu.com" in host:
        collector = ZhihuCollector()
        item = await collector.fetch(url)
        if with_comments:
            comments = await collector.fetch_comments(url)
            item.layers["comments"] = comments
            item.layers["comments_summary"] = await summarize_comments(comments, no_ai=no_ai)
    elif "mp.weixin.qq.com" in host or "weixin.sogou.com" in host:
        collector = WeixinCollector()
        item = await collector.fetch(url)
    elif "bilibili.com" in host:
        collector = BilibiliCollector()
        item = await collector.fetch(url)
        if with_comments:
            comments = await collector.fetch_comments(url)
            item.layers["comments"] = comments
            item.layers["comments_summary"] = await summarize_comments(comments, no_ai=no_ai)
    else:
        item = await WebCollector().fetch(url)
    save_item(item)
    card_path = export_card(item, get_data_dir() / "cards")
    return {"item": item, "card_path": str(card_path)}
