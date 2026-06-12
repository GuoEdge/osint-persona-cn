"""搜索服务测试."""

import pytest

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import search as search_service


@pytest.mark.asyncio
async def test_run_search_with_mocked_collectors(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.pipeline.context.get_data_dir", lambda: tmp_path)

    async def fake_collect(name, query, limit):
        return [
            IntelItem(
                source=name,
                type="test",
                url=f"https://{name}.com/1",
                title=f"{query} on {name}",
                content="content",
            )
        ]

    monkeypatch.setattr(search_service, "_collect_source", fake_collect)
    monkeypatch.setattr(
        search_service,
        "summarize_batch",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(search_service, "simulate_items", lambda *args, **kwargs: [])

    result = await search_service.run_search(
        "MCP", sources=["zhihu", "web"], trace=True, no_ai=True
    )
    assert result["run_id"]
    assert len(result["items"]) == 2
