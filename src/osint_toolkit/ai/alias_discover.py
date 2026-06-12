"""联网发现关联词 / Network-first alias discovery."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.json_util import parse_json_object
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.ai.entity_store import classify_slurs, merge_discovered_aliases
from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.collectors.v2ex import V2exCollector
from osint_toolkit.collectors.web import WebCollector
from osint_toolkit.collectors.zhihu import ZhihuCollector
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.processors.normalize import html_to_text
from osint_toolkit.utils.config import get_search_config

_PROBE_COLLECTORS = {
    "bilibili": BilibiliCollector,
    "zhihu": ZhihuCollector,
    "web": WebCollector,
    "v2ex": V2exCollector,
}

_QUOTE_PATTERNS = [
    re.compile(r"「([^」]{1,24})」"),
    re.compile(r"【([^】]{1,24})】"),
    re.compile(r"《([^》]{1,24})》"),
    re.compile(r"#([\w\u4e00-\u9fff]{2,20})"),
    re.compile(r"\[([^\]]{2,20})\]"),
]

_STOP_TERMS = frozenset(
    {
        "视频",
        "合集",
        "全集",
        "高清",
        "官方",
        "转载",
        "搬运",
        "盘点",
        "解析",
        "攻略",
        "教程",
        "如何",
        "为什么",
        "什么",
        "怎么",
        "最新",
        "热门",
        "推荐",
        "合集",
        "第",
        "集",
    }
)


def _dedupe(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        t = term.strip()
        if not t or len(t) < 2 or len(t) > 24:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _is_noise(term: str, query: str) -> bool:
    t = term.strip()
    if not t or t == query:
        return True
    if t in _STOP_TERMS:
        return True
    if t.isdigit():
        return True
    if len(t) == 1:
        return True
    if re.fullmatch(r"[\W_]+", t):
        return True
    return False


def heuristic_aliases(query: str, items: list[IntelItem]) -> list[str]:
    """从探针检索标题/摘要中提取候选关联词（无 AI）。"""
    q = query.strip()
    if not q:
        return []
    candidates: list[str] = []
    blob_parts: list[str] = []

    for item in items:
        title = html_to_text(item.title or "")
        content = html_to_text(item.content or "")[:300]
        blob_parts.append(f"{title} {content}")
        text = f"{title} {content}"
        for pattern in _QUOTE_PATTERNS:
            for match in pattern.findall(text):
                candidates.append(match.strip())
        for sep in re.split(r"[|｜/／\-—–·•]", title):
            seg = sep.strip()
            if 2 <= len(seg) <= 16 and (q in seg or seg in q or q in text):
                candidates.append(seg)

    blob = " ".join(blob_parts)
    if blob:
        for m in re.finditer(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", blob):
            seg = m.group(0)
            if q in seg and seg != q and len(seg) <= len(q) + 6:
                candidates.append(seg.replace(q, "").strip() or seg)

    filtered = [c for c in candidates if not _is_noise(c, q)]
    return _dedupe(filtered)


async def _probe_source(name: str, query: str, limit: int) -> list[IntelItem]:
    cls = _PROBE_COLLECTORS.get(name)
    if not cls:
        return []
    try:
        return await cls().search(query, limit=limit)
    except Exception:  # noqa: BLE001
        return []


async def probe_network(
    query: str,
    sources: list[str] | None = None,
    *,
    limit: int = 5,
) -> list[IntelItem]:
    """用原查询在多源做轻量探针检索。"""
    cfg = get_search_config()
    default_sources = ["bilibili", "zhihu", "web", "v2ex"]
    probe_sources = cfg.get("discover_sources") or sources or default_sources
    if sources:
        allowed = set(sources)
        probe_sources = [s for s in probe_sources if s in allowed]
    probe_sources = [s for s in probe_sources if s in _PROBE_COLLECTORS]
    if not probe_sources:
        return []
    groups = await asyncio.gather(
        *[_probe_source(s, query, limit) for s in probe_sources],
        return_exceptions=True,
    )
    items: list[IntelItem] = []
    for group in groups:
        if isinstance(group, list):
            items.extend(group)
    return items


def ai_extract_aliases(
    query: str,
    items: list[IntelItem],
    *,
    no_ai: bool = False,
    include_slurs: bool = True,
    disabled_steps: list[str] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """AI 仅从探针证据中归纳关联词，禁止凭空编造。"""
    if no_ai or not is_step_enabled("alias_discover", no_ai=no_ai, disabled_steps=disabled_steps):
        return [], []
    if not items:
        return [], []

    evidence = []
    for i, item in enumerate(items[:20], 1):
        evidence.append(
            {
                "i": i,
                "source": item.source,
                "title": html_to_text(item.title or "")[:120],
                "snippet": html_to_text(item.content or "")[:200],
            }
        )

    client = DeepSeekClient()
    prompt_tpl, _ = load_prompt("alias_discover")
    slur_hint = "可包含贬义/黑称/梗称" if include_slurs else "不要输出贬义黑称"
    raw = client.chat(
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(task="关联词发现"),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt_tpl}\n\n"
                    f"查询: {query}\n"
                    f"要求: {slur_hint}；仅能从证据标题/摘要中出现或可明确推断的圈内缩写；"
                    "优先近期网络叫法；每项给 evidence 引用序号。\n"
                    f"证据:\n{json.dumps(evidence, ensure_ascii=False)}\n"
                    '输出 JSON: {"aliases":[{"term":"","type":"nickname|slang|slur|tag","evidence":[1,2]}]}'
                ),
            },
        ]
    )
    parsed = parse_json_object(raw)
    entries = parsed.get("aliases") or []
    if isinstance(entries, dict):
        entries = [entries]
    terms: list[str] = []
    detailed: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        term = str(entry.get("term") or "").strip()
        if not term or _is_noise(term, query):
            continue
        atype = str(entry.get("type") or "")
        if not include_slurs and atype == "slur":
            continue
        terms.append(term)
        detailed.append(
            {
                "term": term,
                "type": atype,
                "evidence": entry.get("evidence") or [],
            }
        )
    return _dedupe(terms), detailed


async def discover_aliases(
    query: str,
    sources: list[str] | None = None,
    *,
    no_ai: bool = False,
    include_slurs: bool = True,
    disabled_steps: list[str] | None = None,
) -> dict[str, Any]:
    """探针检索 → 启发式 + AI 证据归纳 → 候选关联词。"""
    cfg = get_search_config()
    if not cfg.get("discover_aliases", True):
        return {"discovered_aliases": [], "probe_count": 0, "skipped": True}

    limit = int(cfg.get("discover_probe_limit", 5))
    probe_items = await probe_network(query, sources, limit=limit)
    heuristic = heuristic_aliases(query, probe_items)
    ai_terms, ai_details = ai_extract_aliases(
        query,
        probe_items,
        no_ai=no_ai,
        include_slurs=include_slurs,
        disabled_steps=disabled_steps,
    )

    discovered = _dedupe(ai_terms + heuristic)
    discovered = [t for t in discovered if t != query.strip()]

    probe_sources = sorted({i.source for i in probe_items})
    alias_terms, slur_terms = classify_slurs(discovered, ai_details, include_slurs=include_slurs)

    persist_result: dict[str, Any] = {"saved": False}
    if cfg.get("persist_discovered_aliases", True) and discovered:
        persist_result = merge_discovered_aliases(
            query.strip(),
            alias_terms,
            slur_terms,
            probe_sources=probe_sources,
        )

    return {
        "discovered_aliases": discovered,
        "heuristic_aliases": heuristic,
        "ai_discovered_aliases": ai_terms,
        "ai_details": ai_details,
        "probe_count": len(probe_items),
        "probe_sources": probe_sources,
        "persist": persist_result,
        "probe_samples": [
            {"source": i.source, "title": i.title, "url": i.url}
            for i in probe_items[:8]
        ],
    }
