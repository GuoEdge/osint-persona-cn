"""SSRF 防护测试."""

from __future__ import annotations

import pytest

from osint_toolkit.http.ssrf import SSRFError, assert_public_http_url


def test_blocks_loopback():
    with pytest.raises(SSRFError):
        assert_public_http_url("http://127.0.0.1:8787/api/auth/status")


def test_blocks_file_scheme():
    with pytest.raises(SSRFError):
        assert_public_http_url("file:///etc/passwd")


def test_allows_public_https():
    assert assert_public_http_url("https://example.com/article") == "https://example.com/article"
