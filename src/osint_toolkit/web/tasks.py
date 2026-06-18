"""后台搜索/同步任务 / Background jobs."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.pipeline.job_progress import init_full_sync_progress, make_full_sync_callbacks
from osint_toolkit.pipeline.progress import (
    JobCancelled,
    clear_progress,
    get_progress,
    init_progress,
    is_cancelled,
    request_cancel,
    update_progress,
)
from osint_toolkit.services.run_session import set_run_status
from osint_toolkit.services.search_params import strip_session_keys
from osint_toolkit.research.tree import update_search_node_status

_MAX_JOBS = 50
_jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
_async_tasks: dict[str, asyncio.Task[Any]] = {}


def _search_run_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return strip_session_keys(kwargs)


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + f"-{uuid4().hex[:8]}"


def _trim_jobs() -> None:
    while len(_jobs) > _MAX_JOBS:
        _jobs.popitem(last=False)


def get_job(run_id: str) -> dict[str, Any] | None:
    job = _jobs.get(run_id)
    if job:
        _jobs.move_to_end(run_id)
    return job


def _job_payload(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job)
    progress = get_progress(job_id)
    if progress:
        payload["progress"] = progress
    return payload


def cancel_job(job_id: str) -> bool:
    """请求取消任务（搜罗 / 完整同步等）。"""
    job = _jobs.get(job_id)
    if not job or job.get("status") not in ("running", None):
        return False
    request_cancel(job_id)
    task = _async_tasks.pop(job_id, None)
    if task and not task.done():
        task.cancel()
    return True


def _load_result_from_disk(run_id: str) -> dict[str, Any] | None:
    run_dir = get_data_dir() / "runs" / run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items: list[IntelItem] = []
    for path in sorted(run_dir.glob("*items_dedup.json")) + sorted(run_dir.glob("*items_raw.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            items = [IntelItem.from_dict(d) for d in data]
            break
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = [IntelItem.from_dict(d) for d in data["items"]]
            break
    report = ""
    report_path = run_dir / "report.md"
    if report_path.exists():
        report = report_path.read_text(encoding="utf-8")
    simulations: list[dict] = []
    for path in sorted(run_dir.glob("*_simulations.json")):
        try:
            simulations = json.loads(path.read_text(encoding="utf-8"))
            break
        except json.JSONDecodeError:
            continue
    source_errors: list[dict] = []
    for path in sorted(run_dir.glob("*_collect_all.json")):
        try:
            step = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(step.get("data"), dict):
                source_errors = step["data"].get("source_errors") or []
            break
        except json.JSONDecodeError:
            continue
    query_analysis: dict[str, Any] = {}
    for path in sorted(run_dir.glob("*query_analysis.json")):
        try:
            query_analysis = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(query_analysis, dict) and "data" in query_analysis:
                query_analysis = query_analysis.get("data") or query_analysis
            break
        except json.JSONDecodeError:
            continue
    discover_meta: dict[str, Any] = {}
    for path in sorted(run_dir.glob("*alias_discover.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            discover_meta = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
            if not isinstance(discover_meta, dict):
                discover_meta = {}
            break
        except json.JSONDecodeError:
            continue
    queries_used = query_analysis.get("queries_used") if isinstance(query_analysis, dict) else []
    return {
        "run_id": run_id,
        "items": items,
        "report": report,
        "report_path": str(report_path) if report_path.exists() else None,
        "simulations": simulations,
        "run_dir": str(run_dir),
        "manifest": manifest,
        "source_errors": source_errors,
        "query_analysis": query_analysis if isinstance(query_analysis, dict) else {},
        "discover_meta": discover_meta,
        "queries_used": queries_used or [],
    }


def start_search_job(**kwargs: Any) -> str:
    run_id = new_run_id()
    request_snapshot = {k: v for k, v in kwargs.items() if v is not None}
    set_run_status(run_id, "running", request=request_snapshot)
    _jobs[run_id] = {
        "status": "running",
        "kind": "search",
        "result": None,
        "error": None,
        "query": kwargs.get("query", ""),
        "started_at": datetime.now(UTC).isoformat(),
    }
    init_progress(run_id)
    _trim_jobs()
    task = asyncio.create_task(_execute_search(run_id, **kwargs))
    _async_tasks[run_id] = task
    return run_id


async def _execute_search(run_id: str, **kwargs: Any) -> None:
    from osint_toolkit.services import search as search_service

    final_status = "error"
    error_msg: str | None = None
    try:
        result = await search_service.run_search(**_search_run_kwargs(kwargs), run_id=run_id)
        if is_cancelled(run_id):
            final_status = "cancelled"
            error_msg = "已取消"
            _jobs[run_id] = {"status": "cancelled", "kind": "search", "result": None, "error": error_msg}
        else:
            final_status = "done"
            _jobs[run_id] = {"status": "done", "kind": "search", "result": result, "error": None}
        _jobs.move_to_end(run_id)
        _trim_jobs()
    except (JobCancelled, asyncio.CancelledError):
        final_status = "cancelled"
        error_msg = "已取消"
        _jobs[run_id] = {"status": "cancelled", "kind": "search", "result": None, "error": error_msg}
        _jobs.move_to_end(run_id)
        _trim_jobs()
    except Exception as exc:  # noqa: BLE001
        final_status = "error"
        error_msg = str(exc)
        _jobs[run_id] = {"status": "error", "kind": "search", "result": None, "error": error_msg}
        _jobs.move_to_end(run_id)
        _trim_jobs()
    finally:
        from osint_toolkit.services.run_session import read_request

        req = read_request(run_id) or {}
        tree_id = req.get("tree_id")
        if tree_id:
            update_search_node_status(tree_id, run_id, status=final_status)
        set_run_status(run_id, final_status, error=error_msg)
        clear_progress(run_id)
        _async_tasks.pop(run_id, None)


def get_job_result(run_id: str) -> dict[str, Any] | None:
    job = get_job(run_id)
    if job and job.get("result"):
        return job["result"]
    return _load_result_from_disk(run_id)


def start_browser_sync_job(**kwargs: Any) -> str:
    job_id = new_run_id()
    _jobs[job_id] = {"status": "running", "kind": "browser_sync", "result": None, "error": None}
    _trim_jobs()
    task = asyncio.create_task(_execute_browser_sync(job_id, **kwargs))
    _async_tasks[job_id] = task
    return job_id


async def _execute_browser_sync(job_id: str, **kwargs: Any) -> None:
    from osint_toolkit.services import browser_sync as browser_sync_service

    try:
        result = await browser_sync_service.execute_browser_sync(**kwargs)
        _jobs[job_id] = {"status": "done", "kind": "browser_sync", "result": result, "error": None}
        _jobs.move_to_end(job_id)
        _trim_jobs()
    except Exception as exc:  # noqa: BLE001
        _jobs[job_id] = {"status": "error", "kind": "browser_sync", "result": None, "error": str(exc)}
        _jobs.move_to_end(job_id)
        _trim_jobs()
    finally:
        _async_tasks.pop(job_id, None)


def start_full_sync_job() -> str:
    job_id = new_run_id()
    _jobs[job_id] = {
        "status": "running",
        "kind": "full_sync",
        "steps": [],
        "result": None,
        "error": None,
    }
    init_full_sync_progress(job_id)
    _trim_jobs()
    task = asyncio.create_task(_execute_full_sync(job_id))
    _async_tasks[job_id] = task
    return job_id


async def _execute_full_sync(job_id: str) -> None:
    from osint_toolkit.services import unified_sync

    on_progress, on_step_completed = make_full_sync_callbacks(job_id)

    def on_step(step: dict[str, Any]) -> None:
        job = _jobs.get(job_id)
        if job:
            job["steps"] = list(job.get("steps") or []) + [step]
        name = str(step.get("step") or "")
        if name:
            on_step_completed(name)

    try:
        on_progress("preflight", "检查 Cookie 与登录态…", step_done=0)
        result = await unified_sync.run_full_sync(on_step=on_step, on_progress=on_progress, job_id=job_id)
        if is_cancelled(job_id):
            _jobs[job_id] = {
                "status": "cancelled",
                "kind": "full_sync",
                "steps": result.get("steps") or _jobs.get(job_id, {}).get("steps") or [],
                "result": None,
                "error": "已取消",
            }
        else:
            _jobs[job_id] = {
                "status": "done",
                "kind": "full_sync",
                "steps": result.get("steps") or _jobs.get(job_id, {}).get("steps") or [],
                "result": result,
                "error": None,
            }
        _jobs.move_to_end(job_id)
        _trim_jobs()
    except (JobCancelled, asyncio.CancelledError):
        _jobs[job_id] = {
            "status": "cancelled",
            "kind": "full_sync",
            "steps": (_jobs.get(job_id) or {}).get("steps") or [],
            "result": None,
            "error": "已取消",
        }
        _jobs.move_to_end(job_id)
        _trim_jobs()
    except Exception as exc:  # noqa: BLE001
        _jobs[job_id] = {
            "status": "error",
            "kind": "full_sync",
            "steps": (_jobs.get(job_id) or {}).get("steps") or [],
            "result": None,
            "error": str(exc),
        }
        _jobs.move_to_end(job_id)
        _trim_jobs()
    finally:
        clear_progress(job_id)
        _async_tasks.pop(job_id, None)


def start_playwright_install_job() -> str:
    job_id = new_run_id()
    _jobs[job_id] = {
        "status": "running",
        "kind": "playwright_install",
        "log": [],
        "result": None,
        "error": None,
    }
    init_progress(job_id, step_total=2)
    update_progress(job_id, "pip", detail="准备安装 Playwright…", step_done=0, percent=0)
    _trim_jobs()
    task = asyncio.create_task(_execute_playwright_install(job_id))
    _async_tasks[job_id] = task
    return job_id


def _playwright_percent(phase: str, line: str, step_done: int) -> int:
    lower = line.lower()
    if phase == "pip":
        if "installing" in lower or "collecting" in lower:
            return 25
        return 10 + step_done * 15
    if "downloading" in lower or "chromium" in lower or "msedge" in lower:
        return 55
    if "playwright" in lower:
        return 45
    return 35 + step_done * 25


async def _execute_playwright_install(job_id: str) -> None:
    from osint_toolkit.services import dependencies

    log: list[str] = []
    phase = "pip"

    def _append(msg: str) -> None:
        log.append(msg)
        job = _jobs.get(job_id)
        if job:
            job["log"] = list(log)
        pct = _playwright_percent(phase, msg, int(get_progress(job_id).get("step_done") or 0) if get_progress(job_id) else 0)
        update_progress(
            job_id,
            phase,
            detail=msg[:160],
            percent=min(95, pct),
        )

    def _on_progress(stage: str, detail: str, step_done: int, percent: int) -> None:
        nonlocal phase
        phase = stage
        update_progress(job_id, stage, detail=detail, step_done=step_done, percent=percent)

    try:
        result = await dependencies.install_playwright(log_lines=log, on_log=_append, on_progress=_on_progress)
        update_progress(job_id, "done", detail="Playwright 安装完成", step_done=2, percent=100)
        _jobs[job_id] = {
            "status": "done",
            "kind": "playwright_install",
            "log": log,
            "result": result,
            "error": None,
        }
        _jobs.move_to_end(job_id)
        _trim_jobs()
    except Exception as exc:  # noqa: BLE001
        _jobs[job_id] = {
            "status": "error",
            "kind": "playwright_install",
            "log": log,
            "result": None,
            "error": str(exc),
        }
        _jobs.move_to_end(job_id)
        _trim_jobs()
    finally:
        clear_progress(job_id)
        _async_tasks.pop(job_id, None)


def job_public_view(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    return _job_payload(job_id, job)


def list_active_jobs() -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for job_id, job in list(_jobs.items()):
        if job.get("status") != "running":
            continue
        entry = {
            "job_id": job_id,
            "kind": job.get("kind"),
            "status": "running",
            "query": job.get("query", ""),
            "started_at": job.get("started_at"),
        }
        progress = get_progress(job_id)
        if progress:
            entry["progress"] = {
                "phase": progress.get("phase"),
                "detail": progress.get("detail"),
                "percent": progress.get("percent"),
            }
        active.append(entry)
    return active


def list_active_searches() -> list[dict[str, Any]]:
    return [j for j in list_active_jobs() if j.get("kind") == "search"]
