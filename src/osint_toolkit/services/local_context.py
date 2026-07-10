"""Local user context aggregation for AI-assisted search.

This module is intentionally read-only: it gathers compact, auditable hints
from persona, knowledge, behavior events, and feedback without changing search
ranking or filtering decisions.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.behavior_signals import behavior_category, load_ranked_behavior_samples
from osint_toolkit.persona.context import PersonaContext, load_seen_urls, maybe_load_persona_context
from osint_toolkit.services import knowledge, rag


def _clip(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def _item_hint(item: IntelItem, *, match_reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": item.id,
        "source": item.source,
        "title": _clip(item.title, 120),
        "url": item.url,
        "summary": _clip(item.summary or item.content, 260),
        "relevance": round(float(item.signals.relevance or 0), 3),
        "match_reasons": (match_reasons or [])[:3],
    }


def _behavior_hint(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": str(row.get("event_type") or ""),
        "source": str(row.get("source") or ""),
        "title": _clip(row.get("title") or row.get("url"), 120),
        "url": str(row.get("url") or ""),
        "created_at": str(row.get("created_at") or ""),
        "dwell_sec": int(int(row.get("duration_ms") or 0) / 1000),
    }


def _feedback_patterns(limit: int) -> dict[str, Any]:
    try:
        rows = FeedbackStore().list_recent(limit)
    except Exception:  # noqa: BLE001
        rows = []
    rating_counts = Counter(str(r.get("rating") or "") for r in rows if r.get("rating"))
    recent = [
        {
            "target_type": str(r.get("target_type") or ""),
            "target_id": str(r.get("target_id") or ""),
            "rating": str(r.get("rating") or ""),
            "reason": _clip(r.get("reason"), 120),
            "run_id": str(r.get("run_id") or ""),
        }
        for r in rows[-10:]
    ]
    return {"rating_counts": dict(rating_counts), "recent": recent}


def _persona_projects(persona_ctx: PersonaContext | None, *, limit: int = 8) -> list[dict[str, Any]]:
    if not persona_ctx or not isinstance(persona_ctx.structured, dict):
        return []
    rows = persona_ctx.structured.get("active_projects") or []
    return [row for row in rows if isinstance(row, dict)][:limit]


def _top_interest_domains(persona_ctx: PersonaContext | None, *, limit: int = 8) -> list[dict[str, Any]]:
    if not persona_ctx or not isinstance(persona_ctx.structured, dict):
        return []
    rows = persona_ctx.structured.get("interest_domains") or []
    return [row for row in rows if isinstance(row, dict)][:limit]


def _behavior_focus(behavior_samples: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in behavior_samples[:limit]:
        rows.append(
            {
                "title": row.get("title") or "",
                "source": row.get("source") or "",
                "event_type": row.get("event_type") or "",
                "category": behavior_category(str(row.get("event_type") or "")),
                "dwell_sec": row.get("dwell_sec") or 0,
                "url": row.get("url") or "",
            }
        )
    return rows


def _linkage_summary(
    *,
    knowledge_hits: list[dict[str, Any]],
    knowledge_projects: list[dict[str, Any]],
    knowledge_concepts: list[dict[str, Any]],
    knowledge_gaps: dict[str, Any],
    behavior_samples: list[dict[str, Any]],
    persona_ctx: PersonaContext | None,
) -> dict[str, Any]:
    concept_names = [str(row.get("name") or "") for row in knowledge_concepts if row.get("name")]
    project_names = [str(row.get("name") or "") for row in knowledge_projects if row.get("name")]
    follow_up_questions = [
        str(row.get("question") or "") for row in (knowledge_gaps.get("questions") or []) if row.get("question")
    ][:6]
    return {
        "top_projects": project_names[:6],
        "top_concepts": concept_names[:8],
        "follow_up_questions": follow_up_questions,
        "behavior_focus": _behavior_focus(behavior_samples),
        "persona_projects": _persona_projects(persona_ctx),
        "persona_interest_domains": _top_interest_domains(persona_ctx),
        "knowledge_hit_titles": [str(row.get("title") or "") for row in knowledge_hits[:6]],
    }


def build_local_context(
    query: str,
    *,
    persona_ctx: PersonaContext | None = None,
    knowledge_limit: int = 6,
    concept_limit: int = 8,
    gap_limit: int = 5,
    behavior_limit: int = 12,
    feedback_limit: int = 200,
    seen_limit: int = 80,
) -> dict[str, Any]:
    """Build a compact local context package for AI prompts and run audit."""
    if persona_ctx is None:
        try:
            persona_ctx = maybe_load_persona_context()
        except Exception:  # noqa: BLE001
            persona_ctx = None

    try:
        rag_payload = rag.retrieve(query, limit=knowledge_limit, expand_graph=True)
        knowledge_hits = [
            {
                "id": row.get("item_id") or "",
                "source": row.get("source") or "",
                "title": _clip(row.get("title"), 120),
                "url": row.get("url") or "",
                "summary": _clip(row.get("summary") or row.get("snippet"), 260),
                "relevance": round(float(row.get("score") or 0), 3),
                "match_reasons": [row.get("match_reason") or row.get("relation_reason") or ""],
                "citation": row.get("citation") or "",
                "source_channel": row.get("source_channel") or "",
                "needs_verification": bool(row.get("needs_verification")),
            }
            for row in rag_payload.get("evidence", [])
        ]
    except Exception:  # noqa: BLE001
        knowledge_hits = []

    try:
        knowledge_concepts = knowledge.list_concepts(query=query, limit=concept_limit)
    except Exception:  # noqa: BLE001
        knowledge_concepts = []

    try:
        knowledge_projects = knowledge.list_concepts(query=query, kind="project", limit=max(3, concept_limit // 2))
    except Exception:  # noqa: BLE001
        knowledge_projects = []

    try:
        knowledge_gaps = knowledge.research_questions(query=query, limit=gap_limit)
    except Exception:  # noqa: BLE001
        knowledge_gaps = {"questions": [], "gaps": [], "count": 0}

    try:
        behavior_samples = [_behavior_hint(r) for r in load_ranked_behavior_samples(sample_limit=behavior_limit)]
    except Exception:  # noqa: BLE001
        behavior_samples = []

    try:
        seen_urls = sorted(load_seen_urls(limit=seen_limit))[:seen_limit]
    except Exception:  # noqa: BLE001
        seen_urls = []

    linkage_summary = _linkage_summary(
        knowledge_hits=knowledge_hits,
        knowledge_projects=knowledge_projects,
        knowledge_concepts=knowledge_concepts,
        knowledge_gaps=knowledge_gaps,
        behavior_samples=behavior_samples,
        persona_ctx=persona_ctx,
    )

    return {
        "query": query,
        "persona": {
            "brief": _clip(persona_ctx.brief if persona_ctx else "", 1600),
            "recent_topics": list(persona_ctx.recent_topics if persona_ctx else [])[:12],
            "interest_hints": list(persona_ctx.interest_hints if persona_ctx else [])[:8],
            "active_projects": (
                list((persona_ctx.structured or {}).get("active_projects") or [])[:8] if persona_ctx else []
            ),
            "structured": persona_ctx.structured if persona_ctx else {},
            "stale": bool(persona_ctx.stale) if persona_ctx else False,
        },
        "knowledge_hits": knowledge_hits,
        "knowledge_concepts": knowledge_concepts,
        "knowledge_projects": knowledge_projects,
        "knowledge_gaps": knowledge_gaps,
        "behavior_samples": behavior_samples,
        "feedback_patterns": _feedback_patterns(feedback_limit),
        "seen_urls": seen_urls,
        "linkage_summary": linkage_summary,
        "limits": {
            "knowledge": knowledge_limit,
            "concepts": concept_limit,
            "gaps": gap_limit,
            "behavior": behavior_limit,
            "feedback": feedback_limit,
            "seen_urls": seen_limit,
        },
    }


def compact_for_prompt(local_context: dict[str, Any] | None, *, max_chars: int = 5000) -> str:
    """Return a prompt-sized representation without adding another JSON dependency at call sites."""
    if not local_context:
        return ""
    import json

    payload = {
        "persona": local_context.get("persona") or {},
        "knowledge_hits": local_context.get("knowledge_hits") or [],
        "knowledge_concepts": local_context.get("knowledge_concepts") or [],
        "knowledge_projects": local_context.get("knowledge_projects") or [],
        "knowledge_gaps": local_context.get("knowledge_gaps") or {},
        "behavior_samples": local_context.get("behavior_samples") or [],
        "feedback_patterns": local_context.get("feedback_patterns") or {},
        "linkage_summary": local_context.get("linkage_summary") or {},
    }
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."
