"""知乎账号数据导入 / Zhihu account ingest."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.likes import save_endorsement
from osint_toolkit.ingest.zhihu_activities import (
    _zhihu_content_url,
    activity_entry_from_item,
    classify_activity,
    iter_api_data_items,
)
from osint_toolkit.storage.knowledge import log_event


async def _url_token(client: HttpClient) -> str:
    resp = await client.get("https://www.zhihu.com/api/v4/me")
    return str(resp.json().get("url_token") or "")


async def ingest_profile_meta() -> dict[str, Any]:
    """拉取知乎账号统计（含 vote_to_count），写入 events。"""
    client = HttpClient()
    token = await _url_token(client)
    if not token:
        return {}
    resp = await client.get(
        f"https://www.zhihu.com/api/v4/members/{token}"
        "?include=voteup_count,vote_to_count,favorited_count,answer_count,following_count"
    )
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
    }
    log_event("zhihu_profile", meta)
    return meta


async def ingest_activities(limit: int = 500) -> list[dict]:
    """知乎主页动态流：赞/藏/关注/发布等（activities API + 扩展补洞）。"""
    await ingest_profile_meta()
    client = HttpClient()
    token = await _url_token(client)
    if not token:
        return []
    results: list[dict] = []
    seen: set[str] = set()
    offset = 0
    try:
        while len(results) < limit:
            resp = await client.get(
                f"https://www.zhihu.com/api/v4/members/{token}/activities"
                f"?include=data[*].target&offset={offset}&limit=20"
            )
            if resp.status_code != 200:
                break
            batch = iter_api_data_items(resp.json().get("data"))
            if not batch:
                break
            for item in batch:
                entry = activity_entry_from_item(item, via="api")
                if not entry:
                    continue
                key = f"{entry.get('event_kind')}|{entry['url']}"
                if key in seen:
                    continue
                seen.add(key)
                classified = classify_activity(item)
                event_type = classified[0] if classified else "zhihu_activity"
                log_event(event_type, entry)
                if event_type == "zhihu_vote":
                    save_endorsement(
                        platform="zhihu",
                        target_type="answer",
                        url=entry["url"],
                        content=entry.get("title", ""),
                    )
                elif event_type == "zhihu_fav":
                    save_endorsement(
                        platform="zhihu",
                        target_type="collection",
                        url=entry["url"],
                        content=entry.get("title", ""),
                    )
                results.append(entry)
                if len(results) >= limit:
                    break
            if len(batch) < 20:
                break
            offset += 20
    except Exception as exc:  # noqa: BLE001
        logger.warning("zhihu activities ingest failed: %s", exc)
    return results


async def ingest_votes(limit: int = 500) -> list[dict]:
    """赞同明细（优先 voteanswers API，回退 activities 子集）。"""
    rows = await ingest_voteanswers(limit=limit)
    if rows:
        return rows
    activities = await ingest_activities(limit=limit)
    return [r for r in activities if r.get("event_kind") == "answer_vote"]


async def ingest_voteanswers(limit: int = 500) -> list[dict]:
    """知乎赞同回答明细（members/{token}/voteanswers 分页）。"""
    client = HttpClient()
    token = await _url_token(client)
    if not token:
        return []
    templates = [
        "https://www.zhihu.com/api/v4/members/{token}/voteanswers?offset={offset}&limit=20",
        "https://www.zhihu.com/api/v4/members/{token}/vote_answers?offset={offset}&limit=20",
    ]
    results: list[dict] = []
    seen: set[str] = set()
    for template in templates:
        offset = 0
        try:
            while len(results) < limit:
                resp = await client.get(template.format(token=token, offset=offset))
                if resp.status_code != 200:
                    break
                payload = resp.json()
                batch = iter_api_data_items(payload.get("data"))
                if not batch:
                    break
                for item in batch:
                    target = item.get("target") or item
                    content_url = _zhihu_content_url(target, item)
                    if not content_url or content_url in seen:
                        continue
                    seen.add(content_url)
                    title = (target.get("question") or {}).get("title") or target.get("title") or ""
                    entry = {
                        "source": "zhihu",
                        "title": title,
                        "url": content_url,
                        "event_kind": "answer_vote",
                        "via": "voteanswers_api",
                    }
                    log_event("zhihu_vote", entry)
                    save_endorsement(
                        platform="zhihu",
                        target_type="answer",
                        url=content_url,
                        content=title,
                    )
                    results.append(entry)
                    if len(results) >= limit:
                        break
                paging = payload.get("paging") or {}
                if paging.get("is_end") or len(batch) < 20:
                    break
                offset += 20
            if results:
                break
        except Exception:  # noqa: BLE001
            continue
    return results


async def ingest_followees(limit: int = 500) -> list[dict]:
    """知乎关注的人（members/{token}/followees 分页）。"""
    client = HttpClient()
    token = await _url_token(client)
    if not token:
        return []
    results: list[dict] = []
    seen: set[str] = set()
    offset = 0
    try:
        while len(results) < limit:
            resp = await client.get(
                f"https://www.zhihu.com/api/v4/members/{token}/followees"
                f"?offset={offset}&limit=20"
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
                log_event("zhihu_follow", entry)
                results.append(entry)
                if len(results) >= limit:
                    break
            paging = payload.get("paging") or {}
            if paging.get("is_end") or len(batch) < 20:
                break
            offset += 20
    except Exception as exc:  # noqa: BLE001
        logger.warning("zhihu followees ingest failed: %s", exc)
    return results


def _browse_entry_from_item(item: dict) -> dict | None:
    target = item.get("target") or item
    question = target.get("question") or {}
    answer_id = target.get("id")
    qid = question.get("id")
    if answer_id and qid:
        url_ = f"https://www.zhihu.com/question/{qid}/answer/{answer_id}"
    else:
        url_ = target.get("url") or item.get("url") or ""
    if not url_ or not str(url_).startswith("http"):
        return None
    title = question.get("title") or target.get("title") or item.get("title") or ""
    return {
        "source": "zhihu",
        "title": title,
        "url": url_,
        "event_kind": "browse",
    }


async def ingest_browsing(limit: int = 500) -> list[dict]:
    """知乎最近浏览。网页 /footprints 已 404，改走 Cookie API。"""
    client = HttpClient()
    token = await _url_token(client)
    if not token:
        return []
    templates = [
        "https://www.zhihu.com/api/v4/members/{token}/browsing_histories?offset={offset}&limit=20",
        "https://www.zhihu.com/api/v4/members/{token}/footprints?offset={offset}&limit=20",
        "https://www.zhihu.com/api/v4/footprints?offset={offset}&limit=20",
        "https://www.zhihu.com/api/v4/record_viewed_items?offset={offset}&limit=20",
        "https://www.zhihu.com/api/v4/recent_browsing?offset={offset}&limit=20",
    ]
    results: list[dict] = []
    seen: set[str] = set()
    for template in templates:
        offset = 0
        try:
            while len(results) < limit:
                url = template.format(token=token, offset=offset)
                resp = await client.get(url)
                if resp.status_code != 200:
                    break
                payload = resp.json()
                batch = iter_api_data_items(payload.get("data"))
                if not batch:
                    break
                for item in batch:
                    entry = _browse_entry_from_item(item)
                    if not entry or entry["url"] in seen:
                        continue
                    seen.add(entry["url"])
                    log_event("zhihu_browse", entry)
                    results.append(entry)
                    if len(results) >= limit:
                        break
                paging = payload.get("paging") or {}
                if paging.get("is_end") or len(batch) < 20:
                    break
                offset += 20
            if results:
                break
        except Exception:  # noqa: BLE001
            continue
    return results


async def ingest_favorites(limit: int = 500) -> list[dict]:
    client = HttpClient()
    token = await _url_token(client)
    if not token:
        return []
    results: list[dict] = []
    seen: set[str] = set()
    offset = 0
    try:
        while len(results) < limit:
            fav_resp = await client.get(
                f"https://www.zhihu.com/api/v4/members/{token}/favlists"
                f"?include=answers&offset={offset}&limit=20"
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
                while len(results) < limit:
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
                        title = content.get("title") or coll.get("title", "")
                        url_ = content.get("url") or raw.get("url") or ""
                        if not url_ or url_ in seen:
                            continue
                        seen.add(url_)
                        entry = {
                            "source": "zhihu",
                            "title": title,
                            "url": url_,
                            "type": "collection_item",
                            "collection": coll.get("title", ""),
                        }
                        log_event("zhihu_fav", entry)
                        save_endorsement(
                            platform="zhihu",
                            target_type="collection",
                            url=url_,
                            content=title,
                        )
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
            if paging.get("is_end"):
                break
            offset += 20
    except Exception:  # noqa: BLE001
        pass
    return results
