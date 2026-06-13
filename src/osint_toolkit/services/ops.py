"""统一操作入口 / Unified operations for CLI and Web."""

from __future__ import annotations

from typing import Any, Callable

from osint_toolkit.services import ingest
from osint_toolkit.services.unified_sync import run_full_sync

# 用户可见的操作词汇（CLI / Web / 扩展应保持一致）
SYNC_LABELS = {
    "full": "完整同步",
    "accounts": "账号 API 拉取",
    "browser": "浏览器会话补洞",
    "extension_flush": "上传浏览采集队列",
}

OPERATIONS_RUNBOOK: dict[str, Any] = {
    "tagline": "日常上网 → 一键同步 → 搜罗情报 → 构建画像",
    "recommended": [
        {
            "step": 1,
            "title": "启动情报台",
            "cli": "osint web",
            "note": "http://127.0.0.1:8787",
        },
        {
            "step": 2,
            "title": "同步 Cookie",
            "cli": "osint auth sync-cookies",
            "web": "设置页 或 扩展弹窗「从浏览器同步 Cookie」",
            "note": "Edge 130+ 推荐用扩展，无需关浏览器",
        },
        {
            "step": 3,
            "title": "完整同步行为数据",
            "cli": "osint sync",
            "web": "行为同步 → 一键完整同步",
            "note": "含 B站/知乎 API + Playwright 补洞；可选 AICU 发评",
        },
        {
            "step": 4,
            "title": "搜罗与收录",
            "cli": 'osint search "关键词"',
            "web": "搜罗页",
        },
        {
            "step": 5,
            "title": "构建心智画像",
            "cli": "osint persona build --review",
            "web": "心智画像页",
        },
    ],
    "sync_modes": {
        "full": {
            "label": SYNC_LABELS["full"],
            "description": "预检 → B站/知乎 API → Playwright 补洞 → 可选 AICU → 提示上传扩展队列",
            "when": "首次使用或每周例行同步",
        },
        "accounts": {
            "label": SYNC_LABELS["accounts"],
            "description": "仅 Cookie API 拉取 B站/知乎（观看/收藏/点赞/关注等）",
            "when": "刚同步 Cookie 后快速拉取",
        },
        "browser": {
            "label": SYNC_LABELS["browser"],
            "description": "Playwright 打开 space/recent-viewed 等页拦截 API",
            "when": "API 缺数据（如知乎最近浏览）时补洞",
        },
    },
    "platform_notes": {
        "weixin": "微信仅用于搜罗搜索（搜狗微信），无行为导入；需 sogou/weixin Cookie",
        "bilibili_comments": "发评历史：扩展拉取 AICU 或开启 sync.aicu_enabled 后完整同步",
    },
}


def get_operations_runbook() -> dict[str, Any]:
    return dict(OPERATIONS_RUNBOOK)


async def run_sync(
    mode: str = "full",
    *,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """统一同步入口。mode: full | accounts | browser"""
    mode = (mode or "full").lower()
    if mode == "full":
        return await run_full_sync(on_step=on_step)
    if mode == "accounts":
        return await ingest.ingest_accounts_sync()
    if mode == "browser":
        from osint_toolkit.services import browser_sync as browser_sync_service

        result = await browser_sync_service.execute_browser_sync()
        return {"ok": bool(result.get("accepted")), "mode": "browser", **result}
    raise ValueError(f"unknown sync mode: {mode}")
