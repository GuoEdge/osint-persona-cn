"""知乎采集器 / Zhihu collector."""

from __future__ import annotations

import re
from urllib.parse import quote

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
from osint_toolkit.processors.normalize import html_to_text


class ZhihuCollector(BaseCollector):
    name = "zhihu"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        f"https://www.zhihu.com/search?type=content&q={quote(query)}"
        api = (
            "https://www.zhihu.com/api/v4/search_v3?"
            f"gk_version=gz-gaokao&tab=1&q={quote(query)}&limit={limit}"
        )
        items: list[IntelItem] = []
        try:
            resp = await self.client.get(api)
            if resp.status_code != 200:
                return await self._fallback_search(query, limit)
            data = resp.json()
            for entry in data.get("data", [])[:limit]:
                obj = entry.get("object", {}) or entry
                item = self._parse_object(obj)
                if item:
                    items.append(item)
        except Exception:  # noqa: BLE001
            return await self._fallback_search(query, limit)
        return items[:limit]

    async def _fallback_search(self, query: str, limit: int) -> list[IntelItem]:
        return [
            IntelItem(
                source="zhihu",
                type="search_link",
                url=f"https://www.zhihu.com/search?type=content&q={quote(query)}",
                title=f"知乎搜索: {query}",
                content="请在本机配置 Cookie 后获取完整搜索结果",
            )
        ][:limit]

    def _parse_object(self, obj: dict) -> IntelItem | None:
        otype = obj.get("type") or obj.get("object_type", "")
        if otype == "search_result":
            obj = obj.get("object", obj)
            otype = obj.get("type", "")
        if otype == "answer":
            question = obj.get("question", {})
            return IntelItem(
                source="zhihu",
                type="answer",
                url=f"https://www.zhihu.com/question/{question.get('id')}/answer/{obj.get('id')}",
                title=question.get("title", obj.get("title", "")),
                content=html_to_text(obj.get("excerpt", "") or obj.get("content", "")),
                author=obj.get("author", {}).get("name", ""),
                metrics=IntelMetrics(
                    likes=obj.get("voteup_count", 0),
                    comments=obj.get("comment_count", 0),
                ),
            )
        if otype in {"article", "zvideo"}:
            return IntelItem(
                source="zhihu",
                type=otype,
                url=obj.get("url", ""),
                title=obj.get("title", ""),
                content=html_to_text(obj.get("excerpt", "") or ""),
                author=obj.get("author", {}).get("name", ""),
                metrics=IntelMetrics(likes=obj.get("voteup_count", 0)),
            )
        title = obj.get("title") or obj.get("question", {}).get("title")
        if title:
            return IntelItem(
                source="zhihu",
                type="content",
                url=obj.get("url", ""),
                title=title,
                content=html_to_text(obj.get("excerpt", "") or ""),
            )
        return None

    async def fetch(self, url: str) -> IntelItem:
        text = await self.client.get_text(url)
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        content = html_to_text(text)
        return IntelItem(
            source="zhihu",
            type="page",
            url=url,
            title=title,
            content=content[:8000],
        )
