"""去重 / Deduplication."""

from __future__ import annotations

import re

from osint_toolkit.models.intel_item import IntelItem

_TITLE_STRIP_RE = re.compile(r"[\s【】\[\]《》「」\-_|·:：,.，。!！?？（）()\"'“”]+")


def _url_key(url: str) -> str:
    return url.split("?")[0].split("#")[0].rstrip("/").lower()


def _item_url_key(item: IntelItem) -> str:
    key = _url_key(item.url or "")
    if key:
        return key
    if item.id:
        return f"id:{item.id}"
    return f"t:{item.source}:{_title_key(item.title)}"


def _title_key(title: str) -> str:
    t = _TITLE_STRIP_RE.sub("", (title or "").lower())
    return t[:80]


def _relevance(item: IntelItem) -> float:
    try:
        return float(item.signals.relevance or 0)
    except (TypeError, ValueError):
        return 0.0


def _merge_provenance(keep: IntelItem, other: IntelItem) -> None:
    mq = list(keep.personal.get("matched_queries") or [])
    for q in other.personal.get("matched_queries") or []:
        if q and q not in mq:
            mq.append(q)
    if mq:
        keep.personal["matched_queries"] = mq
    alt = other.personal.get("alt_urls") or []
    if alt:
        merged = list(keep.personal.get("alt_urls") or [])
        for u in alt:
            if u and u not in merged:
                merged.append(u)
        keep.personal["alt_urls"] = merged


def dedup_items(items: list[IntelItem]) -> list[IntelItem]:
    seen_urls: set[str] = set()
    url_best: dict[str, IntelItem] = {}
    title_best: dict[str, IntelItem] = {}
    result: list[IntelItem] = []
    for item in items:
        url_key = _item_url_key(item)
        if url_key in seen_urls:
            existing = url_best.get(url_key)
            if existing is not None:
                _merge_provenance(existing, item)
                if _relevance(item) > _relevance(existing):
                    if existing in result:
                        result[result.index(existing)] = item
                    url_best[url_key] = item
            continue
        seen_urls.add(url_key)
        url_best[url_key] = item
        skip_title_dedup = item.type == "answer" and item.source == "zhihu"
        title_key = _title_key(item.title)
        if not skip_title_dedup and title_key and len(title_key) >= 6:
            existing = title_best.get(title_key)
            if existing is not None:
                if _relevance(item) <= _relevance(existing):
                    continue
                if existing in result:
                    result.remove(existing)
                title_best[title_key] = item
            else:
                title_best[title_key] = item
        result.append(item)
    return result
