"""V2EX 采集器 / V2EX collector."""

from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem


class V2exCollector(BaseCollector):
    name = "v2ex"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        url = f"https://www.v2ex.com/search?q={quote(query)}"
        items: list[IntelItem] = []
        try:
            html = await self.client.get_text(url)
            soup = BeautifulSoup(html, "html.parser")
            for span in soup.select("span.item_title")[:limit]:
                a = span.find("a")
                if not a:
                    continue
                href = a.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.v2ex.com" + href
                items.append(
                    IntelItem(
                        source="v2ex",
                        type="topic",
                        url=href,
                        title=a.get_text(strip=True),
                        content="",
                    )
                )
        except Exception:  # noqa: BLE001
            pass
        return items[:limit]

    async def fetch(self, url: str) -> IntelItem:
        html = await self.client.get_text(url)
        title_match = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        from osint_toolkit.processors.normalize import extract_text_from_html

        return IntelItem(
            source="v2ex",
            type="topic",
            url=url,
            title=title,
            content=extract_text_from_html(html)[:8000],
        )
