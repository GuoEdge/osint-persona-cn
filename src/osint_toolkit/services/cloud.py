"""Cloud-backed Markdown vault service for the knowledge base."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import knowledge_graph
from osint_toolkit.storage.knowledge import save_item
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.utils.atomic_write import atomic_write_text
from osint_toolkit.utils.config import load_config, reset_config_cache
from osint_toolkit.utils.secrets import save_user_config_patch

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)
_SAFE_SEGMENT_RE = re.compile(r"[^\w\u4e00-\u9fff-]+", re.U)
_NOTE_SUFFIX_RE = re.compile(r"\.conflict-\d{8}T\d{6}Z\.md$", re.I)
_MACHINE_START = "<!-- OSINT:BODY:START -->"
_MACHINE_END = "<!-- OSINT:BODY:END -->"
_ITEM_LIMIT = 5000
_SYNC_STATE_SCHEMA_VERSION = 3
_ONEDRIVE_UNSAFE_NAME_RE = re.compile(r'[\"*:<>?/\\|]')
_DEFAULT_VAULT_NAME = "OSINT-Knowledge"
_SYNC_MODES = {"passive", "manual", "scheduled"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _timestamp_slug() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _slugify(text: str, *, fallback: str = "item", limit: int = 72) -> str:
    value = _SAFE_SEGMENT_RE.sub("-", str(text or "").strip()).strip("-._")
    value = re.sub(r"-{2,}", "-", value)
    return (value[:limit].strip("-._") or fallback)


def _normalize_path_value(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).as_posix()


def _safe_name(text: str, *, fallback: str = "item", limit: int = 80) -> str:
    return _slugify(text, fallback=fallback, limit=limit)


def _as_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, list):
        return [str(v).strip() for v in values if str(v).strip()]
    if isinstance(values, tuple):
        return [str(v).strip() for v in values if str(v).strip()]
    return [str(values).strip()] if str(values).strip() else []


def _extract_entities(item: IntelItem) -> list[str]:
    entities = []
    for key in ("entities", "named_entities"):
        entities.extend(_as_list(item.personal.get(key)))
        entities.extend(_as_list(item.layers.get(key)))
    seen: set[str] = set()
    out: list[str] = []
    for entity in entities:
        if entity not in seen:
            seen.add(entity)
            out.append(entity)
    return out


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]


def _device_id_path() -> Path:
    return get_data_dir() / "device_id.txt"


def _local_device_id(*, create: bool = False) -> str:
    path = _device_id_path()
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not create:
        return ""
    path.parent.mkdir(parents=True, exist_ok=True)
    value = str(uuid4())
    path.write_text(value, encoding="utf-8")
    return value


def _cloud_cfg() -> dict[str, Any]:
    cfg = load_config().get("knowledge", {}).get("cloud", {})
    return {
        "provider": str(cfg.get("provider") or "local_folder"),
        "vault_path": str(cfg.get("vault_path") or "").strip(),
        "sync_mode": _normalize_sync_mode(cfg.get("sync_mode")),
        "enabled": bool(cfg.get("enabled", True)),
        "encrypt_backups": bool(cfg.get("encrypt_backups", False)),
        "include_attachments": bool(cfg.get("include_attachments", True)),
        "include_raw_archives": bool(cfg.get("include_raw_archives", False)),
    }


def _normalize_sync_mode(value: Any) -> str:
    mode = str(value or "manual").strip().lower()
    return mode if mode in _SYNC_MODES else "manual"


def _detect_onedrive_candidates() -> list[Path]:
    candidates: list[Path] = []
    for key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        value = os.environ.get(key)
        if value:
            candidates.append(Path(value).expanduser().resolve())
    home = Path.home()
    for child in home.glob("OneDrive*"):
        try:
            resolved = child.resolve()
        except OSError:
            continue
        candidates.append(resolved)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _onedrive_targets(*, vault_name: str = _DEFAULT_VAULT_NAME) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for root in _detect_onedrive_candidates():
        targets.append(
            {
                "root": str(root),
                "vault_path": str((root / _safe_name(vault_name, fallback=_DEFAULT_VAULT_NAME)).resolve()),
            }
        )
    return targets


def _recommended_vault_path(provider: str) -> Path | None:
    if provider == "onedrive_folder":
        candidates = _detect_onedrive_candidates()
        if candidates:
            return candidates[0] / _DEFAULT_VAULT_NAME
    if provider == "local_folder":
        return get_data_dir() / "vault"
    return None


def _matched_onedrive_root(path: Path | None) -> Path | None:
    if path is None:
        return None
    target = path.resolve()
    for candidate in _detect_onedrive_candidates():
        try:
            if target == candidate or candidate in target.parents:
                return candidate
        except OSError:
            continue
    return None


def vault_root(*, create: bool = False) -> Path | None:
    cfg = _cloud_cfg()
    if not cfg["enabled"]:
        return None
    raw = cfg["vault_path"]
    if raw:
        path = Path(raw).expanduser().resolve()
    else:
        recommended = _recommended_vault_path(cfg["provider"]) if cfg["provider"] == "onedrive_folder" else None
        path = recommended.resolve() if recommended else None
    if path is None:
        return None
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _vault_ready() -> bool:
    return vault_root() is not None


def _ensure_layout(root: Path) -> dict[str, Path]:
    layout = {
        "root": root,
        "inbox": root / "Inbox",
        "sources": root / "Sources",
        "topics": root / "Topics",
        "entities": root / "Entities",
        "concepts": root / "Concepts",
        "projects": root / "Projects",
        "daily": root / "Daily",
        "runs": root / "Runs",
        "attachments": root / "Attachments",
        "meta": root / "_osint",
        "backups": root / "_osint" / "backups",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return layout


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2)
    return meta if isinstance(meta, dict) else {}, body


def _parse_machine_payload(body: str) -> tuple[str, str]:
    if _MACHINE_START not in body or _MACHINE_END not in body:
        return body.strip(), body.strip()
    _, _, after = body.partition(_MACHINE_START)
    machine, _, _tail = after.partition(_MACHINE_END)
    human = body.partition(_MACHINE_START)[0].rstrip()
    return human.strip(), machine.strip()


def _topic_link(topic: str) -> str:
    safe = _safe_name(topic, fallback="topic")
    return f"[[Topics/{safe}|{topic}]]"


def _entity_link(entity: str) -> str:
    safe = _safe_name(entity, fallback="entity")
    return f"[[Entities/{safe}|{entity}]]"


def _concept_link(concept: str) -> str:
    safe = _safe_name(concept, fallback="concept")
    return f"[[Concepts/{safe}|{concept}]]"


def _project_link(project: str) -> str:
    safe = _safe_name(project, fallback="project")
    return f"[[Projects/{safe}|{project}]]"


def _item_links(item: IntelItem) -> tuple[list[str], list[str], list[str], list[str]]:
    topics = item.topics or []
    entities = _extract_entities(item)
    concepts = _as_list(item.personal.get("concepts"))
    projects = _as_list(item.personal.get("project"))
    return (
        [_topic_link(topic) for topic in topics],
        [_entity_link(entity) for entity in entities],
        [_concept_link(concept) for concept in concepts],
        [_project_link(project) for project in projects],
    )


def _human_body(item: IntelItem, *, capture_reason: str | None = None) -> str:
    summary = (item.summary or "").strip()
    content = (item.content or "").strip()
    topic_links, entity_links, concept_links, project_links = _item_links(item)
    evidence: list[str] = []
    if capture_reason:
        evidence.append(f"- 收录原因: {capture_reason}")
    if item.personal.get("dwell_sec"):
        evidence.append(f"- 停留时长: {item.personal['dwell_sec']}s")
    if item.personal.get("run_id"):
        evidence.append(f"- 来源 run: {item.personal['run_id']}")
    if item.personal.get("citation_id"):
        evidence.append(f"- 引用编号: {item.personal['citation_id']}")
    lines = [f"# {item.title}", ""]
    if summary:
        lines.extend(["## 核心摘要", summary, ""])
    if topic_links or entity_links or concept_links or project_links:
        lines.append("## 关联")
        if topic_links:
            lines.append("- 主题: " + " ".join(topic_links))
        if entity_links:
            lines.append("- 实体: " + " ".join(entity_links))
        if concept_links:
            lines.append("- 概念: " + " ".join(concept_links))
        if project_links:
            lines.append("- 项目: " + " ".join(project_links))
        lines.append("")
    lines.extend(["## 来源", f"- 平台: {item.source}", f"- URL: {item.url}", ""])
    if evidence:
        lines.extend(["## 行为证据", *evidence, ""])
    lines.extend(["## 正文", content or "（无正文）", ""])
    return "\n".join(lines).strip()


def _machine_body(item: IntelItem) -> str:
    payload = {
        "content": item.content or "",
        "summary": item.summary or "",
        "key_points": item.key_points or [],
        "topics": item.topics or [],
        "entities": _extract_entities(item),
        "concepts": _as_list(item.personal.get("concepts")),
        "claims": _as_list(item.personal.get("claims")),
        "questions": _as_list(item.personal.get("questions")),
        "relations": item.personal.get("relations") or [],
        "project": item.personal.get("project") or "",
        "confidence": item.personal.get("confidence"),
        "evidence_refs": _as_list(item.personal.get("evidence_refs")),
        "metrics": item.metrics.model_dump() if hasattr(item.metrics, "model_dump") else {},
        "signals": item.signals.model_dump() if hasattr(item.signals, "model_dump") else {},
        "layers": item.layers or {},
        "personal": item.personal or {},
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _note_text(item: IntelItem, *, capture_reason: str | None = None, updated_at: str | None = None) -> tuple[str, str]:
    human = _human_body(item, capture_reason=capture_reason)
    machine = _machine_body(item)
    body = f"{human}\n\n{_MACHINE_START}\n{machine}\n{_MACHINE_END}\n"
    meta = {
        "id": item.id,
        "source": item.source,
        "type": item.type,
        "url": item.url,
        "title": item.title,
        "author": item.author or "",
        "published_at": item.published_at,
        "saved_at": item.personal.get("saved_at"),
        "updated_at": updated_at or _now(),
        "summary": item.summary or "",
        "tags": _as_list(item.personal.get("tags")),
        "topics": item.topics or [],
        "entities": _extract_entities(item),
        "concepts": _as_list(item.personal.get("concepts")),
        "claims": _as_list(item.personal.get("claims")),
        "questions": _as_list(item.personal.get("questions")),
        "relations": item.personal.get("relations") or [],
        "project": item.personal.get("project") or "",
        "confidence": item.personal.get("confidence"),
        "evidence_refs": _as_list(item.personal.get("evidence_refs")),
        "run_id": item.personal.get("run_id"),
        "citation_id": item.personal.get("citation_id"),
        "dwell_sec": item.personal.get("dwell_sec"),
        "capture_reason": capture_reason or item.personal.get("capture_reason"),
        "archive_level": item.personal.get("archive_level") or "readable",
        "content_hash": _body_hash(body),
    }
    frontmatter = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{frontmatter}\n---\n{body}", meta["content_hash"]


def _read_sync_row(conn, item_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT item_id, vault_path, content_hash, updated_at, last_synced_at, status, conflict_count, data_json "
        "FROM vault_sync_state WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    if not row:
        return None
    payload = {
        "item_id": row["item_id"],
        "vault_path": row["vault_path"] or "",
        "content_hash": row["content_hash"] or "",
        "updated_at": row["updated_at"] or "",
        "last_synced_at": row["last_synced_at"] or "",
        "status": row["status"] or "",
        "conflict_count": int(row["conflict_count"] or 0),
        "data": {},
    }
    if row["data_json"]:
        try:
            payload["data"] = json.loads(row["data_json"])
        except json.JSONDecodeError:
            payload["data"] = {}
    return payload


def _upsert_sync_row(
    conn,
    *,
    item_id: str,
    vault_path: str,
    content_hash: str,
    updated_at: str,
    last_synced_at: str | None,
    status: str,
    conflict_count: int = 0,
    data: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO vault_sync_state
        (item_id, vault_path, content_hash, updated_at, last_synced_at, status, conflict_count, data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            vault_path = excluded.vault_path,
            content_hash = excluded.content_hash,
            updated_at = excluded.updated_at,
            last_synced_at = excluded.last_synced_at,
            status = excluded.status,
            conflict_count = excluded.conflict_count,
            data_json = excluded.data_json
        """,
        (
            item_id,
            _normalize_path_value(vault_path),
            content_hash,
            updated_at,
            last_synced_at,
            status,
            int(conflict_count),
            json.dumps(data or {}, ensure_ascii=False),
        ),
    )


def _iter_items(limit: int = _ITEM_LIMIT) -> list[IntelItem]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT data_json, created_at FROM intel_items ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    items: list[IntelItem] = []
    for row in rows:
        try:
            item = IntelItem.from_dict(json.loads(row["data_json"]))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        item.personal.setdefault("saved_at", row["created_at"])
        items.append(item)
    return items


def _choose_note_dir(item: IntelItem, capture_reason: str | None, layout: dict[str, Path]) -> Path:
    reason = str(capture_reason or item.personal.get("capture_reason") or "").lower()
    if reason in {"auto_save", "dwell_auto", "extension_auto", "auto_capture"}:
        return layout["inbox"]
    source = _safe_name(item.source or "web", fallback="web")
    return layout["sources"] / source


def _find_existing_note(layout: dict[str, Path], item_id: str) -> Path | None:
    for path in layout["root"].rglob("*.md"):
        if path.is_dir() or "/_osint/" in path.as_posix():
            continue
        try:
            meta, _body = _frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if str(meta.get("id") or "") == item_id:
            return path
    return None


def _note_path(item: IntelItem, layout: dict[str, Path], existing: str = "", capture_reason: str | None = None) -> Path:
    if existing:
        candidate = layout["root"] / Path(existing)
        if candidate.exists():
            return candidate
    found = _find_existing_note(layout, item.id)
    if found:
        return found
    target_dir = _choose_note_dir(item, capture_reason, layout)
    date_prefix = str(item.personal.get("saved_at") or _now())[:10]
    base = f"{date_prefix} - {_safe_name(item.title or item.url, fallback='item')} - {item.id[:8]}"
    return target_dir / f"{base}.md"


def _write_metadata_files(root: Path, items: list[IntelItem], conflicts: list[dict[str, Any]]) -> None:
    layout = _ensure_layout(root)
    for directory in (layout["topics"], layout["entities"], layout["concepts"], layout["projects"]):
        for path in directory.glob("*.md"):
            try:
                path.unlink()
            except OSError:
                pass
    topic_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    entity_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    concept_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    project_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    index_items: list[dict[str, Any]] = []
    for item in items:
        rel_path = _normalize_path_value(item.personal.get("vault_path"))
        concepts = _as_list(item.personal.get("concepts"))
        project = str(item.personal.get("project") or "")
        index_items.append(
            {
                "id": item.id,
                "title": item.title,
                "source": item.source,
                "url": item.url,
                "vault_path": rel_path,
                "topics": item.topics or [],
                "entities": _extract_entities(item),
                "concepts": concepts,
                "project": project,
                "updated_at": item.personal.get("vault_updated_at"),
                "conflict": bool(item.personal.get("vault_conflict")),
            }
        )
        for topic in item.topics or []:
            topic_map[topic].append({"title": item.title, "path": rel_path, "url": item.url})
        for entity in _extract_entities(item):
            entity_map[entity].append({"title": item.title, "path": rel_path, "url": item.url})
        for concept in concepts:
            concept_map[concept].append({"title": item.title, "path": rel_path, "url": item.url})
        if project:
            project_map[project].append({"title": item.title, "path": rel_path, "url": item.url})
    index_payload = {
        "generated_at": _now(),
        "item_count": len(index_items),
        "conflict_count": len(conflicts),
        "items": index_items,
    }
    atomic_write_text(layout["meta"] / "index.json", json.dumps(index_payload, ensure_ascii=False, indent=2))

    graph_payload = knowledge_graph.get_graph(limit=1000)
    atomic_write_text(
        layout["meta"] / "graph.json",
        json.dumps({"generated_at": _now(), **graph_payload}, ensure_ascii=False, indent=2),
    )
    atomic_write_text(
        layout["meta"] / "sync-state.json",
        json.dumps(
            {
                "schema_version": _SYNC_STATE_SCHEMA_VERSION,
                "generated_at": _now(),
                "device_id": _local_device_id(create=True),
                "provider": _cloud_cfg()["provider"],
                "sync_mode": _cloud_cfg()["sync_mode"],
                "vault_path": str(root),
                "is_onedrive_vault": bool(_matched_onedrive_root(root)),
                "conflicts": conflicts,
                "item_count": len(index_items),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    for topic, linked in topic_map.items():
        safe = _safe_name(topic, fallback="topic")
        lines = [f"# {topic}", "", f"- 条目数: {len(linked)}", "", "## 条目", ""]
        for entry in linked[:200]:
            if entry["path"]:
                lines.append(f"- [[{entry['path'][:-3]}|{entry['title']}]]")
            else:
                lines.append(f"- {entry['title']}")
        atomic_write_text(layout["topics"] / f"{safe}.md", "\n".join(lines).strip() + "\n")
    for entity, linked in entity_map.items():
        safe = _safe_name(entity, fallback="entity")
        lines = [f"# {entity}", "", f"- 条目数: {len(linked)}", "", "## 条目", ""]
        for entry in linked[:200]:
            if entry["path"]:
                lines.append(f"- [[{entry['path'][:-3]}|{entry['title']}]]")
            else:
                lines.append(f"- {entry['title']}")
        atomic_write_text(layout["entities"] / f"{safe}.md", "\n".join(lines).strip() + "\n")
    for concept, linked in concept_map.items():
        safe = _safe_name(concept, fallback="concept")
        lines = [f"# {concept}", "", f"- 条目数: {len(linked)}", "", "## 条目", ""]
        for entry in linked[:200]:
            if entry["path"]:
                lines.append(f"- [[{entry['path'][:-3]}|{entry['title']}]]")
            else:
                lines.append(f"- {entry['title']}")
        atomic_write_text(layout["concepts"] / f"{safe}.md", "\n".join(lines).strip() + "\n")
    for project, linked in project_map.items():
        safe = _safe_name(project, fallback="project")
        lines = [f"# {project}", "", f"- 条目数: {len(linked)}", "", "## 条目", ""]
        for entry in linked[:200]:
            if entry["path"]:
                lines.append(f"- [[{entry['path'][:-3]}|{entry['title']}]]")
            else:
                lines.append(f"- {entry['title']}")
        atomic_write_text(layout["projects"] / f"{safe}.md", "\n".join(lines).strip() + "\n")


def _write_daily_and_runs(root: Path) -> dict[str, int]:
    layout = _ensure_layout(root)
    daily_count = 0
    digests_dir = get_data_dir() / "digests"
    if digests_dir.exists():
        for digest in digests_dir.glob("*.md"):
            atomic_write_text(layout["daily"] / digest.name, digest.read_text(encoding="utf-8"))
            daily_count += 1
    run_count = 0
    runs_dir = get_data_dir() / "runs"
    if runs_dir.exists():
        for run_dir in runs_dir.iterdir():
            report = run_dir / "report.md"
            if not run_dir.is_dir() or not report.exists():
                continue
            atomic_write_text(layout["runs"] / f"{run_dir.name}.md", report.read_text(encoding="utf-8"))
            run_count += 1
    return {"daily": daily_count, "runs": run_count}


def _load_conflicts_from_db() -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT item_id, vault_path, data_json, updated_at "
            "FROM vault_sync_state WHERE status = 'conflict' OR conflict_count > 0"
        ).fetchall()
    finally:
        conn.close()
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        payload: dict[str, Any] = {}
        if row["data_json"]:
            try:
                payload = json.loads(row["data_json"])
            except json.JSONDecodeError:
                payload = {}
        payload.setdefault("item_id", row["item_id"])
        payload.setdefault("note_path", row["vault_path"] or "")
        payload.setdefault("detected_at", row["updated_at"] or "")
        conflicts.append(payload)
    return conflicts


def list_cloud_conflicts(limit: int = 100) -> list[dict[str, Any]]:
    conflicts = _load_conflicts_from_db()
    root = vault_root()
    if root and root.exists():
        seen = {
            str(conflict.get("conflict_path") or conflict.get("note_path") or "")
            for conflict in conflicts
        }
        for path in root.rglob("*.conflict-*.md"):
            rel = _normalize_path_value(path.relative_to(root))
            if rel in seen:
                continue
            item_id = path.stem.split(".conflict-", 1)[0]
            try:
                meta, _body = _frontmatter(path.read_text(encoding="utf-8"))
                item_id = str(meta.get("id") or item_id)
            except (OSError, UnicodeDecodeError):
                pass
            conflicts.append(
                {
                    "item_id": item_id,
                    "conflict_path": rel,
                    "detected_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                }
            )
    conflicts.sort(key=lambda entry: str(entry.get("detected_at") or ""), reverse=True)
    return conflicts[: max(1, min(int(limit), 500))]


def _apply_links(items: list[IntelItem]) -> int:
    by_id = {item.id: item for item in items}
    topic_map: dict[str, list[str]] = defaultdict(list)
    entity_map: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for topic in item.topics or []:
            topic_map[topic].append(item.id)
        for entity in _extract_entities(item):
            entity_map[entity].append(item.id)
    links: set[tuple[str, str, str, str]] = set()
    for topic, ids in topic_map.items():
        unique = sorted(set(ids))[:120]
        for index, source_id in enumerate(unique):
            for target_id in unique[index + 1 :]:
                links.add((source_id, target_id, "same_topic", topic))
    for entity, ids in entity_map.items():
        unique = sorted(set(ids))[:120]
        for index, source_id in enumerate(unique):
            for target_id in unique[index + 1 :]:
                links.add((source_id, target_id, "same_entity", entity))
    conn = connect()
    try:
        conn.execute("DELETE FROM knowledge_links")
        for source_id, target_id, relation, evidence in sorted(links):
            if source_id not in by_id or target_id not in by_id:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO knowledge_links "
                "(from_item_id, to_item_id, relation, confidence, evidence) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_id, target_id, relation, 0.85, evidence),
            )
        conn.commit()
    finally:
        conn.close()
    return len(links)


def sync_item_to_cloud(
    item: IntelItem,
    *,
    capture_reason: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = vault_root(create=True)
    if root is None:
        return {"enabled": False, "ready": False, "status": "disabled"}
    cfg = _cloud_cfg()
    layout = _ensure_layout(root)
    item.personal.setdefault("saved_at", _now())
    if capture_reason:
        item.personal["capture_reason"] = capture_reason
    conn = connect()
    try:
        sync_row = _read_sync_row(conn, item.id) or {}
    finally:
        conn.close()
    target = _note_path(item, layout, existing=str(sync_row.get("vault_path") or ""), capture_reason=capture_reason)
    updated_at = _now()
    note_text, content_hash = _note_text(item, capture_reason=capture_reason, updated_at=updated_at)
    rel_path = _normalize_path_value(target.relative_to(root))
    queue_only = not force and cfg["sync_mode"] in {"manual", "scheduled"}
    if queue_only:
        last_synced_at = str(sync_row.get("last_synced_at") or "") or None
        conn = connect()
        try:
            _upsert_sync_row(
                conn,
                item_id=item.id,
                vault_path=rel_path,
                content_hash=content_hash,
                updated_at=updated_at,
                last_synced_at=last_synced_at,
                status="pending",
                conflict_count=0,
                data={"queued_at": updated_at, "sync_mode": cfg["sync_mode"]},
            )
            conn.commit()
        finally:
            conn.close()
        item.personal["vault_path"] = rel_path
        item.personal["vault_updated_at"] = updated_at
        item.personal["vault_conflict"] = False
        item.personal["vault_sync_pending"] = True
        return {
            "enabled": True,
            "ready": True,
            "status": "pending",
            "vault_path": rel_path,
            "sync_mode": cfg["sync_mode"],
            "pending": True,
        }
    conflict_info: dict[str, Any] | None = None
    if target.exists():
        existing_text = target.read_text(encoding="utf-8")
        meta, body = _frontmatter(existing_text)
        actual_hash = _body_hash(body)
        stored_hash = str(meta.get("content_hash") or "")
        if str(meta.get("id") or item.id) == item.id and stored_hash and actual_hash != stored_hash:
            conflict_name = target.with_name(f"{target.stem}.conflict-{_timestamp_slug()}{target.suffix}")
            atomic_write_text(conflict_name, note_text)
            conflict_info = {
                "item_id": item.id,
                "note_path": _normalize_path_value(target.relative_to(root)),
                "conflict_path": _normalize_path_value(conflict_name.relative_to(root)),
                "detected_at": _now(),
            }
        else:
            atomic_write_text(target, note_text)
    else:
        atomic_write_text(target, note_text)
    conn = connect()
    try:
        _upsert_sync_row(
            conn,
            item_id=item.id,
            vault_path=rel_path,
            content_hash=content_hash,
            updated_at=updated_at,
            last_synced_at=_now(),
            status="conflict" if conflict_info else "synced",
            conflict_count=1 if conflict_info else 0,
            data=conflict_info or {},
        )
        conn.commit()
    finally:
        conn.close()
    item.personal["vault_path"] = rel_path
    item.personal["vault_updated_at"] = updated_at
    item.personal["vault_conflict"] = bool(conflict_info)
    item.personal["vault_sync_pending"] = False
    if conflict_info:
        item.personal["vault_conflict_path"] = conflict_info["conflict_path"]
    return {
        "enabled": True,
        "ready": True,
        "status": "conflict" if conflict_info else "synced",
        "vault_path": rel_path,
        "conflict": conflict_info,
    }


def sync_cloud() -> dict[str, Any]:
    root = vault_root(create=True)
    if root is None:
        return get_cloud_status()
    items = _iter_items()
    knowledge_graph.enrich_items(items, persist_items=True)
    conflicts: list[dict[str, Any]] = []
    updated_items: list[IntelItem] = []
    for item in items:
        result = sync_item_to_cloud(
            item,
            capture_reason=str(item.personal.get("capture_reason") or "sync"),
            force=True,
        )
        if result.get("conflict"):
            conflicts.append(result["conflict"])
        save_item(item)
        updated_items.append(item)
    link_count = _apply_links(updated_items)
    exported = _write_daily_and_runs(root)
    _write_metadata_files(root, updated_items, conflicts)
    return {
        **get_cloud_status(),
        "ok": True,
        "synced_items": len(updated_items),
        "link_count": link_count,
        "daily_exported": exported["daily"],
        "run_reports_exported": exported["runs"],
        "conflicts": conflicts,
    }


def backup_cloud() -> dict[str, Any]:
    synced = sync_cloud()
    root = vault_root(create=True)
    if root is None:
        return synced
    layout = _ensure_layout(root)
    backup_name = f"{_timestamp_slug()}.json"
    payload = {
        "created_at": _now(),
        "status": synced,
    }
    atomic_write_text(layout["backups"] / backup_name, json.dumps(payload, ensure_ascii=False, indent=2))
    synced["backup_path"] = _normalize_path_value((layout["backups"] / backup_name).relative_to(root))
    return synced


def refresh_cloud_indexes() -> dict[str, Any]:
    root = vault_root(create=True)
    if root is None:
        return get_cloud_status()
    items = _iter_items()
    knowledge_graph.enrich_items(items, persist_items=True)
    link_count = _apply_links(items)
    conflicts = _load_conflicts_from_db()
    exported = _write_daily_and_runs(root)
    _write_metadata_files(root, items, conflicts)
    return {
        **get_cloud_status(),
        "ok": True,
        "link_count": link_count,
        "daily_exported": exported["daily"],
        "run_reports_exported": exported["runs"],
    }


def init_cloud(
    *,
    provider: str = "auto",
    vault_path: str | None = None,
    onedrive_root: str | None = None,
    vault_name: str | None = None,
    sync_mode: str = "manual",
    sync_after: bool = False,
) -> dict[str, Any]:
    allowed = {"auto", "local_folder", "onedrive_folder", "rclone", "webdav", "syncthing", "git"}
    if provider not in allowed:
        raise ValueError(f"unsupported cloud provider: {provider}")
    mode = _normalize_sync_mode(sync_mode)
    selected = provider
    if selected == "auto":
        selected = "onedrive_folder" if _detect_onedrive_candidates() else "local_folder"
    if vault_path:
        root = Path(vault_path).expanduser().resolve()
    elif selected == "onedrive_folder" and onedrive_root:
        candidate = Path(onedrive_root).expanduser().resolve()
        known_roots = {str(path).lower(): path for path in _detect_onedrive_candidates()}
        if str(candidate).lower() not in known_roots:
            raise ValueError("所选 OneDrive 根目录不在当前检测结果中")
        root = candidate / _safe_name(vault_name or _DEFAULT_VAULT_NAME, fallback=_DEFAULT_VAULT_NAME)
    else:
        recommended = _recommended_vault_path(selected)
        if recommended is None:
            raise ValueError(f"vault_path is required for provider: {selected}")
        root = recommended.expanduser().resolve()
    if selected == "onedrive_folder":
        matched_root = _matched_onedrive_root(root)
        if matched_root is None:
            raise ValueError("OneDrive vault 必须位于检测到的 OneDrive 根目录下")
    if get_data_dir().resolve() in root.parents or root == get_data_dir().resolve():
        # This is allowed for local fallback, but never for cloud-flavored providers.
        if selected != "local_folder":
            raise ValueError("cloud vault must not be placed inside ~/.osint")
    _ensure_layout(root)
    config_path = save_user_config_patch(
        {
            "knowledge": {
                "cloud": {
                    "enabled": True,
                    "provider": selected,
                    "vault_path": str(root),
                    "sync_mode": mode,
                }
            }
        }
    )
    reset_config_cache()
    status = sync_cloud() if sync_after else get_cloud_status()
    return {
        **status,
        "ok": True,
        "config_path": config_path,
        "provider": selected,
        "vault_path": str(root),
        "sync_mode": mode,
    }


def _item_from_note(path: Path, root: Path) -> IntelItem | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    meta, body = _frontmatter(text)
    if not meta:
        return None
    human_body, machine_body = _parse_machine_payload(body)
    payload: dict[str, Any] = {}
    if machine_body:
        try:
            payload = json.loads(machine_body)
        except json.JSONDecodeError:
            payload = {}
    item = IntelItem(
        id=str(meta.get("id") or path.stem),
        source=str(meta.get("source") or "web"),
        type=str(meta.get("type") or "note"),
        url=str(meta.get("url") or ""),
        title=str(meta.get("title") or path.stem),
        author=str(meta.get("author") or ""),
        published_at=meta.get("published_at"),
        content=str(payload.get("content") or human_body or ""),
        summary=str(meta.get("summary") or payload.get("summary") or ""),
        key_points=payload.get("key_points") or [],
        topics=meta.get("topics") or payload.get("topics") or [],
        layers=payload.get("layers") or {},
        personal=payload.get("personal") or {},
    )
    item.personal["saved_at"] = str(meta.get("saved_at") or item.personal.get("saved_at") or _now())
    item.personal["vault_path"] = _normalize_path_value(path.relative_to(root))
    item.personal["vault_updated_at"] = str(meta.get("updated_at") or "")
    item.personal["vault_conflict"] = path.name.endswith(".md") and ".conflict-" in path.name
    item.personal["capture_reason"] = str(meta.get("capture_reason") or item.personal.get("capture_reason") or "")
    item.personal["archive_level"] = str(meta.get("archive_level") or item.personal.get("archive_level") or "readable")
    if meta.get("run_id"):
        item.personal["run_id"] = str(meta["run_id"])
    if meta.get("citation_id"):
        item.personal["citation_id"] = str(meta["citation_id"])
    if meta.get("dwell_sec") is not None:
        item.personal["dwell_sec"] = int(meta["dwell_sec"])
    tags = _as_list(meta.get("tags"))
    if tags:
        item.personal["tags"] = tags
    entities = _as_list(meta.get("entities"))
    if entities:
        item.personal["entities"] = entities
    concepts = _as_list(meta.get("concepts") or payload.get("concepts"))
    if concepts:
        item.personal["concepts"] = concepts
    claims = _as_list(meta.get("claims") or payload.get("claims"))
    if claims:
        item.personal["claims"] = claims
    questions = _as_list(meta.get("questions") or payload.get("questions"))
    if questions:
        item.personal["questions"] = questions
    relations = meta.get("relations") or payload.get("relations")
    if isinstance(relations, list):
        item.personal["relations"] = relations
    if meta.get("project") or payload.get("project"):
        item.personal["project"] = str(meta.get("project") or payload.get("project") or "")
    if meta.get("confidence") is not None or payload.get("confidence") is not None:
        try:
            item.personal["confidence"] = float(meta.get("confidence") or payload.get("confidence") or 0)
        except (TypeError, ValueError):
            pass
    evidence_refs = _as_list(meta.get("evidence_refs") or payload.get("evidence_refs"))
    if evidence_refs:
        item.personal["evidence_refs"] = evidence_refs
    return item


def reindex_cloud() -> dict[str, Any]:
    root = vault_root()
    if root is None or not root.exists():
        return get_cloud_status()
    items: dict[str, IntelItem] = {}
    conflicts: list[dict[str, Any]] = []
    conflict_ids: set[str] = set()
    for path in root.rglob("*.md"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("_osint/", "Topics/", "Entities/", "Concepts/", "Projects/")):
            continue
        item = _item_from_note(path, root)
        if item is None:
            continue
        if item.personal.get("vault_conflict"):
            conflict_ids.add(item.id)
            conflicts.append(
                {
                    "item_id": item.id,
                    "conflict_path": rel,
                    "detected_at": item.personal.get("vault_updated_at") or _now(),
                }
            )
            continue
        items[item.id] = item
    seen_ids = set(items) | set(conflict_ids)
    conn = connect()
    try:
        existing_rows = conn.execute("SELECT item_id FROM vault_sync_state").fetchall()
        stale_ids = [str(row["item_id"]) for row in existing_rows if str(row["item_id"]) not in seen_ids]
        if stale_ids:
            placeholders = ",".join("?" for _ in stale_ids)
            conn.execute(f"DELETE FROM intel_fts WHERE item_id IN ({placeholders})", stale_ids)
            conn.execute(f"DELETE FROM intel_items WHERE id IN ({placeholders})", stale_ids)
            conn.execute(f"DELETE FROM vault_sync_state WHERE item_id IN ({placeholders})", stale_ids)
        else:
            stale_ids = []
        conn.commit()
    finally:
        conn.close()
    for item in items.values():
        item.personal["vault_conflict"] = item.id in conflict_ids
        knowledge_graph.enrich_item_object(item)
        save_item(item)
    conn = connect()
    try:
        for item in items.values():
            _upsert_sync_row(
                conn,
                item_id=item.id,
                vault_path=str(item.personal.get("vault_path") or ""),
                content_hash="",
                updated_at=str(item.personal.get("vault_updated_at") or ""),
                last_synced_at=_now(),
                status="conflict" if item.id in conflict_ids else "synced",
                conflict_count=1 if item.id in conflict_ids else 0,
                data={},
            )
        conn.commit()
    finally:
        conn.close()
    link_count = _apply_links(list(items.values()))
    _write_metadata_files(root, list(items.values()), conflicts)
    return {
        **get_cloud_status(),
        "ok": True,
        "reindexed_items": len(items),
        "pruned_items": len(stale_ids),
        "link_count": link_count,
        "conflicts": conflicts,
    }


def _read_sync_state_meta(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {}
    path = root / "_osint" / "sync-state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _path_health(root: Path | None) -> dict[str, Any]:
    if root is None or not root.exists():
        return {
            "checked_files": 0,
            "max_abs_path": 0,
            "max_rel_path": 0,
            "long_path_count": 0,
            "unsafe_name_count": 0,
            "examples": [],
        }
    checked = 0
    max_abs = 0
    max_rel = 0
    long_path_count = 0
    unsafe_name_count = 0
    examples: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        checked += 1
        rel = path.relative_to(root).as_posix()
        abs_len = len(str(path))
        rel_len = len(rel)
        max_abs = max(max_abs, abs_len)
        max_rel = max(max_rel, rel_len)
        if abs_len >= 240:
            long_path_count += 1
            if len(examples) < 5:
                examples.append(rel)
        name = path.name
        if _ONEDRIVE_UNSAFE_NAME_RE.search(name) or name.endswith((" ", ".")):
            unsafe_name_count += 1
            if len(examples) < 5 and rel not in examples:
                examples.append(rel)
    return {
        "checked_files": checked,
        "max_abs_path": max_abs,
        "max_rel_path": max_rel,
        "long_path_count": long_path_count,
        "unsafe_name_count": unsafe_name_count,
        "examples": examples,
    }


def _layout_health(root: Path | None) -> dict[str, bool]:
    if root is None:
        return {}
    required = {
        "Inbox": root / "Inbox",
        "Sources": root / "Sources",
        "Concepts": root / "Concepts",
        "Projects": root / "Projects",
        "_osint": root / "_osint",
        "index.json": root / "_osint" / "index.json",
        "graph.json": root / "_osint" / "graph.json",
        "sync-state.json": root / "_osint" / "sync-state.json",
    }
    return {name: path.exists() for name, path in required.items()}


def _cloud_health(
    *,
    cfg: dict[str, Any],
    root: Path | None,
    conflict_count: int,
    item_count: int,
) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    matched_root = _matched_onedrive_root(root)
    checks["is_onedrive_vault"] = bool(matched_root)
    checks["matched_onedrive_root"] = str(matched_root) if matched_root else ""
    checks["layout"] = _layout_health(root)
    checks["path_health"] = _path_health(root)
    checks["local_device_id"] = _local_device_id(create=False)
    checks["sync_state_meta"] = _read_sync_state_meta(root)
    checks["writable"] = bool(root and root.exists() and os.access(root, os.W_OK))

    if root is None:
        issues.append("未配置 Markdown vault，跨设备同步与恢复未启用。")
    elif not root.exists():
        issues.append("vault 路径不存在，当前无法同步或重建。")
    else:
        if not checks["writable"]:
            issues.append("vault 目录当前不可写，后续同步可能失败。")
        layout = checks["layout"]
        if not layout.get("Inbox", False) or not layout.get("Sources", False) or not layout.get("_osint", False):
            warnings.append("vault 目录结构不完整，建议重新初始化或执行一次同步。")
        if item_count > 0 and not layout.get("index.json", False):
            warnings.append("缺少 _osint/index.json，跨设备浏览和恢复信息可能不完整。")
        if item_count > 0 and not layout.get("sync-state.json", False):
            warnings.append("缺少 _osint/sync-state.json，设备间状态追踪会变弱。")

    if cfg["provider"] == "onedrive_folder" and root and not matched_root:
        issues.append("当前 provider=onedrive_folder，但 vault_path 不在检测到的 OneDrive 目录下。")
    if matched_root and checks["path_health"]["long_path_count"] > 0:
        warnings.append("检测到较长路径条目，OneDrive/Windows 上可能出现同步或打开风险。")
    if checks["path_health"]["unsafe_name_count"] > 0:
        warnings.append("检测到潜在的 OneDrive 不安全文件名，请检查 path_health.examples。")
    if conflict_count > 0:
        warnings.append("当前存在待合并冲突副本，建议先处理后再跨设备编辑。")
    if cfg["sync_mode"] == "scheduled":
        warnings.append("scheduled 模式当前先进入待同步队列，自动调度尚未启用，请手动触发 cloud sync。")
    if cfg["sync_mode"] == "manual" and root is not None:
        warnings.append("manual 模式下新收录会先留在本地索引，执行 cloud sync 后才会写入 vault。")

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "checks": checks,
    }


def get_cloud_status() -> dict[str, Any]:
    cfg = _cloud_cfg()
    root = vault_root()
    recommended = _recommended_vault_path(cfg["provider"])
    conflict_count = 0
    item_count = 0
    last_synced_at = ""
    statuses: dict[str, int] = {}
    conn = connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM vault_sync_state "
            "WHERE status = 'conflict' OR conflict_count > 0"
        ).fetchone()
        conflict_count = int(row["c"] or 0) if row else 0
        row = conn.execute("SELECT COUNT(*) AS c FROM vault_sync_state").fetchone()
        item_count = int(row["c"] or 0) if row else 0
        row = conn.execute("SELECT MAX(last_synced_at) AS ts FROM vault_sync_state").fetchone()
        last_synced_at = str(row["ts"] or "") if row else ""
        for row in conn.execute("SELECT status, COUNT(*) AS c FROM vault_sync_state GROUP BY status"):
            statuses[str(row["status"] or "unknown")] = int(row["c"] or 0)
    finally:
        conn.close()
    conflicts = list_cloud_conflicts(limit=20)
    conflict_count = max(conflict_count, len(conflicts))
    health = _cloud_health(cfg=cfg, root=root, conflict_count=conflict_count, item_count=item_count)
    matched_root = health["checks"].get("matched_onedrive_root") or ""
    sync_state_meta = health["checks"].get("sync_state_meta") or {}
    return {
        "enabled": cfg["enabled"],
        "provider": cfg["provider"],
        "sync_mode": cfg["sync_mode"],
        "vault_path": str(root) if root else "",
        "vault_exists": bool(root and root.exists()),
        "ready": bool(root),
        "recommended_vault_path": str(recommended) if recommended else "",
        "one_drive_candidates": [str(path) for path in _detect_onedrive_candidates()],
        "one_drive_targets": _onedrive_targets(),
        "is_onedrive_vault": bool(matched_root),
        "matched_onedrive_root": matched_root,
        "include_attachments": cfg["include_attachments"],
        "include_raw_archives": cfg["include_raw_archives"],
        "item_count": item_count,
        "conflict_count": conflict_count,
        "conflicts": conflicts,
        "last_synced_at": last_synced_at,
        "statuses": statuses,
        "sync_state_schema_version": sync_state_meta.get("schema_version"),
        "last_writer_device_id": sync_state_meta.get("device_id", ""),
        "health": health,
    }
