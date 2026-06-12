"""配置加载 / Configuration loader."""

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config/config.yaml") -> dict[str, Any]:
    """加载 YAML 配置文件，文件不存在时返回空字典。"""
    config_path = Path(path)
    if not config_path.exists():
        return {}

    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
