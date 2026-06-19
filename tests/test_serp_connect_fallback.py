"""SERP provider connection error should not abort the whole chain."""

from __future__ import annotations

import httpx
import pytest

from osint_toolkit.collectors.serp.engine import SerpEngine


@pytest.mark.asyncio
async def test_serp_continues_after_connect_error(monkeypatch):
    calls: list[str] = []

    async def fake_invoke(self, name, query, limit):
        calls.append(name)
        if name == "duckduckgo_html":
            return [], "duckduckgo_html: 网络连接失败"
        if name == "baidu_html":
            from osint_toolkit.collectors.serp.models import SerpHit

            return (
                [SerpHit(title="t", url="https://example.com/a", snippet="s", engine="baidu_html", query=query)],
                None,
            )
        return [], f"{name}: empty"

    monkeypatch.setattr(SerpEngine, "_invoke", fake_invoke)
    monkeypatch.setattr(
        "osint_toolkit.collectors.serp.engine._provider_chain",
        lambda cfg: ["duckduckgo_html", "baidu_html"],
    )
    monkeypatch.setattr("osint_toolkit.collectors.serp.engine._effective_strategy", lambda cfg: "fallback")

    engine = SerpEngine()
    hits, attempts = await engine.search("test", limit=3)
    assert len(hits) == 1
    assert "baidu_html" in calls
