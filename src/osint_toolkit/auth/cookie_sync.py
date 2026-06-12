"""浏览器 Cookie 同步 / Browser cookie synchronization."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from osint_toolkit.auth.paths import get_cookies_dir
from osint_toolkit.utils.config import get_cookie_sync_config

DEFAULT_DOMAINS = [
    "bilibili.com",
    "zhihu.com",
    "baidu.com",
    "bing.com",
    "v2ex.com",
    "juejin.cn",
    "sspai.com",
    "huxiu.com",
    "36kr.com",
]

DOMAIN_REQUIRED_KEYS: dict[str, list[str]] = {
    "bilibili.com": ["SESSDATA"],
    "zhihu.com": ["z_c0"],
}


@dataclass
class CookieSyncResult:
    browser: str
    output_dir: Path
    domains_requested: list[str]
    domains_synced: list[str] = field(default_factory=list)
    cookie_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    synced_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def _normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    if domain.startswith("."):
        domain = domain[1:]
    return domain


def _cookie_matches_domain(cookie_domain: str, target_domain: str) -> bool:
    cookie_domain = _normalize_domain(cookie_domain.lstrip("."))
    target_domain = _normalize_domain(target_domain)
    return cookie_domain == target_domain or cookie_domain.endswith(f".{target_domain}")


def _group_cookies_by_domain(
    cookies: list[dict[str, Any]],
    domains: list[str],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {d: [] for d in domains}
    for cookie in cookies:
        cookie_domain = str(cookie.get("domain", ""))
        for domain in domains:
            if _cookie_matches_domain(cookie_domain, domain):
                grouped[domain].append(cookie)
    return grouped


def _to_cookie_header(cookies: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        if name in seen:
            continue
        seen.add(name)
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def _extract_browser_cookies(browser: str, domains: list[str]) -> list[dict[str, Any]]:
    import rookiepy

    browser = browser.lower()
    if browser == "edge":
        return list(rookiepy.edge(domains=domains))
    if browser in {"chrome", "chromium", "brave", "vivaldi", "opera", "opera_gx", "arc"}:
        extractor = getattr(rookiepy, browser)
        return list(extractor(domains=domains))
    if browser == "firefox":
        return list(rookiepy.firefox(domains=domains))
    raise ValueError(f"不支持的浏览器: {browser}")


def sync_browser_cookies(
    *,
    browser: str | None = None,
    domains: list[str] | None = None,
    output_dir: Path | None = None,
) -> CookieSyncResult:
    """
    从本机浏览器提取 Cookie 并按域名写入本地文件。

  Windows 上推荐 Edge。同步前建议关闭浏览器，避免 Cookie 数据库被锁定。
    """
    cfg = get_cookie_sync_config()
    browser = (browser or cfg.get("browser") or "edge").lower()
    domains = domains or list(cfg.get("domains") or DEFAULT_DOMAINS)
    domains = [_normalize_domain(d) for d in domains]
    output_dir = output_dir or get_cookies_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    result = CookieSyncResult(
        browser=browser,
        output_dir=output_dir,
        domains_requested=domains,
    )

    try:
        raw_cookies = _extract_browser_cookies(browser, domains)
    except Exception as exc:  # noqa: BLE001
        hint = ""
        if platform.system() == "Windows":
            hint = " 请先完全关闭 Edge 后重试。"
        else:
            hint = f" 当前系统为 {platform.system()}，请在 Windows 本机运行此命令。"
        msg = f"读取浏览器 Cookie 失败: {exc}.{hint}"
        if "rookiepy" in str(exc):
            msg += " 请用 gochj-web 目录下的 .venv 启动 Web（start-osint-web.bat），不要用系统 Python 3.14。"
        low = str(exc).lower()
        if "appbound" in low or "app-bound" in low or "running as admin" in low:
            msg += " Edge 130+ 请用扩展弹窗「从浏览器同步 Cookie」，或右键以管理员运行 sync-cookies-admin.bat。"
        result.errors.append(msg)
        _write_index(result)
        return result

    grouped = _group_cookies_by_domain(raw_cookies, domains)
    for domain, domain_cookies in grouped.items():
        if not domain_cookies:
            continue
        payload = {
            "domain": domain,
            "browser": browser,
            "synced_at": result.synced_at,
            "cookie_header": _to_cookie_header(domain_cookies),
            "cookies": domain_cookies,
        }
        out_file = output_dir / f"{domain}.json"
        out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result.domains_synced.append(domain)
        result.cookie_counts[domain] = len(domain_cookies)

    _write_index(result)
    return result


def _write_index(result: CookieSyncResult) -> None:
    index_path = result.output_dir / "_index.json"
    index_path.write_text(
        json.dumps(
            {
                "browser": result.browser,
                "synced_at": result.synced_at,
                "domains_requested": result.domains_requested,
                "domains_synced": result.domains_synced,
                "cookie_counts": result.cookie_counts,
                "errors": result.errors,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def import_cookie_headers(
    *,
    headers_by_domain: dict[str, str],
    browser: str = "extension",
    output_dir: Path | None = None,
) -> CookieSyncResult:
    """从扩展或手动粘贴写入 Cookie 文件（绕过 Edge App-Bound 加密）。"""
    output_dir = output_dir or get_cookies_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    domains = [_normalize_domain(d) for d in headers_by_domain]
    result = CookieSyncResult(
        browser=browser,
        output_dir=output_dir,
        domains_requested=domains,
    )
    for domain in domains:
        header = str(headers_by_domain.get(domain) or headers_by_domain.get(f".{domain}") or "").strip()
        if not header:
            continue
        payload = {
            "domain": domain,
            "browser": browser,
            "synced_at": result.synced_at,
            "cookie_header": header,
            "cookies": [],
        }
        out_file = output_dir / f"{domain}.json"
        out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result.domains_synced.append(domain)
        result.cookie_counts[domain] = max(1, header.count(";") + 1)
    if not result.domains_synced:
        result.errors.append("未收到任何域名的 Cookie 字符串")
    _write_index(result)
    return result


def load_domain_cookie_file(domain: str, cookies_dir: Path | None = None) -> dict[str, Any] | None:
    """读取某域名 Cookie JSON 文件。"""
    domain = _normalize_domain(domain)
    path = (cookies_dir or get_cookies_dir()) / f"{domain}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def cookies_for_playwright(domains: list[str] | None = None) -> list[dict[str, Any]]:
    """将 ~/.osint/cookies 转为 Playwright add_cookies 格式。"""
    domains = domains or ["bilibili.com", "zhihu.com"]
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for domain in domains:
        data = load_domain_cookie_file(domain)
        if not data:
            continue
        raw = data.get("cookies") or []
        if raw:
            for c in raw:
                name = str(c.get("name") or "")
                value = c.get("value")
                if not name or value is None:
                    continue
                dom = str(c.get("domain") or f".{domain}")
                path = str(c.get("path") or "/")
                key = (name, dom, path)
                if key in seen:
                    continue
                seen.add(key)
                item: dict[str, Any] = {
                    "name": name,
                    "value": str(value),
                    "domain": dom,
                    "path": path,
                }
                if c.get("expires") is not None:
                    item["expires"] = int(c["expires"])
                if c.get("httpOnly") is not None:
                    item["httpOnly"] = bool(c["httpOnly"])
                if c.get("secure") is not None:
                    item["secure"] = bool(c["secure"])
                out.append(item)
            continue
        header = str(data.get("cookie_header") or "")
        for part in header.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, _, value = part.partition("=")
            name = name.strip()
            if not name:
                continue
            dom = f".{domain}" if not domain.startswith(".") else domain
            key = (name, dom, "/")
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "value": value.strip(), "domain": dom, "path": "/"})
    return out


def load_cookie_header(domain: str, cookies_dir: Path | None = None) -> str | None:
    """读取某域名已同步的 Cookie 请求头字符串。"""
    domain = _normalize_domain(domain)
    path = (cookies_dir or get_cookies_dir()) / f"{domain}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    header = data.get("cookie_header")
    return str(header) if header else None


def get_last_sync_errors(cookies_dir: Path | None = None) -> list[str]:
    """读取最近一次 Cookie 同步的错误信息。"""
    index_path = (cookies_dir or get_cookies_dir()) / "_index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    errors = data.get("errors") or []
    return [str(e) for e in errors if e]


def validate_domain_cookie(domain: str, cookies_dir: Path | None = None) -> dict[str, Any]:
    """检查域名 Cookie 是否存在且包含关键字段。"""
    domain = _normalize_domain(domain)
    header = load_cookie_header(domain, cookies_dir)
    if not header:
        return {
            "domain": domain,
            "ok": False,
            "reason": "未找到同步文件，请先运行 osint auth sync-cookies",
        }

    required = DOMAIN_REQUIRED_KEYS.get(domain, [])
    missing = [key for key in required if f"{key}=" not in header]
    if missing:
        return {
            "domain": domain,
            "ok": False,
            "reason": f"缺少关键 Cookie: {', '.join(missing)}",
        }
    return {"domain": domain, "ok": True, "reason": "ok"}


def cookie_header_for_url(url: str, cookies_dir: Path | None = None) -> str | None:
    """根据 URL 自动匹配已同步的 Cookie。"""
    host = urlparse(url).hostname or ""
    host = host.lower()
    if not host:
        return None

    cookies_path = cookies_dir or get_cookies_dir()
    for domain_file in cookies_path.glob("*.json"):
        if domain_file.name == "_index.json":
            continue
        domain = domain_file.stem
        if host == domain or host.endswith(f".{domain}"):
            return load_cookie_header(domain, cookies_path)
    return None
