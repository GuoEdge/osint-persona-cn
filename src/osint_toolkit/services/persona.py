"""Persona 服务 / Persona service."""

from __future__ import annotations

from typing import Any

from osint_toolkit.ai.suggest_queries import suggest_queries
from osint_toolkit.persona.builder import build_persona_draft
from osint_toolkit.persona.auto_rebuild import dismiss_auto_rebuild_notice, get_auto_rebuild_mode, get_auto_rebuild_notice
from osint_toolkit.persona.context import is_persona_stale, load_persona_context, maybe_load_persona_context
from osint_toolkit.persona.store import (
    list_versions,
    load_mental_model,
    load_persona_brief,
    mental_model_path,
    rollback_version,
)


def show_persona() -> dict[str, Any]:
    versions = [p.stem.replace("mental_model.", "") for p in list_versions()]
    return {
        "mental_model": load_mental_model(),
        "brief": load_persona_brief(),
        "mental_model_path": str(mental_model_path()),
        "versions": versions,
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
    return result


def rollback_persona(version: int) -> dict[str, Any]:
    ok = rollback_version(version)
    return {"ok": ok, "version": version}


async def refresh_persona_status() -> dict[str, Any]:
    """auto 模式下若画像过时则先重建，再返回状态。"""
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
