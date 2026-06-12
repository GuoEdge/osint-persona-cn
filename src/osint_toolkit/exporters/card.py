"""情报卡片导出 / Intelligence card export."""

from __future__ import annotations

from pathlib import Path

from osint_toolkit.models.intel_item import IntelItem


def export_card(item: IntelItem, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {item.title}",
        "",
        f"- 来源: {item.source}",
        f"- URL: {item.url}",
        "",
        "## 核心摘要",
        item.summary or item.content[:500],
        "",
    ]
    comments = item.layers.get("comments") or item.layers.get("comments_summary")
    if comments:
        lines.extend(["## 社区补充", str(comments), ""])
    path = output_dir / f"{item.id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
