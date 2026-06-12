"""反馈持久化 / Feedback persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from osint_toolkit.auth.paths import get_data_dir


class FeedbackStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (get_data_dir() / "feedback.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        *,
        target_type: str,
        target_id: str,
        rating: str,
        reason: str = "",
        run_id: str | None = None,
        step: str | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "target_type": target_type,
            "target_id": target_id,
            "rating": rating,
            "reason": reason,
            "run_id": run_id,
            "step": step,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        entries = [json.loads(line) for line in lines if line.strip()]
        return entries[-limit:]

    def map_latest_by_target(
        self,
        target_ids: list[str] | None = None,
        *,
        limit: int = 2000,
    ) -> dict[str, str]:
        """Return latest rating per ``target_type:target_id`` key."""
        allowed = set(target_ids) if target_ids is not None else None
        out: dict[str, str] = {}
        for entry in self.list_recent(limit):
            tid = str(entry.get("target_id", ""))
            if not tid:
                continue
            if allowed is not None and tid not in allowed:
                continue
            ttype = str(entry.get("target_type") or "item")
            out[f"{ttype}:{tid}"] = str(entry.get("rating") or "")
        return out
