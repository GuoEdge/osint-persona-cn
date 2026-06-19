"""搜罗模式（profile）目录 / Search profile catalog for UI and docs."""

from __future__ import annotations

from typing import Any

from osint_toolkit.collectors.registry import DEFAULT_SEARCH_SOURCES
from osint_toolkit.collectors.source_catalog import get_source_labels
from osint_toolkit.utils.config import load_config

# 内置说明：与用户 config profiles 合并，config 可覆盖 label / summary / detail / sources
_BUILTIN: dict[str, dict[str, Any]] = {
    "default": {
        "label": "默认",
        "summary": "日常话题搜罗：知乎、B站、网页与微信，广度与速度均衡。",
        "detail": (
            "启用信源：知乎、B站、网页搜索（Bing/SERP）、微信（搜狗，含阅读量过滤）。"
            "适用大多数人物、事件、概念速览。Pipeline 与其他模式相同（别名发现、去重、AI 摘要、可选报告、B站热评挖掘）。"
            "画像模拟由下方「跳过画像模拟」勾选决定。"
        ),
        "sources": ["zhihu", "bilibili", "web", "weixin"],
    },
    "full": {
        "label": "全量",
        "summary": "在默认基础上增加 V2EX 与 RSS，信源最全、耗时更长。",
        "detail": (
            "启用信源：知乎、B站、网页、微信、V2EX、RSS（条目来自 config 中 rss_feeds）。"
            "适合需要社区讨论与技术站点、同时关注订阅源动态时使用。"
            "能力与默认模式相同，仅并行请求更多，搜罗与 AI 阶段可能更慢。"
        ),
        "sources": ["zhihu", "bilibili", "web", "v2ex", "rss", "weixin"],
    },
    "research": {
        "label": "深度研究",
        "summary": "偏社区与技术站点，不含微信；默认开启画像模拟。",
        "detail": (
            "启用信源：知乎、B站、V2EX、网页（不含微信与 RSS，减少公众号低质文干扰）。"
            "适合技术课题、产品调研、社区舆情。切换到此模式会自动取消「跳过画像模拟」（需已构建心智画像）。"
            "其余 AI 能力与默认相同。"
        ),
        "sources": ["zhihu", "bilibili", "v2ex", "web"],
        "simulate_persona": True,
    },
    "zhihu_deep": {
        "label": "知乎深挖",
        "summary": "仅知乎，适合问答与观点型话题；默认跳过画像模拟。",
        "detail": (
            "启用信源：仅知乎。依赖知乎 Cookie 或开放平台 AccessSecret。"
            "会走全局知乎深度配置（多类型搜索、展开高赞回答与评论挖掘），单源时结果更集中。"
            "不含 B站/微信等，搜罗更快但视角较窄。默认保持「跳过画像模拟」以节省时间。"
        ),
        "sources": ["zhihu"],
        "simulate_persona": False,
        "source_auto_restrict": True,
    },
}

_SOURCE_LABELS: dict[str, str] = get_source_labels()


def _source_labels(sources: list[str]) -> str:
    return "、".join(_SOURCE_LABELS.get(s, s) for s in sources)


def get_search_profile_catalog() -> list[dict[str, Any]]:
    """返回搜罗模式列表，供 Web 与 API 使用。"""
    cfg = load_config()
    raw_profiles: dict[str, Any] = cfg.get("profiles") or {}
    if not raw_profiles:
        raw_profiles = {"default": {"sources": list(DEFAULT_SEARCH_SOURCES)}}

    catalog: list[dict[str, Any]] = []
    for profile_id, profile_cfg in raw_profiles.items():
        if not isinstance(profile_cfg, dict):
            continue
        builtin = dict(_BUILTIN.get(profile_id) or {})
        merged: dict[str, Any] = {**builtin, **profile_cfg}
        sources = list(merged.get("sources") or builtin.get("sources") or DEFAULT_SEARCH_SOURCES)
        entry = {
            "id": profile_id,
            "label": str(merged.get("label") or profile_id),
            "summary": str(merged.get("summary") or f"信源：{_source_labels(sources)}"),
            "detail": str(merged.get("detail") or ""),
            "sources": sources,
            "source_labels": _source_labels(sources),
        }
        if "simulate_persona" in merged:
            entry["simulate_persona"] = bool(merged["simulate_persona"])
        if merged.get("source_auto_restrict"):
            entry["source_auto_restrict"] = True
        catalog.append(entry)
    return catalog


def get_search_profile(profile_id: str) -> dict[str, Any] | None:
    for item in get_search_profile_catalog():
        if item["id"] == profile_id:
            return item
    return None
