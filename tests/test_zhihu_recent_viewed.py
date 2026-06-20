"""Zhihu recent-viewed bootstrap parse tests."""

from osint_toolkit.ingest.zhihu_recent_viewed import parse_recent_viewed_html


def test_parse_recent_viewed_html_from_initial_state():
    html = """
    <html><body>
    <script id="js-initialData" type="text/json">
    {"initialState":{"recentViewed":{"data":[{"target":{"type":"answer","id":9,
    "question":{"id":1,"title":"Hello"},"url":"https://www.zhihu.com/question/1/answer/9"}}]}}}
    </script></body></html>
    """
    rows = parse_recent_viewed_html(html, limit=10)
    assert len(rows) >= 1
    assert rows[0]["via"] == "recent_viewed_bootstrap"
    assert "question/1" in rows[0]["url"]
