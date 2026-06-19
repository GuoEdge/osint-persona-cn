"""Pipeline 步骤编排 / Pipeline step runner."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osint_toolkit.pipeline.context import RunContext
from osint_toolkit.pipeline.trace import trace_step


@dataclass
class StepResult:
    step: str
    status: str = "ok"
    duration_ms: int = 0
    input_summary: str = ""
    output_summary: str = ""
    issues: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    ai_invoked: bool = False
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "issues": self.issues,
            "artifacts": self.artifacts,
            "ai_invoked": self.ai_invoked,
        }


class PipelineRunner:
    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.steps: list[StepResult] = []
        self.run_dir = ctx.ensure_run_dir()
        self._write_manifest()

    def _write_manifest(self) -> None:
        manifest_path = self.run_dir / "manifest.json"
        existing: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        manifest = {
            "run_id": self.ctx.run_id,
            "command": self.ctx.command,
            "query": self.ctx.query,
            "profile": self.ctx.profile,
            "sources": self.ctx.sources,
            "started_at": existing.get("started_at") or self.ctx.started_at,
            "status": existing.get("status") or "running",
            "steps": existing.get("steps") or [],
        }
        if existing.get("request"):
            manifest["request"] = existing["request"]
        if existing.get("finished_at"):
            manifest["finished_at"] = existing["finished_at"]
        if existing.get("error"):
            manifest["error"] = existing["error"]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _append_trace(self, result: StepResult) -> None:
        self.steps.append(result)
        line = (
            f"[{result.step}] {result.status} ({result.duration_ms}ms) "
            f"{result.output_summary}"
        )
        if result.issues:
            line += " | issues: " + "; ".join(result.issues)
        with (self.run_dir / "trace.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        trace_step(
            result.step,
            result.output_summary or result.input_summary,
            enabled=self.ctx.trace,
            status="error" if result.status == "error" else "ok",
        )
        manifest_path = self.run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["steps"] = [s.to_dict() for s in self.steps]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _step_index(self) -> int:
        return len(self.steps) + 1

    def _step_path(self, name: str) -> Path:
        return self.run_dir / f"{self._step_index():02d}_{name}.json"

    def _write_step_file(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def begin_step(self, name: str, *, input_summary: str = "", ai_invoked: bool = False) -> Path:
        """长耗时步骤开始前落盘 running 状态，便于运行详情页审查。"""
        path = self._step_path(name)
        self._write_step_file(
            path,
            {
                "step": name,
                "status": "running",
                "duration_ms": 0,
                "input_summary": input_summary,
                "output_summary": "",
                "issues": [],
                "artifacts": [],
                "ai_invoked": ai_invoked,
            },
        )
        manifest_path = self.run_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
            steps = list(manifest.get("steps") or [])
            steps = [s for s in steps if not (isinstance(s, dict) and s.get("step") == name)]
            steps.append(
                {
                    "step": name,
                    "status": "running",
                    "duration_ms": 0,
                    "input_summary": input_summary,
                    "output_summary": "",
                    "issues": [],
                    "artifacts": [],
                    "ai_invoked": ai_invoked,
                }
            )
            manifest["steps"] = steps
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def run_step(
        self,
        name: str,
        func: Callable[[], Any],
        *,
        input_summary: str = "",
        artifact_name: str | None = None,
        ai_invoked: bool = False,
        step_path: Path | None = None,
    ) -> StepResult:
        start = time.perf_counter()
        issues: list[str] = []
        status = "ok"
        data: Any = None
        path = step_path or self._step_path(name)
        if not path.exists():
            self._write_step_file(
                path,
                {
                    "step": name,
                    "status": "running",
                    "duration_ms": 0,
                    "input_summary": input_summary,
                    "output_summary": "",
                    "issues": [],
                    "artifacts": [],
                    "ai_invoked": ai_invoked,
                },
            )
        try:
            data = func()
        except Exception as exc:  # noqa: BLE001
            status = "error"
            issues.append(str(exc))
        duration_ms = int((time.perf_counter() - start) * 1000)
        artifacts: list[str] = []
        if artifact_name and data is not None:
            path = self._write_artifact(artifact_name, data)
            artifacts.append(path.name)
        output_summary = ""
        if isinstance(data, list):
            output_summary = f"{len(data)} items"
        elif isinstance(data, dict) and "count" in data:
            output_summary = f"{data['count']} items"
        elif data is not None:
            output_summary = "completed"
        result = StepResult(
            step=name,
            status=status,
            duration_ms=duration_ms,
            input_summary=input_summary,
            output_summary=output_summary,
            issues=issues,
            artifacts=artifacts,
            ai_invoked=ai_invoked,
            data=data,
        )
        self._write_step_file(path, result.to_dict())
        self._append_trace(result)
        return result

    def _write_artifact(self, name: str, data: Any) -> Path:
        path = self.run_dir / name
        if isinstance(data, (dict, list)):
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        else:
            path.write_text(str(data), encoding="utf-8")
        return path
