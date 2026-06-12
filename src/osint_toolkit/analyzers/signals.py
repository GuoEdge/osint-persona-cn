"""客观特征提取 / Objective signal extraction."""

from __future__ import annotations

import re

from osint_toolkit.models.intel_item import IntelItem, IntelSignals

MARKETING_PATTERNS = ["优惠", "购买", "公众号", "加我", "带货", "限时"]
HYPE_PATTERNS = ["震惊", "必看", "万字干货", "天花板", "绝绝子"]


def extract_signals(item: IntelItem, query: str = "", match_terms: list[str] | None = None) -> IntelSignals:
    text = (item.title + " " + item.content).lower()
    terms = match_terms or []
    if query.strip():
        terms = list(terms) + [query.strip()]
    terms = [t.lower().strip() for t in terms if t and str(t).strip()]
    terms = list(dict.fromkeys(terms))
    relevance = 0.5
    if terms:
        hits = sum(1 for t in terms if t in text)
        relevance = min(1.0, hits / max(len(terms), 1) + 0.2)
    density = "high" if len(item.content) > 800 else "medium" if len(item.content) > 200 else "low"
    marketing = 0.0
    for p in MARKETING_PATTERNS + HYPE_PATTERNS:
        if p in item.title or p in item.content[:300]:
            marketing += 0.15
    marketing = min(1.0, marketing)
    fold_reason = None
    if marketing > 0.6 and relevance < 0.4:
        fold_reason = "营销疑似且相关性低"
    signals = IntelSignals(
        relevance=round(relevance, 2),
        density=density,
        marketing_suspect=round(marketing, 2),
        freshness="unknown",
        fold_reason=fold_reason,
    )
    item.signals = signals
    return signals


def apply_persona_boost(item: IntelItem, topics: list[str]) -> None:
    if not topics:
        return
    title = item.title.lower()
    hits = sum(1 for topic in topics if topic.lower() in title)
    if hits <= 0:
        return
    boost = 0.1 + 0.05 * min(hits - 1, 2)
    item.signals.relevance = round(min(1.0, item.signals.relevance + boost), 2)
