"""Pipeline 追踪输出 / Trace logging."""

from __future__ import annotations

from rich.console import Console

console = Console()


def trace_step(step: str, message: str, *, enabled: bool, status: str = "info") -> None:
    if not enabled:
        return
    color = {"ok": "green", "warn": "yellow", "error": "red"}.get(status, "cyan")
    console.print(f"[{color}][{step}][/{color}] {message}")
