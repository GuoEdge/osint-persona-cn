"""Persona 存储 / Persona storage."""

from __future__ import annotations

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
    return sorted(persona_dir().glob("mental_model.v*.yaml"))


def rollback_version(version: int) -> bool:
    src = persona_dir() / f"mental_model.v{version}.yaml"
    if not src.exists():
        return False
    mental_model_path().write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return True
