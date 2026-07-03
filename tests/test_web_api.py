"""Web API 测试."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_page_workspace(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "搜罗" in r.text
    assert "nav_groups" not in r.text  # rendered, not variable name
    assert "个人情报" in r.text


def test_api_health_sets_cookie(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("ok") == "true"
    # Cookie may be set when web auth is enabled (default in tests)
    if "osint_token" in r.cookies:
        assert len(r.cookies["osint_token"]) > 8


def test_page_routes(client):
    for path in ["/save", "/knowledge", "/digest", "/persona", "/ingest", "/behavior", "/runs", "/ai", "/settings"]:
        r = client.get(path)
        assert r.status_code == 200, path


def test_auth_status(client):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data


def test_setup_status(client):
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert "steps" in data
    assert "ready" in data


def test_ingest_capabilities(client):
    r = client.get("/api/ingest/capabilities")
    assert r.status_code == 200
    assert "items" in r.json()


def test_auth_paths(client):
    r = client.get("/api/auth/paths")
    assert r.status_code == 200
    assert "data_dir" in r.json()


def test_knowledge_items(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    r = client.get("/api/knowledge/items?limit=5")
    assert r.status_code == 200
    assert "items" in r.json()


def test_runs_list(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
    r = client.get("/api/runs")
    assert r.status_code == 200
    assert r.json()["runs"] == []


def test_search_async(client, monkeypatch):
    async def fake_search(**kwargs):
        return {
            "run_id": kwargs.get("run_id", "test-run"),
            "items": [
                IntelItem(source="web", type="test", url="https://x.com", title="Test", content="c"),
            ],
            "report": "",
            "report_path": None,
            "simulations": [],
            "run_dir": "/tmp",
        }

    async def fake_execute(run_id, **kwargs):
        from osint_toolkit.web import tasks

        tasks._jobs[run_id] = {"status": "done", "result": await fake_search(**kwargs, run_id=run_id), "error": None}

    def fake_start(**kwargs):
        from osint_toolkit.web import tasks

        run_id = "20260101-120000-abcd1234"
        tasks._jobs[run_id] = {"status": "running", "result": None, "error": None}
        import asyncio

        asyncio.get_event_loop().create_task(fake_execute(run_id, **kwargs))
        return {"run_id": run_id, "status": "running"}

    monkeypatch.setattr("osint_toolkit.web.routes.api.start_search_job", fake_start)

    r = client.post("/api/search", json={"query": "test", "sources": ["web"], "no_ai": True})
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert "run_id" in r.json()


def test_ai_directives(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.ai.steering.directives_path", lambda: tmp_path / "ai_directives.yaml")
    r = client.get("/api/ai/directives")
    assert r.status_code == 200
    body = {"data": {"hard_constraints": ["test"], "soft_preferences": {}}}
    r2 = client.put("/api/ai/directives", json=body)
    assert r2.status_code == 200


def test_ai_prompts(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.ai.prompt_loader.get_data_dir", lambda: tmp_path)
    r = client.get("/api/ai/prompts")
    assert r.status_code == 200
    assert "prompts" in r.json()


def test_feedback(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.feedback.store.get_data_dir", lambda: tmp_path)
    r = client.post(
        "/api/feedback",
        json={"target_id": "item-1", "rating": "useful", "run_id": "run-1"},
    )
    assert r.status_code == 200
    assert "entry" in r.json()

    r2 = client.get("/api/feedback/recent?target_ids=item-1")
    assert r2.status_code == 200
    assert r2.json()["feedback"]["item:item-1"] == "useful"


def test_sim_override_persists_current_simulation_artifact(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-abcd1234"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text('{"status":"done"}', encoding="utf-8")
    (run_dir / "simulations.json").write_text(
        json.dumps([
            {"item_id": "item-1", "interest": "skip", "confidence": 0.99, "verdict": "AI 判定无价值"}
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "items_final.json").write_text(
        json.dumps(
            [
                {
                    "id": "item-1",
                    "source": "web",
                    "type": "snippet",
                    "title": "t",
                    "url": "https://x.test",
                    "signals": {"relevance": 0.1, "fold_reason": "低相关"},
                }
            ]
        ),
        encoding="utf-8",
    )

    r = client.post(
        f"/api/runs/{run_id}/sim-override",
        json={"item_id": "item-1", "interest": "interested"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["updated_simulation"] is True
    sims = json.loads((run_dir / "simulations.json").read_text(encoding="utf-8"))
    assert sims[0]["interest"] == "interested"
    assert sims[0]["overridden"] is True
    assert sims[0]["ai_original"]["interest"] == "skip"
    items = json.loads((run_dir / "items_final.json").read_text(encoding="utf-8"))
    assert items[0]["signals"]["relevance"] == 0.7
    assert "fold_reason" not in items[0]["signals"]


def test_sim_override_returns_failure_when_item_missing(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-abcd1234"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "simulations.json").write_text('[{"item_id":"other"}]', encoding="utf-8")

    r = client.post(
        f"/api/runs/{run_id}/sim-override",
        json={"item_id": "item-1", "interest": "skip"},
    )

    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_sim_override_rejects_invalid_interest(client):
    r = client.post(
        "/api/runs/20260101-120000-abcd1234/sim-override",
        json={"item_id": "item-1", "interest": "bad"},
    )

    assert r.status_code == 422


def test_aicu_status(client, monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.utils.config.load_config",
        lambda: {"ingest": {"aicu_enabled": True}},
    )
    r = client.get("/api/ingest/aicu-status")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_ingest_recognition_api(client):
    r = client.get("/api/ingest/recognition")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert "recent" in body
    assert "inventory" in body


def test_run_detail_rejects_invalid_run_id(client):
    r = client.get("/api/runs/bad%run")
    assert r.status_code == 400


def test_run_detail_skips_list_artifacts(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_dir = tmp_path / "runs" / "20260101-120000-abcd1234"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        '{"run_id":"20260101-120000-abcd1234","command":"search","query":"x","steps":[]}',
        encoding="utf-8",
    )
    (run_dir / "01_collect_all.json").write_text('{"step":"collect_all","status":"ok"}', encoding="utf-8")
    (run_dir / "items_raw.json").write_text("[{}]", encoding="utf-8")
    r = client.get("/api/runs/20260101-120000-abcd1234")
    assert r.status_code == 200
    assert len(r.json()["steps"]) == 1


def test_sse_scan_reemits_changed_step_file(tmp_path, monkeypatch):
    from osint_toolkit.web.routes.api import _scan_run_dir

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-abcd1234"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    step_path = run_dir / "01_demo.json"
    step_path.write_text('{"step":"demo","status":"running"}', encoding="utf-8")

    first = _scan_run_dir(run_id, {})
    assert first["new_steps"][0]["data"]["status"] == "running"

    step_path.write_text('{"step":"demo","status":"ok"}', encoding="utf-8")
    stat = step_path.stat()
    os.utime(step_path, ns=(stat.st_atime_ns + 1_000_000, stat.st_mtime_ns + 1_000_000))
    second = _scan_run_dir(run_id, first["new_file_versions"])

    assert second["new_steps"][0]["data"]["status"] == "ok"
