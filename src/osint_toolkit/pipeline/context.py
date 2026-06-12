"""运行上下文 / Run context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from osint_toolkit.auth.paths import get_data_dir


@dataclass
class RunContext:
    command: str
    query: str = ""
    profile: str = "default"
    sources: list[str] = field(default_factory=list)
    trace: bool = False
    ai_instruct: str = ""
    no_ai: bool = False
    no_simulate: bool = False
    disabled_ai_steps: list[str] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + f"-{uuid4().hex[:8]}")
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    run_dir: Path | None = None

    def ensure_run_dir(self) -> Path:
        if self.run_dir is None:
            self.run_dir = get_data_dir() / "runs" / self.run_id
            self.run_dir.mkdir(parents=True, exist_ok=True)
        return self.run_dir
