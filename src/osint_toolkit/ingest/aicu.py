"""AICU 第三方 B 站发评历史导入 / Posted-comment history via aicu.cc."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.bilibili_account import _nav_mid
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.utils.config import load_config

AICU_GETREPLY = "https://api.aicu.cc/api/v3/search/getreply"
_CF_MARKERS = ("Just a moment", "safeline", "cf-browser-verification", "challenge-platform")


def parent_url_from_dyn(dyn: dict[str, Any] | None, *, aid_bvid: dict[str, str] | None = None) -> str:
    """Map AICU dyn {oid, type} to a content URL."""
    if not dyn:
        return ""
    oid = str(dyn.get("oid") or "")
    if not oid:
        return ""
    ctype = int(dyn.get("type") or 0)
    cache = aid_bvid or {}
    if ctype == 1:
        bvid = cache.get(oid)
        if bvid:
            return f"https://www.bilibili.com/video/{bvid}"
        return f"https://www.bilibili.com/video/av{oid}"
    if ctype == 12:
        return f"https://www.bilibili.com/read/cv{oid}"
    if ctype == 17:
        return f"https://www.bilibili.com/opus/{oid}"
    return ""


def parse_aicu_reply(
    reply: dict[str, Any],
    *,
    aid_bvid: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    rpid = str(reply.get("rpid") or "")
    message = str(reply.get("message") or "").strip()
    if not rpid:
        return None
    dyn = reply.get("dyn") if isinstance(reply.get("dyn"), dict) else {}
    parent_url = parent_url_from_dyn(dyn, aid_bvid=aid_bvid)
    title = message[:200] if message else f"评论 rpid={rpid}"
    return {
        "source": "bilibili",
        "title": title,
        "url": parent_url,
        "message": message,
        "rpid": rpid,
        "parent_url": parent_url,
        "comment_time": int(reply.get("time") or 0),
        "event_kind": "comment_post",
        "via": "aicu",
    }


def parse_aicu_page(body: dict[str, Any]) -> tuple[list[dict[str, Any]], bool, int]:
    """Return (replies, is_end, all_count)."""
    if body.get("code") not in (0, None):
        return [], True, 0
    data = body.get("data") or {}
    cursor = data.get("cursor") or {}
    is_end = bool(cursor.get("is_end"))
    all_count = int(cursor.get("all_count") or 0)
    raw = data.get("replies") or []
    return [r for r in raw if isinstance(r, dict)], is_end, all_count


def extract_replies_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Accept AICU API page JSON, array of pages, or bare replies list."""
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "rpid" in payload[0]:
            return [r for r in payload if isinstance(r, dict)]
        replies: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                replies.extend(parse_aicu_page(item)[0])
        return replies
    if isinstance(payload, dict):
        if "replies" in payload and isinstance(payload.get("replies"), list):
            return [r for r in payload["replies"] if isinstance(r, dict)]
        return parse_aicu_page(payload)[0]
    return []


def _dedup_key(event_type: str, rpid: str) -> str:
    return f"{event_type}|{rpid}"


def _try_mark_dedup(conn, dedup_key: str, event_type: str) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO event_dedup (dedup_key, event_type) VALUES (?, ?)",
        (dedup_key, event_type),
    )
    return cur.rowcount > 0


def _aicu_request_headers() -> dict[str, str]:
    cfg = load_config()
    http_cfg = cfg.get("http", {})
    ingest_cfg = cfg.get("ingest", {})
    ua = str(
        http_cfg.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        )
    )
    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.aicu.cc/",
        "Origin": "https://www.aicu.cc",
    }
    cookie = str(ingest_cfg.get("aicu_cookie") or "").strip()
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _is_waf_block(status_code: int, text: str) -> bool:
    if status_code in {403, 468, 503}:
        return True
    snippet = (text or "")[:500]
    return any(marker in snippet for marker in _CF_MARKERS)


async def _fetch_aicu_page(
    client: httpx.AsyncClient,
    *,
    uid: int,
    pn: int,
    ps: int,
) -> dict[str, Any]:
    headers = _aicu_request_headers()
    resp = await client.get(
        AICU_GETREPLY,
        params={"uid": str(uid), "pn": str(pn), "ps": str(ps), "mode": "0", "keyword": ""},
        headers=headers,
        timeout=30.0,
    )
    text = resp.text
    if _is_waf_block(resp.status_code, text):
        raise RuntimeError(
            "aicu_waf_blocked: AICU 拦截了程序访问（网页能查、脚本不能）。"
            "请用扩展「浏览器拉取 AICU 发评」或粘贴 Network 里的 JSON 导入。"
        )
    resp.raise_for_status()
    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        if _is_waf_block(resp.status_code, text):
            raise RuntimeError("aicu_waf_blocked: 响应非 JSON，可能被 WAF 拦截") from exc
        raise


async def _resolve_bvid(client: HttpClient, aid: str, cache: dict[str, str]) -> None:
    if aid in cache:
        return
    try:
        resp = await client.get(f"https://api.bilibili.com/x/web-interface/view?aid={aid}")
        payload = resp.json()
        if payload.get("code") == 0:
            bvid = (payload.get("data") or {}).get("bvid") or ""
            if bvid:
                cache[aid] = bvid
    except Exception:  # noqa: BLE001
        pass


async def _persist_replies(
    replies: list[dict[str, Any]],
    *,
    limit: int,
    bili: HttpClient | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Return (saved_rows, skipped, all_count_hint)."""
    bili = bili or HttpClient()
    results: list[dict[str, Any]] = []
    aid_bvid: dict[str, str] = {}
    skipped = 0
    conn = connect()
    try:
        for raw in replies:
            dyn = raw.get("dyn") if isinstance(raw.get("dyn"), dict) else {}
            if int(dyn.get("type") or 0) == 1:
                oid = str(dyn.get("oid") or "")
                if oid and oid not in aid_bvid:
                    await _resolve_bvid(bili, oid, aid_bvid)

            entry = parse_aicu_reply(raw, aid_bvid=aid_bvid)
            if not entry:
                continue
            dedup_key = _dedup_key("bilibili_comment_post", entry["rpid"])
            if not _try_mark_dedup(conn, dedup_key, "bilibili_comment_post"):
                skipped += 1
                continue
            conn.execute(
                "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
                ("bilibili_comment_post", json.dumps(entry, ensure_ascii=False)),
            )
            results.append(entry)
            if len(results) >= limit:
                break
        conn.commit()
    finally:
        conn.close()
    return results, skipped, len(replies)


async def get_bilibili_mid() -> int | None:
    return await _nav_mid(HttpClient())


async def ingest_aicu_from_json(payload: Any, *, limit: int = 10_000) -> dict[str, Any]:
    cfg = load_config().get("ingest", {})
    if not cfg.get("aicu_enabled", False):
        return {"ok": False, "error": "aicu_disabled", "count": 0}

    replies = extract_replies_from_payload(payload)
    if not replies:
        return {"ok": False, "error": "aicu_json_empty", "count": 0}

    results, skipped, all_count = await _persist_replies(replies, limit=limit)
    return {
        "ok": True,
        "count": len(results),
        "skipped": skipped,
        "all_count": all_count,
        "source": "json",
        "rows": results[:20],
    }


async def ingest_aicu_comments(
    *,
    limit: int = 10_000,
    page_size: int | None = None,
    delay_sec: float | None = None,
) -> dict[str, Any]:
    cfg = load_config().get("ingest", {})
    if not cfg.get("aicu_enabled", False):
        return {"ok": False, "error": "aicu_disabled", "count": 0}

    ps = int(page_size or cfg.get("aicu_page_size") or 100)
    delay = float(delay_sec if delay_sec is not None else cfg.get("aicu_delay_sec", 1.5))

    bili = HttpClient()
    mid = await _nav_mid(bili)
    if not mid:
        return {"ok": False, "error": "bilibili_not_logged_in", "count": 0}

    all_replies: list[dict[str, Any]] = []
    pn = 1
    all_count = 0

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            while len(all_replies) < limit:
                body = await _fetch_aicu_page(client, uid=mid, pn=pn, ps=ps)
                replies, is_end, all_count = parse_aicu_page(body)
                if not replies and pn == 1:
                    break
                all_replies.extend(replies)
                if is_end or not replies:
                    break
                pn += 1
                if delay > 0:
                    await asyncio.sleep(delay)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "aicu_waf_blocked" in msg:
            return {
                "ok": False,
                "error": "aicu_waf_blocked",
                "detail": msg,
                "count": 0,
                "uid": mid,
                "hint": "先在浏览器打开 aicu.cc 查一次 UID，再用扩展拉取或粘贴 JSON",
            }
        return {"ok": False, "error": f"aicu_request_failed: {exc}", "count": 0, "uid": mid}

    results, skipped, _ = await _persist_replies(all_replies[:limit], limit=limit, bili=bili)
    return {
        "ok": True,
        "count": len(results),
        "skipped": skipped,
        "all_count": all_count,
        "uid": mid,
        "rows": results[:20],
    }
