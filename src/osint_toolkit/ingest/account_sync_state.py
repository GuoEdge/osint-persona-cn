"""Incremental cursors for Bilibili account-side API sync."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.auth.paths import get_data_dir

_STATE_FILE = "account_sync_state.json"


def _state_path():
    return get_data_dir() / _STATE_FILE


def load_account_sync_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_account_sync_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    bilibili = state.setdefault("bilibili", {})
    bilibili["last_sync_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _to_int(value: object) -> int:
    if value is None or value is False:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _bvid_from_url(url: str) -> str:
    url = url.strip()
    if "/video/BV" in url or "/video/bv" in url.lower():
        part = url.rsplit("/", 1)[-1]
        return part.split("?")[0]
    return ""


# --- History (view_at + bvid cursor) ---


def history_fields_from_api_item(item: dict[str, Any]) -> tuple[int, str, str]:
    """Return (view_at, bvid, url) from a B站 history list item."""
    history_meta = item.get("history") if isinstance(item.get("history"), dict) else {}
    if not history_meta:
        history_meta = item
    view_at = _to_int(history_meta.get("view_at", item.get("view_at", 0)))
    bvid = str(history_meta.get("bvid", "") or item.get("bvid", "")).strip()
    link = (
        item.get("uri", "")
        or item.get("short_link_v2", "")
        or (f"https://www.bilibili.com/video/{bvid}" if bvid else "")
        or item.get("bvid", "")
    )
    return view_at, bvid, str(link)


def filter_new_history(
    items: list[dict[str, Any]],
    cursor: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Drop history rows already covered by the stored cursor."""
    last_view_at = _to_int(cursor.get("last_view_at", 0))
    last_bvid = str(cursor.get("last_bvid", "")).strip()
    seen_at_cursor = _string_set(cursor.get("bvids_at_last_view_at", []))
    if last_bvid:
        seen_at_cursor.add(last_bvid)

    accepted: list[dict[str, Any]] = []
    newest_view_at = last_view_at
    newest_bvid = last_bvid

    for item in items:
        view_at, bvid, link = history_fields_from_api_item(item)
        if view_at < last_view_at:
            continue
        if view_at == last_view_at and bvid and bvid in seen_at_cursor:
            continue
        accepted.append(item)
        if view_at > newest_view_at:
            newest_view_at = view_at
            newest_bvid = bvid
        elif view_at == newest_view_at and bvid:
            newest_bvid = bvid

    updated = {
        "last_view_at": newest_view_at,
        "last_bvid": newest_bvid,
        "bvids_at_last_view_at": _history_bvids_at_view_at(
            items,
            newest_view_at,
            fallback_bvid=newest_bvid,
            previous_seen=seen_at_cursor if newest_view_at == last_view_at else set(),
        ),
    }
    return accepted, updated


def filter_new_history_entries(
    entries: list[dict[str, Any]],
    cursor: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter normalized history rows (url, view_at, bvid) against cursor."""
    fake_items = [
        {
            "history": {
                "view_at": entry.get("view_at", 0),
                "bvid": entry.get("bvid", ""),
            },
            "uri": entry.get("url", ""),
            "title": entry.get("title", ""),
        }
        for entry in entries
    ]
    accepted_items, updated = filter_new_history(fake_items, cursor)
    new_urls = {history_fields_from_api_item(item)[2] for item in accepted_items}
    new_urls.discard("")
    fresh = [entry for entry in entries if entry.get("url") in new_urls]
    return fresh, updated


def _history_bvids_at_view_at(
    items: list[dict[str, Any]],
    view_at: int,
    *,
    fallback_bvid: str = "",
    previous_seen: set[str] | None = None,
) -> list[str]:
    bvids: set[str] = set()
    if view_at > 0:
        for item in items:
            item_view_at, bvid, _ = history_fields_from_api_item(item)
            if item_view_at != view_at:
                continue
            if bvid:
                bvids.add(bvid)
    if previous_seen:
        bvids.update(previous_seen)
    if fallback_bvid:
        bvids.add(fallback_bvid)
    return sorted(bvids)


# --- Favorites / likes (bvid or url sets) ---


def _entries_bvids(entries: list[dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for entry in entries:
        bvid = str(entry.get("bvid") or "").strip()
        if not bvid:
            bvid = _bvid_from_url(str(entry.get("url") or ""))
        if bvid:
            out.add(bvid)
    return sorted(out)


def filter_new_by_bvids(
    entries: list[dict[str, Any]],
    seen_bvids: set[str],
) -> list[dict[str, Any]]:
    if not seen_bvids:
        return list(entries)
    fresh: list[dict[str, Any]] = []
    for entry in entries:
        bvid = str(entry.get("bvid") or "").strip() or _bvid_from_url(str(entry.get("url") or ""))
        if bvid and bvid in seen_bvids:
            continue
        fresh.append(entry)
    return fresh


def favorite_signature(entries: list[dict[str, Any]]) -> str:
    """Stable signature: folder_id:bvid,... per folder."""
    by_folder: dict[str, list[str]] = {}
    for entry in entries:
        folder = str(entry.get("folder") or entry.get("folder_id") or "default")
        bvid = str(entry.get("bvid") or "").strip() or _bvid_from_url(str(entry.get("url") or ""))
        if bvid:
            by_folder.setdefault(folder, []).append(bvid)
    parts = [
        f"{folder}:{','.join(sorted(set(bvids)))}"
        for folder, bvids in sorted(by_folder.items())
        if bvids
    ]
    return "|".join(parts)


def like_signature(entries: list[dict[str, Any]]) -> str:
    return ",".join(_entries_bvids(entries))


def following_signature(entries: list[dict[str, Any]]) -> str:
    mids = sorted(
        {
            str(entry.get("uid") or entry.get("mid") or "").strip()
            for entry in entries
            if str(entry.get("uid") or entry.get("mid") or "").strip()
        }
    )
    return ",".join(mids)


def filter_new_following(
    entries: list[dict[str, Any]],
    seen_mids: set[str],
) -> list[dict[str, Any]]:
    if not seen_mids:
        return list(entries)
    fresh: list[dict[str, Any]] = []
    for entry in entries:
        mid = str(entry.get("uid") or entry.get("mid") or "").strip()
        if mid and mid in seen_mids:
            continue
        fresh.append(entry)
    return fresh


def update_bilibili_section(
    state: dict[str, Any],
    *,
    history: dict[str, Any] | None = None,
    favorites: list[dict[str, Any]] | None = None,
    likes: list[dict[str, Any]] | None = None,
    following: list[dict[str, Any]] | None = None,
) -> None:
    """Merge one sync pass into persisted bilibili cursors."""
    section = state.setdefault("bilibili", {})
    if history is not None:
        section["history"] = history
    if favorites is not None:
        section["favorite_signature"] = favorite_signature(favorites)
        section["favorite_bvids"] = _entries_bvids(favorites)
    if likes is not None:
        section["like_signature"] = like_signature(likes)
        section["like_bvids"] = _entries_bvids(likes)
    if following is not None:
        section["following_signature"] = following_signature(following)
        section["following_mids"] = [
            str(entry.get("uid") or entry.get("mid") or "").strip()
            for entry in following
            if str(entry.get("uid") or entry.get("mid") or "").strip()
        ]
