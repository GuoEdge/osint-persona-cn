"""Zhihu public URL normalization tests."""

from __future__ import annotations

from osint_toolkit.utils.zhihu_urls import public_zhihu_url


def test_api_article_url_to_zhuanlan():
    url = public_zhihu_url("https://api.zhihu.com/articles/2049151623004413971")
    assert url == "https://zhuanlan.zhihu.com/p/2049151623004413971"


def test_api_answer_url_with_question():
    url = public_zhihu_url(
        "https://api.zhihu.com/answers/999",
        {"question": {"id": 12345}},
    )
    assert url == "https://www.zhihu.com/question/12345/answer/999"


def test_build_article_url_from_object():
    url = public_zhihu_url("", {"type": "article", "id": 42})
    assert url == "https://zhuanlan.zhihu.com/p/42"


def test_passthrough_web_url():
    url = "https://www.zhihu.com/question/1"
    assert public_zhihu_url(url) == url


def test_content_url_from_target_answer():
    from osint_toolkit.utils.zhihu_urls import content_url_from_target

    url = content_url_from_target(
        {"type": "answer", "id": 9, "question": {"id": 1}},
        {},
    )
    assert url == "https://www.zhihu.com/question/1/answer/9"


def test_content_url_from_target_api_url():
    from osint_toolkit.utils.zhihu_urls import content_url_from_target

    url = content_url_from_target(
        {"url": "https://api.zhihu.com/articles/42"},
        {},
    )
    assert url == "https://zhuanlan.zhihu.com/p/42"
