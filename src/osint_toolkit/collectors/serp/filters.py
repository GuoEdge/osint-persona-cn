"""SERP 结果过滤：排除广告、热搜卡片等非自然搜索结果。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_BAIDU_NON_ORGANIC_HOSTS = frozenset(
    {
        "top.baidu.com",
        "www.baidu.com",
        "baike.baidu.com",
        "zhidao.baidu.com",
        "tieba.baidu.com",
        "map.baidu.com",
        "image.baidu.com",
        "haokan.baidu.com",
    }
)

_BAIDU_NON_ORGANIC_PATH = re.compile(
    r"^/(s|baidu|widget|hot|board|top)(/|\?|$)",
    re.I,
)

_AD_MARKERS = re.compile(
    r"广告|推广|赞助|commercial|sponsored|tuiguang|ec_ad|b_ad",
    re.I,
)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def is_ad_block(block) -> bool:
    """根据 DOM class / 属性判断是否为广告块。"""
    if block is None:
        return True
    classes = " ".join(block.get("class") or []).lower()
    if any(
        token in classes
        for token in (
            "ec_ad",
            "b_ad",
            "b_adBottom",
            "b_adTop",
            "c-container ec_ad",
            "ad-container",
            "ad_item",
            "sponsor",
            "tuiguang",
            "result-op",
        )
    ):
        return True
    for attr in ("data-tuiguang", "data-ad", "data-landurl"):
        if block.get(attr):
            return True
    text = block.get_text(" ", strip=True)[:120]
    if _AD_MARKERS.search(text):
        return True
    return False


def is_baidu_non_organic(url: str, title: str = "") -> bool:
    host = _host(url)
    if not host:
        return True
    if host in _BAIDU_NON_ORGANIC_HOSTS:
        path = urlparse(url).path or ""
        if host == "www.baidu.com" and not _BAIDU_NON_ORGANIC_PATH.match(path):
            return False
        return True
    if "baidu.com" in host and "baidu.com/link" in url:
        return False
    if title and _AD_MARKERS.search(title):
        return True
    return False


def is_bing_non_organic(block, url: str) -> bool:
    if block and "b_ans" in " ".join(block.get("class") or []):
        # 知识卡片 / 答案框，非网页结果
        if not block.select_one("h2 a[href^='http']"):
            return True
    if _AD_MARKERS.search(url):
        return True
    return False


def is_sogou_ad(block) -> bool:
    if block is None:
        return True
    classes = " ".join(block.get("class") or []).lower()
    return "ad" in classes or "spread" in classes
