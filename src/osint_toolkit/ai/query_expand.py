"""查询扩展 / Query expansion with entity packs, rules, and AI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from osint_toolkit.ai.query_analyze import analyze_query
from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.persona.context import PersonaContext
from osint_toolkit.utils.config import load_config

def get_search_config() -> dict[str, Any]:
    return dict(load_config().get("search", {}))


def _entities_dir() -> Path:
    return get_data_dir() / "entities"


def _dedupe_preserve_order(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        t = term.strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _load_entity_packs() -> list[dict[str, Any]]:
    directory = _entities_dir()
    if not directory.is_dir():
        return []
    packs: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict) and "entities" in data:
            packs.append(data)
        elif isinstance(data, list):
            packs.append({"entities": data})
    return packs


def _entity_aliases_for_query(query: str, *, include_slurs: bool) -> list[str]:
    q = query.strip()
    if not q:
        return []
    ql = q.lower()
    found: list[str] = []
    for pack in _load_entity_packs():
        entities = pack.get("entities") or {}
        if isinstance(entities, list):
            for entry in entities:
                if not isinstance(entry, dict):
                    continue
                canonical = str(entry.get("canonical") or entry.get("name") or "").strip()
                aliases = entry.get("aliases") or []
                slurs = entry.get("slurs") or []
                names = [canonical] + [str(a) for a in aliases]
                if include_slurs:
                    names.extend(str(s) for s in slurs)
                if any(n.lower() == ql for n in names if n):
                    found.extend(names)
        elif isinstance(entities, dict):
            for canonical, spec in entities.items():
                if not isinstance(spec, dict):
                    continue
                aliases = spec.get("aliases") or []
                slurs = spec.get("slurs") or []
                names = [canonical] + [str(a) for a in aliases]
                if include_slurs:
                    names.extend(str(s) for s in slurs)
                if any(n.lower() == ql for n in names if n):
                    found.extend(names)
    return _dedupe_preserve_order([a for a in found if a.lower() != ql])


def _rule_expand(query: str) -> list[str]:
    q = query.strip()
    if not q:
        return []
    out: list[str] = []
    if re.fullmatch(r"[\u4e00-\u9fff]{3,6}", q):
        given = q[-2:] if len(q) >= 3 else q
        if given and given != q:
            out.append(given)
            if len(given) >= 2:
                out.append(f"小{given[0]}")
            else:
                out.append(f"小{given}")
        for suffix in ("酱", "碳", "女士"):
            if not q.endswith(suffix) and given:
                out.append(f"{given}{suffix}")
    return _dedupe_preserve_order([t for t in out if t.lower() != q.lower()])


def per_query_limit(total_limit: int, num_queries: int) -> int:
    cfg = get_search_config()
    ratio = float(cfg.get("per_query_limit_ratio", 0.85))
    floor = int(cfg.get("zhihu_per_query_limit_min", 20)) if cfg.get("zhihu_aggressive", True) else 3
    per = max(floor, int(total_limit * ratio))
    if num_queries > 1 and not cfg.get("zhihu_aggressive", True):
        per = max(3, min(per, total_limit))
    return per


def expand_query(
    query: str,
    sources: list[str],
    persona_ctx: PersonaContext | None = None,
    *,
    no_ai: bool = False,
    disabled_steps: list[str] | None = None,
    include_slurs: bool | None = None,
    discovered_aliases: list[str] | None = None,
    discover_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge network discovery, entity packs, rules, and AI into expanded search queries."""
    cfg = get_search_config()
    if include_slurs is None:
        include_slurs = bool(cfg.get("include_slurs", True))

    network_aliases = _dedupe_preserve_order(discovered_aliases or [])
    entity_aliases = _entity_aliases_for_query(query, include_slurs=include_slurs)
    rule_aliases = _rule_expand(query)

    analysis = analyze_query(
        query,
        sources,
        persona_ctx,
        no_ai=no_ai,
        disabled_steps=disabled_steps,
    )

    ai_queries = analysis.get("expanded_queries") or [query]
    if isinstance(ai_queries, str):
        ai_queries = [ai_queries]
    ai_aliases = analysis.get("aliases") or []
    if isinstance(ai_aliases, str):
        ai_aliases = [ai_aliases]

    merged = _dedupe_preserve_order(
        [query]
        + network_aliases
        + entity_aliases
        + rule_aliases
        + [str(q) for q in ai_queries if str(q).strip() != query]
        + [str(a) for a in ai_aliases]
    )
    max_q = int(cfg.get("max_expanded_queries", 8))
    queries_used = merged[:max_q]
    aliases = [t for t in merged if t != query]

    return {
        "intent": analysis.get("intent", query),
        "expanded_queries": queries_used,
        "aliases": aliases,
        "queries_used": queries_used,
        "recommended_sources": analysis.get("recommended_sources") or sources,
        "network_aliases": network_aliases,
        "entity_aliases": entity_aliases,
        "rule_aliases": rule_aliases,
        "ai_aliases": [str(a) for a in ai_aliases],
        "discover_meta": discover_meta or {},
        "include_slurs": include_slurs,
    }
