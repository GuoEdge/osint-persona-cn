"""pytest 全局配置."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_web_auth(monkeypatch):
    monkeypatch.setenv("OSINT_DISABLE_WEB_AUTH", "1")
