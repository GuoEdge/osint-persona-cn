"""API 密钥服务 / Secrets service for Web & CLI."""

from __future__ import annotations

from typing import Any

from osint_toolkit.services import auth
from osint_toolkit.utils.secrets import list_secret_statuses, save_secret


def list_api_secrets() -> dict[str, Any]:
    items = list_secret_statuses()
    return {"items": items}


def save_api_secret(secret_id: str, value: str) -> dict[str, Any]:
    result = save_secret(secret_id, value)
    probe = test_api_secret(secret_id)
    return {**result, "probe": probe}


def test_api_secret(secret_id: str) -> dict[str, Any]:
    target_map = {
        "deepseek": "deepseek",
        "zhihu_openapi": "zhihu_openapi",
    }
    target = target_map.get(secret_id)
    if not target:
        return {"ok": False, "detail": f"未知密钥: {secret_id}"}
    for entry in auth.get_auth_status(target):
        if entry.get("key") == target:
            return {"ok": bool(entry.get("ok")), "detail": str(entry.get("detail") or "")}
    return {"ok": False, "detail": "探针无结果"}
