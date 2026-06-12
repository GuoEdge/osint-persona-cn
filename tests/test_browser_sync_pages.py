"""Browser sync page list tests."""

from osint_toolkit.ingest.browser_sync import build_sync_pages


def test_zhihu_only_pages():
    pages = build_sync_pages(platforms=("zhihu",), zhihu_token="sankichu")
    assert len(pages) == 3
    assert pages[0]["url"] == "https://www.zhihu.com/recent-viewed"


def test_bilibili_only_pages():
    pages = build_sync_pages(platforms=("bilibili",), bilibili_mid="32823281")
    assert len(pages) == 5
    assert any("account/history" in p["url"] for p in pages)
    assert any("/dynamic" in p["url"] for p in pages)


def test_empty_without_tokens():
    assert build_sync_pages(platforms=("bilibili", "zhihu")) == []
