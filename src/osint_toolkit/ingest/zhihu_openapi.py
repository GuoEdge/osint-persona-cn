"""知乎数据开放平台客户端 / Zhihu Data Open Platform client."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
from osint_toolkit.processors.normalize import html_to_text
from osint_toolkit.utils.config import load_config
from osint_toolkit.utils.zhihu_urls import public_zhihu_url

logger = logging.getLogger(__name__)

_DEFAULT_FEATURES: dict[str, bool] = {
    "search": True,
    "hot_list": True,
    "global_search": False,
}


def get_zhihu_config() -> dict[str, Any]:
    """合并默认与用户配置的 zhihu 段。"""
    defaults: dict[str, Any] = {
        "openapi": {
            "enabled": True,
            "base_url": "https://developer.zhihu.com",
            "access_secret": "${ZHIHU_ACCESS_SECRET}",
            "prefer_search": True,
            "merge_search_v3": True,
            "search_count": 10,
            "hot_list_count": 30,
            "features": dict(_DEFAULT_FEATURES),
        }
    }
    cfg = dict(load_config().get("zhihu") or {})
    openapi_defaults = dict(defaults["openapi"])
    openapi_cfg = dict(cfg.get("openapi") or {})
    features = dict(_DEFAULT_FEATURES)
    features.update(openapi_cfg.get("features") or {})
    merged_openapi = {**openapi_defaults, **openapi_cfg, "features": features}
    return {**defaults, **cfg, "openapi": merged_openapi}


def _openapi_cfg() -> dict[str, Any]:
    return dict(get_zhihu_config().get("openapi") or {})


def access_secret() -> str:
    from osint_toolkit.utils.secrets import resolve_secret_optional

    return resolve_secret_optional("zhihu_openapi")


def openapi_configured() -> bool:
    return bool(access_secret()) and bool(_openapi_cfg().get("enabled", True))


def openapi_enabled(feature: str) -> bool:
    if not openapi_configured():
        return False
    features = _openapi_cfg().get("features") or {}
    return bool(features.get(feature, True))


def _clean_url(url: str) -> str:
    if not url:
        return url
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _infer_type_from_url(url: str) -> str:
    if "/answer/" in url:
        return "answer"
    if "/p/" in url or "zhuanlan" in url:
        return "article"
    if "/question/" in url:
        return "question"
    return "snippet"


def _map_content_type(content_type: str, url: str) -> str:
    ct = str(content_type or "").strip().lower()
    mapping = {"article": "article", "answer": "answer", "question": "question"}
    if ct in mapping:
        return mapping[ct]
    return _infer_type_from_url(url)


def _parse_comment_list(comment_list: list[Any] | None) -> list[dict[str, Any]]:
    if not comment_list:
        return []
    out: list[dict[str, Any]] = []
    for entry in comment_list:
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("Content") or entry.get("content") or "").strip()
        if not content:
            continue
        out.append(
            {
                "author": str(entry.get("AuthorName") or entry.get("author") or ""),
                "content": html_to_text(content),
                "likes": int(entry.get("VoteUpCount") or entry.get("likes") or 0),
            }
        )
    return out


def openapi_item_to_intel(raw: dict[str, Any]) -> IntelItem | None:
    """将开放平台返回的单条记录转为 IntelItem。"""
    url = _clean_url(str(raw.get("Url") or raw.get("url") or ""))
    title = str(raw.get("Title") or raw.get("title") or "").strip()
    if not url and not title:
        return None
    if title.endswith(" - 知乎"):
        title = title[: -len(" - 知乎")].strip()

    content = html_to_text(
        str(raw.get("ContentText") or raw.get("Summary") or raw.get("summary") or "")
    )
    item_type = _map_content_type(str(raw.get("ContentType") or ""), url)
    comments = _parse_comment_list(raw.get("CommentInfoList"))

    personal: dict[str, Any] = {
        "via": "zhihu_openapi",
        "content_id": raw.get("ContentID"),
    }
    if comments:
        personal["openapi_comments"] = comments
    if raw.get("RankingScore") is not None:
        personal["ranking_score"] = raw.get("RankingScore")

    return IntelItem(
        source="zhihu",
        type=item_type,
        url=public_zhihu_url(url),
        title=title or url,
        content=content,
        author=str(raw.get("AuthorName") or ""),
        metrics=IntelMetrics(
            likes=int(raw.get("VoteUpCount") or 0),
            comments=int(raw.get("CommentCount") or 0),
        ),
        personal=personal,
    )


def _raise_api_error(payload: dict[str, Any]) -> None:
    code = payload.get("Code")
    if code == 0:
        return
    message = str(payload.get("Message") or payload.get("message") or "unknown error")
    raise RuntimeError(f"知乎开放平台 API 错误 Code={code}: {message}")


async def _api_get(
    path: str,
    params: dict[str, Any],
    *,
    client: HttpClient | None = None,
) -> dict[str, Any]:
    cfg = _openapi_cfg()
    base = str(cfg.get("base_url") or "https://developer.zhihu.com").rstrip("/")
    secret = access_secret()
    if not secret:
        raise RuntimeError("未配置 ZHIHU_ACCESS_SECRET")

    query = "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in params.items())
    url = f"{base}{path}?{query}"
    http = client or HttpClient()
    headers = {
        "Authorization": f"Bearer {secret}",
        "X-Request-Timestamp": str(int(time.time())),
    }
    resp = await http.get(url, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"知乎开放平台 HTTP {resp.status_code}")
    payload = resp.json()
    _raise_api_error(payload)
    data = payload.get("Data")
    if not isinstance(data, dict):
        raise RuntimeError("知乎开放平台响应缺少 Data")
    return data


async def search(
    query: str,
    *,
    limit: int = 10,
    client: HttpClient | None = None,
) -> list[IntelItem]:
    """站内搜索 zhihu_search（单次最多 10 条）。"""
    if not openapi_enabled("search"):
        return []
    cfg = _openapi_cfg()
    count = min(max(1, limit), int(cfg.get("search_count") or 10))
    data = await _api_get(
        "/api/v1/content/zhihu_search",
        {"Query": query, "Count": count},
        client=client,
    )
    items: list[IntelItem] = []
    seen: set[str] = set()
    for raw in data.get("Items") or []:
        if not isinstance(raw, dict):
            continue
        item = openapi_item_to_intel(raw)
        if not item or item.url in seen:
            continue
        seen.add(item.url)
        items.append(item)
        if len(items) >= limit:
            break
    return items


async def global_search(
    query: str,
    *,
    limit: int = 10,
    client: HttpClient | None = None,
) -> list[IntelItem]:
    """全网搜索 global_search（含站外链接，source 标记为 web）。"""
    if not openapi_enabled("global_search"):
        return []
    count = min(max(1, limit), 20)
    data = await _api_get(
        "/api/v1/content/global_search",
        {"Query": query, "Count": count},
        client=client,
    )
    items: list[IntelItem] = []
    seen: set[str] = set()
    for raw in data.get("Items") or []:
        if not isinstance(raw, dict):
            continue
        url = _clean_url(str(raw.get("Url") or ""))
        if not url or url in seen:
            continue
        seen.add(url)
        title = str(raw.get("Title") or url).strip()
        content = html_to_text(str(raw.get("ContentText") or ""))
        source = "zhihu" if "zhihu.com" in url else "web"
        item_type = _map_content_type(str(raw.get("ContentType") or ""), url)
        items.append(
            IntelItem(
                source=source,
                type=item_type if source == "zhihu" else "snippet",
                url=public_zhihu_url(url) if source == "zhihu" else url,
                title=title,
                content=content,
                personal={"via": "zhihu_openapi_global"},
            )
        )
        if len(items) >= limit:
            break
    return items


async def hot_list(
    *,
    limit: int = 30,
    client: HttpClient | None = None,
) -> list[IntelItem]:
    """知乎热榜 hot_list。"""
    if not openapi_enabled("hot_list"):
        return []
    cfg = _openapi_cfg()
    count = min(max(1, limit), int(cfg.get("hot_list_count") or 30))
    data = await _api_get(
        "/api/v1/content/hot_list",
        {"Count": count},
        client=client,
    )
    items: list[IntelItem] = []
    seen: set[str] = set()
    for raw in data.get("Items") or []:
        if not isinstance(raw, dict):
            continue
        item = openapi_item_to_intel(raw)
        if not item or item.url in seen:
            continue
        item.personal["hot_list"] = True
        seen.add(item.url)
        items.append(item)
        if len(items) >= limit:
            break
    return items


async def test_connection(*, client: HttpClient | None = None) -> dict[str, Any]:
    """探针：验证 access_secret 是否可用。"""
    if not openapi_configured():
        return {"ok": False, "detail": "未配置 ZHIHU_ACCESS_SECRET 或 openapi.enabled=false"}
    try:
        data = await _api_get(
            "/api/v1/content/zhihu_search",
            {"Query": "test", "Count": 1},
            client=client,
        )
        count = len(data.get("Items") or [])
        return {"ok": True, "detail": f"openapi 可用，探针返回 {count} 条"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}


def test_connection_sync(*, client: HttpClient | None = None) -> dict[str, Any]:
    """同步探针（供 auth / CLI 使用）。"""
    if not openapi_configured():
        return {"ok": False, "detail": "未配置 ZHIHU_ACCESS_SECRET 或 openapi.enabled=false"}
    try:
        asyncio.get_running_loop()
        return {"ok": True, "detail": "access_secret 已配置"}
    except RuntimeError:
        return asyncio.run(test_connection(client=client))
