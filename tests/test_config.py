"""配置加载测试 / Config loader tests."""

import os

from osint_toolkit.utils.config import _expand_env, get_ai_config, load_config


def test_expand_env():
    os.environ["TEST_OSINT_KEY"] = "secret"
    assert _expand_env("${TEST_OSINT_KEY}") == "secret"


def test_default_ai_config():
    cfg = get_ai_config()
    assert cfg["base_url"] == "https://api.deepseek.com"
    assert cfg["model"] == "deepseek-v4-flash"


def test_load_config_has_cookie_sync():
    cfg = load_config()
    assert "cookie_sync" in cfg
    assert "bilibili.com" in cfg["cookie_sync"]["domains"]
