"""Playwright 浏览器同步服务 / Browser sync service."""

from __future__ import annotations

from typing import Any

from osint_toolkit.ingest.browser_sync import run_browser_sync
from osint_toolkit.utils.config import get_browser_sync_config


async def browser_sync_status() -> dict[str, Any]:
    cfg = get_browser_sync_config()
    try:
        import playwright  # noqa: F401

        playwright_ok = True
    except ImportError:
        playwright_ok = False
    return {
        "enabled": bool(cfg.get("browser_sync_enabled", True)),
        "playwright_installed": playwright_ok,
        "mode": cfg.get("browser_sync_mode", "auto"),
        "cdp_url": cfg.get("browser_sync_cdp_url"),
        "after_api": bool(cfg.get("browser_sync_after_api", True)),
    }


async def execute_browser_sync(
    *,
    platforms: tuple[str, ...] = ("bilibili", "zhihu"),
    mode: str | None = None,
    headless: bool | None = None,
) -> dict[str, Any]:
    result = await run_browser_sync(platforms=platforms, mode=mode, headless=headless)
    if (result.get("accepted") or 0) > 0:
        from osint_toolkit.persona.auto_rebuild import maybe_auto_rebuild_persona

        result["persona_rebuild"] = await maybe_auto_rebuild_persona()
    return result
