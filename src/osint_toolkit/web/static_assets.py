"""Static asset cache-busting version."""

from __future__ import annotations

from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static"
_ASSETS = ("app.js", "app.css", "tokens.css", "ui.css", "theme-init.js")

_ASSET_VERSION_CACHE: tuple[tuple[str, int], ...] | None = None
_ASSET_VERSION_RESULT: str | None = None


def static_asset_version() -> str:
    """基于静态文件修改时间，供模板 ?v= 参数使用。"""
    global _ASSET_VERSION_CACHE, _ASSET_VERSION_RESULT
    key_parts: list[tuple[str, int]] = []
    stamps: list[str] = []
    for name in _ASSETS:
        path = _STATIC / name
        if path.is_file():
            info = path.stat()
            key_parts.append((name, info.st_mtime_ns))
            stamps.append(str(int(info.st_mtime)))
    key = tuple(key_parts)
    if _ASSET_VERSION_CACHE is not None and key == _ASSET_VERSION_CACHE and _ASSET_VERSION_RESULT is not None:
        return _ASSET_VERSION_RESULT
    result = "-".join(stamps) if stamps else "0"
    _ASSET_VERSION_CACHE = key
    _ASSET_VERSION_RESULT = result
    return result
