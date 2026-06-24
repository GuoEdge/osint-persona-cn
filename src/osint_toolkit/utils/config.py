"""配置加载 / Configuration loader."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")

_ENV_DEP_KEYS: frozenset[str] = frozenset(
    {
        "OSINT_DATA_DIR",
        "DEEPSEEK_API_KEY",
        "ZHIHU_ACCESS_SECRET",
        "BING_SEARCH_API_KEY",
        "SERPAPI_KEY",
        "SEARXNG_BASE_URL",
    }
)

_CONFIG_CACHE: dict[str, Any] | None = None
_CONFIG_KEY: tuple | None = None


def reset_config_cache() -> None:
    """清除 load_config 缓存（测试 / 写入后调用）。"""
    global _CONFIG_CACHE, _CONFIG_KEY
    _CONFIG_CACHE = None
    _CONFIG_KEY = None


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
            "min_request_interval_sec": 1.0,
            "rate_limit_retry_max": 4,
            "rate_limit_retry_base_sec": 1.5,
            "features": {
                "search": True,
                "hot_list": True,
                "global_search": True,
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
            "ingest_likes": True,
            "my_comments": True,
        },
        "comments_fetch_limit": 60,
        "danmaku_max_lines": 800,
        "subtitle_prefer": "ai_first",
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
        "default": {
            "label": "默认",
            "sources": ["zhihu", "bilibili", "web", "weixin"],
        },
        "full": {
            "label": "全量",
            "sources": ["zhihu", "bilibili", "web", "v2ex", "rss", "weixin"],
        },
        "research": {
            "label": "深度研究",
            "sources": ["zhihu", "bilibili", "v2ex", "web"],
            "simulate_persona": True,
        },
        "zhihu_deep": {
            "label": "知乎深挖",
            "sources": ["zhihu"],
            "simulate_persona": False,
        },
    },
    "rules": {
        "boost_authors": [],
        "block_patterns": [],
    },
    "search": {
        "max_concurrent_searches": 2,
        "max_queued_searches": 20,
        "sse_max_lifetime_sec": 3600,
        "zhihu_global_collect_sem": 2,
        "max_expanded_queries": 5,
        "max_expanded_queries_strict": 3,
        "max_expanded_queries_narrow": 4,
        "strict_mode": False,
        "skip_alias_discover_narrow": True,
        "max_collect_tasks": 18,
        "collect_timeout_sec": 900,
        "collect_early_stop_items": 45,
        "min_summarize_relevance": 0.25,
        "ai_relevance_refine": True,
        "ai_relevance_refine_top": 36,
        "ai_relevance_borderline_low": 0.12,
        "ai_relevance_borderline_high": 0.58,
        "ai_relevance_blend": 0.35,
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
        "zhihu_answers_hot_top": 10,
        "zhihu_answers_recent_top": 4,
        "zhihu_answers_per_question": 14,
        "zhihu_comment_limit": 120,
        "zhihu_comment_pages": 8,
        "zhihu_comment_mine_top": 12,
        "zhihu_openapi_deep_fetch_top": 5,
        "zhihu_openapi_deep_fetch_min_relevance": 0.35,
        "zhihu_openapi_deep_fetch_max_snippet_len": 400,
        "zhihu_deep_fetch_ai": True,
        "zhihu_deep_fetch_skip_relevance": 0.12,
        "zhihu_fetch_child_comments": True,
        "zhihu_child_comment_roots": 10,
        "zhihu_child_comment_limit": 20,
        "zhihu_per_query_limit_min": 20,
        "source_auto_route": {
            "mode": "gentle",
            "strong_threshold": 45,
            "weak_threshold": 12,
            "min_active_sources": 3,
            "max_active_sources": 12,
            "max_auto_enable": 6,
            "protect_core": True,
            "protect_user_selected": True,
            "core_sources": ["zhihu", "web"],
            "auto_enable_scope": "catalog",
            "ai_blend": 0.55,
            "ai_blend_cryptic": 0.78,
            "cryptic_rule_max": 35,
            "cryptic_strong_threshold": 38,
            "ai_auto_enable_min": 55,
            "ai_strong_tier_min": 65,
        },
        "discover_aliases": True,
        "discover_probe_limit": 5,
        "discover_sources": ["bilibili", "zhihu", "web", "v2ex", "weixin"],
        "persist_discovered_aliases": True,
        "foreign_expand": {
            "enabled": "auto",
            "max_foreign_queries": 3,
            "intl_probe_enabled": "auto",
            "discover_sources_intl": ["github", "web"],
        },
        "rule_expand_enabled": True,
        "rule_expand_min_existing": 2,
        "rule_nickname_suffixes": False,
        "ai_summarize_top": 15,
        "ai_summarize_extended": 35,
        "persona_sim_top": 20,
        "site_fetch_content_top": 3,
        "thread_expand_top": 5,
        "serp": {
            "primary": "auto",
            "strategy": "auto",
            "fallbacks": ["bing_html", "sogou_html", "duckduckgo_html", "baidu_html"],
            "merge_min_hits": 5,
            "parallel_html": True,
            "exclude_ads": True,
            "provider_weights": {
                "bing_html": 4,
                "sogou_html": 2,
                "duckduckgo_html": 2,
                "baidu_html": 1,
            },
            "cache_ttl_sec": 600,
            "html_retry_count": 1,
            "bing_api_key": "${BING_SEARCH_API_KEY}",
            "serpapi_key": "${SERPAPI_KEY}",
            "searxng_base_url": "${SEARXNG_BASE_URL}",
            "duckduckgo_region": "cn-zh",
            "provider_delay_ms": 300,
            "enabled_providers": [],
            "site_searches": [
                "github.com",
                "bilibili.com",
                "zhihu.com",
                "ithome.com",
                "sspai.com",
                "juejin.cn",
                "solidot.org",
                "36kr.com",
                "huxiu.com",
                "caixin.com",
                "thepaper.cn",
                "ifeng.com",
                "smzdm.com",
                "chiphell.com",
                "gcores.com",
                "ngabbs.com",
                "weibo.com",
                "okjike.com",
                "tieba.baidu.com",
                "jianshu.com",
                "xiaohongshu.com",
                "maimai.cn",
                "reddit.com",
                "news.ycombinator.com",
                "music.163.com",
                "y.qq.com",
                "kugou.com",
                "music.migu.cn",
                "douban.com",
                "xiaoyuzhoufm.com",
                "ximalaya.com",
            ],
            "web_fetch_content": True,
            "web_fetch_top": 5,
        },
        "weixin": {
            "resolve_mp_urls": True,
            "resolve_top": 3,
            "fetch_read_count_top": 10,
            "fetch_read_delay_ms": 400,
            "min_read_count": 500,
            "min_snippet_chars": 40,
            "drop_unknown_read_count": False,
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
    "watches": [],
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载配置，合并默认值、配置文件与环境变量。"""
    global _CONFIG_CACHE, _CONFIG_KEY

    paths: list[Path]
    if path is not None:
        paths = [Path(path)]
    else:
        paths = get_config_paths()

    if path is None:
        file_key = tuple((str(p), p.stat().st_mtime_ns) for p in paths if p.exists())
        env_key = tuple(sorted((k, os.environ[k]) for k in _ENV_DEP_KEYS if k in os.environ))
        key = file_key + env_key
        if _CONFIG_CACHE is not None and key == _CONFIG_KEY:
            return dict(_CONFIG_CACHE)
    else:
        key = None

    config = dict(DEFAULT_CONFIG)
    for config_path in paths:
        if config_path.exists():
            with config_path.open(encoding="utf-8") as f:
                file_cfg = yaml.safe_load(f) or {}
            config = _deep_merge(config, file_cfg)

    result = _expand_env(config)
    if path is None:
        _CONFIG_CACHE = result
        _CONFIG_KEY = key
    return dict(result)


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
