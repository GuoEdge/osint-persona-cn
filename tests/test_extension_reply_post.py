"""Extension reply/add capture tests."""

from osint_toolkit.ingest.extension_events import parse_api_capture


def test_parse_reply_post_as_comment_post():
    body = {
        "code": 0,
        "_osint_reply_post": {
            "type": "1",
            "oid": "12345",
            "message": "这是我的评论",
        },
        "_osint_response": {"data": {"reply": {"rpid": 999}}},
    }
    rows = parse_api_capture("https://api.bilibili.com/x/v2/reply/add", body)
    assert len(rows) == 1
    assert rows[0][0] == "bilibili_comment_post"
    assert rows[0][1]["event_kind"] == "comment_post"
    assert rows[0][1]["message"] == "这是我的评论"
    assert rows[0][1]["rpid"] == "999"
