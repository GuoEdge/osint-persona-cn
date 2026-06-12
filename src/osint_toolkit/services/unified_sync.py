"""统一同步流水线 / Unified full-sync orchestration."""

from __future__ import annotations

from typing import Any, Callable

from osint_toolkit.services import browser_sync as browser_sync_service
from osint_toolkit.services import ingest
from osint_toolkit.utils.config import load_sync_config


async def run_full_sync(
    *,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run preflight → accounts-sync → browser-sync → optional AICU → extension flush hint."""
    cfg = load_sync_config()
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []

    def emit(step: dict[str, Any]) -> None:
        steps.append(step)
        if on_step:
            on_step(step)

    # 1. preflight
    preflight = await ingest.ingest_preflight()
    emit({"step": "preflight", "ok": bool(preflight.get("ready")), "data": preflight})
    if not preflight.get("ready"):
        return {
            "ok": False,
            "steps": steps,
            "warnings": list(preflight.get("hints") or []),
            "extension_flush_hint": _extension_flush_hint(),
        }

    # 2. accounts-sync (API pull only — browser-sync is a separate step)
    bili = await ingest.ingest_bilibili(include_favorites=True, include_likes=True)
    zhihu = await ingest.ingest_zhihu()
    accounts_count = (bili.get("count") or 0) + (zhihu.get("count") or 0)
    acct_warnings = list(bili.get("warnings") or []) + list(zhihu.get("warnings") or [])
    warnings.extend(acct_warnings)
    emit(
        {
            "step": "accounts-sync",
            "ok": accounts_count > 0,
            "count": accounts_count,
            "bilibili": bili,
            "zhihu": zhihu,
            "warnings": acct_warnings,
        }
    )

    if accounts_count > 0:
        from osint_toolkit.persona.auto_rebuild import maybe_auto_rebuild_persona

        persona = await maybe_auto_rebuild_persona()
        steps[-1]["persona_rebuild"] = persona

    # 3. browser-sync job (inline when enabled)
    bs_result: dict[str, Any] | None = None
    if cfg.get("browser_sync_enabled", True):
        try:
            bs_result = await browser_sync_service.execute_browser_sync(
                platforms=tuple(p for p in ("bilibili", "zhihu") if p),
                mode=cfg.get("browser_sync_mode"),
                headless=cfg.get("browser_sync_headless"),
            )
            if bs_result.get("warnings"):
                warnings.extend(bs_result["warnings"])
            emit(
                {
                    "step": "browser-sync",
                    "ok": bool(bs_result.get("accepted")),
                    "accepted": bs_result.get("accepted", 0),
                    "mode_used": bs_result.get("mode_used"),
                    "data": bs_result,
                }
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"浏览器会话补洞失败: {exc}"
            warnings.append(msg)
            emit({"step": "browser-sync", "ok": False, "error": str(exc)})
    else:
        emit({"step": "browser-sync", "ok": True, "skipped": True, "reason": "browser_sync_enabled=false"})

    # 4. optional AICU
    aicu_result: dict[str, Any] | None = None
    if cfg.get("aicu_enabled", False):
        probe = await _probe_aicu()
        status = str(probe.get("status", ""))
        if status == "PASS":
            try:
                aicu_result = await ingest.ingest_aicu()
                emit({"step": "aicu", "ok": bool(aicu_result.get("ok", aicu_result.get("count", 0))), "probe": probe, "data": aicu_result})
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"AICU 导入失败: {exc}")
                emit({"step": "aicu", "ok": False, "probe": probe, "error": str(exc)})
        else:
            emit({"step": "aicu", "ok": status in ("DISABLE", "WAF_BLOCKED"), "probe": probe, "skipped": status != "PASS"})
            if probe.get("reason"):
                warnings.append(f"AICU: {probe['reason']}")
    else:
        emit({"step": "aicu", "ok": True, "skipped": True, "reason": "aicu_enabled=false"})

    flush_hint = _extension_flush_hint()
    emit({"step": "extension-flush", "ok": True, "hint": flush_hint})

    ok = accounts_count > 0 or bool(bs_result and bs_result.get("accepted"))
    return {
        "ok": ok,
        "count": accounts_count + int((bs_result or {}).get("accepted") or 0),
        "steps": steps,
        "warnings": warnings,
        "extension_flush_hint": flush_hint,
        "aicu": aicu_result,
    }


def _extension_flush_hint() -> dict[str, Any]:
    return {
        "action": "flush_queue",
        "message": "请在扩展弹窗点击「立即上报」或等待自动 flush，以提交浏览器拦截的 API 数据。",
        "alarm": "flush-queue",
    }


async def _probe_aicu() -> dict[str, Any]:
    """Same logic as scripts/probe_aicu.py."""
    import json

    import httpx

    from osint_toolkit.ingest.aicu import AICU_GETREPLY, _aicu_request_headers, _is_waf_block, get_bilibili_mid
    from osint_toolkit.utils.config import load_config

    ingest_cfg = load_config().get("ingest", {})
    if not ingest_cfg.get("aicu_enabled", False):
        return {"status": "DISABLE", "reason": "ingest.aicu_enabled 未开启"}

    mid = await get_bilibili_mid()
    if not mid:
        return {"status": "DISABLE", "reason": "B站未登录，无法探测 AICU"}

    headers = _aicu_request_headers()
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(
                AICU_GETREPLY,
                params={"uid": str(mid), "pn": "1", "ps": "5", "mode": "0", "keyword": ""},
                headers=headers,
            )
            text = resp.text[:500]
            if _is_waf_block(resp.status_code, text):
                return {
                    "status": "WAF_BLOCKED",
                    "reason": "AICU 被 WAF 拦截，建议使用 browser-sync 补洞",
                    "http_status": resp.status_code,
                }
            data = resp.json()
            replies = (data.get("data") or {}).get("replies") or []
            if data.get("code") not in (0, None):
                return {"status": "FAIL", "reason": data.get("message", "unknown"), "code": data.get("code")}
            return {"status": "PASS", "mid": mid, "sample_count": len(replies)}
        except json.JSONDecodeError:
            return {"status": "WAF_BLOCKED", "reason": "响应非 JSON，可能被 WAF 拦截"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "FAIL", "reason": str(exc)}
