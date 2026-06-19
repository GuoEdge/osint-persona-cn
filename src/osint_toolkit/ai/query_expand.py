"""查询扩展 / Query expansion with entity packs, rules, and AI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from osint_toolkit.ai.alias_filter import (
    filter_relevant_terms,
    has_relevance_to_query,
    is_narrow_product_query,
    is_valid_search_term,
    product_variants,
)
from osint_toolkit.ai.query_analyze import analyze_query
from osint_toolkit.collectors.source_routing import apply_source_routing, compute_source_scores
from osint_toolkit.collectors.source_resolve import blend_rule_and_ai_scores, detect_cryptic_from_scores
from osint_toolkit.ai.source_planner import detect_cryptic_query, plan_sources
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


def _name_matches_query(name: str, query: str) -> bool:
    """精确或包含匹配：搜「祥子」可命中词表里的「丰川祥子」。"""
    n = name.strip()
    q = query.strip()
    if not n or not q:
        return False
    if is_narrow_product_query(q):
        return n.lower() == q.lower() or has_relevance_to_query(n, q)
    nl, ql = n.lower(), q.lower()
    if nl == ql:
        return True
    if len(n) <= 4 and len(q) > len(n) + 2:
        if not re.search(rf"(?<![\w.\-]){re.escape(nl)}(?![\w.\-])", ql):
            return False
    if len(q) >= 2 and ql in nl:
        return True
    if len(n) >= 2 and len(q) > len(n) and nl in ql:
        return True
    return False


def _collect_entity_names(
    entities: dict | list,
    *,
    include_slurs: bool,
) -> list[tuple[str, list[str]]]:
    """Return (canonical, all_names) pairs from a pack section."""
    rows: list[tuple[str, list[str]]] = []
    if isinstance(entities, list):
        for entry in entities:
            if not isinstance(entry, dict):
                continue
            canonical = str(entry.get("canonical") or entry.get("name") or "").strip()
            aliases = [str(a) for a in (entry.get("aliases") or [])]
            slurs = [str(s) for s in (entry.get("slurs") or [])] if include_slurs else []
            names = _dedupe_preserve_order([canonical, *aliases, *slurs])
            if canonical:
                rows.append((canonical, names))
    elif isinstance(entities, dict):
        for canonical, spec in entities.items():
            if not isinstance(spec, dict):
                continue
            aliases = [str(a) for a in (spec.get("aliases") or [])]
            slurs = [str(s) for s in (spec.get("slurs") or [])] if include_slurs else []
            names = _dedupe_preserve_order([str(canonical), *aliases, *slurs])
            rows.append((str(canonical), names))
    return rows


def _entity_aliases_for_query(query: str, *, include_slurs: bool) -> list[str]:
    q = query.strip()
    if not q:
        return []
    if is_narrow_product_query(q):
        return [
            a
            for a in product_variants(q)
            if a.lower() != q.lower() and is_valid_search_term(a, query=q, require_relevance=True)
        ]
    found: list[str] = []
    for pack in _load_entity_packs():
        for _canonical, names in _collect_entity_names(
            pack.get("entities") or {},
            include_slurs=include_slurs,
        ):
            if any(_name_matches_query(n, q) for n in names if n):
                found.extend(names)
    ql = q.lower()
    return filter_relevant_terms(
        [
            a
            for a in found
            if a.lower() != ql and is_valid_search_term(a, query=q, require_relevance=True)
        ],
        q,
    )


def _rule_expand(query: str, *, existing_aliases: list[str] | None = None) -> list[str]:
    """轻量昵称规则：仅在联网/词表仍不足时补简称，默认不再机械追加酱/碳/女士。"""
    cfg = get_search_config()
    if not cfg.get("rule_expand_enabled", True):
        return []

    q = query.strip()
    if not q:
        return []

    existing = {t.lower() for t in _dedupe_preserve_order(existing_aliases or [])}
    min_existing = int(cfg.get("rule_expand_min_existing", 2))
    if len(existing) >= min_existing:
        return []

    out: list[str] = []
    if re.fullmatch(r"[\u4e00-\u9fff]{3,6}", q):
        given = q[-2:] if len(q) >= 3 else q
        if given and given != q and given.lower() not in existing:
            out.append(given)
            short = f"小{given[0]}" if len(given) >= 2 else f"小{given}"
            if short.lower() not in existing and short.lower() != q.lower():
                out.append(short)
        if cfg.get("rule_nickname_suffixes", False) and given:
            for suffix in ("酱", "碳", "女士"):
                if not q.endswith(suffix):
                    candidate = f"{given}{suffix}"
                    if candidate.lower() not in existing:
                        out.append(candidate)
    return _dedupe_preserve_order([t for t in out if t.lower() != q.lower()])


def per_query_limit(total_limit: int, num_queries: int) -> int:
    cfg = get_search_config()
    ratio = float(cfg.get("per_query_limit_ratio", 0.6))
    floor = int(cfg.get("zhihu_per_query_limit_min", 20)) if cfg.get("zhihu_aggressive", True) else 3
    per = max(3, int(total_limit * ratio))
    if cfg.get("zhihu_aggressive", True):
        per = max(per, min(floor, total_limit))
    else:
        per = max(3, min(per, total_limit))
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
    profile: str = "default",
    source_overrides: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Merge network discovery, entity packs, rules, and AI into expanded search queries."""
    cfg = get_search_config()
    strict = bool(cfg.get("strict_mode", False))
    narrow = is_narrow_product_query(query)
    if include_slurs is None:
        include_slurs = bool(cfg.get("include_slurs", True))

    network_aliases = filter_relevant_terms(
        [
            a
            for a in (discovered_aliases or [])
            if is_valid_search_term(a, query=query, require_relevance=True)
        ],
        query,
    )
    entity_aliases = _entity_aliases_for_query(query, include_slurs=include_slurs)
    rule_aliases = [] if narrow else _rule_expand(query, existing_aliases=network_aliases + entity_aliases)

    analysis = analyze_query(
        query,
        sources,
        persona_ctx,
        no_ai=no_ai or narrow or strict,
        disabled_steps=disabled_steps,
    )

    ai_queries = analysis.get("expanded_queries") or [query]
    if isinstance(ai_queries, str):
        ai_queries = [ai_queries]
    ai_aliases = analysis.get("aliases") or []
    if isinstance(ai_aliases, str):
        ai_aliases = [ai_aliases]

    if narrow:
        merged = _dedupe_preserve_order([query, *product_variants(query), *network_aliases, *entity_aliases])
    else:
        merged = _dedupe_preserve_order(
            [query]
            + network_aliases
            + entity_aliases
            + rule_aliases
            + [
                str(q)
                for q in ai_queries
                if str(q).strip() != query and is_valid_search_term(str(q), query=query, require_relevance=True)
            ]
            + [str(a) for a in ai_aliases if is_valid_search_term(str(a), query=query, require_relevance=True)]
        )
    merged = filter_relevant_terms(merged, query)
    default_max = 4 if strict else 5
    max_q = int(cfg.get("max_expanded_queries_strict" if strict else "max_expanded_queries", default_max))
    if narrow:
        max_q = min(max_q, int(cfg.get("max_expanded_queries_narrow", 4)))
    queries_used = merged[:max_q]
    aliases = [t for t in queries_used if t != query]

    rule_scores = compute_source_scores(
        query,
        ai_priority=analysis.get("recommended_sources") if isinstance(analysis.get("recommended_sources"), list) else None,
    )
    cryptic_hint = detect_cryptic_query(query, rule_scores) or detect_cryptic_from_scores(rule_scores)

    source_plan = plan_sources(
        query,
        sources,
        persona_ctx=persona_ctx,
        rule_scores=rule_scores,
        query_intent=str(analysis.get("intent") or query),
        expanded_queries=queries_used,
        is_cryptic_hint=cryptic_hint,
        no_ai=no_ai or narrow or strict,
        disabled_steps=disabled_steps,
    )
    is_cryptic = bool(source_plan.get("is_cryptic")) or cryptic_hint
    blended_scores, score_breakdown = blend_rule_and_ai_scores(
        rule_scores,
        source_plan,
        is_cryptic=is_cryptic,
    )

    routing = apply_source_routing(
        query,
        sources,
        analysis.get("recommended_sources") if isinstance(analysis.get("recommended_sources"), list) else None,
        profile=profile,
        scores=blended_scores,
        score_breakdown=score_breakdown,
        ai_plan=source_plan,
        source_overrides=source_overrides,
    )

    return {
        "intent": analysis.get("intent", query),
        "expanded_queries": queries_used,
        "aliases": aliases,
        "queries_used": queries_used,
        "source_plan": source_plan,
        "active_sources": routing.get("active_sources") or routing.get("recommended_sources") or sources,
        "recommended_sources": routing.get("active_sources") or routing.get("recommended_sources") or sources,
        "source_routing": {
            "domain": routing.get("domain") or "",
            "label": routing.get("label") or "",
            "mode": routing.get("mode") or "gentle",
            "hint": routing.get("hint") or "",
            "active_sources": routing.get("active_sources") or [],
            "auto_enabled": routing.get("auto_enabled") or [],
            "skipped": routing.get("skipped") or [],
            "user_sources": routing.get("user_sources") or list(sources),
            "scores": routing.get("scores") or {},
            "score_breakdown": routing.get("score_breakdown") or {},
            "rule_scores": routing.get("rule_scores") or {},
            "is_cryptic": routing.get("is_cryptic", False),
            "suggested_sources": routing.get("suggested_sources") or [],
            "boost_site_domains": routing.get("boost_site_domains") or [],
        },
        "network_aliases": network_aliases,
        "entity_aliases": entity_aliases,
        "rule_aliases": rule_aliases,
        "ai_aliases": [str(a) for a in ai_aliases],
        "discover_meta": discover_meta or {},
        "include_slurs": include_slurs,
    }
