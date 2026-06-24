"""外文关键词拓展 / Foreign-language query expansion for international sources."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from osint_toolkit.ai.alias_filter import (
    filter_relevant_terms,
    is_narrow_product_query,
    is_valid_search_term,
    product_variants,
)
from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.json_util import parse_json_object
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.collectors.queries_by_source import is_primarily_latin
from osint_toolkit.collectors.source_catalog import any_source_accepts_foreign
from osint_toolkit.http.reachability import has_proxy_configured, intl_probe_enabled
from osint_toolkit.utils.config import load_config

_CJK = re.compile(r"[\u4e00-\u9fff]")


def foreign_expand_config() -> dict[str, Any]:
    return dict(load_config().get("search", {}).get("foreign_expand") or {})


def foreign_expand_enabled(
    query: str,
    sources: list[str],
    *,
    force: bool = False,
) -> bool:
    cfg = foreign_expand_config()
    mode = str(cfg.get("enabled") or "auto")
    if mode == "off":
        return False
    if mode == "on" or force:
        return True
    if is_primarily_latin(query) or is_narrow_product_query(query):
        return True
    return any_source_accepts_foreign(sources)


def _entities_dir() -> Path:
    return get_data_dir() / "entities"


def _entity_foreign_aliases(query: str) -> list[str]:
    q = query.strip()
    if not q:
        return []
    directory = _entities_dir()
    if not directory.is_dir():
        return []
    found: list[str] = []
    for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        entities = data.get("entities")
        if isinstance(entities, dict):
            items = [{"canonical": k, **(v if isinstance(v, dict) else {})} for k, v in entities.items()]
        elif isinstance(entities, list):
            items = entities
        else:
            continue
        for entry in items:
            if not isinstance(entry, dict):
                continue
            canonical = str(entry.get("canonical") or entry.get("name") or "").strip()
            names = [canonical] + [str(a) for a in (entry.get("aliases") or [])]
            names_en = [str(a) for a in (entry.get("aliases_en") or entry.get("en_aliases") or [])]
            if not any(q in n or n in q for n in names if n):
                continue
            found.extend(names_en)
            for pair in entry.get("lang_pairs") or []:
                if isinstance(pair, dict):
                    if q in (pair.get("zh") or pair.get("cn") or ""):
                        found.append(str(pair.get("en") or pair.get("latin") or ""))
                    if q.lower() in str(pair.get("en") or "").lower():
                        found.append(str(pair.get("zh") or pair.get("cn") or ""))
    return [t for t in found if t.strip() and t.strip() != q]


def _ai_foreign_expand(
    query: str,
    *,
    chinese_aliases: list[str],
    no_ai: bool,
    disabled_steps: list[str] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    if no_ai or not is_step_enabled("foreign_expand", no_ai=no_ai, disabled_steps=disabled_steps):
        return [], []
    prompt_tpl, _ = load_prompt("foreign_expand")
    try:
        client = DeepSeekClient()
        raw = client.chat(
            messages=[
                {"role": "system", "content": build_system_prompt(task="外文拓展")},
                {
                    "role": "user",
                    "content": (
                        f"{prompt_tpl}\n\n"
                        f"查询: {query}\n"
                        f"已有中文关联词: {json.dumps(chinese_aliases[:8], ensure_ascii=False)}\n"
                        "输出 JSON: {\"en_queries\":[],\"romanization\":[],\"confidence\":0.0}"
                    ),
                },
            ],
            temperature=0.2,
        )
        data = parse_json_object(raw)
        terms: list[str] = []
        for key in ("en_queries", "romanization", "foreign_queries"):
            val = data.get(key)
            if isinstance(val, list):
                terms.extend(str(x) for x in val if str(x).strip())
            elif isinstance(val, str) and val.strip():
                terms.append(val.strip())
        details = [{"term": t, "via": "ai_foreign_expand"} for t in terms]
        return terms, details
    except Exception:  # noqa: BLE001
        return [], []


def _filter_foreign_terms(terms: list[str], query: str) -> list[str]:
    q = query.strip()
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        t = str(term or "").strip()
        if not t or t.lower() == q.lower():
            continue
        if t.lower() in seen:
            continue
        if not is_valid_search_term(t, query=q, require_relevance=False):
            continue
        if _CJK.search(t) and not is_primarily_latin(q):
            continue
        seen.add(t.lower())
        out.append(t)
    return out


def expand_foreign_terms(
    query: str,
    sources: list[str],
    *,
    chinese_aliases: list[str] | None = None,
    intl_probe_terms: list[str] | None = None,
    no_ai: bool = False,
    disabled_steps: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Return foreign_queries separate from domestic Chinese expansion."""
    cfg = foreign_expand_config()
    if not foreign_expand_enabled(query, sources, force=force):
        return {
            "foreign_queries": [],
            "foreign_aliases": [],
            "skipped": True,
            "reason": "no_intl_sources",
            "meta": {},
        }

    max_f = int(cfg.get("max_foreign_queries", 3))
    terms: list[str] = []
    meta: dict[str, Any] = {"sources": []}

    if is_narrow_product_query(query):
        terms.extend(product_variants(query))

    terms.extend(_entity_foreign_aliases(query))
    if intl_probe_terms:
        terms.extend(intl_probe_terms)
        meta["intl_probe"] = len(intl_probe_terms)

    ai_terms, ai_details = _ai_foreign_expand(
        query,
        chinese_aliases=chinese_aliases or [],
        no_ai=no_ai,
        disabled_steps=disabled_steps,
    )
    terms.extend(ai_terms)
    if ai_details:
        meta["ai"] = ai_details

    if is_primarily_latin(query) and query.strip():
        terms.insert(0, query.strip())

    filtered = _filter_foreign_terms(terms, query)
    filtered = filter_relevant_terms(filtered, query, allow_cross_script=True)
    foreign_queries = filtered[:max_f]

    degraded = not has_proxy_configured() and not intl_probe_enabled()
    reason = ""
    if degraded and any_source_accepts_foreign(sources):
        reason = "intl_degraded_no_proxy"

    return {
        "foreign_queries": foreign_queries,
        "foreign_aliases": [t for t in foreign_queries if t != query],
        "skipped": not foreign_queries,
        "reason": reason,
        "degraded": degraded,
        "meta": meta,
    }


async def probe_foreign_aliases(
    query: str,
    *,
    no_ai: bool = True,
) -> list[str]:
    """Light intl network probe for foreign alias terms (github/web)."""
    if not intl_probe_enabled():
        return []
    from osint_toolkit.ai.alias_discover import heuristic_aliases, probe_network

    cfg = foreign_expand_config()
    intl_sources = list(cfg.get("discover_sources_intl") or ["github", "web"])
    limit = min(3, int(load_config().get("search", {}).get("discover_probe_limit", 5)))
    items = await probe_network(query, intl_sources, limit=limit)
    return heuristic_aliases(query, items)
