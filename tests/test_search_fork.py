"""Search fork parameter merge tests."""

from __future__ import annotations

import json

from osint_toolkit.services.search_fork import build_fork_search_params


def test_fork_inherits_query_and_sets_fork_id(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-a1b2c3d4"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "request.json").write_text(
        json.dumps({"query": "MCP", "sources": ["zhihu"], "limit": 5}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "query": "MCP", "status": "done"}, ensure_ascii=False),
        encoding="utf-8",
    )
    merged = build_fork_search_params(run_id, {"query": "MCP 深化"})
    assert merged["query"] == "MCP 深化"
    assert merged["fork_from_run_id"] == run_id
    assert merged.get("sources") == ["zhihu"]
