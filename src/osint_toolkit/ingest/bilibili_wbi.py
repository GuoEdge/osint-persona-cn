"""B站 WBI 签名 / Bilibili WBI signing."""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from functools import reduce
from typing import Any

from osint_toolkit.http.client import HttpClient

_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def _mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return reduce(lambda s, i: s + raw[i], _MIXIN_KEY_ENC_TAB, "")[:32]


def sign_wbi_params(params: dict[str, Any], img_key: str, sub_key: str) -> dict[str, Any]:
    signed = dict(params)
    signed["wts"] = round(time.time())
    signed = dict(sorted(signed.items()))
    signed = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in signed.items()
    }
    query = urllib.parse.urlencode(signed)
    signed["w_rid"] = hashlib.md5((query + _mixin_key(img_key, sub_key)).encode()).hexdigest()
    return signed


def _key_from_url(url: str) -> str:
    name = url.rsplit("/", 1)[-1]
    return name.split(".", 1)[0]


async def fetch_wbi_keys(client: HttpClient) -> tuple[str, str]:
    resp = await client.get("https://api.bilibili.com/x/web-interface/nav")
    data = resp.json().get("data") or {}
    wbi = data.get("wbi_img") or {}
    img_url = wbi.get("img_url") or ""
    sub_url = wbi.get("sub_url") or ""
    if not img_url or not sub_url:
        raise RuntimeError("无法从 nav 获取 WBI keys")
    return _key_from_url(img_url), _key_from_url(sub_url)


async def wbi_get(client: HttpClient, base_url: str, params: dict[str, Any]) -> Any:
    img_key, sub_key = await fetch_wbi_keys(client)
    signed = sign_wbi_params(params, img_key, sub_key)
    qs = urllib.parse.urlencode(signed)
    resp = await client.get(f"{base_url}?{qs}")
    return resp.json()
