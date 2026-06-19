"""引用编号 / Citation ID assignment for report cross-references."""

from __future__ import annotations

from osint_toolkit.models.intel_item import IntelItem


def citation_id_for_item(item: IntelItem) -> str | None:
    cid = item.personal.get("citation_id")
    return str(cid) if cid else None


def assign_citation_ids(items: list[IntelItem]) -> dict[str, str]:
    """为条目分配 c1、c2… 引用编号，返回 citation_id -> item_id 映射。"""
    citation_map: dict[str, str] = {}
    for idx, item in enumerate(items, start=1):
        cid = f"c{idx}"
        item.personal["citation_id"] = cid
        citation_map[cid] = item.id
    return citation_map
