"""B站采集器 / Bilibili collector."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import OrderedDict
from typing import Any

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
from osint_toolkit.processors.normalize import html_to_text

logger = logging.getLogger(__name__)

class BilibiliCollector(BaseCollector):
    name = "bilibili"
    _OID_CACHE_MAX = 2000
    _oid_cache: OrderedDict[str, str] = OrderedDict()

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
                    out = fallback[:limit]
                    await self._hydrate_video_descriptions(out)
                    return out
            if errors:
                raise RuntimeError("; ".join(errors))
        out = deduped[:limit]
        await self._hydrate_video_descriptions(out)
        return out

    _WEAK_DESC_MAX_LEN = 120

    @classmethod
    def _is_weak_video_desc(cls, content: str) -> bool:
        """搜索 API / UP 主简介常只有一句；仍应尝试 view 详情与字幕。"""
        text = (content or "").strip()
        if not text:
            return True
        if text.startswith("标签:"):
            return True
        if len(text) <= 2 or text in {"-", "—", ".", "无", "暂无简介", "暂无"}:
            return True
        if len(text) <= cls._WEAK_DESC_MAX_LEN and "\n\n" not in text:
            return True
        return False

    @classmethod
    def _needs_subtitle_fallback(cls, content: str) -> bool:
        return cls._is_weak_video_desc(content)

    async def _apply_subtitle_from_url(self, item: IntelItem) -> None:
        from osint_toolkit.ingest import bilibili_sdk

        if (item.layers.get("subtitle") or {}).get("text"):
            return
        subtitle_result = await bilibili_sdk.fetch_subtitle_for_url(item.url)
        text = str(subtitle_result.get("text") or "").strip()
        if not text:
            item.layers["subtitle"] = {
                "text": "",
                "kind": "none",
                "source": subtitle_result.get("source"),
                "reason": subtitle_result.get("reason", "no_tracks"),
            }
            return
        track = subtitle_result.get("track")
        kind = "legacy"
        if isinstance(track, dict):
            kind = bilibili_sdk._track_label(track)
        item.layers["subtitle"] = {
            "text": text,
            "kind": kind,
            "source": subtitle_result.get("source"),
            "aid": subtitle_result.get("aid"),
            "cid": subtitle_result.get("cid"),
        }
        if text not in (item.content or ""):
            item.content = (
                str(item.content or "").strip() + f"\n\n[字幕:{kind}]\n{text}"
            ).strip()[:16000]

    async def _hydrate_video_descriptions(self, items: list[IntelItem]) -> None:
        """搜索 API 常不返回简介；补 view desc，仍空则尝试 AI/CC 字幕。"""
        from osint_toolkit.ingest import bilibili_sdk

        async def fill(item: IntelItem) -> None:
            if item.type != "video":
                return
            item.content = bilibili_sdk._normalize_video_desc(item.content or "")
            current = (item.content or "").strip()
            if self._is_weak_video_desc(current):
                meta = await bilibili_sdk.fetch_video_meta(item.url, client=self.client)
                desc = str(meta.get("desc") or "").strip()
                if desc and len(desc) > len(current):
                    item.content = desc[:12000]
                elif desc and not current:
                    item.content = desc[:12000]
                if meta.get("author") and not item.author:
                    item.author = str(meta["author"])
            if self._needs_subtitle_fallback(item.content or ""):
                await self._apply_subtitle_from_url(item)

        if items:
            await asyncio.gather(*[fill(i) for i in items], return_exceptions=True)

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
            except Exception as exc:  # noqa: BLE001
                logger.warning("bilibili sdk search failed, fallback to WBI: %s", exc)
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
        from osint_toolkit.ingest import bilibili_sdk

        bvid = entry.get("bvid") or ""
        aid = entry.get("aid")
        if not bvid and not aid:
            return None
        url = f"https://www.bilibili.com/video/{bvid or ('av' + str(aid))}"
        title = re.sub(r"<[^>]+>", "", entry.get("title", ""))
        desc = bilibili_sdk._normalize_video_desc(
            html_to_text(entry.get("description", "") or entry.get("desc", ""))
        )
        if not desc:
            tags = str(entry.get("tag") or "").strip()
            if tags:
                desc = f"标签: {tags.replace(',', ' ')}"
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
        item_type = self._type_from_url(url)
        text = await self.client.get_text(url)
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        desc_match = re.search(r'"desc":"(.*?)"', text)
        content = desc_match.group(1).encode().decode("unicode_escape") if desc_match else ""
        item = IntelItem(
            source="bilibili",
            type=item_type,
            url=url,
            title=title,
            content=content[:12000],
        )
        if item_type == "video":
            await self.enrich_video(item, page_html=text)
            if not (item.layers.get("subtitle") or {}).get("text"):
                item.content = (item.content + "\n\n[注: 未获取字幕，未分析画面]").strip()[:16000]
        return item

    @staticmethod
    def _type_from_url(url: str) -> str:
        if re.search(r"(?:/read/)?cv\d+", url, re.I):
            return "article"
        if re.search(r"/opus/\d+", url):
            return "article"
        return "video"

    async def enrich_video(self, item: IntelItem, *, page_html: str | None = None) -> None:
        from osint_toolkit.analyzers.danmaku import aggregate_danmaku, summarize_danmaku
        from osint_toolkit.ingest import bilibili_sdk

        if item.type != "video":
            return
        sdk_ok = False
        if bilibili_sdk.sdk_enabled("subtitle") or bilibili_sdk.sdk_enabled("danmaku"):
            try:
                await bilibili_sdk.enrich_video_item(item)
                sdk_ok = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("bilibili sdk enrich failed, fallback to legacy: %s", exc)
        if not sdk_ok or not (item.layers.get("subtitle") or {}).get("text"):
            await self._apply_subtitle_from_url(item)
        if not item.layers.get("danmaku_top") and bilibili_sdk.sdk_enabled("danmaku"):
            lines = await bilibili_sdk.fetch_danmaku_lines(item.url)
            if lines:
                top = aggregate_danmaku(lines, top_n=15)
                item.layers["danmaku_top"] = top
                item.layers["danmaku_count"] = len(lines)
                summary = await summarize_danmaku(top)
                if summary:
                    item.layers["danmaku_summary"] = summary

    async def _fetch_subtitle_legacy(self, page_html: str) -> str:
        """Deprecated: page_html 不再用于解析 aid/cid。"""
        _ = page_html
        return ""

    async def _fetch_subtitle(self, page_html: str) -> str:
        return await self._fetch_subtitle_legacy(page_html)

    async def fetch_comments(self, url: str, limit: int | None = None) -> list[dict]:
        from osint_toolkit.ingest import bilibili_sdk

        if limit is None:
            limit = int(bilibili_sdk.get_bilibili_config().get("comments_fetch_limit") or 60)
        oid = await self._resolve_oid(url)
        if not oid:
            logger.warning("bilibili fetch_comments: could not resolve oid for %s", url)
            return []
        comment_type = self._comment_type_from_url(url)
        if bilibili_sdk.sdk_enabled("comments"):
            try:
                return await bilibili_sdk.fetch_comments_lazy(
                    oid,
                    comment_type=comment_type,
                    limit=limit,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("bilibili sdk comments failed, fallback to legacy: %s", exc)
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("bilibili wbi reply failed, fallback to legacy: %s", exc)
        api = (
            f"https://api.bilibili.com/x/v2/reply/main?type={comment_type}&oid={oid}&mode=3&plat=1"
        )
        try:
            resp = await self.client.get(api)
            data = resp.json()
            if data.get("code") not in (0, None):
                return [], 0
            payload = data.get("data") or {}
            cursor = payload.get("cursor") or {}
            pagination = cursor.get("pagination_reply") or {}
            next_offset = int(pagination.get("next_offset") or 0)
            return payload.get("replies") or [], next_offset
        except Exception as exc:  # noqa: BLE001
            logger.warning("bilibili legacy reply failed: %s", exc)
            return [], 0

    @classmethod
    def _remember_oid(cls, url: str, oid: str) -> None:
        cls._oid_cache[url] = oid
        cls._oid_cache.move_to_end(url)
        while len(cls._oid_cache) > cls._OID_CACHE_MAX:
            cls._oid_cache.popitem(last=False)

    async def _resolve_oid(self, url: str) -> str | None:
        if url in self._oid_cache:
            self._oid_cache.move_to_end(url)
            return self._oid_cache[url]
        oid: str | None = None
        cv = re.search(r"(?:/read/)?cv(\d+)", url, re.I)
        if cv:
            oid = cv.group(1)
        elif (opus := re.search(r"/opus/(\d+)", url)):
            oid = opus.group(1)
        elif "BV" in url:
            from osint_toolkit.ingest import bilibili_sdk

            aid, _cid = await bilibili_sdk.resolve_video_aid_cid(url, client=self.client)
            oid = str(aid) if aid else None
            if not oid:
                logger.warning("bilibili _resolve_oid: resolve_video_aid_cid returned None for %s", url)
        else:
            av = re.search(r"av(\d+)", url)
            oid = av.group(1) if av else None
        if oid:
            self._remember_oid(url, oid)
        return oid
