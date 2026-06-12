"""统一情报条目模型 / Unified intelligence item model."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class IntelMetrics(BaseModel):
    likes: int = 0
    views: int = 0
    comments: int = 0


class IntelSignals(BaseModel):
    relevance: float = 0.0
    density: str = "unknown"
    marketing_suspect: float = 0.0
    freshness: str = "unknown"
    corroboration: int = 0
    fold_reason: str | None = None


class IntelItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    type: str
    url: str
    title: str
    content: str = ""
    author: str = ""
    published_at: str | None = None
    metrics: IntelMetrics = Field(default_factory=IntelMetrics)
    signals: IntelSignals = Field(default_factory=IntelSignals)
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    layers: dict[str, Any] = Field(default_factory=dict)
    personal: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntelItem:
        return cls.model_validate(data)
