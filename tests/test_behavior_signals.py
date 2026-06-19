"""Behavior signal scoring tests."""

from __future__ import annotations

from osint_toolkit.persona.behavior_signals import INVENTORY_SNAPSHOT_TYPES, score_event


def test_inventory_snapshot_types_score_zero():
    for event_type in INVENTORY_SNAPSHOT_TYPES:
        assert score_event(event_type, {"url": "https://example.com/item"}) == 0


def test_zhihu_vote_still_scores_high():
    score = score_event(
        "zhihu_vote",
        {"url": "https://www.zhihu.com/question/1/answer/1", "via": "voteanswers_api"},
    )
    assert score >= 80
