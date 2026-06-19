"""认证服务 / Auth service."""

from __future__ import annotations

from typing import Any

from osint_toolkit.ai.client import DeepSeekClient, resolve_api_key
from osint_toolkit.ai.steering import directives_path
from osint_toolkit.auth.cookie_sync import (
    DEFAULT_DOMAINS,
    CookieSyncResult,
    import_cookie_headers,
    sync_browser_cookies,
    validate_domain_cookie,
)
from osint_toolkit.auth.paths import get_config_paths, get_cookies_dir, get_data_dir


def get_auth_status(target: str = "all", *, live_probe: bool = False) -> list[dict[str, Any]]:
    """live_probe=False 时仅检查本地配置/Cookie 文件，避免页面加载触发远程探测卡住。"""
    target = target.lower()
    results: list[dict[str, Any]] = []
    if target in {"all", "deepseek"}:
        entry: dict[str, Any] = {"name": "DeepSeek API", "key": "deepseek"}
        try:
            resolve_api_key()
            if live_probe:
                result = DeepSeekClient().test_connection()
                entry["ok"] = bool(result.get("ok"))
                entry["detail"] = f"model={result.get('model', '')}"
            else:
                entry["ok"] = True
                entry["detail"] = "已配置（未探测连通性）"
        except Exception as exc:  # noqa: BLE001
            entry["ok"] = False
            entry["detail"] = str(exc)
        results.append(entry)
    if target in {"all", "bilibili"}:
        r = validate_domain_cookie("bilibili.com")
        results.append({"name": "bilibili.com", "key": "bilibili", "ok": r["ok"], "detail": r["reason"]})
    if target in {"all", "zhihu"}:
        r = validate_domain_cookie("zhihu.com")
        results.append({"name": "zhihu.com", "key": "zhihu", "ok": r["ok"], "detail": r["reason"]})
    if target in {"all", "zhihu_openapi"}:
        if live_probe:
            from osint_toolkit.ingest.zhihu_openapi import test_connection_sync

            openapi = test_connection_sync()
            ok = bool(openapi.get("ok"))
            detail = str(openapi.get("detail") or "")
        else:
            from osint_toolkit.utils.secrets import resolve_secret

            try:
                resolve_secret("zhihu_openapi")
                ok = True
                detail = "已配置（未探测连通性）"
            except Exception as exc:  # noqa: BLE001
                ok = False
                detail = str(exc)
        results.append(
            {
                "name": "知乎开放平台",
                "key": "zhihu_openapi",
                "ok": ok,
                "detail": detail,
            }
        )
    return results


def sync_cookies(
    *,
    browser: str | None = None,
    domains: list[str] | None = None,
) -> CookieSyncResult:
    return sync_browser_cookies(browser=browser, domains=domains)


def import_cookies(
    *,
    headers_by_domain: dict[str, str],
    browser: str = "extension",
) -> CookieSyncResult:
    return import_cookie_headers(headers_by_domain=headers_by_domain, browser=browser)


def get_paths() -> dict[str, Any]:
    return {
        "config_paths": [str(p) for p in get_config_paths()],
        "cookies_dir": str(get_cookies_dir()),
        "data_dir": str(get_data_dir()),
        "directives_path": str(directives_path()),
        "api_key_hint": "设置页「API 密钥」或 DEEPSEEK_API_KEY / ZHIHU_ACCESS_SECRET 环境变量",
    }


def list_domains() -> list[str]:
    return list(DEFAULT_DOMAINS)
