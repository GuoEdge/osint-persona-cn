"""B站账号数据导入 / Bilibili account ingest."""

from __future__ import annotations

import logging
from typing import Any

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest import account_sync_state as sync_state
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


def _bilibili_section() -> dict[str, Any]:
    return sync_state.load_account_sync_state().get("bilibili") or {}


def _persist_bilibili(**kwargs: Any) -> None:
    state = sync_state.load_account_sync_state()
    sync_state.update_bilibili_section(state, **kwargs)
    sync_state.save_account_sync_state(state)


async def _fetch_history_entries(limit: int) -> list[dict[str, Any]]:
    from osint_toolkit.ingest import bilibili_sdk

    if bilibili_sdk.sdk_enabled("ingest_history"):
        try:
            return await bilibili_sdk.ingest_history(limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bilibili sdk history failed, fallback to httpx: %s", exc)

    client = HttpClient()
    url = "https://api.bilibili.com/x/web-interface/history/cursor?max=0&view_at=0&ps=20"
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        while len(results) < limit:
            resp = await client.get(url)
            data = resp.json().get("data") or {}
            batch = data.get("list") or []
            if not batch:
                break
            for item in batch:
                view_at, bvid, link = sync_state.history_fields_from_api_item(item)
                if not link or link in seen:
                    continue
                seen.add(link)
                history_meta = item.get("history") if isinstance(item.get("history"), dict) else item
                results.append(
                    {
                        "source": "bilibili",
                        "title": item.get("title", "") or history_meta.get("title", ""),
                        "url": link,
                        "progress": history_meta.get("progress", 0),
                        "duration": history_meta.get("duration", 0),
                        "event_kind": "watch_history",
                        "view_at": view_at,
                        "bvid": bvid,
                    }
                )
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


async def ingest_history(limit: int = 500) -> list[dict]:
    section = _bilibili_section()
    cursor = section.get("history") or {}
    fetched = await _fetch_history_entries(limit)
    if not fetched:
        return []
    fresh, updated_cursor = sync_state.filter_new_history_entries(fetched, cursor)
    for entry in fresh:
        log_event("bilibili_watch", entry)
    _persist_bilibili(history=updated_cursor)
    return fresh


async def _fetch_favorite_entries(limit: int) -> list[dict[str, Any]]:
    from osint_toolkit.ingest import bilibili_sdk

    if bilibili_sdk.sdk_enabled("ingest_favorites"):
        try:
            return await bilibili_sdk.ingest_favorites(limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bilibili sdk favorites failed, fallback to httpx: %s", exc)

    client = HttpClient()
    results: list[dict[str, Any]] = []
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
                    results.append(
                        {
                            "source": "bilibili",
                            "title": media.get("title", ""),
                            "url": url,
                            "folder": folder.get("title", ""),
                            "folder_id": str(media_id),
                            "bvid": str(bvid),
                            "event_kind": "favorite",
                        }
                    )
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


async def ingest_favorites(limit: int = 500) -> list[dict]:
    section = _bilibili_section()
    seen_bvids = sync_state._string_set(section.get("favorite_bvids", []))
    fetched = await _fetch_favorite_entries(limit)
    if not fetched:
        return []
    fresh = sync_state.filter_new_by_bvids(fetched, seen_bvids)
    for entry in fresh:
        log_event("bilibili_fav", entry)
    _persist_bilibili(favorites=fetched)
    return fresh


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


def _like_entries_from_items(items: list[dict], *, seen: set[str], limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in items:
        url = _video_url(item)
        if not url or url in seen:
            continue
        seen.add(url)
        bvid = str(item.get("bvid") or item.get("bv_id") or sync_state._bvid_from_url(url))
        results.append(
            {
                "source": "bilibili",
                "title": item.get("title", ""),
                "url": url,
                "bvid": bvid,
                "event_kind": "like",
            }
        )
        if len(results) >= limit:
            break
    return results


async def _fetch_like_entries(limit: int) -> list[dict[str, Any]]:
    client = HttpClient()
    mid = await _nav_mid(client)
    if not mid:
        return []
    results: list[dict[str, Any]] = []
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
                    resp = await client.get(f"https://api.bilibili.com/x/space/like/video?vmid={mid}")
                    legacy = resp.json()
                    if legacy.get("code") in (0, None):
                        data = legacy.get("data")
                        legacy_items = data if isinstance(data, list) else (data or {}).get("list") or []
                        return _like_entries_from_items(legacy_items, seen=seen, limit=limit)
                break
            before = len(results)
            results.extend(_like_entries_from_items(items, seen=seen, limit=limit))
            if len(results) >= limit or len(results) == before:
                break
            if len(items) < 20:
                break
            pn += 1
    except Exception:  # noqa: BLE001
        if not results:
            try:
                resp = await client.get(f"https://api.bilibili.com/x/space/like/video?vmid={mid}")
                legacy = resp.json()
                if legacy.get("code") in (0, None):
                    data = legacy.get("data")
                    legacy_items = data if isinstance(data, list) else (data or {}).get("list") or []
                    return _like_entries_from_items(legacy_items, seen=seen, limit=limit)
            except Exception:  # noqa: BLE001
                pass
    return results


async def ingest_likes(limit: int = 500) -> list[dict]:
    """B站最近点赞视频（WBI like/archive/list，回退 x/space/like/video）。"""
    section = _bilibili_section()
    seen_bvids = sync_state._string_set(section.get("like_bvids", []))
    fetched = await _fetch_like_entries(limit)
    if not fetched:
        return []
    fresh = sync_state.filter_new_by_bvids(fetched, seen_bvids)
    for entry in fresh:
        log_event("bilibili_like", entry)
    _persist_bilibili(likes=fetched)
    return fresh


async def _fetch_following_entries(limit: int) -> list[dict[str, Any]]:
    from osint_toolkit.ingest import bilibili_sdk

    if bilibili_sdk.sdk_enabled("ingest_followings"):
        try:
            return await bilibili_sdk.ingest_followings(limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bilibili sdk followings failed, fallback to httpx: %s", exc)

    client = HttpClient()
    mid = await _nav_mid(client)
    if not mid:
        return []
    results: list[dict[str, Any]] = []
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
                results.append(
                    {
                        "source": "bilibili",
                        "title": user.get("uname", ""),
                        "url": url,
                        "event_kind": "following",
                        "uid": uid,
                    }
                )
                if len(results) >= limit:
                    break
            if len(batch) < 50:
                break
            pn += 1
    except Exception:  # noqa: BLE001
        pass
    return results


async def ingest_followings(limit: int = 500) -> list[dict]:
    """B站关注列表（SDK user.get_followings，回退 x/relation/followings）。"""
    section = _bilibili_section()
    seen_mids = sync_state._string_set(section.get("following_mids", []))
    fetched = await _fetch_following_entries(limit)
    if not fetched:
        return []
    fresh = sync_state.filter_new_following(fetched, seen_mids)
    for entry in fresh:
        log_event("bilibili_follow", entry)
    _persist_bilibili(following=fetched)
    return fresh
