"""Run delete, cleanup, and report export tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from osint_toolkit.services.runs import cleanup_runs, delete_run, get_run_report_export
from osint_toolkit.web.app import create_app


def _patch_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)


def _write_run(tmp_path, run_id: str, *, status: str = "done", query: str = "test", with_report: bool = False):
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    started = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    finished = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": status,
                "query": query,
                "started_at": started,
                "finished_at": finished,
            }
        ),
        encoding="utf-8",
    )
    if with_report:
        (run_dir / "report.md").write_text("# hello", encoding="utf-8")


def test_delete_run(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    run_id = "20260101-120000-dead0001"
    _write_run(tmp_path, run_id)
    delete_run(run_id)
    assert not (tmp_path / "runs" / run_id).exists()


def test_cleanup_runs_respects_keep_latest(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    ids = ["20260101-120000-aaa00001", "20260101-120000-aaa00002", "20260101-120000-aaa00003"]
    for i, run_id in enumerate(ids):
        _write_run(tmp_path, run_id, query=f"q{i}")
    result = cleanup_runs(older_than_days=0, keep_latest=2, dry_run=True)
    assert result["count"] == 1


def test_get_run_report_export(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    run_id = "20260101-120000-ee0e0001"
    _write_run(tmp_path, run_id, query="话题A", with_report=True)
    content, name = get_run_report_export(run_id)
    assert content == "# hello"
    assert name.endswith(".md")
    assert run_id in name


def test_api_run_delete_and_report_download(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    _write_run(tmp_path, "20260101-120000-abcd1234", with_report=True)
    client = TestClient(create_app())
    dl = client.get("/api/runs/20260101-120000-abcd1234/report/download")
    assert dl.status_code == 200
    assert "# hello" in dl.text
    assert "attachment" in dl.headers.get("content-disposition", "")
    rm = client.delete("/api/runs/20260101-120000-abcd1234")
    assert rm.status_code == 200
    assert not (tmp_path / "runs" / "20260101-120000-abcd1234").exists()


def test_api_runs_cleanup_dry_run(tmp_path, monkeypatch):
    _patch_data_dir(monkeypatch, tmp_path)
    _write_run(tmp_path, "20260101-120000-old00001")
    client = TestClient(create_app())
    r = client.post("/api/runs/cleanup", json={"older_than_days": 1, "keep_latest": 0, "dry_run": True})
    assert r.status_code == 200
    assert r.json()["count"] >= 1
    assert (tmp_path / "runs" / "20260101-120000-old00001").exists()
