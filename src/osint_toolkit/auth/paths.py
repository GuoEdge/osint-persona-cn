"""本地认证与数据路径 / Local auth and data paths."""

import os
from pathlib import Path


def get_data_dir() -> Path:
    """返回 OSINT 本地数据目录，默认 ~/.osint。"""
    override = os.environ.get("OSINT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".osint"


def get_cookies_dir() -> Path:
    return get_data_dir() / "cookies"


def get_config_paths() -> list[Path]:
    """按优先级返回配置文件搜索路径。"""
    candidates = [
        Path("config/config.yaml"),
        get_data_dir() / "config.yaml",
    ]
    return [p.expanduser().resolve() for p in candidates]
