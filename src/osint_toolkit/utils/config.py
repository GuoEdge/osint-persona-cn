"""配置加载 / Configuration loader."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def get_config_paths() -> list[Path]:
    """按优先级返回配置文件搜索路径。"""
    data_dir = Path(os.environ.get("OSINT_DATA_DIR", Path.home() / ".osint")).expanduser()
    return [
        Path("config/config.yaml").resolve(),
        (data_dir / "config.yaml").resolve(),
    ]


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            return os.environ.get(key, "")

        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


DEFAULT_CONFIG: dict[str, Any] = {
    "ai": {
        "provider": "deepseek",
        "api_key": "${DEEPSEEK_API_KEY}",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "timeout": 120,
    },
    "cookie_sync": {
        "browser": "edge",
        "profile": "Default",
        "domains": [
            "bilibili.com",
            "zhihu.com",
            "baidu.com",
            "bing.com",
            "v2ex.com",
            "juejin.cn",
            "sspai.com",
            "huxiu.com",
            "36kr.com",
        ],
        "auto_sync_before_search": True,
    },
    "http": {
        "timeout": 30,
        "user_agent": "OSINT-Toolkit/0.1.0",
        "proxy": None,
    },
    "output": {
        "default_format": "markdown",
        "reports_dir": "reports",
    },
    "profiles": {
        "default": {"sources": ["zhihu", "bilibili", "web"]},
        "research": {"sources": ["zhihu", "bilibili", "v2ex", "web"], "simulate_persona": True},
    },
    "rules": {
        "boost_authors": [],
        "block_patterns": [],
    },
    "rss_feeds": ["https://sspai.com/feed"],
    "source_packs": {
        "tech_research": ["zhihu", "bilibili", "v2ex", "web", "rss"],
    },
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载配置，合并默认值、配置文件与环境变量。"""
    config = dict(DEFAULT_CONFIG)

    paths: list[Path]
    if path is not None:
        paths = [Path(path)]
    else:
        paths = get_config_paths()

    for config_path in paths:
        if config_path.exists():
            with config_path.open(encoding="utf-8") as f:
                file_cfg = yaml.safe_load(f) or {}
            config = _deep_merge(config, file_cfg)
            break

    return _expand_env(config)


def get_ai_config() -> dict[str, Any]:
    return dict(load_config().get("ai", {}))


def get_cookie_sync_config() -> dict[str, Any]:
    return dict(load_config().get("cookie_sync", {}))
