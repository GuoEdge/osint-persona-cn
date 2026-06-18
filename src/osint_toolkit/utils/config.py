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
        "persona_inject": True,
        "dwell_save_no_ai": True,
        "auto_persona_rebuild_threshold": 50,
        "auto_persona_rebuild": "auto",
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
            "sogou.com",
            "weixin.sogou.com",
            "mp.weixin.qq.com",
        ],
        "auto_sync_before_search": True,
    },
    "http": {
        "timeout": 30,
        "user_agent": "OSINT-Toolkit/0.1.0",
        "proxy": None,
    },
    "zhihu": {
        "openapi": {
            "enabled": True,
            "base_url": "https://developer.zhihu.com",
            "access_secret": "${ZHIHU_ACCESS_SECRET}",
            "prefer_search": True,
            "merge_search_v3": True,
            "search_count": 10,
            "hot_list_count": 30,
            "features": {
                "search": True,
                "hot_list": True,
                "global_search": False,
            },
        },
    },
    "bilibili": {
        "use_sdk": True,
        "sdk_client": "httpx",
        "enable_bili_ticket": False,
        "features": {
            "search": True,
            "comments": True,
            "subtitle": True,
            "danmaku": True,
            "ingest_history": True,
            "ingest_favorites": True,
            "ingest_followings": True,
            "my_comments": True,
        },
        "comments_fetch_limit": 60,
        "danmaku_max_lines": 800,
        "search": {
            "types": ["video", "article", "bili_user"],
            "order_video": "totalrank",
            "order_article": "totalrank",
            "order_user": "fans",
            "time_start": None,
            "time_end": None,
            "video_zone_tid": None,
            "time_range_minutes": -1,
            "serp_fallback": True,
            "legacy_wbi_fallback": True,
        },
    },
    "output": {
        "default_format": "markdown",
        "reports_dir": "reports",
    },
    "profiles": {
        "default": {"sources": ["zhihu", "bilibili", "web", "weixin"]},
        "full": {"sources": ["zhihu", "bilibili", "web", "v2ex", "rss", "weixin"]},
        "research": {"sources": ["zhihu", "bilibili", "v2ex", "web"], "simulate_persona": True},
        "zhihu_deep": {"sources": ["zhihu"], "simulate_persona": False},
    },
    "rules": {
        "boost_authors": [],
        "block_patterns": [],
    },
    "search": {
        "max_expanded_queries": 8,
        "per_query_limit_ratio": 0.6,
        "include_slurs": True,
        "comment_mine_top": 12,
        "zhihu_aggressive": True,
        "zhihu_search_types": ["general", "content"],
        "zhihu_search_per_type": 40,
        "zhihu_search_pages": 5,
        "zhihu_expand_answers": True,
        "zhihu_expand_from_answers": True,
        "zhihu_expand_question_top": 15,
        "zhihu_answers_per_question": 50,
        "zhihu_comment_limit": 120,
        "zhihu_comment_pages": 8,
        "zhihu_comment_mine_top": 12,
        "zhihu_fetch_child_comments": True,
        "zhihu_child_comment_roots": 10,
        "zhihu_child_comment_limit": 20,
        "zhihu_per_query_limit_min": 20,
        "discover_aliases": True,
        "discover_probe_limit": 5,
        "discover_sources": ["bilibili", "zhihu", "web", "v2ex", "weixin"],
        "persist_discovered_aliases": True,
        "rule_expand_enabled": True,
        "rule_expand_min_existing": 2,
        "rule_nickname_suffixes": False,
        "serp": {
            "primary": "auto",
            "strategy": "fallback",
            "fallbacks": ["duckduckgo_html", "bing_html", "baidu_html", "sogou_html"],
            "merge_min_hits": 5,
            "bing_api_key": "${BING_SEARCH_API_KEY}",
            "serpapi_key": "${SERPAPI_KEY}",
            "searxng_base_url": "${SEARXNG_BASE_URL}",
            "duckduckgo_region": "cn-zh",
            "provider_delay_ms": 300,
            "enabled_providers": [],
            "site_searches": ["github.com", "bilibili.com", "zhihu.com"],
            "web_fetch_content": True,
            "web_fetch_top": 5,
        },
        "weixin": {
            "resolve_mp_urls": True,
            "resolve_top": 3,
            "playwright_on_block": True,
            "serp_fallback": True,
        },
    },
    "extension": {
        "dwell_save_enabled": True,
        "dwell_save_ms": 90000,
    },
    "sync": {
        "prefer_server_api": True,
        "browser_sync_after_api": True,
        "browser_sync_enabled": True,
        "browser_sync_mode": "auto",
        "browser_sync_cdp_url": "http://127.0.0.1:9222",
        "browser_sync_headless": True,
        "max_pages_per_run": 6,
        "scroll_rounds": 4,
        "scroll_interval_ms": 1500,
        "initial_wait_ms": 3000,
        "page_gap_ms": 8000,
        "probe_pages_enabled": True,
        "aicu_enabled": False,
        "browser_history_enabled": True,
        "browser_history_since_days": 90,
    },
    "ingest": {
        "aicu_enabled": False,
        "aicu_page_size": 100,
        "aicu_delay_sec": 1.5,
        "browser_sync_enabled": True,
        "browser_sync_after_api": True,
        "browser_sync_mode": "auto",
        "browser_sync_cdp_url": "http://127.0.0.1:9222",
        "browser_sync_headless": True,
        "browser_sync_max_pages": 6,
        "browser_sync_page_gap_ms": 8000,
        "browser_sync_scroll_rounds": 4,
        "browser_sync_scroll_interval_ms": 1500,
        "browser_sync_initial_wait_ms": 3000,
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

    return _expand_env(config)


def get_ai_config() -> dict[str, Any]:
    return dict(load_config().get("ai", {}))


def get_cookie_sync_config() -> dict[str, Any]:
    return dict(load_config().get("cookie_sync", {}))


def get_search_config() -> dict[str, Any]:
    return dict(load_config().get("search", {}))


def get_serp_config() -> dict[str, Any]:
    search = get_search_config()
    serp = dict(search.get("serp") or {})
    defaults = dict(DEFAULT_CONFIG.get("search", {}).get("serp") or {})
    merged = dict(defaults)
    merged.update(serp)
    return merged


def get_weixin_config() -> dict[str, Any]:
    search = get_search_config()
    weixin = dict(search.get("weixin") or {})
    defaults = dict(DEFAULT_CONFIG.get("search", {}).get("weixin") or {})
    merged = dict(defaults)
    merged.update(weixin)
    return merged


def get_extension_sync_config() -> dict[str, Any]:
    return load_sync_config()


def load_sync_config() -> dict[str, Any]:
    """合并 sync 段与 legacy extension.sync / ingest.browser_sync_* 键。"""
    cfg = load_config()
    sync = dict(cfg.get("sync") or {})
    ext_sync = (cfg.get("extension") or {}).get("sync") or {}
    ingest = cfg.get("ingest") or {}
    legacy_map = {
        "prefer_server_api": ext_sync.get("prefer_server_api"),
        "probe_pages_enabled": ext_sync.get("probe_pages_enabled"),
        "scroll_rounds": ext_sync.get("scroll_rounds") or ingest.get("browser_sync_scroll_rounds"),
        "scroll_interval_ms": ext_sync.get("scroll_interval_ms") or ingest.get("browser_sync_scroll_interval_ms"),
        "initial_wait_ms": ext_sync.get("initial_wait_ms") or ingest.get("browser_sync_initial_wait_ms"),
        "page_gap_ms": ext_sync.get("page_gap_ms") or ingest.get("browser_sync_page_gap_ms"),
        "max_pages_per_run": ext_sync.get("max_pages_per_run") or ingest.get("browser_sync_max_pages"),
        "browser_sync_after_api": ingest.get("browser_sync_after_api"),
        "browser_sync_enabled": ingest.get("browser_sync_enabled"),
        "browser_sync_mode": ingest.get("browser_sync_mode"),
        "browser_sync_cdp_url": ingest.get("browser_sync_cdp_url"),
        "browser_sync_headless": ingest.get("browser_sync_headless"),
        "aicu_enabled": ingest.get("aicu_enabled"),
    }
    for key, val in legacy_map.items():
        if val is not None and key not in sync:
            sync[key] = val
    # aicu：sync 与 ingest 任一为 true 即启用
    sync["aicu_enabled"] = bool(sync.get("aicu_enabled", False) or ingest.get("aicu_enabled", False))
    return sync


def get_aicu_enabled() -> bool:
    return bool(load_sync_config().get("aicu_enabled", False))


def get_browser_sync_config() -> dict[str, Any]:
    sync = load_sync_config()
    return {
        "browser_sync_enabled": sync.get("browser_sync_enabled", True),
        "browser_sync_after_api": sync.get("browser_sync_after_api", True),
        "browser_sync_mode": sync.get("browser_sync_mode", "auto"),
        "browser_sync_cdp_url": sync.get("browser_sync_cdp_url", "http://127.0.0.1:9222"),
        "browser_sync_headless": sync.get("browser_sync_headless", True),
        "browser_sync_max_pages": sync.get("max_pages_per_run", 6),
        "browser_sync_page_gap_ms": sync.get("page_gap_ms", 8000),
        "browser_sync_scroll_rounds": sync.get("scroll_rounds", 4),
        "browser_sync_scroll_interval_ms": sync.get("scroll_interval_ms", 1500),
        "browser_sync_initial_wait_ms": sync.get("initial_wait_ms", 3000),
    }
