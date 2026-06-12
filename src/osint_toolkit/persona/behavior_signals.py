"""行为事件权重 / Behavior event scoring for persona."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.storage.sqlite import connect

_HIGH_VALUE_TYPES = frozenset(
    {
        "bilibili_like",
        "bilibili_coin",
        "bilibili_fav",
        "bilibili_watch",
        "bilibili_comment_post",
        "bilibili_comment_like",
        "zhihu_vote",
        "zhihu_fav",
        "github_star",
        "ext_save",
    }
)


def score_event(event_type: str, data: dict[str, Any]) -> int:
    score = 0
    if event_type in _HIGH_VALUE_TYPES:
        score += 80
    if event_type == "bilibili_coin":
        score += 10
    if event_type == "github_star":
        score += 15
    if event_type == "zhihu_vote" and data.get("via") == "voteanswers_api":
        score += 20
    if event_type == "bilibili_comment_like":
        score -= 15
    if event_type == "bilibili_comment_post":
        score -= 5
    if event_type == "ext_page_dwell":
        ms = int(data.get("duration_ms") or 0)
        if ms >= 90_000:
            score += 60
        score += min(ms // 15_000, 40)
    if event_type == "ext_page_visit":
        score += 5
    if data.get("via") == "extension" and data.get("event_kind") in ("like", "favorite", "comment_like"):
        score += 20
    if data.get("event_kind") == "comment_post":
        score += 15
    message = str(data.get("message") or data.get("title") or "")
    if message and event_type in ("bilibili_comment_post", "bilibili_comment_like"):
        score += min(len(message) // 20, 10)
    return score


def load_ranked_behavior_samples(*, fetch_limit: int = 400, sample_limit: int = 40) -> list[dict[str, Any]]:
    conn = connect()
    rows = conn.execute(
        "SELECT event_type, data_json, created_at FROM events ORDER BY id DESC LIMIT ?",
        (fetch_limit,),
    ).fetchall()
    conn.close()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        data = json.loads(row["data_json"])
        s = score_event(str(row["event_type"]), data)
        if s < 8:
            continue
        ranked.append(
            (
                s,
                {
                    "event_type": row["event_type"],
                    "created_at": row["created_at"],
                    **data,
                },
            )
        )
    ranked.sort(key=lambda x: (-x[0], x[1].get("created_at", "")))
    return [item for _, item in ranked[:sample_limit]]


def load_recent_interest_hints(*, limit: int = 12) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    for item in load_ranked_behavior_samples(sample_limit=limit):
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")[:100]
        if not url and not title:
            continue
        hints.append(
            {
                "title": title or url,
                "url": url,
                "source": str(item.get("source") or ""),
                "event_type": str(item.get("event_type") or ""),
                "dwell_sec": str(int(int(item.get("duration_ms") or 0) / 1000)),
            }
        )
    return hints
