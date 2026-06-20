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


def build_citation_urls(items: list[IntelItem]) -> dict[str, str]:
    """citation_id -> 可打开的原文 URL（供前端引用跳转）。"""
    from osint_toolkit.utils.zhihu_urls import public_zhihu_url

    out: dict[str, str] = {}
    for item in items:
        cid = item.personal.get("citation_id")
        if not cid:
            continue
        url = str(item.url or "").strip()
        if item.source == "zhihu" and url:
            url = public_zhihu_url(url) or url
        if url.startswith("http://") or url.startswith("https://"):
            out[str(cid)] = url
    return out
