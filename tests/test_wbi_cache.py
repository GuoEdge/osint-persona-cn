"""WBI key cache tests."""

from __future__ import annotations

import pytest

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest import bilibili_wbi as wbi


@pytest.mark.asyncio
async def test_fetch_wbi_keys_uses_cache(monkeypatch):
    wbi.clear_wbi_key_cache()
    calls = {"n": 0}

    class FakeResp:
        def json(self):
            return {
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/aaa.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/bbb.png",
                    }
                }
            }

    async def fake_get(_url):
        calls["n"] += 1
        return FakeResp()

    client = HttpClient()
    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(wbi.time, "time", lambda: 1000.0)

    k1 = await wbi.fetch_wbi_keys(client)
    k2 = await wbi.fetch_wbi_keys(client)
    assert k1 == ("aaa", "bbb")
    assert k2 == k1
    assert calls["n"] == 1

    monkeypatch.setattr(wbi.time, "time", lambda: 5000.0)
    await wbi.fetch_wbi_keys(client, force_refresh=True)
    assert calls["n"] == 2
