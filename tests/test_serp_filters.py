"""SERP 广告/热搜过滤测试."""

from bs4 import BeautifulSoup

from osint_toolkit.collectors.serp.filters import (
    is_ad_block,
    is_baidu_non_organic,
    is_bing_non_organic,
)


def test_baidu_hot_search_url_blocked():
    assert is_baidu_non_organic("https://top.baidu.com/board?platform=pc")
    assert is_baidu_non_organic("https://www.baidu.com/s?wd=hot")


def test_baidu_organic_redirect_allowed():
    assert not is_baidu_non_organic("https://www.baidu.com/link?url=https%3A%2F%2Fexample.com")


def test_ad_block_detects_ec_ad():
    html = '<div class="c-container ec_ad"><h3><a href="http://ad.com">推广</a></h3></div>'
    block = BeautifulSoup(html, "html.parser").select_one("div")
    assert is_ad_block(block)


def test_bing_answer_without_link_is_non_organic():
    html = '<li class="b_ans"><p>答案摘要</p></li>'
    block = BeautifulSoup(html, "html.parser").select_one("li")
    assert is_bing_non_organic(block, "https://bing.com")
