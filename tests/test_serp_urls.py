"""SERP URL normalization tests."""

from osint_toolkit.collectors.serp.urls import normalize_result_url


def test_normalize_baidu_link():
    wrapped = "https://www.baidu.com/link?url=https%3A%2F%2Fexample.com%2Fpage"
    assert normalize_result_url(wrapped) == "https://example.com/page"


def test_normalize_passthrough():
    url = "https://example.com/article"
    assert normalize_result_url(url) == url
