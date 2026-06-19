"""后台搜索/同步任务 / Background jobs."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict, deque
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.pipeline.job_progress import init_full_sync_progress, make_full_sync_callbacks
from osint_toolkit.pipeline.progress import (
    JobCancelled,
    clear_progress,
    finish_progress,
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
_TERMINAL_JOB_STATUSES = frozenset({"done", "error", "cancelled"})
_jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
_async_tasks: dict[str, asyncio.Task[Any]] = {}
_search_queue: deque[tuple[str, dict[str, Any]]] = deque()


class SearchQueueFullError(Exception):
    """排队搜罗任务已达上限。"""


def _max_queued_searches() -> int:
    from osint_toolkit.utils.config import get_search_config

    return max(1, int(get_search_config().get("max_queued_searches", 20)))


def _max_concurrent_searches() -> int:
    from osint_toolkit.utils.config import get_search_config

    return max(1, int(get_search_config().get("max_concurrent_searches", 2)))


def _count_running_searches() -> int:
    return sum(
        1 for job in _jobs.values() if job.get("kind") == "search" and job.get("status") == "running"
    )


def _queue_position(run_id: str) -> int | None:
    for index, (queued_id, _) in enumerate(_search_queue):
        if queued_id == run_id:
            return index + 1
    return None


def _refresh_queue_positions() -> None:
    for index, (run_id, _) in enumerate(_search_queue):
        job = _jobs.get(run_id)
        if job and job.get("status") == "queued":
            job["queue_position"] = index + 1


def _remove_from_search_queue(run_id: str) -> None:
    global _search_queue
    if not _search_queue:
        return
    _search_queue = deque((item for item in _search_queue if item[0] != run_id))
    _refresh_queue_positions()


def _launch_search(run_id: str, **kwargs: Any) -> None:
    job = _jobs.get(run_id)
    if not job or job.get("status") != "queued":
        return
    job["status"] = "running"
    job["started_at"] = datetime.now(UTC).isoformat()
    job.pop("queue_position", None)
    set_run_status(run_id, "running")
    init_progress(run_id)
    task = asyncio.create_task(_execute_search(run_id, **kwargs))
    _async_tasks[run_id] = task


def _drain_search_queue() -> None:
    while _search_queue and _count_running_searches() < _max_concurrent_searches():
        run_id, kwargs = _search_queue.popleft()
        job = _jobs.get(run_id)
        if not job or job.get("status") != "queued":
            continue
        _launch_search(run_id, **kwargs)
    _refresh_queue_positions()


def drain_search_queue() -> None:
    """启动排队中的搜罗任务（例如调高并发上限后）。"""
    _drain_search_queue()


def _search_run_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return strip_session_keys(kwargs)


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + f"-{uuid4().hex[:8]}"


def _trim_jobs() -> None:
    while len(_jobs) > _MAX_JOBS:
        victim_id: str | None = None
        for job_id, job in _jobs.items():
            if job.get("status") in _TERMINAL_JOB_STATUSES:
                victim_id = job_id
                break
        if victim_id is None:
            break
        job = _jobs.pop(victim_id)
        if job.get("kind") == "search" and job.get("status") == "queued":
            _remove_from_search_queue(victim_id)
            set_run_status(victim_id, "interrupted", error="任务记录已回收")


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
    from osint_toolkit.services.run_session import read_manifest

    job = _jobs.get(job_id)
    if not job:
        in_queue = any(rid == job_id for rid, _ in _search_queue)
        manifest = read_manifest(job_id) if not in_queue else None
        if in_queue or (manifest and manifest.get("status") == "queued"):
            _remove_from_search_queue(job_id)
            set_run_status(job_id, "cancelled", error="已取消")
            return True
        return False
    if job.get("status") == "queued" and job.get("kind") == "search":
        _remove_from_search_queue(job_id)
        query = job.get("query", "")
        _jobs[job_id] = {
            "status": "cancelled",
            "kind": "search",
            "result": None,
            "error": "已取消",
            "query": query,
        }
        _jobs.move_to_end(job_id)
        set_run_status(job_id, "cancelled", error="已取消")
        _trim_jobs()
        return True
    if job.get("status") != "running":
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
    source_warnings: list[dict] = []
    for path in sorted(run_dir.glob("*_collect_all.json")):
        try:
            step = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(step.get("data"), dict):
                source_errors = step["data"].get("source_errors") or []
                source_warnings = step["data"].get("source_warnings") or []
            break
        except json.JSONDecodeError:
            continue
    query_analysis: dict[str, Any] = {}
    from osint_toolkit.services.run_artifacts import load_query_analysis_from_run

    query_analysis = load_query_analysis_from_run(run_dir)
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
    citation_map: dict[str, str] = {}
    for item in items:
        cid = item.personal.get("citation_id")
        if cid:
            citation_map[str(cid)] = item.id
    intel_stats = {
        "new_count": sum(1 for i in items if not i.personal.get("already_seen")),
        "seen_count": sum(1 for i in items if i.personal.get("already_seen")),
        "total": len(items),
    }
    return {
        "run_id": run_id,
        "items": items,
        "report": report,
        "report_path": str(report_path) if report_path.exists() else None,
        "simulations": simulations,
        "run_dir": str(run_dir),
        "manifest": manifest,
        "source_errors": source_errors,
        "source_warnings": source_warnings,
        "citation_map": citation_map,
        "intel_stats": intel_stats,
        "query_analysis": query_analysis if isinstance(query_analysis, dict) else {},
        "discover_meta": discover_meta,
        "queries_used": queries_used or [],
    }


def start_search_job(**kwargs: Any) -> dict[str, Any]:
    run_id = new_run_id()
    request_snapshot = {k: v for k, v in kwargs.items() if v is not None}
    query = str(kwargs.get("query") or "")
    created_at = datetime.now(UTC).isoformat()
    can_run_now = _count_running_searches() < _max_concurrent_searches()

    if can_run_now:
        set_run_status(run_id, "running", request=request_snapshot)
        _jobs[run_id] = {
            "status": "running",
            "kind": "search",
            "result": None,
            "error": None,
            "query": query,
            "created_at": created_at,
            "started_at": created_at,
        }
        init_progress(run_id)
        _trim_jobs()
        task = asyncio.create_task(_execute_search(run_id, **kwargs))
        _async_tasks[run_id] = task
        return {"run_id": run_id, "status": "running"}

    set_run_status(run_id, "queued", request=request_snapshot)
    if len(_search_queue) >= _max_queued_searches():
        raise SearchQueueFullError(f"排队任务已达上限（{_max_queued_searches()}），请稍后再试或取消旧任务")
    _jobs[run_id] = {
        "status": "queued",
        "kind": "search",
        "result": None,
        "error": None,
        "query": query,
        "created_at": created_at,
    }
    _search_queue.append((run_id, dict(kwargs)))
    _trim_jobs()
    _refresh_queue_positions()
    queue_position = _queue_position(run_id)
    return {"run_id": run_id, "status": "queued", "queue_position": queue_position}


async def _execute_search(run_id: str, **kwargs: Any) -> None:
    from osint_toolkit.services import search as search_service
    from osint_toolkit.services.run_session import patch_manifest

    final_status = "error"
    error_msg: str | None = None
    result: dict[str, Any] | None = None
    try:
        result = await search_service.run_search(**_search_run_kwargs(kwargs), run_id=run_id)
        prior = _jobs.get(run_id) or {}
        query = prior.get("query", "")
        created_at = prior.get("created_at")
        started_at = prior.get("started_at")
        if is_cancelled(run_id):
            final_status = "cancelled"
            error_msg = "已取消"
            _jobs[run_id] = {
                "status": "cancelled",
                "kind": "search",
                "result": None,
                "error": error_msg,
                "query": query,
                "created_at": created_at,
                "started_at": started_at,
            }
        else:
            final_status = "done"
            item_count = len(result.get("items") or []) if isinstance(result, dict) else 0
            _jobs[run_id] = {
                "status": "done",
                "kind": "search",
                "result": None,
                "error": None,
                "query": query,
                "created_at": created_at,
                "started_at": started_at,
                "item_count": item_count,
            }
        _jobs.move_to_end(run_id)
        _trim_jobs()
    except (JobCancelled, asyncio.CancelledError):
        final_status = "cancelled"
        error_msg = "已取消"
        prior = _jobs.get(run_id) or {}
        _jobs[run_id] = {
            "status": "cancelled",
            "kind": "search",
            "result": None,
            "error": error_msg,
            "query": prior.get("query", ""),
            "created_at": prior.get("created_at"),
            "started_at": prior.get("started_at"),
        }
        _jobs.move_to_end(run_id)
        _trim_jobs()
    except Exception as exc:  # noqa: BLE001
        final_status = "error"
        error_msg = str(exc)
        prior = _jobs.get(run_id) or {}
        _jobs[run_id] = {
            "status": "error",
            "kind": "search",
            "result": None,
            "error": error_msg,
            "query": prior.get("query", ""),
            "created_at": prior.get("created_at"),
            "started_at": prior.get("started_at"),
        }
        _jobs.move_to_end(run_id)
        _trim_jobs()
    finally:
        from osint_toolkit.services.run_session import read_request

        if isinstance(result, dict):
            patch_manifest(
                run_id,
                item_count=len(result.get("items") or []),
                source_error_count=len(result.get("source_errors") or []),
            )
        req = read_request(run_id) or {}
        tree_id = req.get("tree_id")
        if tree_id:
            update_search_node_status(tree_id, run_id, status=final_status)
        set_run_status(run_id, final_status, error=error_msg)
        finish_progress(run_id)
        _async_tasks.pop(run_id, None)
        _drain_search_queue()


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
                "result": None,
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
    return [j for j in list_search_tasks(limit=50) if j.get("status") in ("running", "queued")]


def _search_task_entry(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    status = job.get("status")
    entry: dict[str, Any] = {
        "job_id": job_id,
        "run_id": job_id,
        "kind": "search",
        "status": status,
        "query": job.get("query", ""),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "item_count": job.get("item_count"),
        "error": job.get("error"),
    }
    if status == "queued":
        entry["queue_position"] = _queue_position(job_id) or job.get("queue_position")
    if status == "running":
        progress = get_progress(job_id)
        if progress:
            entry["progress"] = {
                "phase": progress.get("phase"),
                "detail": progress.get("detail"),
                "percent": progress.get("percent"),
            }
    return entry


def list_search_tasks(limit: int = 30) -> list[dict[str, Any]]:
    """搜罗任务列表：进行中、排队中、近期已完成/失败/取消。"""
    entries: list[dict[str, Any]] = []
    for job_id, job in _jobs.items():
        if job.get("kind") != "search":
            continue
        entries.append(_search_task_entry(job_id, job))

    def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        status = item.get("status")
        if status == "running":
            return (0, 0, item.get("started_at") or "")
        if status == "queued":
            pos = int(item.get("queue_position") or 9999)
            return (1, pos, item.get("created_at") or "")
        return (2, 0, item.get("started_at") or item.get("created_at") or "")

    entries.sort(key=sort_key)
    active = [e for e in entries if e.get("status") in ("running", "queued")]
    terminal = [e for e in entries if e.get("status") not in ("running", "queued")]
    terminal.reverse()
    ordered = active + terminal
    return ordered[: max(1, limit)]
