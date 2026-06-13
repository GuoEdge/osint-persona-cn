"""B站采集器 / Bilibili collector."""

from __future__ import annotations

import json
import re
from typing import Any

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
from osint_toolkit.processors.normalize import html_to_text


class BilibiliCollector(BaseCollector):
    name = "bilibili"
    _oid_cache: dict[str, str] = {}

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def _search_handlers(self) -> dict[str, Any]:
        return {
            "video": self._parse_video,
            "article": self._parse_article,
            "bili_user": self._parse_user,
            "topic": self._parse_topic,
            "media_bangumi": self._parse_bangumi,
            "media_ft": self._parse_media_ft,
        }

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        from osint_toolkit.ingest import bilibili_sdk

        handlers = self._search_handlers()
        search_types = bilibili_sdk.configured_search_types()
        items: list[IntelItem] = []
        errors: list[str] = []
        for search_type in search_types:
            parser = handlers.get(search_type)
            if not parser:
                errors.append(f"{search_type}: no parser")
                continue
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
        if not deduped:
            search_cfg = bilibili_sdk.get_search_config()
            if search_cfg.get("serp_fallback", True):
                fallback = await self._serp_site_search(query, limit)
                if fallback:
                    return fallback[:limit]
            if errors:
                raise RuntimeError("; ".join(errors))
        return deduped[:limit]

    async def _search_type(self, query: str, search_type: str, limit: int) -> list[dict]:
        from osint_toolkit.ingest import bilibili_sdk

        normalized = bilibili_sdk.normalize_search_type(search_type)
        search_cfg = bilibili_sdk.get_search_config()

        if bilibili_sdk.sdk_enabled("search"):
            try:
                return await bilibili_sdk.search_entries(
                    query,
                    normalized,
                    limit=limit,
                )
            except Exception:
                if not search_cfg.get("legacy_wbi_fallback", True):
                    raise
                if not bilibili_sdk.legacy_wbi_supports(normalized):
                    raise

        if not bilibili_sdk.legacy_wbi_supports(normalized):
            raise RuntimeError(f"legacy wbi search does not support type={normalized}")

        from osint_toolkit.ingest.bilibili_wbi import wbi_get

        base = "https://api.bilibili.com/x/web-interface/wbi/search/type"
        params = {
            "search_type": normalized,
            "keyword": query,
            "page": 1,
            "page_size": limit,
        }
        data = await wbi_get(self.client, base, params)
        code = data.get("code")
        if code == -352:
            raise RuntimeError(data.get("message") or "风控校验失败")
        if code not in (0, None):
            raise RuntimeError(data.get("message") or f"bilibili api code={code}")
        payload = data.get("data") or {}
        return (payload.get("result") or [])[:limit]

    async def _serp_site_search(self, query: str, limit: int) -> list[IntelItem]:
        """WBI 搜索失败时，用 SERP site:bilibili.com 回退。"""
        from osint_toolkit.collectors.serp.engine import SerpEngine, hits_to_items

        engine = SerpEngine(client=self.client)
        hits, _ = await engine.site_search("bilibili.com", query, limit=limit)
        items = hits_to_items(hits, source="bilibili")
        for item in items:
            href = item.url
            if "/video/" in href or "BV" in href:
                item.type = "video"
            elif "/read/cv" in href:
                item.type = "article"
            else:
                item.type = "snippet"
        return items

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

    def _parse_user(self, entry: dict) -> IntelItem | None:
        mid = entry.get("mid")
        if not mid:
            return None
        uname = re.sub(r"<[^>]+>", "", entry.get("uname", "") or entry.get("title", ""))
        sign = html_to_text(entry.get("usign", "") or entry.get("sign", "") or "")
        return IntelItem(
            source="bilibili",
            type="user",
            url=f"https://space.bilibili.com/{mid}",
            title=uname,
            content=sign,
            author=uname,
            metrics=IntelMetrics(views=int(entry.get("fans", 0) or 0)),
        )

    def _parse_topic(self, entry: dict) -> IntelItem | None:
        topic_id = entry.get("id") or entry.get("topic_id")
        if not topic_id:
            return None
        title = re.sub(r"<[^>]+>", "", entry.get("title", "") or entry.get("name", ""))
        desc = html_to_text(entry.get("description", "") or entry.get("desc", "") or "")
        return IntelItem(
            source="bilibili",
            type="topic",
            url=f"https://www.bilibili.com/v/topic/detail/?topic_id={topic_id}",
            title=title,
            content=desc,
            metrics=IntelMetrics(views=int(entry.get("view", 0) or entry.get("arc", 0) or 0)),
        )

    def _parse_bangumi(self, entry: dict) -> IntelItem | None:
        season_id = entry.get("season_id")
        media_id = entry.get("media_id") or entry.get("id")
        if season_id:
            url = f"https://www.bilibili.com/bangumi/play/ss{season_id}"
        elif media_id:
            url = f"https://www.bilibili.com/bangumi/media/md{media_id}"
        else:
            return None
        title = re.sub(r"<[^>]+>", "", entry.get("title", "") or entry.get("org_title", ""))
        desc = html_to_text(entry.get("desc", "") or entry.get("evaluate", "") or "")
        return IntelItem(
            source="bilibili",
            type="bangumi",
            url=url,
            title=title,
            content=desc,
            metrics=IntelMetrics(
                views=int(entry.get("play", 0) or entry.get("view", 0) or 0),
                likes=int(entry.get("favorites", 0) or entry.get("follow", 0) or 0),
            ),
        )

    def _parse_media_ft(self, entry: dict) -> IntelItem | None:
        item = self._parse_bangumi(entry)
        if item:
            item.type = "media"
        return item

    async def fetch(self, url: str) -> IntelItem:
        text = await self.client.get_text(url)
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        desc_match = re.search(r'"desc":"(.*?)"', text)
        content = desc_match.group(1).encode().decode("unicode_escape") if desc_match else ""
        item = IntelItem(
            source="bilibili",
            type="video",
            url=url,
            title=title,
            content=content[:12000],
        )
        await self.enrich_video(item, page_html=text)
        if not (item.layers.get("subtitle") or {}).get("text"):
            item.content = (item.content + "\n\n[注: 未获取字幕，未分析画面]").strip()[:16000]
        return item

    async def enrich_video(self, item: IntelItem, *, page_html: str | None = None) -> None:
        from osint_toolkit.ingest import bilibili_sdk

        if item.type != "video":
            return
        if bilibili_sdk.sdk_enabled("subtitle") or bilibili_sdk.sdk_enabled("danmaku"):
            try:
                await bilibili_sdk.enrich_video_item(item)
                return
            except Exception:  # noqa: BLE001
                pass
        if page_html is None:
            page_html = await self.client.get_text(item.url)
        subtitle = await self._fetch_subtitle_legacy(page_html)
        if subtitle:
            item.layers["subtitle"] = {"text": subtitle, "kind": "legacy", "source": "legacy"}
            item.content = (str(item.content or "").strip() + "\n\n[字幕]\n" + subtitle).strip()[:16000]

    async def _fetch_subtitle_legacy(self, page_html: str) -> str:
        from osint_toolkit.processors.subtitle import pick_subtitle_track, parse_subtitle_json

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
            tracks = (data.get("subtitle") or {}).get("subtitles") or []
            track = pick_subtitle_track(tracks)
            if not track:
                return ""
            sub_url = track.get("subtitle_url", "")
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url
            body = await self.client.get_text(sub_url)
            return parse_subtitle_json(body)
        except Exception:  # noqa: BLE001
            return ""

    async def _fetch_subtitle(self, page_html: str) -> str:
        return await self._fetch_subtitle_legacy(page_html)

    async def fetch_comments(self, url: str, limit: int | None = None) -> list[dict]:
        from osint_toolkit.ingest import bilibili_sdk

        if limit is None:
            limit = int(bilibili_sdk.get_bilibili_config().get("comments_fetch_limit") or 60)
        oid = await self._resolve_oid(url)
        if not oid:
            return []
        comment_type = self._comment_type_from_url(url)
        from osint_toolkit.ingest import bilibili_sdk

        if bilibili_sdk.sdk_enabled("comments"):
            try:
                return await bilibili_sdk.fetch_comments_lazy(
                    oid,
                    comment_type=comment_type,
                    limit=limit,
                )
            except Exception:  # noqa: BLE001
                pass
        collected: list[dict] = []
        seen_rpids: set[int] = set()
        next_offset = 0
        pages = 0
        while len(collected) < limit and pages < max(4, (limit // 20) + 1):
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
