"""知乎账号数据导入 / Zhihu account ingest."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest import account_sync_state as sync_state
from osint_toolkit.ingest.zhihu_activities import iter_api_data_items
from osint_toolkit.ingest.zhihu_endpoint_registry import (
    PUBLISH_ENDPOINTS,
    LayerStatus,
    layer_status_from_count,
    paginate_member_api,
)
from osint_toolkit.storage.knowledge import log_event, log_events_batch
from osint_toolkit.utils.zhihu_urls import content_url_from_target

_ZHIHU_CONTENT_URL = re.compile(
    r"https?://(?:www\.|zhuanlan\.)?zhihu\.com/(?:question/\d+(?:/answer/\d+)?|p/\d+|pin/\d+|zvideo/[\w]+|people/[\w]+|column/[\w]+)",
    re.I,
)


async def _aclose_if_real(client: Any) -> None:
    aclose = getattr(client, "aclose", None)
    if asyncio.iscoroutinefunction(aclose):
        await aclose()


async def _url_token(client: HttpClient | None = None) -> str:
    owns = client is None
    c = client or HttpClient()
    try:
        resp = await c.get("https://www.zhihu.com/api/v4/me")
        return str(resp.json().get("url_token") or "")
    finally:
        if owns:
            aclose = getattr(c, "aclose", None)
            if asyncio.iscoroutinefunction(aclose):
                await aclose()


def _zhihu_section() -> dict[str, Any]:
    return sync_state.load_account_sync_state().get("zhihu") or {}


def _persist_zhihu(**kwargs: Any) -> None:
    def _update(state: dict[str, Any]) -> None:
        sync_state.update_zhihu_section(state, **kwargs)
    sync_state.atomic_update_state(_update)



def _browse_entry_from_item(item: dict) -> dict | None:
    target = item.get("target") or item
    url_ = content_url_from_target(target, item)
    if not url_ or not str(url_).startswith("http"):
        return None
    question = target.get("question") or {}
    title = question.get("title") or target.get("title") or item.get("title") or ""
    return {
        "source": "zhihu",
        "title": title,
        "url": url_,
        "event_kind": "browse",
    }


def _publish_entry_from_item(item: dict, *, event_kind: str, via: str) -> dict | None:
    target = item.get("target") or item
    url_ = content_url_from_target(target, item)
    if not url_ or not str(url_).startswith("http"):
        return None
    question = target.get("question") or {}
    title = (
        str(question.get("title") or "").strip()
        or str(target.get("title") or "").strip()
        or str(item.get("title") or "").strip()
        or str(target.get("excerpt") or "")[:120]
    )
    entry: dict[str, Any] = {
        "source": "zhihu",
        "title": title or "未命名内容",
        "url": url_,
        "event_kind": event_kind,
        "via": via,
    }
    for ts_key in ("created_time", "updated_time", "created", "updated"):
        if target.get(ts_key) is not None:
            entry[ts_key] = target.get(ts_key)
    return entry


async def ingest_profile_meta() -> dict[str, Any]:
    """拉取知乎账号统计，写入 events。"""
    client = HttpClient()
    try:
        token = await _url_token(client)
        if not token:
            return {}
        resp = await client.get(f"https://www.zhihu.com/api/v4/members/{token}")
        if resp.status_code != 200:
            resp = await client.get("https://www.zhihu.com/api/v4/me")
        if resp.status_code != 200:
            return {}
        data = resp.json()
        meta = {
            "source": "zhihu",
            "url_token": token,
            "vote_to_count": data.get("vote_to_count", 0),
            "voteup_count": data.get("voteup_count", 0),
            "favorited_count": data.get("favorited_count", 0),
            "answer_count": data.get("answer_count", 0),
            "articles_count": data.get("articles_count", 0),
            "pins_count": data.get("pins_count", 0),
        }
        log_event("zhihu_profile", meta)
        return meta
    finally:
        await _aclose_if_real(client)


async def ingest_activities(
    limit: int = 500,
    *,
    skip_answer_votes: bool = False,
) -> tuple[list[dict], str | None]:
    """拉取知乎动态流（含点赞/收藏/关注等近期行为）。

    真正的动态流端点是 ``/api/v3/moments/{token}/activities``（v3 moments），
    而非已废弃的 ``/api/v4/members/{token}/activities``（v4，返回空）。
    每页 7 条，用 ``offset``（毫秒时间戳）翻页，verb 包含：
    - ``MEMBER_VOTEUP_ANSWER``：点赞回答
    - ``MEMBER_VOTE_PIN``：点赞想法
    - 其它：收藏/关注/发布等
    """
    from osint_toolkit.ingest.zhihu_activities import activity_entry_from_item, classify_activity

    del skip_answer_votes
    client = HttpClient()
    try:
        token = await _url_token(client)
        if not token:
            return [], None
        section = _zhihu_section()
        seen_urls = sync_state._string_set(section.get("activity_urls", []))
        results: list[dict] = []
        seen: set[str] = set()

        base_url = f"https://www.zhihu.com/api/v3/moments/{token}/activities"
        referer = f"https://www.zhihu.com/people/{token}/activities"
        params = "?limit=20&desktop=true&ws_qiangzhisafe=0"
        next_url = f"{base_url}{params}"

        try:
            page = 0
            while len(results) < limit and next_url:
                resp = await client.get(next_url, headers={"Referer": referer})
                if resp.status_code != 200:
                    break
                payload = resp.json()
                batch = iter_api_data_items(payload.get("data"))
                if not batch:
                    break
                for item in batch:
                    entry = activity_entry_from_item(item, via="moments_api")
                    if not entry or entry["url"] in seen:
                        continue
                    seen.add(entry["url"])
                    results.append(entry)
                    if len(results) >= limit:
                        break
                paging = payload.get("paging") or {}
                if paging.get("is_end"):
                    break
                next_url = paging.get("next") or ""
                page += 1
                if page > 50:
                    break
        except Exception as exc:  # noqa: BLE001
            logger.warning("zhihu activities (moments) ingest failed: %s", exc)

        if not results:
            logger.debug("zhihu moments activities returned 0 items")
            return [], None

        fresh = sync_state.filter_new_by_urls(results, seen_urls)
        if fresh:
            batch = []
            for entry in fresh:
                url = str(entry.get("url") or "")
                et = "zhihu_activity"
                classified = classify_activity({"verb": entry.get("verb", ""), "type": entry.get("activity_type", "")})
                if classified:
                    et = classified[0]
                batch.append((et, entry, f"{et}|{url}"))
            log_events_batch(batch)
        _persist_zhihu(activities=results)
        logger.info("zhihu moments: %d total, %d fresh (votes=%d)",
                    len(results), len(fresh),
                    sum(1 for r in results if "vote" in str(r.get("event_kind", ""))))
        return fresh, "moments"
    finally:
        await _aclose_if_real(client)


async def ingest_voteanswers(limit: int = 500) -> tuple[list[dict], str | None]:
    """已停用：voteanswers 等端点 404，见 docs/ZHIHU_PERSONA.md。"""
    del limit
    logger.debug("zhihu voteanswers API skipped (deprecated)")
    return [], None


async def ingest_votes(limit: int = 500) -> list[dict]:
    """赞同仅由扩展被动采集；Cookie 同步不再请求 voteanswers。"""
    del limit
    return []


async def _ingest_member_list(
    specs: tuple[Any, ...],
    *,
    event_kind: str,
    event_type: str,
    via: str,
    state_key: str,
    limit: int = 500,
) -> tuple[list[dict], str | None]:
    client = HttpClient()
    try:
        token = await _url_token(client)
        if not token:
            return [], None
        section = _zhihu_section()
        seen_urls = sync_state._string_set(section.get(state_key, []))
        raw_items, endpoint_key = await paginate_member_api(client, token, specs, limit=limit)
        results: list[dict] = []
        seen: set[str] = set()
        for item in raw_items:
            entry = _publish_entry_from_item(item, event_kind=event_kind, via=via)
            if not entry or entry["url"] in seen:
                continue
            seen.add(entry["url"])
            results.append(entry)
        fresh = sync_state.filter_new_by_urls(results, seen_urls)
        if fresh:
            log_events_batch([
                (event_type, e, f"{event_type}|{str(e.get('url') or '')}")
                for e in fresh
            ])
        if state_key == "answer_urls":
            _persist_zhihu(answers=results)
        elif state_key == "article_urls":
            _persist_zhihu(articles=results)
        elif state_key == "pin_urls":
            _persist_zhihu(pins=results)
        return fresh, endpoint_key
    finally:
        await _aclose_if_real(client)


async def ingest_member_answers(limit: int = 500) -> tuple[list[dict], str | None]:
    spec = next(s for s in PUBLISH_ENDPOINTS if s.key == "answers")
    return await _ingest_member_list(
        (spec,),
        event_kind="create_answer",
        event_type="zhihu_answer",
        via="answers_api",
        state_key="answer_urls",
        limit=limit,
    )


async def ingest_member_articles(limit: int = 500) -> tuple[list[dict], str | None]:
    spec = next(s for s in PUBLISH_ENDPOINTS if s.key == "articles")
    return await _ingest_member_list(
        (spec,),
        event_kind="create_article",
        event_type="zhihu_article",
        via="articles_api",
        state_key="article_urls",
        limit=limit,
    )


async def ingest_member_pins(limit: int = 500) -> tuple[list[dict], str | None]:
    spec = next(s for s in PUBLISH_ENDPOINTS if s.key == "pins")
    return await _ingest_member_list(
        (spec,),
        event_kind="create_pin",
        event_type="zhihu_pin",
        via="pins_api",
        state_key="pin_urls",
        limit=limit,
    )


async def ingest_followees(limit: int = 500) -> list[dict]:
    client = HttpClient()
    try:
        token = await _url_token(client)
        if not token:
            return []
        section = _zhihu_section()
        seen_urls = sync_state._string_set(section.get("followee_urls", []))
        results: list[dict] = []
        seen: set[str] = set()
        offset = 0
        _page = 0
        try:
            while len(results) < limit:
                _page += 1
                if _page > 50:
                    break
                resp = await client.get(
                    f"https://www.zhihu.com/api/v4/members/{token}/followees"
                    f"?offset={offset}&limit=20",
                    headers={"Referer": f"https://www.zhihu.com/people/{token}"},
                )
                if resp.status_code != 200:
                    break
                payload = resp.json()
                batch = iter_api_data_items(payload.get("data"))
                if not batch:
                    break
                for member in batch:
                    url_token = str(member.get("url_token") or "")
                    if not url_token:
                        continue
                    url_ = f"https://www.zhihu.com/people/{url_token}"
                    if url_ in seen:
                        continue
                    seen.add(url_)
                    entry = {
                        "source": "zhihu",
                        "title": member.get("name", "") or url_token,
                        "url": url_,
                        "event_kind": "follow",
                        "via": "followees_api",
                    }
                    results.append(entry)
                    if len(results) >= limit:
                        break
                paging = payload.get("paging") or {}
                if paging.get("is_end") or len(batch) < 20:
                    break
                offset += 20
        except Exception as exc:  # noqa: BLE001
            logger.warning("zhihu followees ingest failed: %s", exc)
        fresh = sync_state.filter_new_by_urls(results, seen_urls)
        if fresh:
            log_events_batch([
                ("zhihu_follow", e, f"zhihu_follow|{str(e.get('url') or '')}")
                for e in fresh
            ])
        _persist_zhihu(followees=results)
        return fresh
    finally:
        await _aclose_if_real(client)


async def ingest_browsing(limit: int = 500) -> tuple[list[dict], dict[str, Any]]:
    """浏览记录：优先调 /api/v4/unify-consumption/read_history API，回退 Edge 历史。

    2024-11 发现知乎 /recent-viewed 页面实际调用
    /api/v4/unify-consumption/read_history 端点（HttpClient 可直接调），
    每页 20 条，offset 翻页，含 read_time 时间戳。
    """
    api_fresh, api_meta = await _ingest_browsing_via_api(limit=limit)
    if api_meta.get("source") == "read_history_api" and api_fresh:
        edge_fresh = ingest_zhihu_browse_from_edge(limit=limit)
        api_urls = {f.get("url") for f in api_fresh}
        combined = api_fresh + [e for e in edge_fresh if e.get("url") not in api_urls]
        return combined, {**api_meta, "edge_supplement": len(edge_fresh)}
    # API 失败或空，回退 Edge 历史
    fresh = ingest_zhihu_browse_from_edge(limit=limit)
    return fresh, {"api_endpoint": None, "bootstrap_count": 0, "source": "edge_history"}


async def _ingest_browsing_via_api(limit: int = 500) -> tuple[list[dict], dict[str, Any]]:
    """通过 /api/v4/unify-consumption/read_history 拉取浏览历史。"""
    client = HttpClient()
    try:
        token = await _url_token(client)
        if not token:
            return [], {"source": "no_token"}
        section = _zhihu_section()
        seen_urls = sync_state._string_set(section.get("browsing_urls", []))
        results: list[dict] = []
        seen: set[str] = set()
        offset = 0
        total_count = 0
        try:
            while len(results) < limit:
                url = (
                    f"https://www.zhihu.com/api/v4/unify-consumption/read_history"
                    f"?offset={offset}&limit=20"
                )
                resp = await client.get(url, headers={"Referer": "https://www.zhihu.com/recent-viewed"})
                if resp.status_code != 200:
                    break
                payload = resp.json()
                batch = iter_api_data_items(payload.get("data"))
                if not batch:
                    break
                for item in batch:
                    entry = _parse_read_history_item(item)
                    if not entry or entry["url"] in seen:
                        continue
                    seen.add(entry["url"])
                    results.append(entry)
                    if len(results) >= limit:
                        break
                paging = payload.get("paging") or {}
                if paging.get("is_end"):
                    break
                total_count = int(paging.get("totals") or total_count)
                offset += 20
                if offset > 1000:
                    break
        except Exception as exc:  # noqa: BLE001
            logger.warning("zhihu read_history API failed (partial %d items): %s", len(results), exc)
            if results:
                fresh = sync_state.filter_new_by_urls(results, seen_urls)
                if fresh:
                    log_events_batch([
                        ("zhihu_browse", e, f"zhihu_browse|{str(e.get('url') or '')}")
                        for e in fresh
                    ])
                _persist_zhihu(browsing=results)
                return fresh, {"source": "read_history_api_partial", "error": str(exc), "fetched": len(results)}
            return [], {"source": "error", "error": str(exc)}
        if not results:
            return [], {"source": "empty"}
        fresh = sync_state.filter_new_by_urls(results, seen_urls)
        if fresh:
            log_events_batch([
                ("zhihu_browse", e, f"zhihu_browse|{str(e.get('url') or '')}")
                for e in fresh
            ])
        _persist_zhihu(browsing=results)
        logger.info("zhihu read_history: %d total, %d fresh (api_total=%d)", len(results), len(fresh), total_count)
        return fresh, {"source": "read_history_api", "api_total": total_count, "fetched": len(results)}
    finally:
        await _aclose_if_real(client)


def _parse_read_history_item(item: dict[str, Any]) -> dict | None:
    """解析 /api/v4/unify-consumption/read_history 返回的单条记录。

    数据结构：{card_type: "single_card", data: {header, content, action, extra, matrix}}
    - action.url: 内容 URL（如 question/.../answer/...，也可能是相对路径）
    - header.title: 标题
    - content.summary: 摘要
    - content.author_name: 作者
    - extra.content_type: answer/question/article/profile
    - extra.read_time: Unix 时间戳
    """
    inner = item.get("data") or item
    if not isinstance(inner, dict):
        return None
    action = inner.get("action") or {}
    url = str(action.get("url") or "").strip()
    if not url:
        return None
    if url.startswith("/"):
        url = "https://www.zhihu.com" + url
    elif not url.startswith("http"):
        return None
    header = inner.get("header") or {}
    content = inner.get("content") or {}
    extra = inner.get("extra") or {}
    title = str(header.get("title") or content.get("summary") or "")[:200]
    if not title:
        title = "未命名内容"
    read_time = extra.get("read_time")
    if isinstance(read_time, (int, float)):
        read_time = int(read_time)
    else:
        read_time = None
    return {
        "source": "zhihu",
        "title": title,
        "url": url,
        "event_kind": "browse",
        "via": "read_history_api",
        "author": str(content.get("author_name") or ""),
        "content_type": str(extra.get("content_type") or ""),
        "read_time": read_time,
    }


def ingest_zhihu_browse_from_edge(*, since_days: int = 90, limit: int = 200) -> list[dict]:
    """L3：从 Edge 浏览历史提取知乎内容 URL，写入 zhihu_browse。"""
    from osint_toolkit.ingest.browser import ingest_browser_history

    rows = ingest_browser_history(since_days=since_days)
    section = _zhihu_section()
    seen_urls = sync_state._string_set(section.get("browsing_urls", []))
    candidates: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("url") or "")
        if not _ZHIHU_CONTENT_URL.search(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        entry = {
            "source": "zhihu",
            "title": str(row.get("title") or "")[:200],
            "url": url,
            "event_kind": "browse",
            "via": "edge_history",
            "visited_at": row.get("visited_at"),
        }
        candidates.append(entry)
        if len(candidates) >= limit:
            break
    fresh = sync_state.filter_new_by_urls(candidates, seen_urls)
    if fresh:
        log_events_batch([
            ("zhihu_browse", e, f"zhihu_browse|{str(e.get('url') or '')}")
            for e in fresh
        ])
    if candidates:
        _persist_zhihu(browsing=candidates)
    return fresh


async def ingest_favorites(limit: int = 500) -> list[dict]:
    client = HttpClient()
    try:
        token = await _url_token(client)
        if not token:
            return []
        section = _zhihu_section()
        seen_urls = sync_state._string_set(section.get("favorite_urls", []))
        results: list[dict] = []
        seen: set[str] = set()
        offset = 0
        _fav_page = 0
        try:
            while len(results) < limit:
                _fav_page += 1
                if _fav_page > 50:
                    break
                fav_resp = await client.get(
                    f"https://www.zhihu.com/api/v4/members/{token}/favlists"
                    f"?include=answers&offset={offset}&limit=20",
                    headers={"Referer": "https://www.zhihu.com/collections"},
                )
                fav_payload = fav_resp.json()
                collections = iter_api_data_items(fav_payload.get("data"))
                if not collections:
                    break
                for coll in collections:
                    cid = coll.get("id")
                    if not cid:
                        continue
                    item_offset = 0
                    _item_page = 0
                    while len(results) < limit:
                        _item_page += 1
                        if _item_page > 50:
                            break
                        items_resp = await client.get(
                            f"https://www.zhihu.com/api/v4/collections/{cid}/items"
                            f"?offset={item_offset}&limit=20"
                        )
                        items_payload = items_resp.json()
                        items = iter_api_data_items(items_payload.get("data"))
                        if not items:
                            break
                        for raw in items:
                            content = raw.get("content") or raw
                            collection_title = str(coll.get("title") or "").strip()
                            question = (content.get("question") or {}) if isinstance(content, dict) else {}
                            title = (
                                str(question.get("title") or "").strip()
                                or str(content.get("title") or "").strip()
                                or str(raw.get("title") or "").strip()
                            )
                            if not title:
                                excerpt = str(content.get("excerpt") or "").strip()
                                if excerpt:
                                    title = excerpt[:120]
                            if not title and collection_title:
                                title = f"（收藏夹：{collection_title}）"
                            if not title:
                                title = "未命名内容"
                            url_ = content_url_from_target(content, raw)
                            if not url_ or url_ in seen:
                                continue
                            seen.add(url_)
                            entry = {
                                "source": "zhihu",
                                "title": title,
                                "url": url_,
                                "type": "collection_item",
                                "collection": collection_title,
                            }
                            results.append(entry)
                            if len(results) >= limit:
                                break
                        paging = items_payload.get("paging") or {}
                        if paging.get("is_end"):
                            break
                        item_offset += 20
                    if len(results) >= limit:
                        break
                paging = fav_payload.get("paging") or {}
                if paging.get("is_end") or len(collections) < 20:
                    break
                offset += 20
        except Exception as exc:  # noqa: BLE001
            logger.warning("zhihu_account: ingest_favorites failed: %s", exc)
        fresh = sync_state.filter_new_by_urls(results, seen_urls)
        if fresh:
            log_events_batch([
                ("zhihu_fav", e, f"zhihu_fav|{str(e.get('url') or '')}")
                for e in fresh
            ])
        _persist_zhihu(favorites=results)
        return fresh
    finally:
        await _aclose_if_real(client)


def zhihu_layer_status(
    *,
    vote_count: int,
    browse_count: int,
    activity_count: int,
    vote_endpoint: str | None = None,
    browse_endpoint: str | None = None,
    activity_endpoint: str | None = None,
    browse_bootstrap: int = 0,
    browse_edge: int = 0,
    synthetic_count: int = 0,
) -> dict[str, Any]:
    del vote_endpoint, browse_endpoint, activity_endpoint, browse_bootstrap, activity_count
    browse_status = layer_status_from_count(browse_count)
    activity_status: LayerStatus = "skip"
    if synthetic_count > 0:
        activity_status = "ok"
    return {
        "votes": {
            "status": "skip",
            "count": vote_count,
            "endpoint": None,
            "layer": "extension_post",
            "note": "voteanswers API 已废弃（404）；点赞由扩展 POST 拦截实时记录 + moments 动态流获取历史",
        },
        "browse": {
            "status": browse_status,
            "count": browse_count,
            "endpoint": None,
            "bootstrap_count": 0,
            "edge_count": browse_edge or browse_count,
            "layer": "read_history_api",
            "note": "通过 /api/v4/unify-consumption/read_history 获取浏览历史；Edge 历史作为补充",
        },
        "activity": {
            "status": activity_status,
            "count": 0,
            "synthetic_count": synthetic_count,
            "endpoint": None,
            "layer": "moments_api" if synthetic_count else "skip",
            "note": "动态流通过 /api/v3/moments/{token}/activities 获取（含点赞/收藏/关注历史）",
        },
    }
