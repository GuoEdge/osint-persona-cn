"""Persona 服务 / Persona service."""

from __future__ import annotations

from typing import Any

from osint_toolkit.ai.suggest_queries import suggest_queries
from osint_toolkit.persona.auto_rebuild import (
    dismiss_auto_rebuild_notice,
    get_auto_rebuild_mode,
    get_auto_rebuild_notice,
)
from osint_toolkit.persona.behavior_signals import (
    load_behavior_category_summary,
    load_behavior_workbench,
    load_ranked_behavior_samples,
)
from osint_toolkit.persona.builder import build_persona_draft
from osint_toolkit.persona.context import is_persona_stale, load_persona_context, maybe_load_persona_context
from osint_toolkit.persona.store import (
    list_version_entries,
    load_mental_model,
    load_persona_brief,
    mental_model_path,
    rollback_version,
)
from osint_toolkit.persona.structured import structured_from_model
from osint_toolkit.utils.config import load_config


def show_persona() -> dict[str, Any]:
    model = load_mental_model()
    brief = load_persona_brief()
    current_version = int(model.get("version") or 0)
    version_history = list_version_entries(current_version=current_version)
    versions = [str(item["label"]) for item in version_history]
    built = int(model.get("events_at_last_build") or 0) > 0
    event_breakdown = model.get("event_breakdown") if isinstance(model.get("event_breakdown"), dict) else {}
    high_interest_hints = model.get("high_interest_hints") if isinstance(model.get("high_interest_hints"), list) else []
    evidence = {}
    structured = structured_from_model(model)
    ranked_samples = load_ranked_behavior_samples(fetch_limit=500, sample_limit=16)
    category_summary = load_behavior_category_summary(fetch_limit=500)
    behavior_workbench = load_behavior_workbench(fetch_limit=500, per_category=4)
    if isinstance(structured.get("evidence"), dict):
        evidence = structured.get("evidence") or {}
    return {
        "mental_model": model,
        "brief": brief,
        "mental_model_path": str(mental_model_path()),
        "versions": versions,
        "version_history": version_history,
        "built": built,
        "brief_ai_generated": bool(model.get("brief_ai_generated")),
        "brief_ai_error": model.get("brief_ai_error"),
        "structured": structured,
        "structured_source": model.get("structured_source") or "rules",
        "structured_ai_error": model.get("structured_ai_error"),
        "console": {
            "event_breakdown": event_breakdown,
            "recent_sources": model.get("recent_sources") or {},
            "recent_event_types": model.get("recent_event_types") or {},
            "sample_size": model.get("sample_size") or {},
            "high_interest_hints": high_interest_hints,
            "ranked_behavior_samples": ranked_samples,
            "behavior_category_summary": category_summary,
            "behavior_workbench": behavior_workbench,
            "evidence": evidence,
            "version_retention": 10,
            "dedup_note": {
                "event_level": "行为事件写入前会按 dedup key 去重，避免同一事件反复入库。",
                "inventory_level": "账号收藏/关注类同步会作为清单快照保留，并与近期高频行为分开统计。",
                "semantic_limit": "跨平台同主题内容仍可能同时出现，这是语义层重合，不等于原始事件重复写入。",
            },
        },
    }


def build_persona(*, review: bool = False, structured: bool = False) -> dict[str, Any]:
    draft = build_persona_draft(review=review)
    result: dict[str, Any] = {
        "version": draft["mental_model"].get("version"),
        "mental_model_path": str(mental_model_path()),
        "review": review,
        "brief_preview": (draft.get("persona_brief") or "")[:300],
        "structured": structured_from_model(draft["mental_model"]) if structured else {},
        "structured_source": draft["mental_model"].get("structured_source") or "rules",
    }
    if review and draft.get("review_summary"):
        result["review_summary"] = draft["review_summary"]
    if draft.get("brief_ai_error"):
        result["brief_ai_error"] = draft["brief_ai_error"]
    return result


def rollback_persona(version: int) -> dict[str, Any]:
    ok = rollback_version(version)
    return {"ok": ok, "version": version}


async def refresh_persona_status(*, auto_rebuild: bool = False) -> dict[str, Any]:
    """返回画像状态；仅当 auto_rebuild=True 且在 auto 模式且过时时才触发重建。"""
    if auto_rebuild:
        from osint_toolkit.persona.auto_rebuild import maybe_auto_rebuild_persona

        if get_auto_rebuild_mode() == "auto" and is_persona_stale():
            await maybe_auto_rebuild_persona()
    return get_persona_status()


def get_persona_status() -> dict[str, Any]:
    model = load_mental_model()
    ctx = load_persona_context()
    mode = get_auto_rebuild_mode()
    stale = is_persona_stale()
    ai_cfg = load_config().get("ai", {})
    return {
        "version": model.get("version"),
        "built_at": model.get("built_at"),
        "stale": stale,
        "stale_prompt": stale and mode == "prompt",
        "auto_rebuild_mode": mode,
        "auto_rebuild_notice": get_auto_rebuild_notice(),
        "events_at_last_build": model.get("events_at_last_build"),
        "auto_rebuild_threshold": int(ai_cfg.get("auto_persona_rebuild_threshold", 50) or 50),
        "auto_rebuild_max_age_hours": int(ai_cfg.get("auto_persona_rebuild_max_age_hours", 168) or 0),
        "recent_topics": ctx.recent_topics,
        "hints_count": len(ctx.interest_hints),
        "structured_source": model.get("structured_source") or "rules",
        "structured_fields": [key for key, value in (ctx.structured or {}).items() if value],
    }


def dismiss_persona_notice() -> dict[str, Any]:
    return {"ok": dismiss_auto_rebuild_notice()}


def get_suggested_queries(*, no_ai: bool = False) -> dict[str, Any]:
    queries = suggest_queries(maybe_load_persona_context(), no_ai=no_ai)
    return {"queries": queries, "count": len(queries)}


def get_structured_persona() -> dict[str, Any]:
    model = load_mental_model()
    return {
        "version": model.get("version"),
        "built_at": model.get("built_at"),
        "source": model.get("structured_source") or "rules",
        "stale": is_persona_stale(),
        "structured": structured_from_model(model),
        "ai_error": model.get("structured_ai_error"),
    }
