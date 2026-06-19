"""路径安全校验 / Safe path segment validation."""

from __future__ import annotations

import re
from pathlib import Path

RUN_ID_RE = re.compile(r"^\d{8}-\d{6}-[a-f0-9]{8}$")
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$", re.IGNORECASE)
PROMPT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class PathSecurityError(ValueError):
    """用户输入的路径片段不合法。"""


def assert_run_id(run_id: str) -> str:
    value = str(run_id or "").strip()
    if not RUN_ID_RE.fullmatch(value):
        raise PathSecurityError(f"invalid run_id: {run_id!r}")
    return value


def assert_safe_id(value: str, *, label: str = "id") -> str:
    text = str(value or "").strip()
    if not SAFE_ID_RE.fullmatch(text):
        raise PathSecurityError(f"invalid {label}: {value!r}")
    return text


def assert_safe_filename(name: str) -> str:
    text = str(name or "").strip()
    if not text or text in {".", ".."}:
        raise PathSecurityError(f"invalid filename: {name!r}")
    if "/" in text or "\\" in text or ".." in text:
        raise PathSecurityError(f"invalid filename: {name!r}")
    if not SAFE_FILENAME_RE.fullmatch(text):
        raise PathSecurityError(f"invalid filename: {name!r}")
    return text


def assert_domain(domain: str) -> str:
    text = str(domain or "").strip().lower()
    if text.startswith("."):
        text = text[1:]
    if not text or len(text) > 253:
        raise PathSecurityError(f"invalid domain: {domain!r}")
    if "/" in text or "\\" in text or ".." in text:
        raise PathSecurityError(f"invalid domain: {domain!r}")
    if not DOMAIN_RE.fullmatch(text):
        raise PathSecurityError(f"invalid domain: {domain!r}")
    return text


def assert_prompt_name(name: str) -> str:
    text = str(name or "").strip()
    if not PROMPT_NAME_RE.fullmatch(text):
        raise PathSecurityError(f"invalid prompt name: {name!r}")
    return text


def resolve_under(root: Path, *parts: str) -> Path:
    """解析路径并确保结果在 root 之下。"""
    root_resolved = root.resolve()
    candidate = root_resolved
    for part in parts:
        if not part:
            continue
        segment = str(part).replace("\\", "/")
        if segment.startswith("/") or ".." in segment.split("/"):
            raise PathSecurityError(f"unsafe path segment: {part!r}")
        candidate = candidate / segment
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathSecurityError(f"path escapes root: {parts!r}") from exc
    return resolved
