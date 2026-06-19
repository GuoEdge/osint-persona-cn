"""搜罗前信源身份预检 / Source auth preflight before collect."""

from __future__ import annotations

from typing import Any

from osint_toolkit.auth.cookie_sync import validate_domain_cookie
from osint_toolkit.collectors.source_auth import get_source_auth
from osint_toolkit.utils.secrets import resolve_secret


def _cookie_ok(domains: list[str]) -> tuple[bool, str]:
    if not domains:
        return False, "未配置 Cookie 域名"
    ok_domains: list[str] = []
    reasons: list[str] = []
    for domain in domains:
        result = validate_domain_cookie(domain)
        if result.get("ok"):
            ok_domains.append(domain)
        else:
            reasons.append(f"{domain}: {result.get('reason', '未同步')}")
    if ok_domains:
        return True, f"已同步 {ok_domains[0]}"
    return False, reasons[0] if reasons else "未同步 Cookie"


def _api_ok(key_name: str) -> tuple[bool, str]:
    try:
        resolve_secret(key_name)
        return True, "API Key 已配置"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _compute_ui_status(check: dict[str, Any]) -> str:
    """供前端信源芯片展示的状态枚举。"""
    mode = str(check.get("mode") or "none")
    if mode == "none":
        return "none"
    if mode == "serp_only":
        return "serp_only"
    if check.get("ok") and not check.get("using_serp_fallback"):
        return "ready"
    if check.get("using_serp_fallback"):
        return "serp_fallback"
    if check.get("action") == "sync_cookies_or_api":
        return "needs_auth"
    if check.get("action") == "sync_cookies":
        return "needs_login"
    if not check.get("ok"):
        return "needs_login"
    return "unknown"


def _finalize_check(entry: dict[str, Any]) -> dict[str, Any]:
    entry["ui_status"] = _compute_ui_status(entry)
    return entry


def check_source_auth(source_id: str) -> dict[str, Any]:
    """检查单个信源是否满足身份要求。"""
    policy = get_source_auth(source_id)
    mode = str(policy.get("mode") or "none")
    serp_fallback = bool(policy.get("serp_fallback"))
    cookie_domains = list(policy.get("cookie_domains") or [])
    entry: dict[str, Any] = {
        "source": source_id,
        "mode": mode,
        "serp_fallback": serp_fallback,
        "login_url": policy.get("login_url") or "",
        "login_hint": policy.get("login_hint") or "",
        "cookie_domains": cookie_domains,
        "ok": True,
        "reason": "",
        "action": None,
        "using_serp_fallback": False,
    }

    if mode == "none":
        entry["reason"] = "无需登录"
        return _finalize_check(entry)

    if mode == "serp_only":
        entry["reason"] = "仅搜索引擎 site: 摘要"
        entry["using_serp_fallback"] = True
        return _finalize_check(entry)

    cookie_ok, cookie_reason = _cookie_ok(cookie_domains) if cookie_domains else (False, "无 Cookie 域")

    if mode == "cookie_or_api":
        api_key = str(policy.get("api_key") or "")
        api_ok, api_reason = _api_ok(api_key) if api_key else (False, "")
        if cookie_ok or api_ok:
            entry["reason"] = cookie_reason if cookie_ok else api_reason
            return _finalize_check(entry)
        entry["ok"] = False
        entry["reason"] = f"需 Cookie 或 API：{cookie_reason}"
        entry["action"] = "sync_cookies_or_api"
        return _finalize_check(entry)

    if mode == "cookie_required":
        if cookie_ok:
            entry["reason"] = cookie_reason
            return _finalize_check(entry)
        entry["ok"] = False
        entry["reason"] = cookie_reason
        entry["action"] = "sync_cookies"
        return _finalize_check(entry)

    if mode == "cookie_recommended":
        if cookie_ok:
            entry["reason"] = cookie_reason
            return _finalize_check(entry)
        if serp_fallback:
            entry["ok"] = True
            entry["using_serp_fallback"] = True
            entry["reason"] = f"未登录，将用搜索引擎摘要兜底（{cookie_reason}）"
            entry["action"] = "sync_cookies"
            return _finalize_check(entry)
        entry["ok"] = False
        entry["reason"] = cookie_reason
        entry["action"] = "sync_cookies"
        return _finalize_check(entry)

    entry["reason"] = "未知策略"
    return _finalize_check(entry)


def apply_auth_gates(
    sources: list[str],
    *,
    serp_fallback_accepted: list[str] | None = None,
) -> dict[str, Any]:
    """过滤无法使用的信源，并为可 SERP 兜底的信源附加提示。"""
    accepted_serp = set(serp_fallback_accepted or [])
    allowed: list[str] = []
    skipped: list[str] = []
    warnings: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []

    for sid in sources:
        check = check_source_auth(sid)
        checks.append(check)
        if check["ok"]:
            if check.get("using_serp_fallback") and sid not in accepted_serp:
                if str(check.get("mode")) == "serp_only":
                    allowed.append(sid)
                    continue
                skipped.append(sid)
                warnings.append(
                    {
                        "source": sid,
                        "warning": (
                            f"已跳过：{check.get('reason') or '未登录'}。"
                            "请登录并同步 Cookie，或在勾选时选择「不登录，使用搜索引擎摘要」。"
                        ),
                        "query": "",
                    }
                )
                continue
            allowed.append(sid)
            if check.get("using_serp_fallback"):
                warnings.append(
                    {
                        "source": sid,
                        "warning": str(check.get("reason") or "未登录，使用搜索引擎摘要"),
                        "query": "",
                    }
                )
            continue
        if sid in accepted_serp:
            allowed.append(sid)
            warnings.append(
                {
                    "source": sid,
                    "warning": (
                        f"未登录，已按你的选择使用搜索引擎摘要（{check.get('reason') or '身份未就绪'}）"
                    ),
                    "query": "",
                }
            )
            continue
        if check.get("serp_fallback") and str(check.get("mode")) != "cookie_required":
            allowed.append(sid)
            warnings.append(
                {
                    "source": sid,
                    "warning": str(check.get("reason") or "身份未就绪，已降级为搜索引擎摘要"),
                    "query": "",
                }
            )
            continue
        skipped.append(sid)
        warnings.append(
            {
                "source": sid,
                "warning": f"已跳过：{check.get('reason') or '身份未验证'}。{check.get('login_hint') or ''}",
                "query": "",
            }
        )

    return {
        "allowed_sources": allowed,
        "skipped_sources": skipped,
        "warnings": warnings,
        "checks": checks,
    }


def check_sources_auth(sources: list[str]) -> dict[str, Any]:
    """供 API / UI 展示的身份检查结果（不过滤）。"""
    checks = [check_source_auth(s) for s in sources]
    need_sync = [c for c in checks if c.get("action") == "sync_cookies" and not c.get("ok")]
    need_api = [c for c in checks if c.get("action") == "sync_cookies_or_api" and not c.get("ok")]
    return {
        "checks": checks,
        "all_ok": all(c.get("ok") for c in checks),
        "need_cookie_sync": need_sync,
        "need_api": need_api,
    }
