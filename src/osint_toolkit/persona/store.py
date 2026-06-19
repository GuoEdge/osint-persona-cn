"""Persona 存储 / Persona storage."""

from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from osint_toolkit.auth.paths import get_data_dir

DEFAULT_MODEL: dict[str, Any] = {
    "version": 1,
    "boost_authors": [],
    "block_patterns": [],
    "endorsement_patterns": {},
    "entertainment_boundary": {"policy": "observe_only"},
}


def persona_dir() -> Path:
    path = get_data_dir() / "persona"
    path.mkdir(parents=True, exist_ok=True)
    return path


def mental_model_path() -> Path:
    return persona_dir() / "mental_model.yaml"


def persona_brief_path() -> Path:
    return persona_dir() / "persona_brief.md"


def load_mental_model() -> dict[str, Any]:
    path = mental_model_path()
    if not path.exists():
        return dict(DEFAULT_MODEL)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    merged = dict(DEFAULT_MODEL)
    merged.update(data)
    return merged


def save_mental_model(data: dict[str, Any]) -> Path:
    path = mental_model_path()
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def load_persona_brief() -> str:
    path = persona_brief_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def save_persona_brief(text: str) -> Path:
    path = persona_brief_path()
    path.write_text(text, encoding="utf-8")
    return path


def list_versions() -> list[Path]:
    return sorted(
        persona_dir().glob("mental_model.v*.yaml"),
        key=lambda p: _version_from_stem(p.stem),
    )


def _version_from_stem(stem: str) -> int:
    match = re.search(r"v(\d+)$", stem)
    return int(match.group(1)) if match else 0


def _iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def archive_brief_version(version: int) -> None:
    if version < 1:
        return
    src = persona_brief_path()
    if not src.exists():
        return
    dst = persona_dir() / f"persona_brief.v{version}.md"
    if not dst.exists():
        shutil.copy2(src, dst)


def list_version_entries(*, current_version: int | None = None) -> list[dict[str, Any]]:
    """画像版本元数据（含构建时间），供 Web 时间线/热力图展示。"""
    current_model = load_mental_model()
    if current_version is None:
        current_version = int(current_model.get("version") or 0)
    entries: list[dict[str, Any]] = []
    seen: set[int] = set()
    for path in list_versions():
        ver = _version_from_stem(path.stem)
        if ver < 1:
            continue
        seen.add(ver)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        built_at = data.get("built_at") or _iso_from_mtime(path)
        brief_path = persona_dir() / f"persona_brief.v{ver}.md"
        entries.append(
            {
                "version": ver,
                "label": f"v{ver}",
                "built_at": built_at,
                "events_at_last_build": data.get("events_at_last_build"),
                "brief_ai_generated": bool(data.get("brief_ai_generated")),
                "has_brief_archive": brief_path.exists(),
                "is_current": ver == current_version,
            }
        )
    if current_version >= 1 and current_version not in seen:
        model_path = mental_model_path()
        built_at = current_model.get("built_at")
        if not built_at and model_path.exists():
            built_at = _iso_from_mtime(model_path)
        brief_path = persona_dir() / f"persona_brief.v{current_version}.md"
        entries.append(
            {
                "version": current_version,
                "label": f"v{current_version}",
                "built_at": built_at or "",
                "events_at_last_build": current_model.get("events_at_last_build"),
                "brief_ai_generated": bool(current_model.get("brief_ai_generated")),
                "has_brief_archive": brief_path.exists(),
                "is_current": True,
            }
        )
    entries.sort(key=lambda item: int(item["version"]), reverse=True)
    return entries


def rollback_version(version: int) -> bool:
    src = persona_dir() / f"mental_model.v{version}.yaml"
    if not src.exists():
        return False
    mental_model_path().write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    brief_src = persona_dir() / f"persona_brief.v{version}.md"
    if brief_src.exists():
        persona_brief_path().write_text(brief_src.read_text(encoding="utf-8"), encoding="utf-8")
    return True
