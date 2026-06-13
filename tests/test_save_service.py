"""Save service routing tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_save_url_routes_weixin(monkeypatch):
    from osint_toolkit.services import save as save_svc

    class FakeCollector:
        async def fetch(self, url):
            from osint_toolkit.models.intel_item import IntelItem

            return IntelItem(source="weixin", type="article", url=url, title="t", content="c")

    monkeypatch.setattr(save_svc, "WeixinCollector", lambda: FakeCollector())
    monkeypatch.setattr(save_svc, "save_item", lambda item: 1)
    monkeypatch.setattr(save_svc, "export_card", lambda item, path: path / "card.md")

    result = await save_svc.save_url("https://mp.weixin.qq.com/s/abc", no_ai=True)
    assert result["item"].source == "weixin"
