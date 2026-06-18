"""统一 API 密钥解析与持久化 / Unified secret resolution and persistence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

from pathlib import Path

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.utils.config import _deep_merge, _expand_env


@dataclass(frozen=True)
class SecretSpec:
    id: str
    label: str
    env_var: str
    config_path: tuple[str, ...]
    description: str
    optional: bool = True


SECRET_SPECS: dict[str, SecretSpec] = {
    "deepseek": SecretSpec(
        id="deepseek",
        label="DeepSeek API Key",
        env_var="DEEPSEEK_API_KEY",
        config_path=("ai", "api_key"),
        description="AI 摘要、搜罗报告、关联词扩展、追问",
    ),
    "zhihu_openapi": SecretSpec(
        id="zhihu_openapi",
        label="知乎开放平台 Access Secret",
        env_var="ZHIHU_ACCESS_SECRET",
        config_path=("zhihu", "openapi", "access_secret"),
        description="知乎官方站内搜索与热榜（免 Cookie）",
    ),
}


def user_config_path() -> Path:
    return get_data_dir() / "config.yaml"


def load_user_config_raw() -> dict[str, Any]:
    path = user_config_path()
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_user_config_patch(patch: dict[str, Any]) -> str:
    """Deep-merge patch into ~/.osint/config.yaml and return path string."""
    path = user_config_path()
    merged = _deep_merge(load_user_config_raw(), patch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(path)


def _env_from_windows_user(name: str) -> str | None:
    if os.name != "nt":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value).strip() or None
    except OSError:
        return None


def _nested_get(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _nested_set(data: dict[str, Any], path: tuple[str, ...], value: Any) -> dict[str, Any]:
    root = dict(data)
    cur = root
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value
    return root


def _literal_from_user_config(spec: SecretSpec) -> str:
    raw = _nested_get(load_user_config_raw(), spec.config_path)
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text or text.startswith("${"):
        return ""
    return text


def resolve_secret(secret_id: str, *, explicit: str | None = None) -> str:
    """解析密钥：explicit → 环境变量 → Windows 用户环境 → ~/.osint/config.yaml 明文。"""
    spec = SECRET_SPECS.get(secret_id)
    if not spec:
        raise ValueError(f"未知密钥: {secret_id}")
    if explicit and str(explicit).strip():
        return str(explicit).strip()

    env_val = os.environ.get(spec.env_var) or _env_from_windows_user(spec.env_var)
    if env_val:
        os.environ.setdefault(spec.env_var, env_val)
        return env_val

    file_val = _literal_from_user_config(spec)
    if file_val:
        return file_val

    raise ValueError(f"未配置 {spec.label}（{spec.env_var} 或设置页填写）")


def resolve_secret_optional(secret_id: str) -> str:
    try:
        return resolve_secret(secret_id)
    except ValueError:
        return ""


def secret_source(secret_id: str) -> str:
    spec = SECRET_SPECS[secret_id]
    if os.environ.get(spec.env_var):
        return "env"
    if _env_from_windows_user(spec.env_var):
        return "registry"
    if _literal_from_user_config(spec):
        return "file"
    return "none"


def secret_status(secret_id: str) -> dict[str, Any]:
    spec = SECRET_SPECS[secret_id]
    value = resolve_secret_optional(secret_id)
    configured = bool(value)
    return {
        "id": spec.id,
        "label": spec.label,
        "description": spec.description,
        "env_var": spec.env_var,
        "optional": spec.optional,
        "configured": configured,
        "source": secret_source(secret_id) if configured else "none",
        "last4": value[-4:] if len(value) >= 4 else "",
        "config_path": ".".join(spec.config_path),
    }


def list_secret_statuses() -> list[dict[str, Any]]:
    return [secret_status(sid) for sid in SECRET_SPECS]


def save_secret(secret_id: str, value: str) -> dict[str, Any]:
    spec = SECRET_SPECS.get(secret_id)
    if not spec:
        raise ValueError(f"未知密钥: {secret_id}")
    text = str(value or "").strip()
    if not text:
        raise ValueError("密钥不能为空")

    patch = _nested_set({}, spec.config_path, text)
    config_path = save_user_config_patch(patch)
    os.environ[spec.env_var] = text
    return {
        "ok": True,
        "id": secret_id,
        "config_path": config_path,
        "status": secret_status(secret_id),
    }
