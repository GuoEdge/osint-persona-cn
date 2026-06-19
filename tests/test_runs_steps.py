"""Run step listing tests."""

from __future__ import annotations

import json

from osint_toolkit.pipeline.progress import init_progress, update_progress
from osint_toolkit.services.runs import list_run_steps, list_runs, show_run, summarize_run


def _patch_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.pipeline.progress.get_data_dir", lambda: tmp_path)


def test_list_run_steps_from_numbered_files(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    run_id = "20260101-120000-00000001"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "01_alias_discover.json").write_text(
        '{"step":"alias_discover","status":"ok","duration_ms":120}',
        encoding="utf-8",
    )
    steps = list_run_steps(run_id)
    assert len(steps) == 1
    assert steps[0]["step"] == "alias_discover"


def test_list_run_steps_fallback_progress(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    run_id = "20260101-120000-00000002"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "status": "running", "steps": []}),
        encoding="utf-8",
    )
    init_progress(run_id)
    update_progress(
        run_id,
        "collect_all",
        detail="采集中",
        mark_completed={"step": "alias_discover", "status": "ok", "duration_ms": 50, "summary": "3 aliases"},
    )
    steps = list_run_steps(run_id)
    assert any(s.get("step") == "alias_discover" for s in steps)
    assert any(s.get("step") == "collect_all" and s.get("status") == "running" for s in steps)


def test_show_run_includes_progress(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    run_id = "20260101-120000-00000003"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "status": "running", "query": "glm5.2"}),
        encoding="utf-8",
    )
    init_progress(run_id)
    update_progress(run_id, "collect_all", detail="B站 · glm5.2")
    detail = show_run(run_id)
    assert detail["progress"]["phase"] == "collect_all"
    assert detail["query"] == "glm5.2"
    assert detail["summary"]["query"] == "glm5.2"


def test_summarize_run_list_fields(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    run_id = "20260101-120000-00000004"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "done",
                "query": "测试话题",
                "command": "search",
                "sources": ["zhihu", "bilibili"],
                "item_count": 3,
                "started_at": "2026-06-19T02:00:00+00:00",
                "finished_at": "2026-06-19T02:05:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "03_items_dedup.json").write_text("[{}, {}, {}]", encoding="utf-8")
    (run_dir / "report.md").write_text("# report", encoding="utf-8")
    summary = summarize_run(run_id)
    assert summary["item_count"] == 3
    assert summary["has_report"] is True
    assert summary["duration_sec"] == 300
    listed = list_runs(limit=5)
    assert listed[0]["query"] == "测试话题"
