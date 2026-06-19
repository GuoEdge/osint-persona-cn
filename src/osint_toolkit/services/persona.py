"""Persona 服务 / Persona service."""

from __future__ import annotations

from typing import Any

from osint_toolkit.ai.suggest_queries import suggest_queries
from osint_toolkit.persona.builder import build_persona_draft
from osint_toolkit.persona.auto_rebuild import dismiss_auto_rebuild_notice, get_auto_rebuild_mode, get_auto_rebuild_notice
from osint_toolkit.persona.context import is_persona_stale, load_persona_context, maybe_load_persona_context
from osint_toolkit.persona.store import (
    list_version_entries,
    load_mental_model,
    load_persona_brief,
    mental_model_path,
    rollback_version,
)


def show_persona() -> dict[str, Any]:
    model = load_mental_model()
    brief = load_persona_brief()
    current_version = int(model.get("version") or 0)
    version_history = list_version_entries(current_version=current_version)
    versions = [str(item["label"]) for item in version_history]
    built = int(model.get("events_at_last_build") or 0) > 0
    return {
        "mental_model": model,
        "brief": brief,
        "mental_model_path": str(mental_model_path()),
        "versions": versions,
        "version_history": version_history,
        "built": built,
        "brief_ai_generated": bool(model.get("brief_ai_generated")),
        "brief_ai_error": model.get("brief_ai_error"),
    }


def build_persona(*, review: bool = False) -> dict[str, Any]:
    draft = build_persona_draft(review=review)
    result: dict[str, Any] = {
        "version": draft["mental_model"].get("version"),
        "mental_model_path": str(mental_model_path()),
        "review": review,
        "brief_preview": (draft.get("persona_brief") or "")[:300],
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
    return {
        "version": model.get("version"),
        "stale": stale,
        "stale_prompt": stale and mode == "prompt",
        "auto_rebuild_mode": mode,
        "auto_rebuild_notice": get_auto_rebuild_notice(),
        "events_at_last_build": model.get("events_at_last_build"),
        "recent_topics": ctx.recent_topics,
        "hints_count": len(ctx.interest_hints),
    }


def dismiss_persona_notice() -> dict[str, Any]:
    return {"ok": dismiss_auto_rebuild_notice()}


def get_suggested_queries(*, no_ai: bool = False) -> dict[str, Any]:
    queries = suggest_queries(maybe_load_persona_context(), no_ai=no_ai)
    return {"queries": queries, "count": len(queries)}
