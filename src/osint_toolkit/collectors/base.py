"""采集器基类 / Collector base."""

from __future__ import annotations

from abc import ABC, abstractmethod

from osint_toolkit.models.intel_item import IntelItem


class BaseCollector(ABC):
    name: str = "base"

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        raise NotImplementedError

    @abstractmethod
    async def fetch(self, url: str) -> IntelItem:
        raise NotImplementedError
