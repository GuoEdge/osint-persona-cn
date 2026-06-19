"""运行记录查询 / Run record queries."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import osint_toolkit.auth.paths as auth_paths
from osint_toolkit.services.run_session import read_progress_disk, run_dir as _run_dir
from osint_toolkit.utils.safe_path import PathSecurityError, assert_run_id, assert_safe_filename, resolve_under

_NUMBERED_STEP = re.compile(r"^\d{2}_.+\.json$")
_SKIP_JSON = frozenset({"manifest.json", "request.json", "progress.json"})
_MAX_LIST_JSON_BYTES = 200_000
_STEP_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _safe_run_dir(run_id: str) -> Path:
    return _run_dir(assert_run_id(run_id))


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_sec(manifest: dict[str, Any]) -> int | None:
    started = _parse_iso(manifest.get("started_at"))
    finished = _parse_iso(manifest.get("finished_at"))
    if started and finished:
        return max(0, int((finished.astimezone(UTC) - started.astimezone(UTC)).total_seconds()))
    if started and manifest.get("status") == "running":
        return max(0, int((datetime.now(UTC) - started.astimezone(UTC)).total_seconds()))
    return None


def _progress_item_count(run_dir: Path) -> int:
    path = run_dir / "progress.json"
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("items_found") or 0)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0


def _quick_item_count(run_dir: Path, manifest: dict[str, Any]) -> int:
    if manifest.get("item_count") is not None:
        try:
            return max(0, int(manifest["item_count"]))
        except (TypeError, ValueError):
            pass
    n = _progress_item_count(run_dir)
    if n > 0:
        return n
    for pattern in ("*items_dedup.json", "*items_raw.json", "items_dedup.json"):
        for path in sorted(run_dir.glob(pattern)):
            try:
                if path.stat().st_size > _MAX_LIST_JSON_BYTES:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, list):
                return len(data)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return len(data["items"])
    return 0


def _quick_step_count(run_dir: Path, manifest: dict[str, Any]) -> int:
    if manifest.get("step_count") is not None:
        try:
            return max(0, int(manifest["step_count"]))
        except (TypeError, ValueError):
            pass
    n = len(manifest.get("steps") or [])
    if n:
        return n
    return len([p for p in run_dir.glob("[0-9][0-9]_*.json") if p.is_file()])


def _source_errors_count(run_dir: Path, manifest: dict[str, Any]) -> int:
    if manifest.get("source_error_count") is not None:
        try:
            return max(0, int(manifest["source_error_count"]))
        except (TypeError, ValueError):
            pass
    for path in sorted(run_dir.glob("*collect_all.json")):
        try:
            if path.stat().st_size > _MAX_LIST_JSON_BYTES:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            payload = data.get("data") if isinstance(data, dict) else None
            if isinstance(payload, dict):
                return len(payload.get("source_errors") or [])
        except (json.JSONDecodeError, OSError):
            continue
    return 0


def _source_warnings_count(run_dir: Path, manifest: dict[str, Any]) -> int:
    if manifest.get("source_warning_count") is not None:
        try:
            return max(0, int(manifest["source_warning_count"]))
        except (TypeError, ValueError):
            pass
    for path in sorted(run_dir.glob("*collect_all.json")):
        try:
            if path.stat().st_size > _MAX_LIST_JSON_BYTES:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            payload = data.get("data") if isinstance(data, dict) else None
            if isinstance(payload, dict):
                return len(payload.get("source_warnings") or [])
        except (json.JSONDecodeError, OSError):
            continue
    return 0


def summarize_run(run_id: str, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """运行记录列表/详情用的轻量摘要。"""
    safe_id = assert_run_id(run_id)
    run_path = _safe_run_dir(safe_id)
    if manifest is None:
        manifest_path = run_path / "manifest.json"
        if not manifest_path.exists():
            return {"run_id": safe_id}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {"run_id": safe_id}
    manifest = manifest or {}
    progress = read_progress_disk(safe_id)
    item_count = _quick_item_count(run_path, manifest) if run_path.exists() else 0
    summary: dict[str, Any] = {
        "run_id": safe_id,
        "command": manifest.get("command") or "search",
        "query": manifest.get("query") or "",
        "status": manifest.get("status") or ("done" if manifest.get("finished_at") else "unknown"),
        "profile": manifest.get("profile"),
        "sources": list(manifest.get("sources") or []),
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
        "duration_sec": _duration_sec(manifest),
        "item_count": item_count,
        "has_report": (run_path / "report.md").exists(),
        "step_count": _quick_step_count(run_path, manifest) if run_path.exists() else 0,
        "source_error_count": _source_errors_count(run_path, manifest) if run_path.exists() else 0,
        "source_warning_count": _source_warnings_count(run_path, manifest) if run_path.exists() else 0,
        "error": manifest.get("error"),
    }
    if progress:
        summary["phase"] = progress.get("phase")
        summary["phase_detail"] = progress.get("detail")
        if summary["status"] == "running":
            summary["item_count"] = max(summary["item_count"], int(progress.get("items_found") or 0))
    req_path = run_path / "request.json"
    if req_path.exists():
        try:
            req = json.loads(req_path.read_text(encoding="utf-8"))
            summary["request"] = req
            if not summary["sources"] and req.get("sources"):
                summary["sources"] = list(req["sources"])
            if req.get("source_overrides"):
                summary["source_overrides"] = req["source_overrides"]
        except json.JSONDecodeError:
            pass
    if manifest.get("collect_sources"):
        summary["collect_sources"] = list(manifest["collect_sources"])
    return summary


def list_runs(limit: int = 20) -> list[dict]:
    runs_dir = auth_paths.get_data_dir() / "runs"
    if not runs_dir.exists():
        return []
    manifests = sorted(runs_dir.glob("*/manifest.json"), reverse=True)[:limit]
    results = []
    for m in manifests:
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        run_id = str(data.get("run_id") or m.parent.name)
        summary = summarize_run(run_id, data)
        summary["path"] = str(m.parent.name)
        results.append(summary)
    return results


def show_run(run_id: str, step: str | None = None) -> dict | str:
    run_path = _safe_run_dir(run_id)
    if not run_path.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    if step:
        if not _STEP_NAME_RE.fullmatch(step):
            raise FileNotFoundError(f"step not found: {step}")
        matches = list(run_path.glob(f"*_{step}.json"))
        if not matches:
            raise FileNotFoundError(f"step not found: {step}")
        return json.loads(matches[0].read_text(encoding="utf-8"))
    manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
    trace = (run_path / "trace.log").read_text(encoding="utf-8") if (run_path / "trace.log").exists() else ""
    manifest["trace"] = trace
    manifest["steps"] = list_run_steps(run_id)
    manifest["artifacts"] = list_run_artifacts(run_id)
    progress = read_progress_disk(run_id)
    if progress:
        manifest["progress"] = progress
    req_path = run_path / "request.json"
    if req_path.exists():
        try:
            manifest["request"] = json.loads(req_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    from osint_toolkit.services.run_artifacts import load_query_analysis_from_run

    query_analysis = load_query_analysis_from_run(run_path)
    if query_analysis.get("queries_used"):
        manifest["queries_used"] = query_analysis["queries_used"]
    manifest["query_analysis"] = query_analysis
    if query_analysis.get("active_sources"):
        manifest["collect_sources"] = query_analysis["active_sources"]
    if query_analysis.get("source_plan"):
        manifest["source_plan"] = query_analysis["source_plan"]
    if query_analysis.get("source_routing"):
        manifest["source_routing"] = query_analysis["source_routing"]
    report = run_path / "report.md"
    if report.exists():
        manifest["report"] = report.read_text(encoding="utf-8")
    errs, warns = _load_run_collect_issues(run_path)
    if errs:
        manifest["source_errors"] = errs
    if warns:
        manifest["source_warnings"] = warns
    manifest["summary"] = summarize_run(run_id, manifest)
    return manifest


def _load_run_collect_issues(run_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """从 collect 步骤快照读取 source_errors / source_warnings。"""
    for path in sorted(run_dir.glob("*.json"), reverse=True):
        if path.name in _SKIP_JSON:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        data = payload.get("data")
        if not isinstance(data, dict):
            continue
        errs = data.get("source_errors")
        warns = data.get("source_warnings")
        if errs or warns:
            return list(errs or []), list(warns or [])
    return [], []


def list_run_steps(run_id: str) -> list[dict]:
    """合并编号步骤文件、manifest.steps 与 progress.completed_steps。"""
    run_path = _safe_run_dir(run_id)
    if not run_path.exists():
        return []

    by_step: dict[str, dict] = {}
    order: list[str] = []

    def _merge_step(data: dict, *, source: str = "") -> None:
        if not isinstance(data, dict):
            return
        name = str(data.get("step") or "").strip()
        if not name:
            return
        payload = dict(data)
        if source:
            payload["_source"] = source
        existing = by_step.get(name)
        if existing is None:
            by_step[name] = payload
            order.append(name)
            return
        # 已完成步骤优先于 running；编号文件优先于 progress 快照
        rank = {"running": 0, "error": 1, "ok": 2, "done": 2}
        old_rank = rank.get(str(existing.get("status") or ""), 1)
        new_rank = rank.get(str(payload.get("status") or ""), 1)
        src_rank = {"file": 3, "manifest": 2, "progress": 1}
        if new_rank > old_rank or src_rank.get(source, 0) > src_rank.get(str(existing.get("_source") or ""), 0):
            by_step[name] = payload
            if name not in order:
                order.append(name)

    for path in sorted(run_path.glob("*.json")):
        if path.name in _SKIP_JSON:
            continue
        if not _NUMBERED_STEP.match(path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or not data.get("step"):
            continue
        data = dict(data)
        data["_file"] = path.name
        _merge_step(data, source="file")

    manifest_path = run_path / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest.get("steps") or []:
                if isinstance(entry, dict):
                    _merge_step(entry, source="manifest")
        except json.JSONDecodeError:
            pass

    progress = read_progress_disk(run_id)
    if progress:
        for entry in progress.get("completed_steps") or []:
            if not isinstance(entry, dict):
                continue
            _merge_step(
                {
                    "step": entry.get("step"),
                    "status": entry.get("status") or "ok",
                    "duration_ms": entry.get("duration_ms"),
                    "output_summary": entry.get("summary") or "",
                    "issues": entry.get("issues") or [],
                },
                source="progress",
            )
        phase = progress.get("phase")
        if phase and phase not in by_step:
            by_step[phase] = {
                "step": phase,
                "status": "running",
                "output_summary": progress.get("detail") or "",
                "duration_ms": None,
                "_source": "progress",
            }
            order.append(phase)

    return [by_step[name] for name in order if name in by_step]


def list_run_artifacts(run_id: str) -> list[str]:
    run_path = _safe_run_dir(run_id)
    if not run_path.exists():
        return []
    return sorted(p.name for p in run_path.iterdir() if p.is_file())


def get_run_artifact(run_id: str, name: str) -> tuple[str, str]:
    run_path = _safe_run_dir(run_id)
    safe_name = assert_safe_filename(name)
    path = resolve_under(run_path, safe_name)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"artifact not found: {name}")
    suffix = path.suffix.lower()
    if suffix in {".json", ".log", ".md", ".txt"}:
        return path.read_text(encoding="utf-8"), "text/plain"
    return path.read_bytes().decode("utf-8", errors="replace"), "application/octet-stream"


def _report_filename(run_id: str, query: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", query).strip("-")[:36] or "report"
    return f"{run_id}-{slug}.md"


def get_run_report_export(run_id: str) -> tuple[str, str]:
    """返回 (markdown 正文, 下载文件名)。"""
    run_path = _safe_run_dir(run_id)
    report_path = run_path / "report.md"
    if not report_path.exists():
        raise FileNotFoundError(f"run {run_id} has no report")
    query = ""
    manifest_path = run_path / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            query = str(manifest.get("query") or "")
        except json.JSONDecodeError:
            pass
    return report_path.read_text(encoding="utf-8"), _report_filename(run_id, query)


def _load_run_item_urls(run_id: str) -> set[str]:
    run_path = _safe_run_dir(run_id)
    if not run_path.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    for path in sorted(run_path.glob("*items_dedup.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items_raw = raw if isinstance(raw, list) else raw.get("items") or []
        urls = {str(it.get("url") or "") for it in items_raw if isinstance(it, dict) and it.get("url")}
        if urls:
            return urls
    return set()


def diff_run_urls(run_id: str, since_run_id: str) -> dict[str, Any]:
    """对比两轮搜罗结果 URL 差异。"""
    current = _load_run_item_urls(run_id)
    since = _load_run_item_urls(since_run_id)
    new_urls = sorted(current - since)
    removed_urls = sorted(since - current)
    return {
        "run_id": run_id,
        "since_run_id": since_run_id,
        "new_urls": new_urls,
        "removed_urls": removed_urls,
        "new_count": len(new_urls),
        "removed_count": len(removed_urls),
        "current_count": len(current),
        "since_count": len(since),
    }


def delete_run(run_id: str) -> None:
    run_path = _safe_run_dir(run_id)
    if not run_path.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    from osint_toolkit.research.tree import mark_broken_run_for_trees

    mark_broken_run_for_trees(run_id)
    shutil.rmtree(run_path)


def _iter_run_entries() -> list[tuple[str, dict[str, Any], Path]]:
    runs_dir = auth_paths.get_data_dir() / "runs"
    if not runs_dir.exists():
        return []
    entries: list[tuple[str, dict[str, Any], Path]] = []
    for manifest_path in runs_dir.glob("*/manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            continue
        run_id = str(data.get("run_id") or manifest_path.parent.name)
        entries.append((run_id, data, manifest_path.parent))
    entries.sort(key=lambda row: str(row[1].get("started_at") or ""), reverse=True)
    return entries


def cleanup_runs(
    *,
    older_than_days: int | None = 30,
    keep_latest: int = 20,
    statuses: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """删除旧运行目录；默认保留最近 keep_latest 条，且跳过 running。"""
    allowed = set(statuses or ["done", "error", "interrupted", "cancelled", "unknown"])
    entries = _iter_run_entries()
    protected = {run_id for run_id, _, _ in entries[: max(0, keep_latest)]}
    cutoff: datetime | None = None
    if older_than_days is not None and older_than_days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

    deleted: list[str] = []
    skipped: list[dict[str, str]] = []
    for run_id, data, path in entries:
        status = str(data.get("status") or "unknown")
        if run_id in protected:
            skipped.append({"run_id": run_id, "reason": "keep_latest"})
            continue
        if status == "running":
            skipped.append({"run_id": run_id, "reason": "running"})
            continue
        if status not in allowed:
            skipped.append({"run_id": run_id, "reason": f"status:{status}"})
            continue
        if cutoff is not None:
            ts = _parse_iso(data.get("finished_at") or data.get("started_at"))
            if ts is None or ts > cutoff:
                skipped.append({"run_id": run_id, "reason": "too_recent"})
                continue
        if dry_run:
            deleted.append(run_id)
            continue
        shutil.rmtree(path, ignore_errors=False)
        deleted.append(run_id)
    return {"deleted": deleted, "skipped": skipped, "count": len(deleted), "dry_run": dry_run}
