"""导入服务 / Ingest service."""

from __future__ import annotations

import asyncio
from typing import Any

from osint_toolkit.auth.cookie_sync import get_last_sync_errors, validate_domain_cookie
from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.aicu import get_bilibili_mid, ingest_aicu_comments, ingest_aicu_from_json
from osint_toolkit.ingest.bilibili_account import (
    ingest_favorites,
    ingest_followings,
    ingest_history,
    ingest_likes,
)
from osint_toolkit.ingest.browser import ingest_browser_history
from osint_toolkit.ingest.likes import list_endorsements
from osint_toolkit.ingest.zhihu_account import (
    ingest_activities,
    ingest_browsing,
    ingest_followees,
    ingest_voteanswers,
)
from osint_toolkit.ingest.zhihu_account import ingest_favorites as ingest_zhihu_favorites


def ingest_browser(*, since_days: int = 90) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        rows = ingest_browser_history(since_days=since_days)
    except Exception as exc:  # noqa: BLE001
        return {"count": 0, "rows": [], "warnings": [str(exc)]}
    return {"count": len(rows), "rows": rows[:20], "warnings": warnings}


async def _probe_bilibili_login() -> tuple[bool, str | None]:
    client = HttpClient()
    try:
        resp = await client.get("https://api.bilibili.com/x/web-interface/nav")
        data = resp.json().get("data") or {}
        if data.get("isLogin") and data.get("mid"):
            return True, str(data.get("mid"))
        return False, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


async def _probe_zhihu_login() -> tuple[bool, str | None]:
    client = HttpClient()
    try:
        resp = await client.get("https://www.zhihu.com/api/v4/me")
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        token = str(resp.json().get("url_token") or "")
        return bool(token), token or None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


async def ingest_preflight() -> dict[str, Any]:
    """快速检查 Cookie 与登录态（不拉全量数据）。"""
    bili_cookie = validate_domain_cookie("bilibili.com")
    zh_cookie = validate_domain_cookie("zhihu.com")
    sync_errors = get_last_sync_errors()
    bili_ok, bili_detail = await _probe_bilibili_login()
    zh_ok, zh_detail = await _probe_zhihu_login()
    hints: list[str] = []
    if sync_errors and (not bili_cookie["ok"] or not zh_cookie["ok"] or not bili_ok or not zh_ok):
        hints.append(sync_errors[-1])
    if not bili_cookie["ok"]:
        hints.append(f"B站 Cookie 文件: {bili_cookie['reason']}")
    elif not bili_ok:
        hints.append(f"B站 Cookie 已过期或未登录（{bili_detail or 'nav 未返回 mid'}）")
    if not zh_cookie["ok"]:
        hints.append(f"知乎 Cookie 文件: {zh_cookie['reason']}")
    elif not zh_ok:
        hints.append(f"知乎 Cookie 已过期或未登录（{zh_detail or 'me 失败'}）")
    if not hints and not bili_ok and not zh_ok:
        hints.append("请先在设置页「同步 Cookie」（需完全关闭 Edge 后点同步）")
    return {
        "cookies": {"bilibili": bili_cookie, "zhihu": zh_cookie},
        "login": {
            "bilibili": {"ok": bili_ok, "detail": bili_detail},
            "zhihu": {"ok": zh_ok, "detail": zh_detail},
        },
        "sync_errors": sync_errors,
        "ready": (bili_ok or zh_ok),
        "hints": hints,
    }


async def ingest_bilibili(*, include_favorites: bool = True, include_likes: bool = True) -> dict[str, Any]:
    warnings: list[str] = []
    cookie = validate_domain_cookie("bilibili.com")
    if not cookie["ok"]:
        warnings.append(cookie["reason"])
        return {
            "count": 0,
            "watch_count": 0,
            "favorite_count": 0,
            "like_count": 0,
            "rows": [],
            "warnings": warnings,
        }
    logged_in, detail = await _probe_bilibili_login()
    if not logged_in:
        warnings.append(f"B站未登录或 Cookie 失效: {detail or '请重新同步 Cookie'}")
        return {
            "count": 0,
            "watch_count": 0,
            "favorite_count": 0,
            "like_count": 0,
            "rows": [],
            "warnings": warnings,
        }
    try:
        watch = await ingest_history()
    except Exception as exc:  # noqa: BLE001
        watch = []
        warnings.append(f"观看历史: {exc}")
    fav: list[dict] = []
    likes: list[dict] = []
    followings: list[dict] = []
    if include_favorites:
        try:
            fav = await ingest_favorites()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"收藏: {exc}")
    if include_likes:
        try:
            likes = await ingest_likes()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"点赞: {exc}")
    try:
        followings = await ingest_followings()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"关注: {exc}")
    rows = watch + fav + likes + followings
    return {
        "count": len(rows),
        "watch_count": len(watch),
        "favorite_count": len(fav),
        "like_count": len(likes),
        "following_count": len(followings),
        "rows": rows[:20],
        "warnings": warnings,
    }


async def ingest_zhihu() -> dict[str, Any]:
    warnings: list[str] = []
    cookie = validate_domain_cookie("zhihu.com")
    if not cookie["ok"]:
        warnings.append(cookie["reason"])
        return {
            "count": 0,
            "favorite_count": 0,
            "activity_count": 0,
            "vote_count": 0,
            "browse_count": 0,
            "rows": [],
            "warnings": warnings,
        }
    logged_in, detail = await _probe_zhihu_login()
    if not logged_in:
        warnings.append(f"知乎未登录或 Cookie 失效: {detail or '请重新同步 Cookie'}")
        return {
            "count": 0,
            "favorite_count": 0,
            "activity_count": 0,
            "vote_count": 0,
            "browse_count": 0,
            "rows": [],
            "warnings": warnings,
        }
    try:
        favorites = await ingest_zhihu_favorites()
    except Exception as exc:  # noqa: BLE001
        favorites = []
        warnings.append(f"收藏: {exc}")
    try:
        activities = await ingest_activities()
    except Exception as exc:  # noqa: BLE001
        activities = []
        warnings.append(f"动态: {exc}")
    voteanswers: list[dict] = []
    try:
        voteanswers = await ingest_voteanswers()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"赞同明细: {exc}")
    followees: list[dict] = []
    try:
        followees = await ingest_followees()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"关注: {exc}")
    try:
        browsing = await ingest_browsing()
    except Exception as exc:  # noqa: BLE001
        browsing = []
        warnings.append(f"浏览记录: {exc}")
    votes = voteanswers or [a for a in activities if a.get("event_kind") == "answer_vote"]
    if not browsing and not activities and not voteanswers:
        warnings.append(
            "知乎浏览/动态 API 为空：同步时会自动打开 recent-viewed 与主页，或请检查隐私设置"
        )
    rows = favorites + activities + voteanswers + followees + browsing
    return {
        "count": len(rows),
        "favorite_count": len(favorites),
        "activity_count": len(activities),
        "vote_count": len(votes),
        "voteanswer_count": len(voteanswers),
        "followee_count": len(followees),
        "browse_count": len(browsing),
        "rows": rows[:20],
        "warnings": warnings,
    }


def get_likes() -> dict[str, Any]:
    rows = list_endorsements()
    return {"count": len(rows), "rows": rows}


async def ingest_aicu() -> dict[str, Any]:
    return await ingest_aicu_comments()


async def ingest_my_comments(limit: int = 10_000) -> dict[str, Any]:
    from osint_toolkit.ingest.bilibili_sdk import ingest_my_comments as _sdk_my_comments

    return await _sdk_my_comments(limit=limit)


async def ingest_aicu_json(payload: Any) -> dict[str, Any]:
    return await ingest_aicu_from_json(payload)


async def bilibili_mid() -> dict[str, Any]:
    mid = await get_bilibili_mid()
    return {"mid": mid, "ok": bool(mid)}


def aicu_status() -> dict[str, Any]:
    from osint_toolkit.utils.config import get_aicu_enabled

    return {"enabled": get_aicu_enabled()}


async def ingest_accounts_sync() -> dict[str, Any]:
    """One-shot B站 + 知乎 Cookie API pull (same as extension server ingest)."""
    import sys

    preflight = await ingest_preflight()
    warnings = list(preflight.get("hints") or [])
    if not preflight.get("ready"):
        return {
            "ok": False,
            "count": 0,
            "bilibili": {"count": 0, "warnings": warnings},
            "zhihu": {"count": 0, "warnings": warnings},
            "preflight": preflight,
            "warnings": warnings,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        }
    bili = await ingest_bilibili(include_favorites=True, include_likes=True)
    zhihu = await ingest_zhihu()
    warnings = warnings + list(bili.get("warnings") or []) + list(zhihu.get("warnings") or [])
    total = (bili.get("count") or 0) + (zhihu.get("count") or 0)
    if total == 0 and not warnings:
        warnings.append(
            "拉取完成但为 0 条：请确认用 start-osint-web.bat 启动（Python 3.12 venv），并在设置页重新同步 Cookie"
        )
    result: dict[str, Any] = {
        "ok": total > 0,
        "count": total,
        "bilibili": bili,
        "zhihu": zhihu,
        "preflight": preflight,
        "warnings": warnings,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    if total > 0:
        from osint_toolkit.persona.auto_rebuild import maybe_auto_rebuild_persona

        result["persona_rebuild"] = await maybe_auto_rebuild_persona()

    from osint_toolkit.utils.config import get_browser_sync_config

    bs_cfg = get_browser_sync_config()
    if bs_cfg.get("browser_sync_enabled", True) and bs_cfg.get("browser_sync_after_api", True):
        try:
            from osint_toolkit.services import browser_sync as browser_sync_service

            bs = await browser_sync_service.execute_browser_sync()
            result["browser_sync"] = bs
            if bs.get("warnings"):
                warnings.extend(bs["warnings"])
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"浏览器会话补洞失败: {exc}")
            result["browser_sync"] = {"ok": False, "error": str(exc)}

    result["warnings"] = warnings
    return result


def _run_sync(coro: Any) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("请在 async 上下文中使用 await ingest_bilibili() / ingest_zhihu()")


def ingest_bilibili_sync(*, include_favorites: bool = True, include_likes: bool = True) -> dict[str, Any]:
    return _run_sync(ingest_bilibili(include_favorites=include_favorites, include_likes=include_likes))


def ingest_zhihu_sync() -> dict[str, Any]:
    return _run_sync(ingest_zhihu())
