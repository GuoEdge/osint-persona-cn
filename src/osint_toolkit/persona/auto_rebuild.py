"""Persona 半自动重建 / Semi-automatic persona rebuild."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.persona.context import get_event_count, is_persona_stale, refresh_persona_stale_flag
from osint_toolkit.persona.store import load_mental_model, load_persona_brief, save_mental_model
from osint_toolkit.utils.config import load_config

logger = logging.getLogger(__name__)


def get_auto_rebuild_mode() -> str:
    mode = str(load_config().get("ai", {}).get("auto_persona_rebuild", "prompt")).lower()
    return mode if mode in {"off", "prompt", "auto"} else "auto"


def set_pending_rebuild_flag(pending: bool = True) -> None:
    model = load_mental_model()
    model["persona_rebuild_pending"] = pending
    save_mental_model(model)


def is_pending_rebuild() -> bool:
    return bool(load_mental_model().get("persona_rebuild_pending"))


def record_auto_rebuild_notice(*, version: int | str) -> dict[str, Any]:
    notice = {
        "at": datetime.now(UTC).isoformat(),
        "version": version,
        "events_at_build": get_event_count(),
    }
    model = load_mental_model()
    model["persona_auto_rebuild_notice"] = notice
    model.pop("persona_auto_rebuild_notice_dismissed_at", None)
    save_mental_model(model)
    return notice


def get_auto_rebuild_notice() -> dict[str, Any] | None:
    model = load_mental_model()
    notice = model.get("persona_auto_rebuild_notice")
    if not isinstance(notice, dict) or not notice.get("at"):
        return None
    if model.get("persona_auto_rebuild_notice_dismissed_at") == notice.get("at"):
        return None
    return notice


def dismiss_auto_rebuild_notice() -> bool:
    model = load_mental_model()
    notice = model.get("persona_auto_rebuild_notice")
    if not isinstance(notice, dict) or not notice.get("at"):
        return False
    model["persona_auto_rebuild_notice_dismissed_at"] = notice["at"]
    save_mental_model(model)
    return True


async def maybe_auto_rebuild_persona() -> dict[str, Any]:
    """在扩展 ingest 等行为数据增长后触发半自动重建。"""
    mode = get_auto_rebuild_mode()
    if mode == "off":
        return {"action": "none"}

    stale = refresh_persona_stale_flag()
    if not stale:
        set_pending_rebuild_flag(False)
        return {"action": "none"}

    if mode == "auto":
        from osint_toolkit.persona.builder import build_persona_draft

        old_brief = load_persona_brief()
        try:
            draft = build_persona_draft()
            version = draft["mental_model"].get("version")
            notice = record_auto_rebuild_notice(version=version)
            set_pending_rebuild_flag(False)
            return {
                "action": "rebuilt",
                "version": version,
                "persona_rebuild_suggested": False,
                "auto_rebuild_notice": notice,
                "brief_preview": (draft.get("persona_brief") or "")[:200],
                "previous_brief_preview": old_brief[:200],
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto persona rebuild failed: %s", exc)
            set_pending_rebuild_flag(True)
            refresh_persona_stale_flag()
            return {"action": "failed", "error": str(exc), "persona_rebuild_suggested": True}

    set_pending_rebuild_flag(True)
    return {"action": "suggested", "persona_rebuild_suggested": True}
