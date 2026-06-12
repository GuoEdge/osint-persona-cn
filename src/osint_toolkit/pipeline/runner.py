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
        manifest = {
            "run_id": self.ctx.run_id,
            "command": self.ctx.command,
            "query": self.ctx.query,
            "profile": self.ctx.profile,
            "sources": self.ctx.sources,
            "started_at": self.ctx.started_at,
            "steps": [],
        }
        (self.run_dir / "manifest.json").write_text(
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

    def run_step(
        self,
        name: str,
        func: Callable[[], Any],
        *,
        input_summary: str = "",
        artifact_name: str | None = None,
        ai_invoked: bool = False,
    ) -> StepResult:
        start = time.perf_counter()
        issues: list[str] = []
        status = "ok"
        data: Any = None
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
        step_file = self.run_dir / f"{len(self.steps) + 1:02d}_{name}.json"
        step_file.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._append_trace(result)
        return result

    def _write_artifact(self, name: str, data: Any) -> Path:
        path = self.run_dir / name
        if isinstance(data, (dict, list)):
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        else:
            path.write_text(str(data), encoding="utf-8")
        return path
