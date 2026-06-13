"""HttpClient header tests."""

from osint_toolkit.http.client import HttpClient


def test_zhihu_search_referer():
    ref = HttpClient._zhihu_referer(
        "https://www.zhihu.com/api/v4/search_v3?t=general&q=python&limit=5"
    )
    assert ref == "https://www.zhihu.com/search?type=content&q=python"


def test_zhihu_default_referer():
    ref = HttpClient._zhihu_referer("https://www.zhihu.com/api/v4/answers/1")
    assert ref == "https://www.zhihu.com/"
