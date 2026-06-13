"""bilibili-api SDK bridge tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.ingest import bilibili_sdk


def test_load_credential_from_cookie_file(tmp_path, monkeypatch):
    cookie_file = tmp_path / "bilibili.com.json"
    cookie_file.write_text(
        json.dumps(
            {
                "domain": "bilibili.com",
                "cookie_header": "SESSDATA=abc; bili_jct=def; buvid3=ghi; DedeUserID=42",
                "cookies": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bilibili_sdk, "load_domain_cookie_file", lambda _d: json.loads(cookie_file.read_text()))
    cred = bilibili_sdk.load_credential()
    assert cred is not None
    assert cred.sessdata == "abc"
    assert cred.bili_jct == "def"
    assert cred.buvid3 == "ghi"
    assert cred.dedeuserid == "42"


def test_sdk_enabled_respects_config(monkeypatch):
    monkeypatch.setattr(bilibili_sdk, "sdk_installed", lambda: True)
    monkeypatch.setattr(
        bilibili_sdk,
        "get_bilibili_config",
        lambda: {
            "use_sdk": True,
            "features": {"comments": False, "ingest_history": True},
        },
    )
    assert bilibili_sdk.sdk_enabled("comments") is False
    assert bilibili_sdk.sdk_enabled("ingest_history") is True


@pytest.mark.asyncio
async def test_fetch_comments_uses_sdk(monkeypatch):
    col = BilibiliCollector()

    async def fake_resolve(_url: str) -> str:
        return "12345"

    async def fake_sdk_comments(oid: str, *, comment_type: int = 1, limit: int = 40):
        assert oid == "12345"
        assert comment_type == 12
        return [{"author": "u", "content": "hi", "likes": 3, "rpid": 1}]

    monkeypatch.setattr(col, "_resolve_oid", fake_resolve)
    monkeypatch.setattr(bilibili_sdk, "sdk_enabled", lambda feature: feature == "comments")
    monkeypatch.setattr(bilibili_sdk, "fetch_comments_lazy", fake_sdk_comments)

    rows = await col.fetch_comments("https://www.bilibili.com/read/cv1", limit=5)
    assert len(rows) == 1
    assert rows[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_ingest_followings_sdk_path(monkeypatch):
    from osint_toolkit.ingest import bilibili_account

    async def fake_sdk_followings(limit: int = 500):
        return [
            {
                "source": "bilibili",
                "title": "up-a",
                "url": "https://space.bilibili.com/1",
                "event_kind": "following",
                "uid": 1,
            }
        ]

    monkeypatch.setattr(bilibili_sdk, "sdk_enabled", lambda feature: feature == "ingest_followings")
    monkeypatch.setattr(bilibili_sdk, "ingest_followings", fake_sdk_followings)
    monkeypatch.setattr(bilibili_account, "log_event", lambda *_a, **_k: None)

    rows = await bilibili_account.ingest_followings(limit=5)
    assert len(rows) == 1
    assert rows[0]["event_kind"] == "following"


@pytest.mark.asyncio
async def test_sdk_fetch_comments_parses_lazy_offset(monkeypatch):
    class FakeCredential:
        sessdata = "x"

    calls: list[str] = []

    class FakeComment:
        @staticmethod
        async def get_comments_lazy(*, oid: int, type_, offset: str = "", order=None, credential=None):
            calls.append(offset)
            if not offset:
                return {
                    "code": 0,
                    "data": {
                        "replies": [
                            {
                                "rpid": 9,
                                "member": {"uname": "a"},
                                "content": {"message": "one"},
                                "like": 2,
                            }
                        ],
                        "cursor": {"pagination_reply": {"next_offset": "next-1"}},
                    },
                }
            return {
                "code": 0,
                "data": {
                    "replies": [
                        {
                            "rpid": 10,
                            "member": {"uname": "b"},
                            "content": {"message": "two"},
                            "like": 5,
                        }
                    ],
                    "cursor": {"pagination_reply": {"next_offset": ""}},
                },
            }

    monkeypatch.setattr(bilibili_sdk, "load_credential", lambda: FakeCredential())
    monkeypatch.setattr(bilibili_sdk, "configure_sdk", lambda: None)
    monkeypatch.setattr(bilibili_sdk, "_comment_resource_type", lambda _t: object())
    import sys

    fake_module = type(sys)("fake_comment")
    fake_module.get_comments_lazy = FakeComment.get_comments_lazy
    fake_module.OrderType = type("OrderType", (), {"TIME": 0})
    monkeypatch.setitem(sys.modules, "bilibili_api", type(sys)("bilibili_api"))
    monkeypatch.setitem(sys.modules, "bilibili_api.comment", fake_module)

    rows = await bilibili_sdk.fetch_comments_lazy("1", comment_type=1, limit=5)
    assert calls == ["", "next-1"]
    assert len(rows) == 2
    assert rows[0]["likes"] == 5
