"""DeepSeek 客户端测试 / AI client tests."""


import pytest

from osint_toolkit.ai.client import _merge_extra_body, resolve_api_key


def test_merge_extra_body_disables_thinking_for_v4():
    merged = _merge_extra_body("deepseek-v4-flash", None)
    assert merged == {"thinking": {"type": "disabled"}}


def test_resolve_api_key_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    assert resolve_api_key() == "test-key"


def test_resolve_api_key_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="未配置 DeepSeek API Key"):
        resolve_api_key()
