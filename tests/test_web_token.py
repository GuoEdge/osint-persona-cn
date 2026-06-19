"""Web API token 中间件测试."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.web.app import create_app
from osint_toolkit.web.web_token import get_or_create_token, reset_token_cache


@pytest.fixture
def authed_client(tmp_path, monkeypatch):
    monkeypatch.delenv("OSINT_DISABLE_WEB_AUTH", raising=False)
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    reset_token_cache()
    token = get_or_create_token()
    client = TestClient(create_app())
    client.headers.update({"X-Osint-Token": token})
    return client


def test_api_without_token_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("OSINT_DISABLE_WEB_AUTH", raising=False)
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    reset_token_cache()
    get_or_create_token()
    client = TestClient(create_app())
    r = client.get("/api/auth/status")
    assert r.status_code == 403


def test_api_with_token_ok(authed_client):
    r = authed_client.get("/api/auth/status")
    assert r.status_code == 200


def test_page_sets_token_meta(authed_client):
    r = authed_client.get("/")
    assert r.status_code == 200
    assert 'name="osint-token"' in r.text
