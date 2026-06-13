"""bilibili-api-python 桥接层（折中集成：搜索/深采/评论，失败回退自研 WBI）。"""

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
            "search": True,
            "comments": True,
            "ingest_history": True,
            "ingest_favorites": True,
            "ingest_followings": True,
        },
        "search": {
            "types": ["video", "article", "bili_user"],
            "order_video": "totalrank",
            "order_article": "totalrank",
            "order_user": "fans",
            "time_start": None,
            "time_end": None,
            "video_zone_tid": None,
            "time_range_minutes": -1,
            "serp_fallback": True,
            "legacy_wbi_fallback": True,
        },
    }
    cfg = dict(load_config().get("bilibili") or {})
    features = dict(defaults["features"])
    features.update(cfg.get("features") or {})
    search_defaults = dict(defaults["search"])
    search_defaults.update(cfg.get("search") or {})
    merged = {**defaults, **cfg, "features": features, "search": search_defaults}
    return merged


def get_search_config() -> dict[str, Any]:
    return dict(get_bilibili_config().get("search") or {})


_SEARCH_TYPE_ALIASES: dict[str, str] = {
    "user": "bili_user",
    "liveuser": "live_user",
    "bangumi": "media_bangumi",
    "ft": "media_ft",
    "media": "media_ft",
}


def normalize_search_type(search_type: str) -> str:
    key = str(search_type or "").strip().lower()
    return _SEARCH_TYPE_ALIASES.get(key, key)


def configured_search_types() -> list[str]:
    types = get_search_config().get("types") or ["video", "article"]
    out: list[str] = []
    seen: set[str] = set()
    for raw in types:
        normalized = normalize_search_type(str(raw))
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out or ["video", "article"]


_LEGACY_WBI_TYPES = frozenset({"video", "article"})


def legacy_wbi_supports(search_type: str) -> bool:
    return normalize_search_type(search_type) in _LEGACY_WBI_TYPES


def _resolve_search_object_type(search_type: str):
    from bilibili_api.search import SearchObjectType

    normalized = normalize_search_type(search_type)
    for item in SearchObjectType:
        if item.value == normalized:
            return item
    raise ValueError(f"unsupported bilibili search type: {search_type}")


def _resolve_order_type(search_enum, search_cfg: dict[str, Any]):
    from bilibili_api.search import OrderArticle, OrderUser, OrderVideo

    if search_enum.value == "video":
        raw = search_cfg.get("order_video") or "totalrank"
        return OrderVideo(str(raw))
    if search_enum.value == "article":
        raw = search_cfg.get("order_article") or "totalrank"
        return OrderArticle(str(raw))
    if search_enum.value == "bili_user":
        raw = search_cfg.get("order_user") or "fans"
        return OrderUser(str(raw))
    return None


async def search_entries(
    query: str,
    search_type: str,
    *,
    limit: int = 10,
    page: int = 1,
) -> list[dict]:
    """调用 bilibili_api.search.search_by_type，返回原始 result 列表。"""
    from bilibili_api import search

    configure_sdk()
    search_cfg = get_search_config()
    search_enum = _resolve_search_object_type(search_type)
    order_type = _resolve_order_type(search_enum, search_cfg)

    kwargs: dict[str, Any] = {
        "keyword": query,
        "search_type": search_enum,
        "page": page,
        "page_size": limit,
    }
    if order_type is not None:
        kwargs["order_type"] = order_type

    time_start = search_cfg.get("time_start")
    time_end = search_cfg.get("time_end")
    if time_start and time_end:
        kwargs["time_start"] = str(time_start)
        kwargs["time_end"] = str(time_end)

    zone_tid = search_cfg.get("video_zone_tid")
    if zone_tid not in (None, "", 0, "0"):
        kwargs["video_zone_type"] = int(zone_tid)

    time_range = int(search_cfg.get("time_range_minutes", -1) or -1)
    if time_range > 0:
        kwargs["time_range"] = time_range

    payload = await search.search_by_type(**kwargs)
    code = payload.get("code")
    if code == -352:
        raise RuntimeError(payload.get("message") or "风控校验失败")
    if code not in (0, None):
        raise RuntimeError(payload.get("message") or f"bilibili sdk search code={code}")

    data = payload.get("data") or {}
    return (data.get("result") or [])[:limit]


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
