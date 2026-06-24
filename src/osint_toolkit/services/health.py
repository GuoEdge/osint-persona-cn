"""系统健康与数据覆盖度 / System health and event coverage."""

from __future__ import annotations

from typing import Any

from osint_toolkit.auth.cookie_sync import validate_domain_cookie
from osint_toolkit.services import ingest as ingest_service
from osint_toolkit.services import ingest_capabilities
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.utils.config import load_sync_config


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def event_type_counts(limit: int = 40) -> dict[str, Any]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT event_type, COUNT(*) AS c
            FROM events
            GROUP BY event_type
            ORDER BY c DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()
    finally:
        conn.close()
    return {
        "total": int(total["c"]) if total else 0,
        "by_type": [{"event_type": r["event_type"], "count": int(r["c"])} for r in rows],
    }


def platform_coverage() -> list[dict[str, Any]]:
    """按平台/行为统计 events 数量，供 ingest 页覆盖度条。"""
    mapping = {
        "bilibili_watch": ("bilibili", "观看历史"),
        "bilibili_fav": ("bilibili", "收藏"),
        "bilibili_like": ("bilibili", "点赞"),
        "bilibili_coin": ("bilibili", "投币"),
        "bilibili_follow": ("bilibili", "关注"),
        "bilibili_comment_post": ("bilibili", "发评"),
        "bilibili_comment_like": ("bilibili", "评论赞"),
        "zhihu_fav": ("zhihu", "收藏"),
        "zhihu_vote": ("zhihu", "赞同"),
        "zhihu_activity": ("zhihu", "动态"),
        "zhihu_browse": ("zhihu", "浏览"),
        "zhihu_follow": ("zhihu", "关注"),
        "github_star": ("github", "Star"),
        "ext_page_visit": ("extension", "浏览"),
        "ext_page_dwell": ("extension", "停留"),
        "browser_visit": ("browser", "Edge 历史"),
        "dwell_save": ("extension", "停留收录"),
    }
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT event_type, COUNT(*) AS c FROM events GROUP BY event_type"
        ).fetchall()
    finally:
        conn.close()
    counts = {r["event_type"]: int(r["c"]) for r in rows}
    by_platform: dict[str, dict[str, Any]] = {}
    for etype, (platform, label) in mapping.items():
        bucket = by_platform.setdefault(platform, {"platform": platform, "behaviors": [], "total": 0})
        c = counts.get(etype, 0)
        bucket["behaviors"].append({"behavior": label, "event_type": etype, "count": c})
        bucket["total"] += c
    return list(by_platform.values())


async def get_health_status() -> dict[str, Any]:
    """行为同步页专用：不探测 DeepSeek，避免无关 API 拖慢加载。"""
    preflight = await ingest_service.ingest_preflight()
    sync_cfg = load_sync_config()
    playwright_ok = _playwright_available()
    bili_cookie = validate_domain_cookie("bilibili.com")
    zh_cookie = validate_domain_cookie("zhihu.com")
    login = preflight.get("login") or {}

    auth_map = {
        "bilibili": {
            "ok": bool(bili_cookie.get("ok") and (login.get("bilibili") or {}).get("ok")),
            "detail": bili_cookie.get("reason") or (login.get("bilibili") or {}).get("detail"),
        },
        "zhihu": {
            "ok": bool(zh_cookie.get("ok") and (login.get("zhihu") or {}).get("ok")),
            "detail": zh_cookie.get("reason") or (login.get("zhihu") or {}).get("detail"),
        },
    }

    blockers: list[str] = []
    warnings: list[str] = []

    if not auth_map["bilibili"]["ok"] and not auth_map["zhihu"]["ok"]:
        blockers.append("B站与知乎均未就绪：请用扩展同步 Cookie 或检查登录态")
    elif not auth_map["bilibili"]["ok"]:
        warnings.append("B站 Cookie 未就绪或已过期（SESSDATA）")
    elif not auth_map["zhihu"]["ok"]:
        warnings.append("知乎 Cookie 未就绪或已过期（z_c0）")

    if sync_cfg.get("browser_sync_enabled") and not playwright_ok:
        warnings.append("Playwright 未安装：浏览器补洞不可用，可在设置页一键安装")

    if not preflight.get("ready"):
        for hint in preflight.get("hints") or []:
            if hint not in warnings:
                warnings.append(hint)

    partial = [
        c for c in ingest_capabilities.CAPABILITIES if c.get("status") == "partial"
    ]

    from osint_toolkit.utils.config import get_aicu_enabled

    aicu_enabled = get_aicu_enabled()
    aicu: dict[str, Any] = {"enabled": aicu_enabled}
    if aicu_enabled:
        from osint_toolkit.ingest.aicu import get_bilibili_mid

        aicu["mid"] = await get_bilibili_mid()

    return {
        "ok": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "auth": auth_map,
        "preflight": preflight,
        "sync_config": sync_cfg,
        "playwright_installed": playwright_ok,
        "events": event_type_counts(),
        "coverage": platform_coverage(),
        "partial_capabilities": len(partial),
        "aicu": aicu,
    }
