"""采集器注册表 / Collector registry (single source of truth)."""

from __future__ import annotations

from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.collectors.rss import RssCollector
from osint_toolkit.collectors.v2ex import V2exCollector
from osint_toolkit.collectors.web import WebCollector
from osint_toolkit.collectors.weixin import WeixinCollector
from osint_toolkit.collectors.zhihu import ZhihuCollector

COLLECTORS = {
    "zhihu": ZhihuCollector,
    "bilibili": BilibiliCollector,
    "web": WebCollector,
    "v2ex": V2exCollector,
    "rss": RssCollector,
    "weixin": WeixinCollector,
}

DEFAULT_SEARCH_SOURCES: list[str] = ["zhihu", "bilibili", "web", "weixin"]

PROBE_SOURCES: list[str] = ["bilibili", "zhihu", "web", "v2ex", "weixin"]


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
