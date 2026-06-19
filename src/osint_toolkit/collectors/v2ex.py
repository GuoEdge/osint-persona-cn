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
        self._warnings: list[str] = []

    def consume_warnings(self) -> list[str]:
        out = list(self._warnings)
        self._warnings.clear()
        return out

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        items: list[IntelItem] = []
        api = f"https://www.v2ex.com/api/search.json?q={quote(query)}"
        try:
            resp = await self.client.get(api)
            if resp.status_code == 200:
                payload = resp.json()
                for hit in (payload.get("results") or [])[:limit]:
                    if not isinstance(hit, dict):
                        continue
                    url = str(hit.get("url") or "")
                    title = str(hit.get("title") or url)
                    snippet = str(hit.get("content") or hit.get("content_rendered") or "")
                    if snippet and "<" in snippet:
                        snippet = BeautifulSoup(snippet, "html.parser").get_text(" ", strip=True)
                    items.append(
                        IntelItem(
                            source="v2ex",
                            type="topic",
                            url=url,
                            title=title,
                            content=snippet[:4000],
                            personal={"via": "v2ex_api"},
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            self._warnings.append(f"V2EX API 失败: {exc}")

        if not items:
            url = f"https://www.v2ex.com/search?q={quote(query)}"
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
                            personal={"via": "html_fallback"},
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                self._warnings.append(f"V2EX HTML 失败: {exc}")
        return items[:limit]

    async def fetch_comments(self, url: str, *, limit: int = 20) -> list[dict]:
        match = re.search(r"/t/(\d+)", url)
        if not match:
            return []
        topic_id = match.group(1)
        try:
            resp = await self.client.get(
                f"https://www.v2ex.com/api/replies/show.json?topic_id={topic_id}"
            )
            if resp.status_code != 200:
                return []
            payload = resp.json()
            out: list[dict] = []
            for reply in (payload if isinstance(payload, list) else payload.get("replies") or [])[:limit]:
                if not isinstance(reply, dict):
                    continue
                content = str(reply.get("content") or "")
                if content and "<" in content:
                    content = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
                out.append(
                    {
                        "content": content,
                        "likes": int(reply.get("thank_count") or reply.get("thanks") or 0),
                        "author": str(reply.get("member", {}).get("username") or ""),
                    }
                )
            return out
        except Exception:  # noqa: BLE001
            return []

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
