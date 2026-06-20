"""合成知乎动态时间线 / Synthetic activity timeline when activities API is empty."""

from __future__ import annotations

from typing import Any


def _timestamp(entry: dict[str, Any]) -> float:
    for key in ("created_time", "updated_time", "created", "updated", "visited_at", "endorsed_at"):
        raw = entry.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def _synthetic_entry(
    *,
    event_type: str,
    event_kind: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    out = dict(entry)
    out["event_kind"] = event_kind
    out["via"] = "synthetic_timeline"
    out["_event_type"] = event_type
    return out


def build_synthetic_activities(
    *,
    votes: list[dict[str, Any]] | None = None,
    favorites: list[dict[str, Any]] | None = None,
    followees: list[dict[str, Any]] | None = None,
    answers: list[dict[str, Any]] | None = None,
    articles: list[dict[str, Any]] | None = None,
    pins: list[dict[str, Any]] | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Merge typed ingest rows into a chronological pseudo-activity list."""
    pool: list[dict[str, Any]] = []
    for entry in votes or []:
        pool.append(_synthetic_entry(event_type="zhihu_vote", event_kind="answer_vote", entry=entry))
    for entry in favorites or []:
        pool.append(_synthetic_entry(event_type="zhihu_fav", event_kind="activity_favorite", entry=entry))
    for entry in followees or []:
        pool.append(_synthetic_entry(event_type="zhihu_follow", event_kind="follow", entry=entry))
    for entry in answers or []:
        pool.append(_synthetic_entry(event_type="zhihu_answer", event_kind="create_answer", entry=entry))
    for entry in articles or []:
        pool.append(_synthetic_entry(event_type="zhihu_article", event_kind="create_article", entry=entry))
    for entry in pins or []:
        pool.append(_synthetic_entry(event_type="zhihu_pin", event_kind="create_pin", entry=entry))

    pool.sort(key=_timestamp, reverse=True)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in pool:
        url = str(entry.get("url") or "")
        kind = str(entry.get("event_kind") or "")
        key = f"{kind}|{url}"
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
        if len(out) >= limit:
            break
    return out
