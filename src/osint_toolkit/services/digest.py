"""简报服务 / Digest service."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.exporters.digest import generate_daily_digest


def get_daily_digest(*, use_ai: bool = False, no_ai: bool = False) -> str:
    return generate_daily_digest(use_ai=use_ai, no_ai=no_ai)


def list_daily_digests(limit: int = 30) -> list[dict[str, Any]]:
    digests_dir = get_data_dir() / "digests"
    if not digests_dir.exists():
        return []
    files = sorted(digests_dir.glob("*.md"), reverse=True)[:limit]
    results: list[dict[str, Any]] = []
    for path in files:
        results.append(
            {
                "date": path.stem,
                "path": str(path),
                "preview": path.read_text(encoding="utf-8")[:200],
            }
        )
    return results


def list_reports(limit: int = 50) -> list[dict[str, Any]]:
    runs_dir = get_data_dir() / "runs"
    if not runs_dir.exists():
        return []
    reports: list[dict[str, Any]] = []
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        report_file = run_dir / "report.md"
        if not report_file.exists():
            continue
        manifest_file = run_dir / "manifest.json"
        manifest: dict[str, Any] = {}
        if manifest_file.exists():
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        reports.append(
            {
                "run_id": run_dir.name,
                "query": manifest.get("query", ""),
                "command": manifest.get("command", ""),
                "report_path": str(report_file),
                "preview": report_file.read_text(encoding="utf-8")[:300],
            }
        )
        if len(reports) >= limit:
            break
    return reports
