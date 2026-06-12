"""Search collector error propagation tests."""

from __future__ import annotations

import pytest

from osint_toolkit.services import search as search_service


@pytest.mark.asyncio
async def test_collect_source_errors_in_result(monkeypatch):
    class FailZhihu:
        async def search(self, query, limit=10):
            raise ConnectionError("network down")

    class OkWeb:
        async def search(self, query, limit=10):
            from osint_toolkit.models.intel_item import IntelItem

            return [IntelItem(source="web", type="page", url="https://x", title="ok", content="c")]

    monkeypatch.setitem(search_service.COLLECTORS, "zhihu", FailZhihu)
    monkeypatch.setitem(search_service.COLLECTORS, "web", OkWeb)

    result = await search_service.run_search("test", sources=["zhihu", "web"], no_ai=True, no_simulate=True)
    errors = result.get("source_errors") or []
    assert any(e.get("source") == "zhihu" for e in errors)
    assert len(result.get("items") or []) >= 1
