"""实体词表持久化 / Persist discovered aliases to ~/.osint/entities/."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from osint_toolkit.auth.paths import get_data_dir

DISCOVERED_FILENAME = "discovered.yaml"


def entities_dir() -> Path:
    path = get_data_dir() / "entities"
    path.mkdir(parents=True, exist_ok=True)
    return path


def discovered_path() -> Path:
    return entities_dir() / DISCOVERED_FILENAME


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entities": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, dict) and "entities" in data:
        return data
    if isinstance(data, dict):
        return {"entities": data}
    return {"entities": {}}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _norm_list(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values or []:
        term = str(value).strip()
        if not term:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    return out


def merge_discovered_aliases(
    canonical: str,
    aliases: list[str],
    slurs: list[str] | None = None,
    *,
    probe_sources: list[str] | None = None,
) -> dict[str, Any]:
    """将联网发现的关联词合并写入 discovered.yaml，供后续搜索复用。"""
    canonical = canonical.strip()
    if not canonical:
        return {"saved": False, "reason": "empty canonical"}

    new_aliases = _norm_list(aliases)
    new_slurs = _norm_list(slurs or [])
    new_aliases = [a for a in new_aliases if a.lower() != canonical.lower()]
    new_slurs = [s for s in new_slurs if s.lower() != canonical.lower()]

    if not new_aliases and not new_slurs:
        return {"saved": False, "reason": "nothing to add"}

    path = discovered_path()
    pack = _load_yaml(path)
    entities: dict[str, Any] = pack.setdefault("entities", {})
    entry: dict[str, Any] = dict(entities.get(canonical) or {})
    existing_aliases = _norm_list(entry.get("aliases") or [])
    existing_slurs = _norm_list(entry.get("slurs") or [])

    alias_keys = {a.lower() for a in existing_aliases}
    slur_keys = {s.lower() for s in existing_slurs}
    added_aliases = [a for a in new_aliases if a.lower() not in alias_keys and a.lower() not in slur_keys]
    added_slurs = [s for s in new_slurs if s.lower() not in slur_keys and s.lower() not in alias_keys]

    if not added_aliases and not added_slurs:
        return {
            "saved": False,
            "reason": "already up to date",
            "path": str(path),
            "canonical": canonical,
        }

    entry["aliases"] = existing_aliases + added_aliases
    entry["slurs"] = existing_slurs + added_slurs
    meta = dict(entry.get("meta") or {})
    meta["updated_at"] = datetime.now(UTC).isoformat()
    meta["auto_discovered"] = True
    if probe_sources:
        prev = set(meta.get("probe_sources") or [])
        meta["probe_sources"] = sorted(prev | set(probe_sources))
    entry["meta"] = meta
    entities[canonical] = entry
    _save_yaml(path, pack)

    return {
        "saved": True,
        "path": str(path),
        "canonical": canonical,
        "added_aliases": added_aliases,
        "added_slurs": added_slurs,
        "total_aliases": len(entry["aliases"]),
        "total_slurs": len(entry["slurs"]),
    }


def classify_slurs(
    discovered: list[str],
    ai_details: list[dict[str, Any]],
    *,
    include_slurs: bool,
) -> tuple[list[str], list[str]]:
    """按 AI 标注将 discovered 拆分为 aliases 与 slurs。"""
    if not include_slurs:
        return _norm_list(discovered), []
    slur_terms = {
        str(d.get("term") or "").strip().lower()
        for d in ai_details
        if str(d.get("type") or "").lower() == "slur" and str(d.get("term") or "").strip()
    }
    aliases: list[str] = []
    slurs: list[str] = []
    for term in _norm_list(discovered):
        if term.lower() in slur_terms:
            slurs.append(term)
        else:
            aliases.append(term)
    return aliases, slurs
