"""B站采集器 / Bilibili collector."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
from osint_toolkit.processors.normalize import html_to_text


class BilibiliCollector(BaseCollector):
    name = "bilibili"
    _oid_cache: dict[str, str] = {}

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        items: list[IntelItem] = []
        errors: list[str] = []
        for search_type, parser in (
            ("video", self._parse_video),
            ("article", self._parse_article),
        ):
            try:
                for entry in await self._search_type(query, search_type, limit):
                    item = parser(entry)
                    if item:
                        items.append(item)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{search_type}: {exc}")
        seen: set[str] = set()
        deduped: list[IntelItem] = []
        for item in items:
            if item.url in seen:
                continue
            seen.add(item.url)
            deduped.append(item)
        if not deduped and errors:
            raise RuntimeError("; ".join(errors))
        return deduped[:limit]

    async def _search_type(self, query: str, search_type: str, limit: int) -> list[dict]:
        url = (
            "https://api.bilibili.com/x/web-interface/search/type?"
            f"search_type={search_type}&keyword={quote(query)}&page=1&page_size={limit}"
        )
        resp = await self.client.get(url)
        text = (resp.text or "").strip()
        if not text:
            raise RuntimeError(f"bilibili {search_type}: empty response (status={resp.status_code})")
        if text[0] not in "{[":
            raise RuntimeError(
                f"bilibili {search_type}: non-json response (status={resp.status_code}, head={text[:80]!r})"
            )
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"bilibili {search_type}: invalid json ({exc})") from exc
        if data.get("code") not in (0, None):
            raise RuntimeError(data.get("message") or f"bilibili api code={data.get('code')}")
        payload = data.get("data") or {}
        return (payload.get("result") or [])[:limit]

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

    def _parse_article(self, entry: dict) -> IntelItem | None:
        cv_id = entry.get("id") or entry.get("cvid") or entry.get("aid")
        if not cv_id:
            return None
        url = f"https://www.bilibili.com/read/cv{cv_id}"
        title = re.sub(r"<[^>]+>", "", entry.get("title", ""))
        desc = html_to_text(entry.get("desc", "") or entry.get("description", ""))
        return IntelItem(
            source="bilibili",
            type="article",
            url=url,
            title=title,
            content=desc,
            author=entry.get("author", "") or entry.get("author_name", ""),
            metrics=IntelMetrics(
                views=int(entry.get("view", 0) or 0),
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

    async def fetch_comments(self, url: str, limit: int = 40) -> list[dict]:
        oid = await self._resolve_oid(url)
        if not oid:
            return []
        comment_type = self._comment_type_from_url(url)
        collected: list[dict] = []
        seen_rpids: set[int] = set()
        next_offset = 0
        pages = 0
        while len(collected) < limit and pages < 2:
            replies, next_offset = await self._fetch_reply_page(oid, next_offset, comment_type)
            if not replies:
                break
            for r in replies:
                rpid = r.get("rpid")
                if rpid in seen_rpids:
                    continue
                seen_rpids.add(rpid)
                collected.append(
                    {
                        "author": r.get("member", {}).get("uname", ""),
                        "content": html_to_text(r.get("content", {}).get("message", "")),
                        "likes": r.get("like", 0),
                        "rpid": rpid,
                    }
                )
                if len(collected) >= limit:
                    break
            pages += 1
            if not next_offset:
                break
        collected.sort(key=lambda c: c.get("likes", 0), reverse=True)
        return collected[:limit]

    def _comment_type_from_url(self, url: str) -> int:
        if re.search(r"(?:/read/)?cv\d+", url, re.I):
            return 12
        if re.search(r"/opus/\d+", url):
            return 17
        return 1

    async def _fetch_reply_page(
        self, oid: str, next_offset: int, comment_type: int = 1
    ) -> tuple[list[dict], int]:
        base = "https://api.bilibili.com/x/v2/reply/wbi/main"
        params: dict[str, Any] = {
            "type": comment_type,
            "oid": oid,
            "mode": 3,
            "plat": 1,
        }
        if next_offset:
            params["pagination_reply"] = json.dumps({"offset": next_offset})
        try:
            from osint_toolkit.ingest.bilibili_wbi import wbi_get

            data = await wbi_get(self.client, base, params)
            if data.get("code") not in (0, None):
                raise RuntimeError(data.get("message") or "wbi reply failed")
            payload = data.get("data") or {}
            replies = payload.get("replies") or []
            cursor = payload.get("cursor") or {}
            return replies, int(cursor.get("pagination_reply", {}).get("next_offset") or 0)
        except Exception:  # noqa: BLE001
            pass
        api = (
            f"https://api.bilibili.com/x/v2/reply/main?type={comment_type}&oid={oid}&mode=3&plat=1"
        )
        try:
            resp = await self.client.get(api)
            data = resp.json()
            if data.get("code") not in (0, None):
                return [], 0
            payload = data.get("data") or {}
            return payload.get("replies") or [], 0
        except Exception:  # noqa: BLE001
            return [], 0

    async def _resolve_oid(self, url: str) -> str | None:
        if url in self._oid_cache:
            return self._oid_cache[url]
        oid: str | None = None
        cv = re.search(r"(?:/read/)?cv(\d+)", url, re.I)
        if cv:
            oid = cv.group(1)
        elif (opus := re.search(r"/opus/(\d+)", url)):
            oid = opus.group(1)
        elif "BV" in url:
            text = await self.client.get_text(url)
            aid_match = re.search(r'"aid":(\d+)', text)
            oid = aid_match.group(1) if aid_match else None
        else:
            av = re.search(r"av(\d+)", url)
            oid = av.group(1) if av else None
        if oid:
            self._oid_cache[url] = oid
        return oid
