"""Watch and research tree coordination tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from osint_toolkit.research.tree import create_tree, mark_broken_run_for_trees
from osint_toolkit.services.watch import should_run_watch
from osint_toolkit.utils.config import DEFAULT_CONFIG


def test_default_config_has_watches():
    assert DEFAULT_CONFIG.get("watches") == []


def test_should_run_watch_interval(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.services.watch.get_data_dir", lambda: tmp_path)
    watch = {"id": "w1", "schedule": "6h", "enabled": True}
    assert should_run_watch(watch) is True

    state_dir = tmp_path / "watches" / "w1"
    state_dir.mkdir(parents=True, exist_ok=True)
    recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    (state_dir / "last_run.json").write_text(
        json.dumps({"run_at": recent, "urls": []}),
        encoding="utf-8",
    )
    assert should_run_watch(watch) is False


def test_mark_broken_run_for_trees(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.research.tree.get_data_dir", lambda: tmp_path)
    tree = create_tree("test", query="q")
    run_id = "run-abc"
    from osint_toolkit.research.tree import attach_search_node

    attach_search_node(tree["id"], parent_node_id=tree["nodes"][0]["id"], run_id=run_id, query="q")
    updated = mark_broken_run_for_trees(run_id)
    assert updated == 1


def test_mark_stale_running_clears_progress(tmp_path, monkeypatch):
    from osint_toolkit.services.run_session import mark_stale_running_as_interrupted

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_dir = tmp_path / "runs" / "20260101-120000-c1d2e3f4"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "20260101-120000-c1d2e3f4", "status": "running", "started_at": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    (run_dir / "progress.json").write_text('{"phase": "collect_all"}', encoding="utf-8")
    touched = mark_stale_running_as_interrupted()
    assert "20260101-120000-c1d2e3f4" in touched
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "interrupted"
    assert not (run_dir / "progress.json").exists()


def test_load_run_collect_issues(tmp_path, monkeypatch):
    from osint_toolkit.services.runs import _load_run_collect_issues, show_run

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-d1e2f3a4"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "status": "done", "query": "q"}),
        encoding="utf-8",
    )
    step = {
        "step": "collect_all",
        "status": "ok",
        "data": {
            "source_warnings": [{"source": "github", "warning": "rate limit", "query": "q"}],
            "source_errors": [{"source": "rss", "error": "timeout", "query": "q"}],
        },
    }
    (run_dir / "02_collect_all.json").write_text(json.dumps(step), encoding="utf-8")
    warns, errs = _load_run_collect_issues(run_dir)
    assert len(warns) == 1
    assert len(errs) == 1
    detail = show_run(run_id)
    assert detail["source_warnings"][0]["source"] == "github"
    assert detail["source_errors"][0]["source"] == "rss"
