"""bilibili-api-python 桥接层（折中集成：深采/评论，搜索仍用自研 WBI）。"""

from __future__ import annotations

import logging
from typing import Any

from osint_toolkit.auth.cookie_sync import load_domain_cookie_file
from osint_toolkit.processors.normalize import html_to_text
from osint_toolkit.utils.config import load_config

logger = logging.getLogger(__name__)

_SDK_CONFIGURED = False


def sdk_installed() -> bool:
    try:
        import bilibili_api  # noqa: F401

        return True
    except ImportError:
        return False


def get_bilibili_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "use_sdk": True,
        "sdk_client": "httpx",
        "enable_bili_ticket": False,
        "features": {
            "comments": True,
            "ingest_history": True,
            "ingest_favorites": True,
            "ingest_followings": True,
        },
    }
    cfg = dict(load_config().get("bilibili") or {})
    features = dict(defaults["features"])
    features.update(cfg.get("features") or {})
    merged = {**defaults, **cfg, "features": features}
    return merged


def sdk_enabled(feature: str) -> bool:
    cfg = get_bilibili_config()
    if not cfg.get("use_sdk", True):
        return False
    if not sdk_installed():
        return False
    return bool((cfg.get("features") or {}).get(feature, True))


def _parse_cookie_pairs(header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        if name:
            out[name] = value.strip()
    return out


def load_credential():
    """从 ~/.osint/cookies/bilibili.com.json 构建 bilibili_api.Credential。"""
    if not sdk_installed():
        return None
    from bilibili_api import Credential

    data = load_domain_cookie_file("bilibili.com")
    if not data:
        return None

    cookies: dict[str, str] = {}
    for item in data.get("cookies") or []:
        name = str(item.get("name") or "")
        if name:
            cookies[name] = str(item.get("value") or "")
    if not cookies:
        cookies = _parse_cookie_pairs(str(data.get("cookie_header") or ""))

    sessdata = cookies.get("SESSDATA")
    if not sessdata:
        return None

    return Credential(
        sessdata=sessdata,
        bili_jct=cookies.get("bili_jct", ""),
        buvid3=cookies.get("buvid3", "") or cookies.get("buvid4", ""),
        dedeuserid=cookies.get("DedeUserID", ""),
        ac_time_value=cookies.get("ac_time_value", ""),
    )


def configure_sdk() -> None:
    """将 gochj 的 http 代理/超时同步到 bilibili_api.request_settings。"""
    global _SDK_CONFIGURED
    if not sdk_installed():
        return
    if _SDK_CONFIGURED:
        return

    from bilibili_api import request_settings, select_client

    bilibili_cfg = get_bilibili_config()
    http_cfg = load_config().get("http") or {}

    client = str(bilibili_cfg.get("sdk_client") or "httpx")
    try:
        select_client(client)
    except Exception as exc:  # noqa: BLE001
        logger.warning("bilibili sdk client %s unavailable, using default: %s", client, exc)

    proxy = http_cfg.get("proxy")
    if proxy:
        request_settings.set_proxy(str(proxy))
    request_settings.set_timeout(float(http_cfg.get("timeout", 30)))
    if bilibili_cfg.get("enable_bili_ticket"):
        request_settings.set_enable_bili_ticket(True)

    _SDK_CONFIGURED = True


async def resolve_mid(credential) -> int | None:
    configure_sdk()
    dede = getattr(credential, "dedeuserid", None) or ""
    if str(dede).isdigit():
        return int(dede)
    from bilibili_api import user

    payload = await user.get_self_info(credential=credential)
    mid = (payload.get("data") or {}).get("mid")
    return int(mid) if mid else None


def _video_url_from_history(item: dict) -> str:
    bvid = item.get("bvid") or item.get("bv_id") or ""
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    short = item.get("short_link_v2") or item.get("short_link") or item.get("uri") or ""
    if short:
        return short
    aid = item.get("aid")
    if aid:
        return f"https://www.bilibili.com/video/av{aid}"
    return item.get("link") or ""


async def ingest_history(limit: int = 500) -> list[dict]:
    from bilibili_api import user

    credential = load_credential()
    if not credential:
        raise RuntimeError("bilibili credential missing")

    configure_sdk()
    results: list[dict] = []
    seen: set[str] = set()
    view_at: int | None = 0
    max_oid: int | None = 0

    while len(results) < limit:
        payload = await user.get_self_history_new(
            credential=credential,
            view_at=view_at,
            max=max_oid,
        )
        data = payload.get("data") or {}
        batch = data.get("list") or []
        if not batch:
            break
        for item in batch:
            url = _video_url_from_history(item.get("history") or item)
            if not url:
                url = _video_url_from_history(item)
            if not url or url in seen:
                continue
            seen.add(url)
            hist = item.get("history") or item
            results.append(
                {
                    "source": "bilibili",
                    "title": hist.get("title", "") or item.get("title", ""),
                    "url": url,
                    "progress": hist.get("progress", 0),
                    "duration": hist.get("duration", 0),
                    "event_kind": "watch_history",
                }
            )
            if len(results) >= limit:
                break
        cursor = data.get("cursor") or {}
        if not cursor.get("max"):
            break
        view_at = cursor.get("view_at")
        max_oid = cursor.get("max")
    return results


async def ingest_favorites(limit: int = 500) -> list[dict]:
    from bilibili_api import favorite_list

    credential = load_credential()
    if not credential:
        raise RuntimeError("bilibili credential missing")

    configure_sdk()
    mid = await resolve_mid(credential)
    if not mid:
        raise RuntimeError("bilibili mid unavailable")

    folders_payload = await favorite_list.get_video_favorite_list(mid, credential=credential)
    folders = (folders_payload.get("data") or {}).get("list") or []

    results: list[dict] = []
    seen: set[str] = set()
    for folder in folders:
        media_id = folder.get("id")
        if not media_id:
            continue
        page = 1
        while len(results) < limit:
            content_payload = await favorite_list.get_video_favorite_list_content(
                int(media_id),
                page=page,
                credential=credential,
            )
            payload = content_payload.get("data") or {}
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
                        "event_kind": "favorite",
                    }
                )
                if len(results) >= limit:
                    break
            if len(medias) < 20:
                break
            page += 1
        if len(results) >= limit:
            break
    return results


async def ingest_followings(limit: int = 500) -> list[dict]:
    from bilibili_api import user

    credential = load_credential()
    if not credential:
        raise RuntimeError("bilibili credential missing")

    configure_sdk()
    mid = await resolve_mid(credential)
    if not mid:
        raise RuntimeError("bilibili mid unavailable")

    u = user.User(mid, credential=credential)
    results: list[dict] = []
    seen: set[str] = set()
    page = 1
    while len(results) < limit:
        payload = await u.get_followings(pn=page, ps=50)
        batch = (payload.get("data") or {}).get("list") or []
        if not batch:
            break
        for row in batch:
            uid = row.get("mid")
            if not uid:
                continue
            url = f"https://space.bilibili.com/{uid}"
            if url in seen:
                continue
            seen.add(url)
            results.append(
                {
                    "source": "bilibili",
                    "title": row.get("uname", ""),
                    "url": url,
                    "event_kind": "following",
                    "uid": uid,
                }
            )
            if len(results) >= limit:
                break
        if len(batch) < 50:
            break
        page += 1
    return results


_COMMENT_TYPE_MAP: dict[int, Any] = {}


def _comment_resource_type(comment_type: int):
    if not _COMMENT_TYPE_MAP:
        from bilibili_api.comment import CommentResourceType

        _COMMENT_TYPE_MAP.update(
            {
                1: CommentResourceType.VIDEO,
                12: CommentResourceType.ARTICLE,
                17: CommentResourceType.DYNAMIC,
            }
        )
    return _COMMENT_TYPE_MAP.get(comment_type, _COMMENT_TYPE_MAP[1])


async def fetch_comments_lazy(
    oid: str,
    *,
    comment_type: int = 1,
    limit: int = 40,
) -> list[dict]:
    from bilibili_api import comment
    from bilibili_api.comment import OrderType

    credential = load_credential()
    configure_sdk()

    collected: list[dict] = []
    seen_rpids: set[int] = set()
    offset = ""
    pages = 0
    resource_type = _comment_resource_type(comment_type)

    while len(collected) < limit and pages < 4:
        payload = await comment.get_comments_lazy(
            oid=int(oid),
            type_=resource_type,
            offset=offset,
            order=OrderType.TIME,
            credential=credential,
        )
        if payload.get("code") not in (0, None):
            raise RuntimeError(payload.get("message") or "bilibili sdk comments failed")
        data = payload.get("data") or {}
        replies = data.get("replies") or []
        if not replies:
            break
        for row in replies:
            rpid = row.get("rpid")
            if rpid in seen_rpids:
                continue
            seen_rpids.add(rpid)
            collected.append(
                {
                    "author": row.get("member", {}).get("uname", ""),
                    "content": html_to_text(row.get("content", {}).get("message", "")),
                    "likes": row.get("like", 0),
                    "rpid": rpid,
                }
            )
            if len(collected) >= limit:
                break
        cursor = data.get("cursor") or {}
        next_offset = (cursor.get("pagination_reply") or {}).get("next_offset")
        offset = str(next_offset) if next_offset else ""
        pages += 1
        if not offset:
            break

    collected.sort(key=lambda c: c.get("likes", 0), reverse=True)
    return collected[:limit]
