"""采集器注册表 / Collector registry (single source of truth)."""

from __future__ import annotations

from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.collectors.github import GithubCollector
from osint_toolkit.collectors.rss import RssCollector
from osint_toolkit.collectors.site_search import build_site_collector
from osint_toolkit.collectors.source_catalog import (
    get_default_source_ids,
    get_site_search_entries,
    get_source_labels,
    merge_source_priority,
)
from osint_toolkit.collectors.v2ex import V2exCollector
from osint_toolkit.collectors.web import WebCollector
from osint_toolkit.collectors.weixin import WeixinCollector
from osint_toolkit.collectors.zhihu import ZhihuCollector

_NATIVE_COLLECTORS = {
    "zhihu": ZhihuCollector,
    "bilibili": BilibiliCollector,
    "web": WebCollector,
    "v2ex": V2exCollector,
    "github": GithubCollector,
    "rss": RssCollector,
    "weixin": WeixinCollector,
}

COLLECTORS: dict[str, type] = dict(_NATIVE_COLLECTORS)
for _entry in get_site_search_entries():
    _fetch = _entry.get("fetch_content")
    if _fetch is None:
        _fetch = str(_entry.get("category") or "") != "music"
    COLLECTORS[str(_entry["id"])] = build_site_collector(
        str(_entry["id"]),
        str(_entry["domain"]),
        fetch_content=bool(_fetch),
    )

DEFAULT_SEARCH_SOURCES: list[str] = get_default_source_ids()

PROBE_SOURCES: list[str] = ["bilibili", "zhihu", "web", "v2ex", "weixin", "ithome"]


def normalize_sources(sources: list[str] | None, *, profile: str = "default") -> tuple[list[str], list[str]]:
    """解析并校验来源列表，返回 (有效来源, 未知来源)。"""
    from osint_toolkit.utils.config import load_config

    cfg = load_config()
    prof = cfg.get("profiles", {}).get(profile, {})
    requested = list(sources or prof.get("sources") or DEFAULT_SEARCH_SOURCES)
    valid = [s for s in requested if s in COLLECTORS]
    unknown = [s for s in requested if s not in COLLECTORS]
    if not valid:
        valid = list(DEFAULT_SEARCH_SOURCES)
    return valid, unknown


__all__ = [
    "COLLECTORS",
    "DEFAULT_SEARCH_SOURCES",
    "PROBE_SOURCES",
    "merge_source_priority",
    "normalize_sources",
]
