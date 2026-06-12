"""报告导出 / Report export."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from osint_toolkit.utils.config import load_config


def export_report(content: str, *, query: str, run_id: str) -> Path:
    cfg = load_config().get("output", {})
    reports_dir = Path(cfg.get("reports_dir", "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", query).strip("-")[:40] or "report"
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    path = reports_dir / f"{date}-{slug}.md"
    path.write_text(content, encoding="utf-8")
    return path
