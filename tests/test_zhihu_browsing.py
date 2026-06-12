"""Zhihu browsing ingest tests."""

from __future__ import annotations

from osint_toolkit.ingest.zhihu_account import _browse_entry_from_item


def test_browse_entry_from_answer_item():
    item = {
        "target": {
            "id": 123,
            "question": {"id": 456, "title": "测试问题"},
        }
    }
    entry = _browse_entry_from_item(item)
    assert entry
    assert entry["url"] == "https://www.zhihu.com/question/456/answer/123"
    assert entry["title"] == "测试问题"
