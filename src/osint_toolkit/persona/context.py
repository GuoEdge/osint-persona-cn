"""统一画像上下文 / PersonaContext for AI injection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from osint_toolkit.persona.behavior_signals import load_recent_interest_hints, score_event
from osint_toolkit.persona.store import load_mental_model, load_persona_brief, save_mental_model
from osint_toolkit.persona.structured import structured_from_model
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.utils.config import load_config

_TOPIC_RE = re.compile(r"[\u4e00-\u9fff]{2,4}|[a-zA-Z]{3,}")


@dataclass
class PersonaContext:
    brief: str = ""
    interest_hints: list[dict] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    structured: dict = field(default_factory=dict)
    stale: bool = False


def is_persona_inject_enabled() -> bool:
    return bool(load_config().get("ai", {}).get("persona_inject", True))


def get_event_count() -> int:
    conn = connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()
        return int(row["c"]) if row else 0
    finally:
        conn.close()


def extract_topics(hints: list[dict], *, limit: int = 12) -> list[str]:
    freq: dict[str, int] = {}
    for hint in hints:
        text = str(hint.get("title") or "")
        for token in _TOPIC_RE.findall(text):
            low = token.lower()
            if len(low) < 2:
                continue
            freq[low] = freq.get(low, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], -len(x[0])))
    return [t for t, _ in ranked[:limit]]


def is_persona_stale() -> bool:
    model = load_mental_model()
    threshold = int(load_config().get("ai", {}).get("auto_persona_rebuild_threshold", 50))
    max_age_hours = int(load_config().get("ai", {}).get("auto_persona_rebuild_max_age_hours", 168) or 0)
    at_build = int(model.get("events_at_last_build") or 0)
    count = get_event_count()
    built_at_raw = str(model.get("built_at") or "").strip()
    if at_build <= 0:
        return count >= 10
    if model.get("persona_rebuild_pending"):
        return True
    if count - at_build >= threshold:
        return True
    if max_age_hours > 0 and built_at_raw:
        try:
            built_at = datetime.fromisoformat(built_at_raw.replace("Z", "+00:00"))
            if built_at.tzinfo is None:
                built_at = built_at.replace(tzinfo=UTC)
            age_hours = (datetime.now(UTC) - built_at.astimezone(UTC)).total_seconds() / 3600
            if age_hours >= max_age_hours:
                return True
        except ValueError:
            return True
    return False


def mark_persona_built() -> None:
    model = load_mental_model()
    model["events_at_last_build"] = get_event_count()
    model["persona_stale"] = False
    save_mental_model(model)


def refresh_persona_stale_flag() -> bool:
    stale = is_persona_stale()
    model = load_mental_model()
    if model.get("persona_stale") != stale:
        model["persona_stale"] = stale
        save_mental_model(model)
    return stale


def load_seen_urls(*, min_score: int = 12, limit: int = 500) -> set[str]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT event_type, data_json FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    seen: set[str] = set()
    for row in rows:
        try:
            data = json.loads(row["data_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if score_event(str(row["event_type"]), data) < min_score:
            continue
        url = str(data.get("url") or data.get("parent_url") or "").strip()
        if url.startswith("http"):
            seen.add(url)
    return seen


def load_persona_context(*, hints_limit: int = 12) -> PersonaContext:
    brief = load_persona_brief().strip()
    model = load_mental_model()
    hints = load_recent_interest_hints(limit=hints_limit)
    topics = extract_topics(hints)
    return PersonaContext(
        brief=brief,
        interest_hints=hints,
        recent_topics=topics,
        structured=structured_from_model(model),
        stale=is_persona_stale(),
    )


def maybe_load_persona_context() -> PersonaContext | None:
    if not is_persona_inject_enabled():
        return None
    return load_persona_context()
