"""Playwright 本机 Edge 会话同步 / Browser profile sync via Playwright."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osint_toolkit.ingest.extension_events import parse_api_capture
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.auth.cookie_sync import cookies_for_playwright, validate_domain_cookie
from osint_toolkit.utils.config import get_browser_sync_config, get_cookie_sync_config

logger = logging.getLogger(__name__)

from osint_toolkit.ingest.capture_patterns import should_capture_url

_RISK_TEXT = re.compile(r"412|访问过于频繁|风控|验证码|Just a moment", re.I)


def edge_user_data_dir() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return Path(local) / "Microsoft" / "Edge" / "User Data"


def edge_profile_locked() -> bool:
    """Heuristic: Edge running or SingletonLock present."""
    if os.name == "nt":
        import subprocess

        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq msedge.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if "msedge.exe" in (out.stdout or "").lower():
                return True
        except Exception:  # noqa: BLE001
            pass
    data_dir = edge_user_data_dir()
    if not data_dir:
        return False
    profile = get_cookie_sync_config().get("profile") or "Default"
    lock = data_dir / profile / "SingletonLock"
    return lock.exists()


def build_sync_pages(
    *,
    platforms: tuple[str, ...],
    bilibili_mid: str = "",
    zhihu_token: str = "",
) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    if "zhihu" in platforms and zhihu_token:
        pages.extend(
            [
                {"label": "知乎最近浏览", "url": "https://www.zhihu.com/recent-viewed"},
                {
                    "label": "知乎主页动态",
                    "url": f"https://www.zhihu.com/people/{zhihu_token}",
                },
                {"label": "知乎收藏", "url": "https://www.zhihu.com/collections"},
            ]
        )
    if "bilibili" in platforms and bilibili_mid:
        pages.extend(
            [
                {
                    "label": "B站投稿",
                    "url": f"https://space.bilibili.com/{bilibili_mid}/video",
                },
                {
                    "label": "B站收藏",
                    "url": f"https://space.bilibili.com/{bilibili_mid}/favlist",
                },
                {
                    "label": "B站观看历史",
                    "url": "https://www.bilibili.com/account/history",
                },
                {
                    "label": "B站动态",
                    "url": f"https://space.bilibili.com/{bilibili_mid}/dynamic",
                },
                {
                    "label": "B站主页",
                    "url": f"https://space.bilibili.com/{bilibili_mid}/",
                },
            ]
        )
    return pages


@dataclass
class CaptureAccumulator:
    accepted: int = 0
    skipped: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    pages_visited: list[str] = field(default_factory=list)
    _seen_keys: set[str] = field(default_factory=set)

    def persist_rows(self, rows: list[tuple[str, dict[str, Any], str]]) -> None:
        if not rows:
            return
        conn = connect()
        try:
            for event_type, data, dedup_key in rows:
                if dedup_key in self._seen_keys:
                    self.skipped += 1
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO event_dedup (dedup_key, event_type) VALUES (?, ?)",
                    (dedup_key, event_type),
                )
                if cur.rowcount <= 0:
                    self.skipped += 1
                    continue
                conn.execute(
                    "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
                    (event_type, json.dumps(data, ensure_ascii=False)),
                )
                self._seen_keys.add(dedup_key)
                self.accepted += 1
                self.by_type[event_type] = self.by_type.get(event_type, 0) + 1
            conn.commit()
        finally:
            conn.close()

    def to_result(self, *, duration_sec: float) -> dict[str, Any]:
        return {
            "ok": self.accepted > 0 or not self.warnings,
            "accepted": self.accepted,
            "skipped": self.skipped,
            "by_type": self.by_type,
            "warnings": self.warnings,
            "pages_visited": self.pages_visited,
            "duration_sec": round(duration_sec, 2),
        }


async def _parse_response_json(response: Any) -> dict[str, Any] | list[Any] | None:
    try:
        ctype = (response.headers.get("content-type") or "").lower()
        if "json" not in ctype and "javascript" not in ctype:
            return None
        return await response.json()
    except Exception:  # noqa: BLE001
        return None


def _handle_response(
    acc: CaptureAccumulator,
    url: str,
    body: Any,
) -> None:
    if not isinstance(body, dict):
        return
    try:
        rows = parse_api_capture(url, body)
        acc.persist_rows(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("browser_sync parse failed %s: %s", url[:120], exc)
        acc.warnings.append(f"解析失败: {url[:80]}…")


async def _human_scroll(page: Any, rounds: int, interval_ms: int) -> None:
    for _ in range(max(1, rounds)):
        await page.evaluate("window.scrollBy(0, Math.max(300, window.innerHeight * 0.6))")
        await asyncio.sleep(interval_ms / 1000.0)


async def _check_page_risk(page: Any, acc: CaptureAccumulator) -> bool:
    try:
        text = await page.evaluate("() => (document.body?.innerText || '').slice(0, 800)")
        if text and _RISK_TEXT.search(text):
            acc.warnings.append(f"页面风控提示: {text[:120]}")
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


async def _resolve_identities(page: Any, acc: CaptureAccumulator) -> tuple[str, str]:
    bilibili_mid = ""
    zhihu_token = ""

    async def on_response(response: Any) -> None:
        nonlocal bilibili_mid, zhihu_token
        url = response.url or ""
        if response.status != 200:
            return
        body = await _parse_response_json(response)
        if not isinstance(body, dict):
            return
        if "bilibili.com/x/web-interface/nav" in url:
            data = body.get("data") or {}
            if data.get("mid"):
                bilibili_mid = str(data["mid"])
        if "zhihu.com/api/v4/me" in url:
            token = body.get("url_token")
            if token:
                zhihu_token = str(token)
        if should_capture_url(url):
            _handle_response(acc, url, body)

    page.on("response", on_response)
    try:
        await page.goto("https://www.bilibili.com", wait_until="domcontentloaded", timeout=45000)
        nav = await page.evaluate(
            """async () => {
              const r = await fetch('/x/web-interface/nav', { credentials: 'include' });
              return r.ok ? r.json() : null;
            }"""
        )
        if isinstance(nav, dict):
            mid = (nav.get("data") or {}).get("mid")
            if mid:
                bilibili_mid = str(mid)
    except Exception:  # noqa: BLE001
        pass
    try:
        await page.goto("https://www.zhihu.com", wait_until="domcontentloaded", timeout=45000)
        me = await page.evaluate(
            """async () => {
              const r = await fetch('/api/v4/me', { credentials: 'include' });
              return r.ok ? r.json() : null;
            }"""
        )
        if isinstance(me, dict) and me.get("url_token"):
            zhihu_token = str(me["url_token"])
    except Exception:  # noqa: BLE001
        pass
    page.remove_listener("response", on_response)
    return bilibili_mid, zhihu_token


async def _visit_sync_page(
    page: Any,
    acc: CaptureAccumulator,
    *,
    label: str,
    url: str,
    scroll_rounds: int,
    scroll_interval_ms: int,
    initial_wait_ms: int,
) -> None:
    pending: list[tuple[str, dict[str, Any]]] = []

    async def on_response(response: Any) -> None:
        resp_url = response.url or ""
        if response.status != 200 or not should_capture_url(resp_url):
            return
        body = await _parse_response_json(response)
        if isinstance(body, dict):
            pending.append((resp_url, body))

    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(initial_wait_ms / 1000.0)
        if await _check_page_risk(page, acc):
            return
        await _human_scroll(page, scroll_rounds, scroll_interval_ms)
        await asyncio.sleep(1.5)
        acc.pages_visited.append(url)
    except Exception as exc:  # noqa: BLE001
        acc.warnings.append(f"{label}: {exc}")
    finally:
        page.remove_listener("response", on_response)

    for resp_url, body in pending:
        _handle_response(acc, resp_url, body)


async def _cdp_reachable(cdp_url: str) -> bool:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{cdp_url.rstrip('/')}/json/version")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def _open_browser_context(
    pw: Any,
    *,
    mode: str,
    headless: bool,
    cdp_url: str,
    acc: CaptureAccumulator,
) -> tuple[Any, Any, str, bool]:
    """Return (context, browser_or_none, mode_used, close_context)."""
    if mode == "cdp":
        browser = await pw.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        return context, browser, "cdp", False

    if mode == "persistent" and not edge_profile_locked():
        user_data = edge_user_data_dir()
        if user_data and user_data.exists():
            profile = get_cookie_sync_config().get("profile") or "Default"
            try:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(user_data),
                    channel="msedge",
                    headless=headless,
                    args=[f"--profile-directory={profile}"],
                )
                return context, None, "persistent", True
            except Exception as exc:  # noqa: BLE001
                acc.warnings.append(f"Persistent 启动失败，改用 Cookie 模式: {exc}")

    # cookies 模式：独立 Edge 实例 + ~/.osint/cookies（Edge 可保持打开）
    bili = validate_domain_cookie("bilibili.com")
    zh = validate_domain_cookie("zhihu.com")
    if not bili["ok"] and not zh["ok"]:
        acc.warnings.append(
            "无可用 Cookie 文件。请先用扩展「从浏览器同步 Cookie」，或关闭 Edge 后用 Persistent 模式。"
        )
        raise RuntimeError("no cookies for browser sync")

    pw_cookies = cookies_for_playwright()
    if not pw_cookies:
        acc.warnings.append("Cookie 文件为空。请重新同步 Cookie。")
        raise RuntimeError("empty playwright cookies")

    browser = await pw.chromium.launch(channel="msedge", headless=headless)
    context = await browser.new_context()
    await context.add_cookies(pw_cookies)
    return context, browser, "cookies", True


async def run_browser_sync(
    *,
    platforms: tuple[str, ...] = ("bilibili", "zhihu"),
    mode: str | None = None,
    headless: bool | None = None,
    max_pages: int | None = None,
) -> dict[str, Any]:
    cfg = get_browser_sync_config()
    if not cfg.get("browser_sync_enabled", True):
        return {"ok": False, "accepted": 0, "warnings": ["browser_sync 已在配置中关闭"]}

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        return {
            "ok": False,
            "accepted": 0,
            "warnings": [
                "未安装 playwright。请运行 scripts/install-browser-sync.ps1 或 pip install -e \".[browser]\""
            ],
            "error": str(exc),
        }

    mode = (mode or cfg.get("browser_sync_mode") or "auto").lower()
    requested_mode = mode
    headless = cfg.get("browser_sync_headless", True) if headless is None else headless
    max_pages = int(max_pages or cfg.get("browser_sync_max_pages") or 6)
    page_gap_ms = int(cfg.get("browser_sync_page_gap_ms") or 8000)
    scroll_rounds = int(cfg.get("browser_sync_scroll_rounds") or 4)
    scroll_interval_ms = int(cfg.get("browser_sync_scroll_interval_ms") or 1500)
    initial_wait_ms = int(cfg.get("browser_sync_initial_wait_ms") or 3000)
    cdp_url = str(cfg.get("browser_sync_cdp_url") or "http://127.0.0.1:9222")

    acc = CaptureAccumulator()
    started = time.monotonic()

    if mode == "persistent" and edge_profile_locked():
        mode = "cookies"
        acc.warnings.append("Edge 正在运行，已自动改用 Cookie 模式（无需关闭 Edge）。")
    elif mode == "auto":
        if await _cdp_reachable(cdp_url):
            mode = "cdp"
        elif not edge_profile_locked():
            mode = "persistent"
        else:
            mode = "cookies"
            acc.warnings.append("Edge 正在运行，已自动改用 Cookie 模式。")

    async with async_playwright() as pw:
        context = None
        browser = None
        mode_used = mode
        close_ctx = True
        try:
            context, browser, mode_used, close_ctx = await _open_browser_context(
                pw,
                mode=mode,
                headless=headless,
                cdp_url=cdp_url,
                acc=acc,
            )
        except RuntimeError as exc:
            result = acc.to_result(duration_sec=time.monotonic() - started)
            result["ok"] = False
            result["error"] = str(exc)
            result["mode_requested"] = requested_mode
            return result

        try:
            page = context.pages[0] if context.pages else await context.new_page()

            bili_mid, zh_token = await _resolve_identities(page, acc)
            if "bilibili" in platforms and not bili_mid:
                acc.warnings.append("B站未登录（nav 无 mid）")
            if "zhihu" in platforms and not zh_token:
                acc.warnings.append("知乎未登录（me 无 url_token）")

            pages = build_sync_pages(
                platforms=platforms,
                bilibili_mid=bili_mid,
                zhihu_token=zh_token,
            )[:max_pages]

            for idx, spec in enumerate(pages):
                await _visit_sync_page(
                    page,
                    acc,
                    label=spec["label"],
                    url=spec["url"],
                    scroll_rounds=scroll_rounds,
                    scroll_interval_ms=scroll_interval_ms,
                    initial_wait_ms=initial_wait_ms,
                )
                if acc.warnings and any("风控" in w for w in acc.warnings[-1:]):
                    break
                if idx + 1 < len(pages):
                    gap = page_gap_ms + random.randint(0, 3000)
                    await asyncio.sleep(gap / 1000.0)
        finally:
            if context and close_ctx:
                await context.close()
            if browser and mode_used in {"cdp", "cookies"}:
                await browser.close()

    result = acc.to_result(duration_sec=time.monotonic() - started)
    result["mode_used"] = mode_used
    result["mode_requested"] = requested_mode or cfg.get("browser_sync_mode") or "persistent"
    return result
