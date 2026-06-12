"""B站采集器 / Bilibili collector."""

from __future__ import annotations

import re
from urllib.parse import quote

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
from osint_toolkit.processors.normalize import html_to_text


class BilibiliCollector(BaseCollector):
    name = "bilibili"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        url = (
            "https://api.bilibili.com/x/web-interface/search/type?"
            f"search_type=video&keyword={quote(query)}&page=1&page_size={limit}"
        )
        items: list[IntelItem] = []
        try:
            resp = await self.client.get(url)
            data = resp.json()
            for entry in data.get("data", {}).get("result", [])[:limit]:
                item = self._parse_video(entry)
                if item:
                    items.append(item)
        except Exception:  # noqa: BLE001
            items = [
                IntelItem(
                    source="bilibili",
                    type="search_link",
                    url=f"https://search.bilibili.com/all?keyword={quote(query)}",
                    title=f"B站搜索: {query}",
                    content="API 请求失败，请检查网络或 Cookie",
                )
            ]
        return items[:limit]

    def _parse_video(self, entry: dict) -> IntelItem | None:
        bvid = entry.get("bvid") or ""
        aid = entry.get("aid")
        url = f"https://www.bilibili.com/video/{bvid or ('av' + str(aid))}"
        title = re.sub(r"<[^>]+>", "", entry.get("title", ""))
        desc = html_to_text(entry.get("description", "") or entry.get("desc", ""))
        return IntelItem(
            source="bilibili",
            type="video",
            url=url,
            title=title,
            content=desc,
            author=entry.get("author", ""),
            metrics=IntelMetrics(
                views=int(entry.get("play", 0) or 0),
                likes=int(entry.get("like", 0) or 0),
            ),
        )

    async def fetch(self, url: str) -> IntelItem:
        text = await self.client.get_text(url)
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        desc_match = re.search(r'"desc":"(.*?)"', text)
        content = desc_match.group(1).encode().decode("unicode_escape") if desc_match else ""
        subtitle = await self._fetch_subtitle(text)
        if subtitle:
            content = (content + "\n\n[字幕]\n" + subtitle).strip()
        else:
            content = (content + "\n\n[注: 未获取字幕，未分析画面]").strip()
        return IntelItem(
            source="bilibili",
            type="video",
            url=url,
            title=title,
            content=content[:12000],
        )

    async def _fetch_subtitle(self, page_html: str) -> str:
        aid_match = re.search(r'"aid":(\d+)', page_html)
        cid_match = re.search(r'"cid":(\d+)', page_html)
        if not aid_match or not cid_match:
            return ""
        player_url = (
            f"https://api.bilibili.com/x/player/v2?aid={aid_match.group(1)}&cid={cid_match.group(1)}"
        )
        try:
            resp = await self.client.get(player_url)
            data = resp.json().get("data", {})
            subtitle = data.get("subtitle", {}).get("subtitles", [])
            if not subtitle:
                return ""
            sub_url = subtitle[0].get("subtitle_url", "")
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url
            body = await self.client.get_text(sub_url)
            from osint_toolkit.processors.subtitle import parse_subtitle_json

            return parse_subtitle_json(body)
        except Exception:  # noqa: BLE001
            return ""

    async def fetch_comments(self, url: str, limit: int = 20) -> list[dict]:
        oid = await self._resolve_oid(url)
        if not oid:
            return []
        api = f"https://api.bilibili.com/x/v2/reply/main?type=1&oid={oid}&mode=3"
        try:
            resp = await self.client.get(api)
            data = resp.json().get("data", {})
            replies = data.get("replies") or []
            return [
                {
                    "author": r.get("member", {}).get("uname", ""),
                    "content": html_to_text(r.get("content", {}).get("message", "")),
                    "likes": r.get("like", 0),
                }
                for r in replies[:limit]
            ]
        except Exception:  # noqa: BLE001
            return []

    async def _resolve_oid(self, url: str) -> str | None:
        if "BV" in url:
            text = await self.client.get_text(url)
            aid_match = re.search(r'"aid":(\d+)', text)
            return aid_match.group(1) if aid_match else None
        av = re.search(r"av(\d+)", url)
        return av.group(1) if av else None
