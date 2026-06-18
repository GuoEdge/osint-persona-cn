"""Digest API tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_digest_daily_hot_list_param(client):
    with patch("osint_toolkit.services.digest.get_daily_digest") as mock_digest:
        mock_digest.return_value = "# 简报"
        resp = client.get("/api/digest/daily?hot_list=0")
        assert resp.status_code == 200
        mock_digest.assert_called_once_with(use_ai=False, no_ai=False, include_hot_list=False)


def test_workspace_has_research_tree_toolbar(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "research-tree-toolbar" in resp.text
    assert "btn-research-new" in resp.text
