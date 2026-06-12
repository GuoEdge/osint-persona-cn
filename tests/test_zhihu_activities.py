"""Zhihu activity classification tests."""

from osint_toolkit.ingest.zhihu_activities import (
    activity_entry_from_item,
    classify_activity,
    iter_api_data_items,
)


def test_iter_api_data_items_from_paging_object():
    items = iter_api_data_items({"data": [{"verb": "x"}], "paging": {"is_end": True}})
    assert len(items) == 1
    assert items[0]["verb"] == "x"


def test_classify_vote_activity():
    assert classify_activity({"verb": "赞同了回答", "type": "MEMBER_VOTEUP_ANSWER"})[0] == "zhihu_vote"


def test_classify_favorite_activity():
    assert classify_activity({"verb": "收藏了回答", "type": "MEMBER_FAVORITE_ANSWER"})[0] == "zhihu_fav"


def test_activity_entry_follow_without_target_url_uses_people_link():
    item = {
        "verb": "关注了用户",
        "type": "MEMBER_FOLLOW",
        "target": {"name": "张三", "url_token": "zhang-san"},
    }
    entry = activity_entry_from_item(item)
    assert entry is not None
    assert entry["url"] == "https://www.zhihu.com/people/zhang-san"
    assert entry["event_kind"] == "follow"


def test_activity_entry_builds_answer_url():
    item = {
        "verb": "赞同了回答",
        "type": "MEMBER_VOTEUP_ANSWER",
        "target": {
            "id": 123,
            "question": {"id": 456, "title": "测试问题"},
        },
    }
    entry = activity_entry_from_item(item)
    assert entry is not None
    assert entry["url"] == "https://www.zhihu.com/question/456/answer/123"
    assert entry["event_kind"] == "answer_vote"
