"""统一同步流水线 / Unified full-sync orchestration."""

from __future__ import annotations

from typing import Any, Callable

from osint_toolkit.pipeline.progress import check_cancelled
from osint_toolkit.services import browser_sync as browser_sync_service
from osint_toolkit.services import ingest
from osint_toolkit.utils.config import load_sync_config


async def run_full_sync(
    *,
    on_step: Callable[[dict[str, Any]], None] | None = None,
    on_progress: Callable[..., None] | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Run preflight → accounts-sync → browser-sync → optional AICU → extension flush hint."""

    def progress(phase: str, detail: str = "", **extra: Any) -> None:
        check_cancelled(job_id)
        if on_progress:
            on_progress(phase, detail, **extra)

    cfg = load_sync_config()
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []

    def emit(step: dict[str, Any]) -> None:
        steps.append(step)
        if on_step:
            on_step(step)

    # 1. preflight
    progress("preflight", "检查 Cookie 与登录态…", step_done=0)
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
    progress("accounts-sync", "拉取 B站/知乎 API…", step_done=1)
    bili = await ingest.ingest_bilibili(include_favorites=True, include_likes=True)
    check_cancelled(job_id)
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

    # 3. Edge 浏览历史（画像信号，与扩展被动浏览互补）
    progress("browser-history", "导入 Edge 浏览历史…", step_done=2)
    browser_count = 0
    if cfg.get("browser_history_enabled", True):
        since_days = int(cfg.get("browser_history_since_days") or 90)
        try:
            browser_result = ingest.ingest_browser(since_days=since_days)
            browser_count = int(browser_result.get("count") or 0)
            if browser_result.get("warnings"):
                warnings.extend(browser_result["warnings"])
            emit(
                {
                    "step": "browser-history",
                    "ok": True,
                    "count": browser_count,
                    "since_days": since_days,
                    "skipped": browser_count == 0 and not browser_result.get("warnings"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Edge 浏览历史导入失败: {exc}"
            warnings.append(msg)
            emit({"step": "browser-history", "ok": False, "error": str(exc)})
    else:
        emit({"step": "browser-history", "ok": True, "skipped": True, "reason": "browser_history_enabled=false"})

    # 4. browser-sync job (inline when enabled)
    progress("browser-sync", "Playwright 浏览器补洞…", step_done=3)
    bs_result: dict[str, Any] | None = None
    if cfg.get("browser_sync_enabled", True):
        try:
            bs_result = await browser_sync_service.execute_browser_sync(
                platforms=tuple(p for p in ("bilibili", "zhihu") if p),
                mode=cfg.get("browser_sync_mode"),
                headless=cfg.get("browser_sync_headless"),
            )
            check_cancelled(job_id)
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

    # 5. optional AICU
    progress("aicu", "AICU 发评导入…", step_done=4)
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

    progress("extension-flush", "等待扩展上报…", step_done=5)
    flush_hint = _extension_flush_hint()
    emit({"step": "extension-flush", "ok": True, "hint": flush_hint})

    ok = accounts_count > 0 or browser_count > 0 or bool(bs_result and bs_result.get("accepted"))
    total_count = accounts_count + browser_count + int((bs_result or {}).get("accepted") or 0)
    if ok:
        from osint_toolkit.services.setup import record_full_sync

        record_full_sync()
    progress("done", f"完整同步完成 · {total_count} 条", step_done=6, percent=100)
    return {
        "ok": ok,
        "count": total_count,
        "steps": steps,
        "warnings": warnings,
        "extension_flush_hint": flush_hint,
        "aicu": aicu_result,
    }


def _extension_flush_hint() -> dict[str, Any]:
    return {
        "action": "flush_queue",
        "message": "请在扩展弹窗点击「上传浏览采集队列」或等待自动同步（约 1 分钟）。",
        "alarm": "flush-queue",
    }


async def _probe_aicu() -> dict[str, Any]:
    from osint_toolkit.ingest.aicu import probe_aicu

    return await probe_aicu()
