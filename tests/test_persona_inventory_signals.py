"""Persona builder inventory vs recent activity breakdown."""

from __future__ import annotations

from osint_toolkit.persona.behavior_signals import (
    INVENTORY_SNAPSHOT_TYPES,
    behavior_category,
    load_behavior_category_summary,
    load_behavior_workbench,
    load_event_type_breakdown,
    score_event,
)
from osint_toolkit.storage.knowledge import log_event


def test_inventory_snapshots_score_zero():
    assert score_event("bilibili_follow", {"url": "https://space.bilibili.com/1"}) == 0
    assert score_event("zhihu_fav", {"url": "https://zhuanlan.zhihu.com/p/1"}) == 0
    assert score_event("zhihu_vote", {"url": "https://www.zhihu.com/question/1/answer/1"}) > 0


def test_event_type_breakdown_splits_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    log_event("bilibili_follow", {"source": "bilibili", "url": "https://space.bilibili.com/1"})
    log_event("zhihu_vote", {"source": "zhihu", "url": "https://www.zhihu.com/question/1/answer/1"})
    breakdown = load_event_type_breakdown(fetch_limit=10)
    assert breakdown["inventory_snapshots"].get("bilibili_follow") == 1
    assert breakdown["recent_activity"].get("zhihu_vote") == 1
    assert "bilibili_follow" not in breakdown["recent_activity"]
    assert "zhihu_vote" in INVENTORY_SNAPSHOT_TYPES or "zhihu_vote" not in breakdown["inventory_snapshots"]


def test_behavior_category_summary_and_workbench(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    log_event(
        "ext_page_dwell",
        {"source": "web", "url": "https://example.com/a", "title": "知识图谱入门", "duration_ms": 120000},
    )
    log_event(
        "zhihu_vote",
        {"source": "zhihu", "url": "https://www.zhihu.com/question/1/answer/2", "title": "本地知识库方案"},
    )
    log_event(
        "bilibili_follow",
        {"source": "bilibili", "url": "https://space.bilibili.com/1"},
    )

    summary = load_behavior_category_summary(fetch_limit=20)
    assert summary["recent_activity_7d"].get("dwell") == 1
    assert summary["recent_activity_7d"].get("endorse") == 1
    assert summary["inventory_snapshots"].get("inventory") == 1

    workbench = load_behavior_workbench(fetch_limit=20, per_category=2)
    categories = {row["category"] for row in workbench}
    assert "dwell" in categories
    assert "endorse" in categories
    dwell_row = next(row for row in workbench if row["category"] == "dwell")
    assert dwell_row["items"][0]["title"] == "知识图谱入门"
    assert behavior_category("ext_page_dwell") == "dwell"
