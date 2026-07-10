"""Structured persona helpers.

The brief is useful for humans and prompts, but the rest of the toolkit needs
stable fields it can query without parsing Markdown.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

PERSONA_STRUCTURED_FIELDS = (
    "interest_domains",
    "active_projects",
    "source_preferences",
    "knowledge_goals",
    "entity_affinities",
    "reading_style",
    "avoid_patterns",
)

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,6}|[a-zA-Z][a-zA-Z0-9_.+-]{2,}")
_SOURCE_LABELS = {
    "bilibili": "B站",
    "zhihu": "知乎",
    "github": "GitHub",
    "web": "网页",
    "extension": "浏览器扩展",
    "weixin": "微信",
    "v2ex": "V2EX",
}
_LOW_VALUE_RATINGS = {"noise", "wrong", "skip", "bad", "not_useful"}
_HIGH_VALUE_RATINGS = {"useful", "helpful", "interested", "good"}


def _text(value: Any, limit: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_text(v) for v in value if _text(v)]
    return [_text(value)] if _text(value) else []


def _tokens_from_text(text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(text or ""):
        value = token.strip()
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(value)
    return tokens


def empty_structured_persona() -> dict[str, Any]:
    return {
        "interest_domains": [],
        "active_projects": [],
        "source_preferences": {"preferred": [], "avoid": [], "notes": []},
        "knowledge_goals": [
            "把浏览、收录与搜罗结果沉淀为可检索的长期知识库",
            "发现旧知识、实体、主题与新问题之间的连接",
        ],
        "entity_affinities": [],
        "reading_style": {"preferred": [], "signals": []},
        "avoid_patterns": [],
        "evidence": {"source": "empty"},
    }


def _field(raw: dict[str, Any], base: dict[str, Any], name: str, expected_type: type) -> Any:
    value = raw.get(name)
    if isinstance(value, expected_type):
        return value
    return base.get(name, [] if expected_type is list else {})


def normalize_structured_persona(
    data: dict[str, Any] | None,
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = fallback if isinstance(fallback, dict) else empty_structured_persona()
    raw = data if isinstance(data, dict) else {}
    normalized = {
        "interest_domains": _field(raw, base, "interest_domains", list),
        "active_projects": _field(raw, base, "active_projects", list),
        "source_preferences": _field(raw, base, "source_preferences", dict),
        "knowledge_goals": _field(raw, base, "knowledge_goals", list),
        "entity_affinities": _field(raw, base, "entity_affinities", list),
        "reading_style": _field(raw, base, "reading_style", dict),
        "avoid_patterns": _field(raw, base, "avoid_patterns", list),
        "evidence": _field(raw, base, "evidence", dict),
    }
    prefs = normalized["source_preferences"]
    normalized["source_preferences"] = {
        "preferred": _as_list(prefs.get("preferred"))[:12] if isinstance(prefs, dict) else [],
        "avoid": _as_list(prefs.get("avoid"))[:12] if isinstance(prefs, dict) else [],
        "notes": _as_list(prefs.get("notes"))[:12] if isinstance(prefs, dict) else [],
    }
    style = normalized["reading_style"]
    normalized["reading_style"] = {
        "preferred": _as_list(style.get("preferred"))[:12] if isinstance(style, dict) else [],
        "signals": _as_list(style.get("signals"))[:12] if isinstance(style, dict) else [],
    }
    normalized["knowledge_goals"] = _as_list(normalized["knowledge_goals"])[:12]
    normalized["avoid_patterns"] = _as_list(normalized["avoid_patterns"])[:12]
    return normalized


def build_rule_structured_persona(
    *,
    sources: Counter | dict[str, int] | None = None,
    event_types: Counter | dict[str, int] | None = None,
    event_breakdown: dict[str, Any] | None = None,
    interest_hints: list[dict[str, Any]] | None = None,
    feedback: list[dict[str, Any]] | None = None,
    ranked_behavior_sample: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sources_counter = Counter(sources or {})
    events_counter = Counter(event_types or {})
    hints = interest_hints or []
    feedback_rows = feedback or []
    samples = ranked_behavior_sample or []

    domain_counter: Counter[str] = Counter()
    entity_counter: Counter[str] = Counter()
    evidence_by_token: dict[str, str] = {}
    for row in [*hints, *samples]:
        title = _text(row.get("title") or row.get("url") or "", 180)
        for token in _tokens_from_text(title):
            low = token.casefold()
            domain_counter[token] += 1
            evidence_by_token.setdefault(low, title)
        for key in ("entities", "entity", "author", "source"):
            for entity in _as_list(row.get(key)):
                entity_counter[entity] += 1

    interest_domains = [
        {
            "name": name,
            "weight": count,
            "evidence": evidence_by_token.get(name.casefold(), ""),
        }
        for name, count in domain_counter.most_common(12)
    ]
    entity_affinities = [
        {"name": name, "kind": "observed", "weight": count, "evidence": f"行为样本出现 {count} 次"}
        for name, count in entity_counter.most_common(12)
    ]

    preferred_sources = [
        _SOURCE_LABELS.get(name, name)
        for name, count in sources_counter.most_common(8)
        if count > 0 and name != "unknown"
    ]
    avoid_sources: Counter[str] = Counter()
    avoid_patterns: Counter[str] = Counter()
    useful_patterns: Counter[str] = Counter()
    for row in feedback_rows:
        rating = str(row.get("rating") or "").strip().lower()
        reason = _text(row.get("reason"), 160)
        target_source = str(row.get("source") or "").strip()
        if rating in _LOW_VALUE_RATINGS:
            if target_source:
                avoid_sources[target_source] += 1
            if reason:
                avoid_patterns[reason] += 1
        elif rating in _HIGH_VALUE_RATINGS and reason:
            useful_patterns[reason] += 1

    reading_style_bits: list[str] = []
    if any(key in events_counter for key in ("ext_page_dwell", "page_visit", "dwell_save")):
        reading_style_bits.append("重视停留后可复读的正文与证据")
    if any(key in events_counter for key in ("zhihu_vote", "bilibili_like", "like")):
        reading_style_bits.append("认可观点密度或实操价值较高的内容")
    if any(key in events_counter for key in ("manual_save", "dwell_save", "save_url")):
        reading_style_bits.append("偏好可沉淀、可整理、可再次引用的材料")

    recent_7d = (event_breakdown or {}).get("recent_activity_7d") or {}
    active_projects = []
    for name, count in Counter(recent_7d).most_common(6):
        active_projects.append(
            {
                "name": str(name),
                "status": "active",
                "signals": [f"近 7 日相关行为 {count} 条"],
            }
        )
    if not active_projects:
        for row in interest_domains[:4]:
            active_projects.append(
                {
                    "name": row["name"],
                    "status": "candidate",
                    "signals": [_text(row.get("evidence"))],
                }
            )

    return normalize_structured_persona(
        {
            "interest_domains": interest_domains,
            "active_projects": active_projects,
            "source_preferences": {
                "preferred": preferred_sources,
                "avoid": [_SOURCE_LABELS.get(name, name) for name, _ in avoid_sources.most_common(8)],
                "notes": [f"{name}: {count} 条近期行为" for name, count in sources_counter.most_common(8)],
            },
            "knowledge_goals": [
                "把浏览、点赞、收藏、搜罗和手动收录转成长期知识资产",
                "围绕主题、实体、项目和问题组织材料，支持再搜索和再研究",
                "在回答和报告中优先引用已有知识，减少重复搜罗",
            ],
            "entity_affinities": entity_affinities,
            "reading_style": {
                "preferred": reading_style_bits or ["偏好可验证、可引用、可沉淀的内容"],
                "signals": [f"{k}: {v}" for k, v in events_counter.most_common(10)],
            },
            "avoid_patterns": [name for name, _ in avoid_patterns.most_common(8)]
            or ["标题党、重复搬运、营销软文、缺少原始证据的观点"],
            "evidence": {
                "source": "rules",
                "event_types": dict(events_counter),
                "recent_sources": dict(sources_counter),
                "useful_feedback_patterns": dict(useful_patterns.most_common(6)),
            },
        }
    )


def structured_from_model(model: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(model, dict):
        return empty_structured_persona()
    existing = model.get("structured")
    if isinstance(existing, dict):
        return normalize_structured_persona(existing)
    return build_rule_structured_persona(
        sources=Counter(model.get("recent_sources") or {}),
        event_types=Counter(model.get("recent_event_types") or {}),
        event_breakdown=model.get("event_breakdown") if isinstance(model.get("event_breakdown"), dict) else {},
        interest_hints=model.get("high_interest_hints") if isinstance(model.get("high_interest_hints"), list) else [],
        feedback=[],
        ranked_behavior_sample=[],
    )
