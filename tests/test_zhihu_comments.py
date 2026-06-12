"""Zhihu comment fetch tests."""

from osint_toolkit.collectors.zhihu import ZhihuCollector


def test_fetch_comments_url_answer():
    col = ZhihuCollector()
    assert col._comment_resource("https://www.zhihu.com/question/1/answer/2") == ("answers", "2")


def test_fetch_comments_url_article():
    col = ZhihuCollector()
    assert col._comment_resource("https://zhuanlan.zhihu.com/p/12345") == ("articles", "12345")
