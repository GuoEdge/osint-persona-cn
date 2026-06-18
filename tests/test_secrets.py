"""Secrets config tests."""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from osint_toolkit.utils import secrets


def test_save_and_resolve_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    result = secrets.save_secret("deepseek", "sk-test-key-1234")
    assert result["ok"] is True
    assert (tmp_path / "config.yaml").exists()

    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["ai"]["api_key"] == "sk-test-key-1234"
    assert secrets.resolve_secret("deepseek") == "sk-test-key-1234"
    status = secrets.secret_status("deepseek")
    assert status["configured"] is True
    assert status["last4"] == "1234"


def test_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    secrets.save_secret("deepseek", "sk-from-file")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    assert secrets.resolve_secret("deepseek") == "sk-from-env"
    assert secrets.secret_source("deepseek") == "env"


def test_list_secret_statuses():
    items = secrets.list_secret_statuses()
    ids = {i["id"] for i in items}
    assert "deepseek" in ids
    assert "zhihu_openapi" in ids


def test_api_config_secrets(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.utils.secrets.get_data_dir", lambda: tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    listed = client.get("/api/config/secrets")
    assert listed.status_code == 200
    assert any(i["id"] == "deepseek" for i in listed.json()["items"])

    saved = client.post("/api/config/secrets/deepseek", json={"value": "sk-web-test-9999"})
    assert saved.status_code == 200
    assert saved.json()["status"]["configured"] is True
    assert "probe" in saved.json()

    bad = client.post("/api/config/secrets/deepseek", json={"value": ""})
    assert bad.status_code == 400


@pytest.fixture
def client():
    from osint_toolkit.web.app import create_app

    return TestClient(create_app())
