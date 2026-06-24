"""本机 Web API 令牌 / Local web API token."""

from __future__ import annotations

import os
import secrets
import sys
from functools import lru_cache

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.utils.atomic_write import atomic_write_text

TOKEN_COOKIE = "osint_token"
TOKEN_HEADER = "x-osint-token"


def is_auth_enabled() -> bool:
    return os.environ.get("OSINT_DISABLE_WEB_AUTH") != "1"


def token_path():
    return get_data_dir() / "web_token"


@lru_cache(maxsize=1)
def get_or_create_token() -> str:
    path = token_path()
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    atomic_write_text(path, token)
    if sys.platform != "win32":
        os.chmod(path, 0o600)
    return token


def reset_token_cache() -> None:
    get_or_create_token.cache_clear()


def token_matches(header_value: str | None, cookie_value: str | None) -> bool:
    expected = get_or_create_token()
    for raw in (header_value, cookie_value):
        if raw and secrets.compare_digest(str(raw).strip(), expected):
            return True
    return False
