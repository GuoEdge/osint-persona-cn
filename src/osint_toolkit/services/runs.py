"""运行记录查询 / Run record queries."""

from __future__ import annotations

import json

from osint_toolkit.auth.paths import get_data_dir


def list_runs(limit: int = 20) -> list[dict]:
    runs_dir = get_data_dir() / "runs"
    if not runs_dir.exists():
        return []
    manifests = sorted(runs_dir.glob("*/manifest.json"), reverse=True)[:limit]
    results = []
    for m in manifests:
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        data["path"] = str(m.parent)
        if not data.get("status"):
            data["status"] = "done" if data.get("finished_at") else "unknown"
        results.append(data)
    return results


def show_run(run_id: str, step: str | None = None) -> dict | str:
    run_dir = get_data_dir() / "runs" / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    if step:
        matches = list(run_dir.glob(f"*_{step}.json"))
        if not matches:
            raise FileNotFoundError(f"step not found: {step}")
        return json.loads(matches[0].read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    trace = (run_dir / "trace.log").read_text(encoding="utf-8") if (run_dir / "trace.log").exists() else ""
    manifest["trace"] = trace
    manifest["steps"] = list_run_steps(run_id)
    manifest["artifacts"] = list_run_artifacts(run_id)
    report = run_dir / "report.md"
    if report.exists():
        manifest["report"] = report.read_text(encoding="utf-8")
    return manifest


def list_run_steps(run_id: str) -> list[dict]:
    run_dir = get_data_dir() / "runs" / run_id
    if not run_dir.exists():
        return []
    steps = []
    for path in sorted(run_dir.glob("*_*.json")):
        if path.name == "manifest.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            data["_file"] = path.name
            steps.append(data)
        except json.JSONDecodeError:
            continue
    return steps


def list_run_artifacts(run_id: str) -> list[str]:
    run_dir = get_data_dir() / "runs" / run_id
    if not run_dir.exists():
        return []
    return sorted(p.name for p in run_dir.iterdir() if p.is_file())


def get_run_artifact(run_id: str, name: str) -> tuple[str, str]:
    run_dir = get_data_dir() / "runs" / run_id
    path = run_dir / name
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"artifact not found: {name}")
    suffix = path.suffix.lower()
    if suffix in {".json", ".log", ".md", ".txt"}:
        return path.read_text(encoding="utf-8"), "text/plain"
    return path.read_bytes().decode("utf-8", errors="replace"), "application/octet-stream"
