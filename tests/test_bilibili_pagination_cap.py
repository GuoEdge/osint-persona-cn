"""Guard: bilibili pagination loops have a ceiling (A7).

These functions use bilibili_api internally. We mock the API calls to return
infinite-duplicate data and verify the loop completes within bounds.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_cursor_response():
    return {
        "code": 0,
        "data": {
            "list": [
                {
                    "title": "deadloop video",
                    "author": "tester",
                    "created": 1700000000,
                    "duration": "00:30",
                    "pic": "https://i0.hdslb.com/bfs/archive/fake.jpg",
                    "bvid": f"BV1xx{i:07d}",
                    "history": {"oid": i, "epid": 0, "dt": 1, "business": "archive"},
                    "uri": f"bilibili://video/BV1xx{i:07d}",
                    "view_at": 1700000000,
                    "progress": 100,
                }
                for i in range(20)
            ],
            "cursor": {"max": 9999, "view_at": 1700000001},
        },
    }


def _make_fav_page_response():
    return {
        "code": 0,
        "data": {
            "medias": [
                {
                    "id": i,
                    "title": "deadloop fav",
                    "type": 2,
                    "uri": f"bilibili://video/BV2xx{i:07d}",
                    "cover": "",
                    "upper": {"name": "t", "mid": 1},
                    "cnt_info": {"collect": 0, "play": 0},
                    "ctime": 1700000000,
                }
                for i in range(20)
            ],
            "has_more": True,
        },
    }


def _make_following_response():
    return {
        "code": 0,
        "data": {
            "list": [
                {"mid": i, "uname": f"user{i}", "face": "", "mtime": 1700000000, "sign": ""}
                for i in range(20)
            ],
            "page": {"num": 1, "size": 20, "total": 9999},
        },
    }


@pytest.mark.asyncio
async def test_ingest_history_has_cap():
    with (
        patch("osint_toolkit.ingest.bilibili_sdk.load_credential", return_value=MagicMock()),
        patch("bilibili_api.user.get_self_history_new", AsyncMock(return_value=_make_cursor_response())),
    ):
        from osint_toolkit.ingest.bilibili_sdk import ingest_history

        result = await ingest_history(limit=50)
    assert len(result) <= 50, f"Expected <=50 items, got {len(result)}"


@pytest.mark.asyncio
async def test_ingest_favorites_has_cap():
    fake_cred = MagicMock()
    folder_list_resp = {
        "code": 0,
        "data": {
            "list": [{"id": 100, "title": "fav folder", "media_count": 9999}],
        },
    }
    with (
        patch("osint_toolkit.ingest.bilibili_sdk.load_credential", return_value=fake_cred),
        patch("osint_toolkit.ingest.bilibili_sdk.resolve_mid", AsyncMock(return_value=1)),
        patch("bilibili_api.favorite_list.get_video_favorite_list", AsyncMock(return_value=folder_list_resp)),
        patch("bilibili_api.favorite_list.get_video_favorite_list_content", AsyncMock(side_effect=lambda *a, **kw: _make_fav_page_response())),
    ):
        from osint_toolkit.ingest.bilibili_sdk import ingest_favorites

        result = await ingest_favorites(limit=50)
    assert len(result) <= 50, f"Expected <=50 items, got {len(result)}"


@pytest.mark.asyncio
async def test_ingest_followings_has_cap():
    fake_user = MagicMock()
    fake_user.get_followings = AsyncMock(return_value=_make_following_response())
    with (
        patch("osint_toolkit.ingest.bilibili_sdk.load_credential", return_value=MagicMock()),
        patch("osint_toolkit.ingest.bilibili_sdk.resolve_mid", AsyncMock(return_value=1)),
        patch("bilibili_api.user.User", return_value=fake_user),
    ):
        from osint_toolkit.ingest.bilibili_sdk import ingest_followings

        result = await ingest_followings(limit=50)
    assert len(result) <= 50, f"Expected <=50 items, got {len(result)}"
