"""微信公众号采集器（搜狗微信搜索）/ WeChat article collector via Sogou."""

from __future__ import annotations

import re

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.weixin_sogou import (
    search_weixin_sogou_http,
    search_weixin_sogou_playwright,
)
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.processors.normalize import extract_text_from_html, html_to_text


class WeixinCollector(BaseCollector):
    name = "weixin"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        rows, err = await search_weixin_sogou_http(self.client, query, limit=limit)
        if not rows:
            pw_rows, pw_err = await search_weixin_sogou_playwright(query, limit=limit)
            if pw_rows:
                rows = pw_rows
            elif err and pw_err:
                raise RuntimeError(f"{err}; {pw_err}")
            elif err:
                raise RuntimeError(err)
            elif pw_err:
                raise RuntimeError(pw_err)

        items: list[IntelItem] = []
        for row in rows:
            items.append(
                IntelItem(
                    source="weixin",
                    type="article",
                    url=row["url"],
                    title=row["title"],
                    content=row.get("snippet") or "",
                    author=row.get("author") or "",
                )
            )
        return items[:limit]

    async def fetch(self, url: str) -> IntelItem:
        target = url
        if "weixin.sogou.com" in url:
            resolved = await self._resolve_sogou_link(url)
            if resolved:
                target = resolved
        text = await self.client.get_text(target)
        title_match = re.search(r'var msg_title = "([^"]+)"', text)
        if not title_match:
            title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        content = extract_text_from_html(text) or html_to_text(text)
        author_match = re.search(r'var nickname = "([^"]+)"', text)
        author = author_match.group(1) if author_match else ""
        return IntelItem(
            source="weixin",
            type="article",
            url=target,
            title=title,
            content=content[:12_000],
            author=author,
        )

    async def _resolve_sogou_link(self, url: str) -> str | None:
        try:
            resp = await self.client.get(
                url,
                headers={
                    "Referer": "https://weixin.sogou.com/",
                    "User-Agent": self.client.user_agent,
                },
            )
            final = str(resp.url)
            if "mp.weixin.qq.com" in final:
                return final
        except Exception:  # noqa: BLE001
            return None
        return None
