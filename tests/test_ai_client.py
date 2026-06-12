"""DeepSeek 客户端测试 / AI client tests."""


import pytest

from osint_toolkit.ai.client import resolve_api_key


def test_resolve_api_key_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    assert resolve_api_key() == "test-key"


def test_resolve_api_key_missing(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="未找到 DeepSeek API Key"):
        resolve_api_key()
