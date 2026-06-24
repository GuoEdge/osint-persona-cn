"""is_sogou_ad must match ad/spread as whole class tokens, not substrings."""

from __future__ import annotations

from osint_toolkit.collectors.serp.filters import is_sogou_ad


class _FakeBlock:
    def __init__(self, classes: list[str]) -> None:
        self._classes = classes

    def get(self, key, default=None):
        if key == "class":
            return self._classes
        return default


def test_sogou_ad_token_match_not_substring():
    assert is_sogou_ad(_FakeBlock(["ad"])) is True
    assert is_sogou_ad(_FakeBlock(["spread"])) is True
    assert is_sogou_ad(_FakeBlock(["ec_ad"])) is True
    assert is_sogou_ad(_FakeBlock(["result", "header"])) is False
    assert is_sogou_ad(_FakeBlock(["loading"])) is False
    assert is_sogou_ad(_FakeBlock(["shadow", "card"])) is False
    assert is_sogou_ad(None) is True
