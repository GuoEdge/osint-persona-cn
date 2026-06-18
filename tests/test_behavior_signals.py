"""Behavior signal scoring tests."""

from __future__ import annotations

from osint_toolkit.persona.behavior_signals import score_event


def test_bilibili_follow_scores_high():
    score = score_event(
        "bilibili_follow",
        {"title": "某 UP 主", "url": "https://space.bilibili.com/123", "event_kind": "following"},
    )
    assert score >= 80


def test_bilibili_follow_included_in_ranked_threshold():
    score = score_event("bilibili_follow", {"title": "UP", "url": "https://space.bilibili.com/1"})
    assert score >= 8
