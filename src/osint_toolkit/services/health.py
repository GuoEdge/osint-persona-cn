"""系统健康与数据覆盖度 / System health and event coverage."""

from __future__ import annotations

import shutil
from typing import Any

from osint_toolkit.services import auth as auth_service
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
        "bilibili_comment": ("bilibili", "发评"),
        "zhihu_fav": ("zhihu", "收藏"),
        "zhihu_vote": ("zhihu", "赞同"),
        "zhihu_activity": ("zhihu", "动态"),
        "zhihu_browse": ("zhihu", "浏览"),
        "zhihu_follow": ("zhihu", "关注"),
        "github_star": ("github", "Star"),
        "page_view": ("extension", "浏览"),
        "dwell_save": ("extension", "停留收录"),
    }
    conn = connect()
    rows = conn.execute(
        "SELECT event_type, COUNT(*) AS c FROM events GROUP BY event_type"
    ).fetchall()
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
    auth_items = auth_service.get_auth_status()
    auth_map = {x["key"]: x for x in auth_items}
    preflight = await ingest_service.ingest_preflight()
    sync_cfg = load_sync_config()
    playwright_ok = _playwright_available()

    blockers: list[str] = []
    warnings: list[str] = []

    if not auth_map.get("bilibili", {}).get("ok"):
        blockers.append("B站 Cookie 未就绪（需 SESSDATA）")
    if not auth_map.get("zhihu", {}).get("ok"):
        blockers.append("知乎 Cookie 未就绪（需 z_c0）")
    if sync_cfg.get("browser_sync_enabled") and not playwright_ok:
        blockers.append("Playwright 未安装（browser-sync 不可用）")
    if not preflight.get("ready"):
        for hint in preflight.get("hints") or []:
            warnings.append(hint)

    partial = [
        c for c in ingest_capabilities.CAPABILITIES if c.get("status") == "partial"
    ]

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
    }
