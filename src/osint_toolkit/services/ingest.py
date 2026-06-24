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
from osint_toolkit.ingest.likes import list_recognition_records
from osint_toolkit.ingest.zhihu_account import (
    ingest_activities,
    ingest_browsing,
    ingest_followees,
    ingest_member_answers,
    ingest_member_articles,
    ingest_member_pins,
    ingest_profile_meta,
    zhihu_layer_status,
)
from osint_toolkit.ingest.zhihu_account import ingest_favorites as ingest_zhihu_favorites
from osint_toolkit.ingest.zhihu_endpoint_registry import ZHIHU_PERSONA_CAPABILITY_NOTE
from osint_toolkit.ingest.zhihu_synthetic import build_synthetic_activities
from osint_toolkit.storage.knowledge import log_event_deduped


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
    finally:
        await client.aclose()


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
    finally:
        await client.aclose()


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
    warnings: list[str] = [ZHIHU_PERSONA_CAPABILITY_NOTE]
    cookie = validate_domain_cookie("zhihu.com")
    if not cookie["ok"]:
        warnings.append(cookie["reason"])
        return _empty_zhihu_result(warnings)

    logged_in, detail = await _probe_zhihu_login()
    if not logged_in:
        warnings.append(f"知乎未登录或 Cookie 失效: {detail or '请重新同步 Cookie'}")
        return _empty_zhihu_result(warnings)

    profile = {}
    try:
        profile = await ingest_profile_meta()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"账号元数据: {exc}")

    favorites: list[dict] = []
    try:
        favorites = await ingest_zhihu_favorites()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"收藏: {exc}")

    answers: list[dict] = []
    articles: list[dict] = []
    pins: list[dict] = []
    try:
        answers, _ = await ingest_member_answers()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"回答: {exc}")
    try:
        articles, _ = await ingest_member_articles()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"文章: {exc}")
    try:
        pins, _ = await ingest_member_pins()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"想法: {exc}")

    followees: list[dict] = []
    try:
        followees = await ingest_followees()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"关注: {exc}")

    browsing: list[dict] = []
    try:
        browsing, _browse_meta = await ingest_browsing()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"浏览记录: {exc}")

    browse_edge = browsing

    activities: list[dict] = []
    try:
        activities, _act_key = await ingest_activities()
        if activities:
            warnings.append(f"动态流(moments API): 新增 {len(activities)} 条（含点赞/收藏/关注动态）")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"动态流: {exc}")

    synthetic: list[dict] = []
    synthetic = build_synthetic_activities(
        votes=[],
        favorites=favorites,
        followees=followees,
        answers=answers,
        articles=articles,
        pins=pins,
    )
    if synthetic:
        warnings.append(f"已用收藏/关注/发布合成 {len(synthetic)} 条时间线事件（非官方动态流）。")
        for entry in synthetic:
            event_type = str(entry.pop("_event_type", None) or "zhihu_activity")
            url = str(entry.get("url") or "")
            kind = str(entry.get("event_kind") or "")
            log_event_deduped(event_type, entry, f"{event_type}|{url}|{kind}|synthetic")

    activities_non_vote: list[dict] = []
    activity_total = len(synthetic)

    layer_status = zhihu_layer_status(
        vote_count=0,
        browse_count=len(browsing),
        activity_count=0,
        browse_edge=len(browse_edge),
        synthetic_count=len(synthetic),
    )

    rows = favorites + followees + browsing + answers + articles + pins
    breakdown = {
        "votes": {"label": "赞同回答", "count": 0},
        "favorites": {"label": "收藏", "count": len(favorites)},
        "activities_non_vote": {"label": "动态流(非赞同)", "count": len(activities_non_vote)},
        "followees": {"label": "关注的人", "count": len(followees)},
        "browsing": {"label": "浏览记录", "count": len(browsing)},
        "answers": {"label": "我的回答", "count": len(answers)},
        "articles": {"label": "我的文章", "count": len(articles)},
        "pins": {"label": "我的想法", "count": len(pins)},
        "synthetic": {"label": "合成动态", "count": len(synthetic)},
    }
    return {
        "count": len(rows) + len(synthetic),
        "favorite_count": len(favorites),
        "activity_count": activity_total,
        "activity_non_vote_count": len(activities_non_vote) + len(synthetic),
        "vote_count": 0,
        "voteanswer_count": 0,
        "followee_count": len(followees),
        "browse_count": len(browsing),
        "answer_count": len(answers),
        "article_count": len(articles),
        "pin_count": len(pins),
        "synthetic_count": len(synthetic),
        "profile": profile,
        "layer_status": layer_status,
        "needs_browser_sync": False,
        "capability_note": ZHIHU_PERSONA_CAPABILITY_NOTE,
        "breakdown": breakdown,
        "rows": rows[:20],
        "warnings": warnings,
    }


def _empty_zhihu_result(warnings: list[str]) -> dict[str, Any]:
    return {
        "count": 0,
        "favorite_count": 0,
        "activity_count": 0,
        "vote_count": 0,
        "browse_count": 0,
        "rows": [],
        "warnings": warnings,
        "layer_status": {},
        "needs_browser_sync": False,
        "capability_note": ZHIHU_PERSONA_CAPABILITY_NOTE,
    }


def get_likes() -> dict[str, Any]:
    return list_recognition_records(limit=50)


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


async def aicu_status_detail(*, probe: bool = False) -> dict[str, Any]:
    from osint_toolkit.ingest.aicu import get_bilibili_mid, probe_aicu
    from osint_toolkit.utils.config import get_aicu_enabled

    enabled = get_aicu_enabled()
    result: dict[str, Any] = {"enabled": enabled}
    if not enabled:
        result["status"] = "DISABLE"
        result["reason"] = "请在 config 中设置 sync.aicu_enabled: true"
        return result
    mid = await get_bilibili_mid()
    result["mid"] = mid
    if not mid:
        result["status"] = "DISABLE"
        result["reason"] = "B站未登录，无法使用 AICU"
        return result
    if probe:
        probe_result = await probe_aicu()
        result.update(probe_result)
    else:
        result["status"] = "READY"
    return result


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
    needs_bs = bool(bili.get("needs_browser_sync"))
    if (
        bs_cfg.get("browser_sync_enabled", True)
        and bs_cfg.get("browser_sync_after_api", True)
        and needs_bs
    ):
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
