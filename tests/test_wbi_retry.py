"""WBI -352 retry tests."""

from __future__ import annotations

import pytest

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest import bilibili_wbi as wbi


@pytest.mark.asyncio
async def test_wbi_get_retries_on_minus_352(monkeypatch):
    wbi.clear_wbi_key_cache()
    nav_calls = {"n": 0}
    api_calls = {"n": 0}

    class FakeResp:
        def __init__(self, payload: dict):
            self._payload = payload

        def json(self):
            return self._payload

    img_key = "a" * 32
    sub_key = "b" * 32
    img_key2 = "c" * 32
    sub_key2 = "d" * 32

    async def fake_get(url):
        if "nav" in url:
            nav_calls["n"] += 1
            if nav_calls["n"] == 1:
                img, sub = img_key, sub_key
            else:
                img, sub = img_key2, sub_key2
            return FakeResp(
                {
                    "data": {
                        "wbi_img": {
                            "img_url": f"https://i0.hdslb.com/bfs/wbi/{img}.png",
                            "sub_url": f"https://i0.hdslb.com/bfs/wbi/{sub}.png",
                        }
                    }
                }
            )
        api_calls["n"] += 1
        if api_calls["n"] == 1:
            return FakeResp({"code": -352, "message": "风控校验失败"})
        return FakeResp({"code": 0, "data": {"ok": True}})

    client = HttpClient()
    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(wbi.time, "time", lambda: 1000.0)

    payload = await wbi.wbi_get(client, "https://api.bilibili.com/x/test", {"pn": 1})
    assert payload["code"] == 0
    assert api_calls["n"] == 2
    assert nav_calls["n"] == 2
