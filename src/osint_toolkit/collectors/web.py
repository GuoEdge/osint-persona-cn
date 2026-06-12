"""Web 搜索采集器 / Web search collector."""

from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem


class WebCollector(BaseCollector):
    name = "web"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        url = f"https://www.bing.com/search?q={quote(query)}&setlang=zh-Hans"
        items: list[IntelItem] = []
        try:
            html = await self.client.get_text(url)
            soup = BeautifulSoup(html, "html.parser")
            for li in soup.select("li.b_algo")[:limit]:
                a = li.find("a")
                if not a or not a.get("href"):
                    continue
                title = a.get_text(strip=True)
                href = a["href"]
                snippet = ""
                p = li.find("p")
                if p:
                    snippet = p.get_text(strip=True)
                items.append(
                    IntelItem(
                        source="web",
                        type="snippet",
                        url=href,
                        title=title,
                        content=snippet,
                    )
                )
        except Exception:  # noqa: BLE001
            items = [
                IntelItem(
                    source="web",
                    type="search_link",
                    url=url,
                    title=f"Web搜索: {query}",
                    content="Web 搜索请求失败",
                )
            ]
        return items[:limit]

    async def fetch(self, url: str) -> IntelItem:
        text = await self.client.get_text(url)
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        from osint_toolkit.processors.normalize import extract_text_from_html

        content = extract_text_from_html(text)[:8000]
        return IntelItem(source="web", type="article", url=url, title=title, content=content)
