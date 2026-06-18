"""客观特征提取 / Objective signal extraction."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from osint_toolkit.models.intel_item import IntelItem, IntelSignals

_DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})"),
    re.compile(r"(20\d{2})\.(\d{1,2})\.(\d{1,2})"),
]
_RELATIVE_PATTERNS = [
    (re.compile(r"(\d+)\s*小时前"), "hours"),
    (re.compile(r"(\d+)\s*天前"), "days"),
    (re.compile(r"(\d+)\s*周前"), "weeks"),
    (re.compile(r"(\d+)\s*个月前"), "months"),
    (re.compile(r"昨天"), "yesterday"),
    (re.compile(r"今天"), "today"),
]

MARKETING_PATTERNS = ["优惠", "购买", "公众号", "加我", "带货", "限时"]
HYPE_PATTERNS = ["震惊", "必看", "万字干货", "天花板", "绝绝子"]


def _guess_freshness(item: IntelItem) -> str:
    meta_date = item.personal.get("date") or item.personal.get("published_at")
    if meta_date:
        try:
            dt = datetime.fromisoformat(str(meta_date).replace("Z", "+00:00"))
            age = datetime.now(UTC) - dt.astimezone(UTC)
            if age <= timedelta(days=7):
                return "recent"
            if age <= timedelta(days=90):
                return "medium"
            return "older"
        except ValueError:
            pass
    haystack = f"{item.title} {item.content[:400]}"
    now = datetime.now(UTC)
    for pat in _DATE_PATTERNS:
        m = pat.search(haystack)
        if m:
            try:
                dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=UTC)
                age = now - dt
                if age <= timedelta(days=30):
                    return "recent"
                if age <= timedelta(days=365):
                    return "medium"
                return "older"
            except ValueError:
                continue
    for pat, kind in _RELATIVE_PATTERNS:
        m = pat.search(haystack)
        if not m:
            continue
        if kind == "today":
            return "recent"
        if kind == "yesterday":
            return "recent"
        if kind == "hours":
            return "recent"
        if kind == "days" and int(m.group(1)) <= 14:
            return "recent"
        if kind in {"days", "weeks"}:
            return "medium"
        return "older"
    return "unknown"


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
    freshness = _guess_freshness(item)
    if freshness == "recent":
        relevance = min(1.0, relevance + 0.05)
    signals = IntelSignals(
        relevance=round(relevance, 2),
        density=density,
        marketing_suspect=round(marketing, 2),
        freshness=freshness,
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
