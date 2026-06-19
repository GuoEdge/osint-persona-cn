"""Tests for incremental Bilibili account sync cursors."""

from __future__ import annotations

import json

from osint_toolkit.ingest import account_sync_state as sync_state


def test_filter_new_history_skips_seen_cursor():
    items = [
        {"history": {"view_at": 100, "bvid": "BV1"}, "uri": "https://www.bilibili.com/video/BV1"},
        {"history": {"view_at": 101, "bvid": "BV2"}, "uri": "https://www.bilibili.com/video/BV2"},
    ]
    cursor = {"last_view_at": 100, "last_bvid": "BV1", "bvids_at_last_view_at": ["BV1"]}
    fresh, updated = sync_state.filter_new_history(items, cursor)
    assert len(fresh) == 1
    assert sync_state.history_fields_from_api_item(fresh[0])[1] == "BV2"
    assert updated["last_view_at"] == 101


def test_filter_new_by_bvids_only_new_favorites():
    entries = [
        {"url": "https://www.bilibili.com/video/BVaaa", "bvid": "BVaaa"},
        {"url": "https://www.bilibili.com/video/BVbbb", "bvid": "BVbbb"},
    ]
    fresh = sync_state.filter_new_by_bvids(entries, {"BVaaa"})
    assert len(fresh) == 1
    assert fresh[0]["bvid"] == "BVbbb"


def test_filter_new_following_skips_known_mids():
    entries = [
        {"uid": 1, "url": "https://space.bilibili.com/1"},
        {"uid": 2, "url": "https://space.bilibili.com/2"},
    ]
    fresh = sync_state.filter_new_following(entries, {"1"})
    assert len(fresh) == 1
    assert fresh[0]["uid"] == 2


def test_update_bilibili_section_persists_signatures(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    state: dict = {}
    sync_state.update_bilibili_section(
        state,
        history={"last_view_at": 5, "last_bvid": "BVx", "bvids_at_last_view_at": ["BVx"]},
        favorites=[{"url": "https://www.bilibili.com/video/BVf", "bvid": "BVf", "folder": "默认"}],
        likes=[{"url": "https://www.bilibili.com/video/BVl", "bvid": "BVl"}],
        following=[{"uid": 9, "url": "https://space.bilibili.com/9"}],
    )
    sync_state.save_account_sync_state(state)
    loaded = sync_state.load_account_sync_state()
    assert loaded["bilibili"]["history"]["last_view_at"] == 5
    assert "BVf" in loaded["bilibili"]["favorite_bvids"]
    assert loaded["bilibili"]["following_mids"] == ["9"]


def test_update_bilibili_section_merges_following_mids():
    state: dict = {
        "bilibili": {"following_mids": ["1", "2"]},
    }
    sync_state.update_bilibili_section(
        state,
        following=[{"uid": 2, "url": "https://space.bilibili.com/2"}, {"uid": 3, "url": "https://space.bilibili.com/3"}],
    )
    assert state["bilibili"]["following_mids"] == ["1", "2", "3"]


def test_filter_new_by_urls_skips_seen():
    entries = [
        {"url": "https://www.zhihu.com/question/1/answer/1"},
        {"url": "https://www.zhihu.com/question/2/answer/2"},
    ]
    fresh = sync_state.filter_new_by_urls(entries, {"https://www.zhihu.com/question/1/answer/1"})
    assert len(fresh) == 1
    assert fresh[0]["url"].endswith("/answer/2")


def test_update_zhihu_section_merges_urls(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    state: dict = {"zhihu": {"favorite_urls": ["https://zhuanlan.zhihu.com/p/1"]}}
    sync_state.update_zhihu_section(
        state,
        favorites=[
            {"url": "https://zhuanlan.zhihu.com/p/1"},
            {"url": "https://zhuanlan.zhihu.com/p/2"},
        ],
        votes=[{"url": "https://www.zhihu.com/question/1/answer/9"}],
    )
    assert "https://zhuanlan.zhihu.com/p/2" in state["zhihu"]["favorite_urls"]
    assert state["zhihu"]["vote_urls"] == ["https://www.zhihu.com/question/1/answer/9"]
    sync_state.save_account_sync_state(state)
    loaded = sync_state.load_account_sync_state()
    assert loaded["zhihu"]["favorite_urls"] == state["zhihu"]["favorite_urls"]


def test_save_account_sync_state_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    state = {"bilibili": {"history": {"last_view_at": 1}}}
    sync_state.save_account_sync_state(state)
    path = tmp_path / "account_sync_state.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["bilibili"]["history"]["last_view_at"] == 1
