from __future__ import annotations

from fastapi.testclient import TestClient

from osint_toolkit.web.app import create_app


def test_cloud_status_api():
    client = TestClient(create_app())
    r = client.get("/api/cloud/status")
    assert r.status_code == 200
    assert "provider" in r.json()
    assert "health" in r.json()


def test_cloud_sync_api_requires_vault(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.cloud.sync_cloud",
        lambda: {"ready": False},
    )
    r = client.post("/api/cloud/sync", json={})
    assert r.status_code == 400


def test_cloud_init_api(monkeypatch, tmp_path):
    client = TestClient(create_app())
    captured: dict = {}

    def _fake_init(**kwargs):
        captured.update(kwargs)
        return {"ready": True, "ok": True, "vault_path": str(tmp_path / "vault")}

    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.cloud.init_cloud",
        _fake_init,
    )
    r = client.post(
        "/api/cloud/init",
        json={
            "provider": "onedrive_folder",
            "onedrive_root": str(tmp_path / "OneDrive"),
            "vault_name": "Knowledge",
            "sync_mode": "manual",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert captured["vault_name"] == "Knowledge"
    assert captured["sync_mode"] == "manual"


def test_cloud_conflicts_api(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.cloud.list_cloud_conflicts",
        lambda limit=50: [{"item_id": "x", "conflict_path": "Inbox/x.conflict.md"}],
    )
    r = client.get("/api/cloud/conflicts")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_cloud_reindex_api(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.cloud.reindex_cloud",
        lambda: {"ready": True, "reindexed_items": 3},
    )
    r = client.post("/api/cloud/reindex")
    assert r.status_code == 200
    assert r.json()["reindexed_items"] == 3
