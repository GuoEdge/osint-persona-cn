"""Runs list must stay fast with large artifact files."""

from __future__ import annotations

import json
import time

from osint_toolkit.services.runs import list_runs


def test_list_runs_skips_huge_items_json(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-1a2b3c4d"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "status": "done", "query": "x", "item_count": 42}),
        encoding="utf-8",
    )
    huge = "[{}]" + ",{}" * 50000
    (run_dir / "05_items_dedup.json").write_text(huge, encoding="utf-8")
    started = time.perf_counter()
    rows = list_runs(limit=5)
    elapsed = time.perf_counter() - started
    assert rows[0]["item_count"] == 42
    assert elapsed < 2.0
