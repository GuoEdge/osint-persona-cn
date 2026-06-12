"""B站账号数据导入 / Bilibili account ingest."""

from __future__ import annotations

import logging

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.bilibili_wbi import wbi_get
from osint_toolkit.storage.knowledge import log_event

logger = logging.getLogger(__name__)


async def _nav_mid(client: HttpClient) -> int | None:
    try:
        resp = await client.get("https://api.bilibili.com/x/web-interface/nav")
        data = resp.json().get("data") or {}
        mid = data.get("mid")
        return int(mid) if mid else None
    except Exception:  # noqa: BLE001
        return None


async def ingest_history(limit: int = 500) -> list[dict]:
    client = HttpClient()
    url = "https://api.bilibili.com/x/web-interface/history/cursor?max=0&view_at=0&ps=20"
    results: list[dict] = []
    seen: set[str] = set()
    try:
        while len(results) < limit:
            resp = await client.get(url)
            data = resp.json().get("data") or {}
            batch = data.get("list") or []
            if not batch:
                break
            for item in batch:
                link = item.get("uri", "") or item.get("short_link_v2", "") or item.get("bvid", "")
                if not link or link in seen:
                    continue
                seen.add(link)
                entry = {
                    "source": "bilibili",
                    "title": item.get("title", ""),
                    "url": link,
                    "progress": item.get("progress", 0),
                    "duration": item.get("duration", 0),
                    "event_kind": "watch_history",
                }
                log_event("bilibili_watch", entry)
                results.append(entry)
                if len(results) >= limit:
                    break
            cursor = data.get("cursor") or {}
            if not cursor.get("max"):
                break
            url = (
                "https://api.bilibili.com/x/web-interface/history/cursor"
                f"?max={cursor['max']}&view_at={cursor['view_at']}&business=archive&ps=20"
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("bilibili history ingest failed: %s", exc)
    return results


async def ingest_favorites(limit: int = 500) -> list[dict]:
    client = HttpClient()
    results: list[dict] = []
    seen: set[str] = set()
    try:
        mid = await _nav_mid(client)
        if not mid:
            return results
        folders_resp = await client.get(
            f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={mid}"
        )
        folders = (folders_resp.json().get("data") or {}).get("list") or []
        for folder in folders:
            media_id = folder.get("id")
            if not media_id:
                continue
            pn = 1
            while len(results) < limit:
                list_url = (
                    "https://api.bilibili.com/x/v3/fav/resource/list"
                    f"?media_id={media_id}&pn={pn}&ps=20&order=mtime"
                )
                resp = await client.get(list_url)
                payload = resp.json().get("data") or {}
                medias = payload.get("medias") or []
                if not medias:
                    break
                for media in medias:
                    bvid = media.get("bvid") or media.get("bv_id") or ""
                    url = f"https://www.bilibili.com/video/{bvid}" if bvid else media.get("link", "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    entry = {
                        "source": "bilibili",
                        "title": media.get("title", ""),
                        "url": url,
                        "folder": folder.get("title", ""),
                        "event_kind": "favorite",
                    }
                    log_event("bilibili_fav", entry)
                    results.append(entry)
                    if len(results) >= limit:
                        break
                if len(medias) < 20:
                    break
                pn += 1
            if len(results) >= limit:
                break
    except Exception:  # noqa: BLE001
        pass
    return results



def _video_url(item: dict) -> str:
    bvid = item.get("bvid") or item.get("bv_id") or ""
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    short = item.get("short_link_v2") or item.get("short_link") or ""
    if short:
        return short
    aid = item.get("aid")
    if aid:
        return f"https://www.bilibili.com/video/av{aid}"
    return item.get("link") or item.get("uri") or ""


def _append_like_entries(
    items: list[dict],
    *,
    results: list[dict],
    seen: set[str],
    limit: int,
) -> None:
    for item in items:
        url = _video_url(item)
        if not url or url in seen:
            continue
        seen.add(url)
        entry = {
            "source": "bilibili",
            "title": item.get("title", ""),
            "url": url,
            "event_kind": "like",
        }
        log_event("bilibili_like", entry)
        results.append(entry)
        if len(results) >= limit:
            break


async def _ingest_likes_legacy(client: HttpClient, mid: int, limit: int) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    resp = await client.get(f"https://api.bilibili.com/x/space/like/video?vmid={mid}")
    payload = resp.json()
    if payload.get("code") not in (0, None):
        return results
    data = payload.get("data")
    if not data:
        return results
    items = data if isinstance(data, list) else (data.get("list") or [])
    _append_like_entries(items, results=results, seen=seen, limit=limit)
    return results


async def ingest_likes(limit: int = 500) -> list[dict]:
    """B站最近点赞视频（WBI like/archive/list，回退 x/space/like/video）。"""
    client = HttpClient()
    mid = await _nav_mid(client)
    if not mid:
        return []
    results: list[dict] = []
    seen: set[str] = set()
    pn = 1
    try:
        while len(results) < limit:
            payload = await wbi_get(
                client,
                "https://api.bilibili.com/x/web-interface/wbi/like/archive/list",
                {"pn": pn, "ps": 20},
            )
            if payload.get("code") not in (0, None):
                break
            items = (payload.get("data") or {}).get("list") or []
            if not items:
                if pn == 1:
                    return await _ingest_likes_legacy(client, mid, limit)
                break
            before = len(results)
            _append_like_entries(items, results=results, seen=seen, limit=limit)
            if len(results) >= limit or len(results) == before:
                break
            if len(items) < 20:
                break
            pn += 1
    except Exception:  # noqa: BLE001
        if not results:
            try:
                return await _ingest_likes_legacy(client, mid, limit)
            except Exception:  # noqa: BLE001
                pass
    return results


async def ingest_followings(limit: int = 500) -> list[dict]:
    """B站关注列表（x/relation/followings）。"""
    client = HttpClient()
    mid = await _nav_mid(client)
    if not mid:
        return []
    results: list[dict] = []
    seen: set[str] = set()
    pn = 1
    try:
        while len(results) < limit:
            resp = await client.get(
                "https://api.bilibili.com/x/relation/followings"
                f"?vmid={mid}&pn={pn}&ps=50&order=desc"
            )
            payload = resp.json()
            if payload.get("code") not in (0, None):
                break
            batch = (payload.get("data") or {}).get("list") or []
            if not batch:
                break
            for user in batch:
                uid = user.get("mid")
                if not uid:
                    continue
                url = f"https://space.bilibili.com/{uid}"
                if url in seen:
                    continue
                seen.add(url)
                entry = {
                    "source": "bilibili",
                    "title": user.get("uname", ""),
                    "url": url,
                    "event_kind": "following",
                    "uid": uid,
                }
                log_event("bilibili_follow", entry)
                results.append(entry)
                if len(results) >= limit:
                    break
            if len(batch) < 50:
                break
            pn += 1
    except Exception:  # noqa: BLE001
        pass
    return results
