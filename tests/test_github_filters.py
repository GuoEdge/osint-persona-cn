"""GitHub repo blocklist tests."""

from __future__ import annotations

import pytest

from osint_toolkit.collectors.github_filters import (
    is_blocked_github_repo,
    parse_github_full_name,
)


@pytest.mark.parametrize(
    ("url", "full_name", "blocked"),
    [
        (
            "https://github.com/cirosantilli/china-dictatorship",
            "cirosantilli/china-dictatorship",
            True,
        ),
        (
            "https://github.com/cirosantilli/china-dictatroship-7",
            "cirosantilli/china-dictatroship-7",
            True,
        ),
        (
            "https://github.com/mRFWq7LwNPZjaVv5v6eo/cihna-dictattorshrip-8",
            "mRFWq7LwNPZjaVv5v6eo/cihna-dictattorshrip-8",
            True,
        ),
        (
            "https://github.com/torvalds/linux",
            "torvalds/linux",
            False,
        ),
        (
            "https://github.com/gege-circle/.github",
            "gege-circle/.github",
            False,
        ),
    ],
)
def test_is_blocked_github_repo(url: str, full_name: str, blocked: bool):
    assert is_blocked_github_repo(url, full_name=full_name) is blocked


def test_parse_github_full_name_from_url():
    owner, repo = parse_github_full_name("https://github.com/foo/bar/issues/1")
    assert owner == "foo"
    assert repo == "bar"


@pytest.mark.asyncio
async def test_github_collector_skips_blocked_repos(monkeypatch):
    from osint_toolkit.collectors.github import GithubCollector

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "items": [
                    {
                        "html_url": "https://github.com/cirosantilli/china-dictatorship",
                        "full_name": "cirosantilli/china-dictatorship",
                        "description": "spam",
                        "stargazers_count": 99999,
                    },
                    {
                        "html_url": "https://github.com/torvalds/linux",
                        "full_name": "torvalds/linux",
                        "description": "kernel",
                        "stargazers_count": 100,
                    },
                ]
            }

    class FakeClient:
        async def get(self, url, headers=None):
            return FakeResp()

    collector = GithubCollector(client=FakeClient())
    items = await collector.search("linux", limit=10)
    assert len(items) == 1
    assert items[0].url.endswith("/torvalds/linux")
