"""Static asset cache-busting version."""

from __future__ import annotations

from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static"
_ASSETS = ("app.js", "app.css", "tokens.css", "ui.css", "theme-init.js")


def static_asset_version() -> str:
    """基于静态文件修改时间，供模板 ?v= 参数使用。"""
    stamps: list[str] = []
    for name in _ASSETS:
        path = _STATIC / name
        if path.is_file():
            stamps.append(str(int(path.stat().st_mtime)))
    return "-".join(stamps) if stamps else "0"
