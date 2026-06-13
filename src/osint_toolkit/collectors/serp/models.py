"""SERP 结果模型 / SERP result models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SerpHit:
    title: str
    url: str
    snippet: str = ""
    engine: str = ""
    query: str = ""
    meta: dict = field(default_factory=dict)
