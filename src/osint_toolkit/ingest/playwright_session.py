"""Playwright 轻量会话 / Lightweight Playwright session for in-browser API calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from osint_toolkit.auth.cookie_sync import cookies_for_playwright
from osint_toolkit.utils.config import get_browser_sync_config


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


async def _launch_chromium(pw: Any, *, headless: bool) -> Any:
    last_exc: Exception | None = None
    for channel in ("msedge", None):
        try:
            kwargs: dict[str, Any] = {"headless": headless}
            if channel:
                kwargs["channel"] = channel
            return await pw.chromium.launch(**kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise RuntimeError(f"无法启动 Playwright 浏览器: {last_exc}")


async def run_with_cookie_page(
    callback: Callable[[Any], Awaitable[Any]],
    *,
    domains: list[str] | None = None,
    headless: bool | None = None,
) -> Any:
    """用已同步 Cookie 启动浏览器，执行 callback(page) 后清理。"""
    if not playwright_available():
        raise RuntimeError("未安装 playwright。请运行 pip install -e \".[browser]\" 并 playwright install")

    cfg = get_browser_sync_config()
    if headless is None:
        headless = bool(cfg.get("browser_sync_headless", True))

    pw_cookies = cookies_for_playwright(domains)
    if not pw_cookies:
        raise RuntimeError("无可用 Cookie，请先用扩展同步 Cookie")

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await _launch_chromium(pw, headless=headless)
        context = await browser.new_context()
        await context.add_cookies(pw_cookies)
        page = await context.new_page()
        try:
            return await callback(page)
        finally:
            await context.close()
            await browser.close()
