"""客观特征提取 / Objective signal extraction."""

from __future__ import annotations

import re

from osint_toolkit.models.intel_item import IntelItem, IntelSignals

MARKETING_PATTERNS = ["优惠", "购买", "公众号", "加我", "带货", "限时"]
HYPE_PATTERNS = ["震惊", "必看", "万字干货", "天花板", "绝绝子"]


def extract_signals(item: IntelItem, query: str = "") -> IntelSignals:
    text = (item.title + " " + item.content).lower()
    q = query.lower().strip()
    relevance = 0.5
    if q:
        tokens = [t for t in re.split(r"\s+", q) if t]
        hits = sum(1 for t in tokens if t in text)
        relevance = min(1.0, hits / max(len(tokens), 1) + 0.2)
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
