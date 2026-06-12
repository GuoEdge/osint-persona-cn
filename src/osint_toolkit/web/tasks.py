"""后台搜索任务 / Background search tasks."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import search as search_service

_MAX_JOBS = 50
_jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()


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
    return {
        "run_id": run_id,
        "items": items,
        "report": report,
        "report_path": str(report_path) if report_path.exists() else None,
        "simulations": simulations,
        "run_dir": str(run_dir),
        "manifest": manifest,
        "source_errors": source_errors,
    }


def start_search_job(**kwargs: Any) -> str:
    run_id = new_run_id()
    _jobs[run_id] = {"status": "running", "result": None, "error": None}
    _trim_jobs()
    asyncio.create_task(_execute_search(run_id, **kwargs))
    return run_id


async def _execute_search(run_id: str, **kwargs: Any) -> None:
    try:
        result = await search_service.run_search(**kwargs, run_id=run_id)
        _jobs[run_id] = {"status": "done", "result": result, "error": None}
        _jobs.move_to_end(run_id)
        _trim_jobs()
    except Exception as exc:  # noqa: BLE001
        _jobs[run_id] = {"status": "error", "result": None, "error": str(exc)}
        _jobs.move_to_end(run_id)
        _trim_jobs()


def get_job_result(run_id: str) -> dict[str, Any] | None:
    job = get_job(run_id)
    if job and job.get("result"):
        return job["result"]
    return _load_result_from_disk(run_id)


def start_browser_sync_job(**kwargs: Any) -> str:
    job_id = new_run_id()
    _jobs[job_id] = {"status": "running", "kind": "browser_sync", "result": None, "error": None}
    _trim_jobs()
    asyncio.create_task(_execute_browser_sync(job_id, **kwargs))
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


def start_full_sync_job() -> str:
    job_id = new_run_id()
    _jobs[job_id] = {
        "status": "running",
        "kind": "full_sync",
        "steps": [],
        "result": None,
        "error": None,
    }
    _trim_jobs()
    asyncio.create_task(_execute_full_sync(job_id))
    return job_id


async def _execute_full_sync(job_id: str) -> None:
    from osint_toolkit.services import unified_sync

    def on_step(step: dict[str, Any]) -> None:
        job = _jobs.get(job_id)
        if job:
            job["steps"] = list(job.get("steps") or []) + [step]

    try:
        result = await unified_sync.run_full_sync(on_step=on_step)
        _jobs[job_id] = {
            "status": "done",
            "kind": "full_sync",
            "steps": result.get("steps") or _jobs.get(job_id, {}).get("steps") or [],
            "result": result,
            "error": None,
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
