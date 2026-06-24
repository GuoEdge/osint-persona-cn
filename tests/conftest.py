"""pytest 全局配置."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch):
    from osint_toolkit.ai.steering import reset_directives_cache
    from osint_toolkit.auth.cookie_sync import reset_cookie_cache
    from osint_toolkit.utils.config import reset_config_cache

    reset_config_cache()
    reset_cookie_cache()
    reset_directives_cache()
    monkeypatch.setenv("OSINT_DISABLE_WEB_AUTH", "1")
    yield
