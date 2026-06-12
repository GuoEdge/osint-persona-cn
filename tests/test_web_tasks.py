"""Web search task LRU and disk fallback tests."""

from __future__ import annotations

import json

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.web import tasks


def test_job_lru_trim(monkeypatch):
    monkeypatch.setattr(tasks, "_MAX_JOBS", 2)
    tasks._jobs.clear()
    tasks._jobs["a"] = {"status": "done", "result": None, "error": None}
    tasks._jobs["b"] = {"status": "done", "result": None, "error": None}
    tasks._trim_jobs()
    assert len(tasks._jobs) == 2
    tasks._jobs["c"] = {"status": "done", "result": None, "error": None}
    tasks._trim_jobs()
    assert len(tasks._jobs) == 2
    assert "a" not in tasks._jobs


def test_load_result_from_disk(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.web.tasks.get_data_dir", lambda: tmp_path)
    run_dir = tmp_path / "runs" / "20260101-test"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "20260101-test", "query": "q", "command": "search"}),
        encoding="utf-8",
    )
    item = IntelItem(source="web", type="page", url="https://x", title="t", content="c")
    (run_dir / "03_items_dedup.json").write_text(json.dumps([item.to_dict()]), encoding="utf-8")
    (run_dir / "report.md").write_text("# report", encoding="utf-8")

    loaded = tasks._load_result_from_disk("20260101-test")
    assert loaded is not None
    assert len(loaded["items"]) == 1
    assert loaded["report"] == "# report"
