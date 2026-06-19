"""Calibrated ETA from timing stats."""

from __future__ import annotations

from pathlib import Path

import pytest

from osint_toolkit.pipeline.timing_stats import (
    SearchEtaTracker,
    estimate,
    estimate_collect_remaining,
    planned_search_phases,
    record,
    reset_cache_for_tests,
)


@pytest.fixture(autouse=True)
def _isolated_timing_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_record_and_estimate_ema():
    record("step:dedup", 2.0)
    record("step:dedup", 4.0)
    val = estimate("step:dedup")
    assert 2.0 < val < 4.0


def test_estimate_collect_remaining_uses_per_source_history():
    record("collect:zhihu", 10.0)
    record("collect:web", 4.0)
    tasks = [("zhihu", "a"), ("web", "b"), ("zhihu", "c")]
    remaining = estimate_collect_remaining(tasks, 0, None)
    assert remaining == pytest.approx(24.0, rel=0.05)


def test_estimate_collect_remaining_calibrates_with_observed():
    record("collect:zhihu", 10.0)
    record("collect:web", 10.0)
    tasks = [("zhihu", "a"), ("web", "b"), ("zhihu", "c")]
    observed = [("zhihu", 20.0), ("web", 20.0)]
    remaining = estimate_collect_remaining(tasks, 2, observed)
    assert remaining > 14.0


def test_search_eta_tracker_remaining_decreases_after_steps():
    phases = planned_search_phases(
        discover_aliases=True,
        comment_mine_top=12,
        digest=True,
        no_simulate=False,
    )
    tracker = SearchEtaTracker(
        phases=phases,
        task_meta=[("zhihu", "q1"), ("web", "q1")],
        step_ctx={"comment_mine_top": 12, "digest": True, "no_simulate": False, "summarize_count": 15},
    )
    before = tracker.remaining_sec(current_phase="alias_discover") or 0
    tracker.mark_step_completed("alias_discover", 40_000)
    after = tracker.remaining_sec(current_phase="ai_query_analyze") or 0
    assert after < before


def test_planned_search_phases_respects_flags():
    phases = planned_search_phases(
        discover_aliases=False,
        comment_mine_top=0,
        digest=False,
        no_simulate=True,
    )
    assert "alias_discover" not in phases
    assert "mine_comments" not in phases
    assert "persona_simulate" not in phases
    assert "ai_report" not in phases
    assert phases == ["ai_query_analyze", "ai_source_plan", "collect_all", "dedup", "ai_summarize"]
