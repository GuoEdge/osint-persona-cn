"""浏览器扩展事件解析 / Extension event normalization."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from osint_toolkit.ingest.capture_patterns import should_capture_url

_BILIBILI_VIDEO = re.compile(r"/video/(BV[\w]+|av\d+)", re.I)

_PLATFORM_HOSTS: tuple[tuple[str, str], ...] = (
    ("bilibili.com", "bilibili"),
    ("zhihu.com", "zhihu"),
    ("github.com", "github"),
    ("v2ex.com", "v2ex"),
    ("juejin.cn", "juejin"),
    ("sspai.com", "sspai"),
    ("huxiu.com", "huxiu"),
    ("36kr.com", "36kr"),
    ("xiaohongshu.com", "xiaohongshu"),
    ("weibo.com", "weibo"),
    ("douban.com", "douban"),
    ("twitter.com", "twitter"),
    ("x.com", "twitter"),
)


def platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for domain, name in _PLATFORM_HOSTS:
        if domain in host:
            return name
    return "web"


def _video_url(item: dict) -> str:
    bvid = item.get("bvid") or item.get("bv_id") or ""
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    short = item.get("short_link_v2") or item.get("short_link") or ""
    if short:
        return short
    aid = item.get("aid") or item.get("id")
    if aid and str(item.get("goto", "")) != "article":
        return f"https://www.bilibili.com/video/av{aid}"
    return item.get("link") or item.get("uri") or ""


def _zhihu_content_url(target: dict, item: dict | None = None) -> str:
    item = item or {}
    target = target or {}
    url = target.get("url") or item.get("url") or ""
    if url.startswith("http"):
        return url
    question = target.get("question") or {}
    answer_id = target.get("id")
    qid = question.get("id")
    if answer_id and qid:
        return f"https://www.zhihu.com/question/{qid}/answer/{answer_id}"
    if target.get("type") == "article" and target.get("id"):
        return f"https://zhuanlan.zhihu.com/p/{target['id']}"
    return url


def _dedup_key(event_type: str, url: str, extra: str = "") -> str:
    raw = f"{event_type}|{url}|{extra}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def parse_api_capture(url: str, body: Any) -> list[tuple[str, dict[str, Any], str]]:
    """Parse hooked API response into (event_type, data, dedup_key) tuples."""
    if not isinstance(body, dict):
        return []
    if not should_capture_url(url):
        return []
    if "bilibili.com" in url:
        return _parse_bilibili_api(url, body)
    if "zhihu.com" in url:
        return _parse_zhihu_api(url, body)
    if "api.github.com/graphql" in url:
        return _parse_github_api(url, body)
    return []


def _parent_url_for_comment(*, oid: str, comment_type: str) -> str:
    if not oid:
        return ""
    if comment_type == "12":
        return f"https://www.bilibili.com/read/cv{oid}"
    if comment_type == "17":
        return f"https://www.bilibili.com/opus/{oid}"
    return f"https://www.bilibili.com/video/av{oid}"


def _iter_reply_nodes(nodes: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if node.get("rpid") is not None:
                found.append(node)
            for sub in node.get("replies") or []:
                walk(sub)

    walk(nodes)
    return found


def _parse_reply_action(body: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    params = body.get("_osint_reply_action") or {}
    if str(params.get("action", "1")) == "0":
        return []
    rpid = str(params.get("rpid") or "")
    oid = str(params.get("oid") or "")
    comment_type = str(params.get("type") or "1")
    if not rpid or not oid:
        return []
    parent_url = _parent_url_for_comment(oid=oid, comment_type=comment_type)
    entry = {
        "source": "bilibili",
        "title": f"评论点赞 rpid={rpid}",
        "url": parent_url,
        "rpid": rpid,
        "oid": oid,
        "comment_type": comment_type,
        "event_kind": "comment_like",
        "via": "extension",
    }
    return [("bilibili_comment_like", entry, _dedup_key("bilibili_comment_like", rpid))]


def _parse_reply_main_likes(body: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    data = body.get("data")
    if not isinstance(data, dict):
        return []
    out: list[tuple[str, dict[str, Any], str]] = []
    for reply in _iter_reply_nodes(data.get("replies") or []):
        if int(reply.get("action") or 0) != 1:
            continue
        rpid = str(reply.get("rpid") or "")
        oid = str(reply.get("oid") or "")
        if not rpid:
            continue
        message = str((reply.get("content") or {}).get("message") or "").strip()
        comment_type = str(reply.get("type") or "1")
        parent_url = _parent_url_for_comment(oid=oid, comment_type=comment_type)
        entry = {
            "source": "bilibili",
            "title": message[:200] if message else f"评论点赞 rpid={rpid}",
            "url": parent_url,
            "rpid": rpid,
            "oid": oid,
            "message": message,
            "event_kind": "comment_like",
            "via": "extension",
        }
        out.append(("bilibili_comment_like", entry, _dedup_key("bilibili_comment_like", rpid)))
    return out


def _parse_bilibili_api(url: str, body: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    if body.get("_osint_reply_action"):
        return _parse_reply_action(body)

    if "/x/v2/reply" in url and "main" in url:
        if body.get("code") not in (0, None):
            return []
        return _parse_reply_main_likes(body)

    if body.get("code") not in (0, None):
        return []
    out: list[tuple[str, dict[str, Any], str]] = []
    data = body.get("data")
    if data is None:
        return []

    if "/wbi/like/archive" in url or "/x/space/like/video" in url or "/x/space/coin/video" in url:
        event_kind = "coin" if "coin" in url else "like"
        event_type = f"bilibili_{event_kind}"
        items = data if isinstance(data, list) else (data.get("list") or [])
        for item in items:
            video_url = _video_url(item)
            if not video_url:
                continue
            entry = {
                "source": "bilibili",
                "title": item.get("title", ""),
                "url": video_url,
                "event_kind": event_kind,
                "via": "extension",
            }
            out.append((event_type, entry, _dedup_key(event_type, video_url)))
        return out

    if "/x/web-interface/history" in url:
        batch = data.get("list") or []
        for item in batch:
            link = item.get("uri") or item.get("short_link_v2") or ""
            hist = item.get("history") or {}
            if not link and hist.get("bvid"):
                link = f"https://www.bilibili.com/video/{hist['bvid']}"
            if not link:
                continue
            entry = {
                "source": "bilibili",
                "title": item.get("title", ""),
                "url": link,
                "progress": item.get("progress", 0),
                "duration": item.get("duration", 0),
                "event_kind": "watch_history",
                "via": "extension",
            }
            out.append(("bilibili_watch", entry, _dedup_key("bilibili_watch", link)))
        return out

    if "/x/v3/fav/" in url or "/fav/resource/list" in url:
        medias = data.get("medias") or []
        for media in medias:
            video_url = _video_url(media)
            if not video_url:
                continue
            entry = {
                "source": "bilibili",
                "title": media.get("title", ""),
                "url": video_url,
                "event_kind": "favorite",
                "via": "extension",
            }
            out.append(("bilibili_fav", entry, _dedup_key("bilibili_fav", video_url)))
        return out

    if "/medialist/" in url:
        medias = data.get("medias") or data.get("list") or []
        for media in medias:
            video_url = _video_url(media)
            if not video_url:
                continue
            entry = {
                "source": "bilibili",
                "title": media.get("title", ""),
                "url": video_url,
                "event_kind": "like",
                "via": "extension",
            }
            out.append(("bilibili_like", entry, _dedup_key("bilibili_like", video_url)))
    return out


def _parse_zhihu_api(url: str, body: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    out: list[tuple[str, dict[str, Any], str]] = []

    from osint_toolkit.ingest.zhihu_activities import iter_api_data_items

    if "/collections/" in url and "/items" in url:
        for item in iter_api_data_items(body.get("data")):
            target = item.get("content") or item.get("target") or item
            content_url = _zhihu_content_url(target, item)
            if not content_url:
                continue
            title = (target.get("question") or {}).get("title") or target.get("title") or ""
            entry = {
                "source": "zhihu",
                "title": title,
                "url": content_url,
                "event_kind": "favorite",
                "via": "extension",
            }
            out.append(("zhihu_fav", entry, _dedup_key("zhihu_fav", content_url)))
        return out

    if "voteanswers" in url or "vote_answers" in url:
        for item in iter_api_data_items(body.get("data")):
            target = item.get("target") or item
            content_url = _zhihu_content_url(target, item)
            if not content_url:
                continue
            title = (target.get("question") or {}).get("title") or target.get("title") or ""
            entry = {
                "source": "zhihu",
                "title": title,
                "url": content_url,
                "type": "answer_vote",
                "via": "extension",
            }
            out.append(("zhihu_vote", entry, _dedup_key("zhihu_vote", content_url)))
        return out

    if "/activities" in url or "recent" in url or "record_viewed" in url or "viewed" in url:
        from osint_toolkit.ingest.zhihu_activities import activity_entry_from_item, classify_activity

        for item in iter_api_data_items(body.get("data")):
            entry = activity_entry_from_item(item, via="extension")
            if not entry:
                continue
            classified = classify_activity(item)
            event_type = classified[0] if classified else "zhihu_activity"
            out.append((event_type, entry, _dedup_key(event_type, entry["url"])))
        if out:
            return out

    if "footprints" in url or "browsing" in url:
        for item in iter_api_data_items(body.get("data")):
            target = item.get("target") or item
            content_url = _zhihu_content_url(target, item)
            if not content_url:
                continue
            title = (target.get("question") or {}).get("title") or target.get("title") or ""
            entry = {
                "source": "zhihu",
                "title": title,
                "url": content_url,
                "event_kind": "browse",
                "via": "extension",
            }
            out.append(("zhihu_browse", entry, _dedup_key("zhihu_browse", content_url)))
    return out


def _iter_github_starred_nodes(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if not isinstance(data, dict):
        return []
    for root_key in ("viewer", "user", "node"):
        root = data.get(root_key)
        if not isinstance(root, dict):
            continue
        starred = root.get("starredRepositories") or root.get("repositories")
        if not isinstance(starred, dict):
            continue
        nodes = starred.get("nodes") or starred.get("edges") or []
        out: list[dict[str, Any]] = []
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("node"), dict):
                out.append(node["node"])
            elif isinstance(node, dict):
                out.append(node)
        if out:
            return out
    return []


def _parse_github_api(url: str, body: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    out: list[tuple[str, dict[str, Any], str]] = []
    for repo in _iter_github_starred_nodes(body):
        name = str(repo.get("nameWithOwner") or repo.get("full_name") or "")
        repo_url = str(repo.get("url") or "")
        if not repo_url and name:
            repo_url = f"https://github.com/{name}"
        if not repo_url.startswith("http"):
            continue
        entry = {
            "source": "github",
            "title": name or repo.get("name", ""),
            "url": repo_url,
            "description": str(repo.get("description") or "")[:200],
            "event_kind": "star",
            "via": "extension",
        }
        out.append(("github_star", entry, _dedup_key("github_star", repo_url)))
    return out


def normalize_extension_payload(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    """Turn a raw extension message into storable events."""
    kind = payload.get("kind") or payload.get("type") or ""
    out: list[tuple[str, dict[str, Any], str]] = []

    if kind == "api_capture":
        return parse_api_capture(str(payload.get("url") or ""), payload.get("body"))

    if kind == "page_visit":
        page_url = str(payload.get("url") or "")
        if not page_url.startswith("http"):
            return []
        platform = str(payload.get("platform") or platform_from_url(page_url))
        entry = {
            "source": platform,
            "url": page_url,
            "title": str(payload.get("title") or ""),
            "event_kind": "page_visit",
            "via": "extension",
        }
        today = datetime.now(UTC).date().isoformat()
        out.append(("ext_page_visit", entry, _dedup_key("ext_page_visit", page_url, today)))
        return out

    if kind == "page_session":
        page_url = str(payload.get("url") or "")
        if not page_url.startswith("http"):
            return []
        duration_ms = int(payload.get("duration_ms") or 0)
        if duration_ms < 3000:
            return []
        platform = str(payload.get("platform") or platform_from_url(page_url))
        entry = {
            "source": platform,
            "url": page_url,
            "title": str(payload.get("title") or ""),
            "duration_ms": duration_ms,
            "event_kind": "page_dwell",
            "via": "extension",
        }
        if platform == "bilibili":
            m = _BILIBILI_VIDEO.search(page_url)
            if m:
                entry["content_type"] = "video"
        key_extra = str(duration_ms // 60000)
        out.append(("ext_page_dwell", entry, _dedup_key("ext_page_dwell", page_url, key_extra)))
        return out

    if kind == "save_to_osint":
        page_url = str(payload.get("url") or "")
        if not page_url:
            return []
        entry = {
            "source": str(payload.get("platform") or "web"),
            "url": page_url,
            "title": str(payload.get("title") or ""),
            "event_kind": "save",
            "via": "extension",
        }
        out.append(("ext_save", entry, _dedup_key("ext_save", page_url)))
        return out

    if kind == "raw_event":
        event_type = str(payload.get("event_type") or "ext_custom")
        data = dict(payload.get("data") or {})
        data.setdefault("via", "extension")
        url = str(data.get("url") or "")
        out.append((event_type, data, _dedup_key(event_type, url or event_type)))
        return out

    return out
