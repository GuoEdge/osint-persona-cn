"""bilibili-api SDK bridge tests."""

from __future__ import annotations

import json

import pytest

from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.ingest import bilibili_sdk


def test_load_credential_from_cookie_file(tmp_path, monkeypatch):
    import sys

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
    monkeypatch.setattr(bilibili_sdk, "sdk_installed", lambda: True)
    monkeypatch.setattr(bilibili_sdk, "load_domain_cookie_file", lambda _d: json.loads(cookie_file.read_text()))

    class FakeCredential:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_mod = type(sys)("bilibili_api")
    fake_mod.Credential = FakeCredential
    monkeypatch.setitem(sys.modules, "bilibili_api", fake_mod)

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
async def test_ingest_followings_sdk_path(monkeypatch, tmp_path):
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

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(bilibili_sdk, "sdk_enabled", lambda feature: feature == "ingest_followings")
    monkeypatch.setattr(bilibili_sdk, "ingest_followings", fake_sdk_followings)
    monkeypatch.setattr(bilibili_account, "log_events_batch", lambda *_a, **_k: 1)

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
    fake_module.OrderType = type("OrderType", (), {"LIKE": 1, "TIME": 0})
    monkeypatch.setitem(sys.modules, "bilibili_api", type(sys)("bilibili_api"))
    monkeypatch.setitem(sys.modules, "bilibili_api.comment", fake_module)

    rows = await bilibili_sdk.fetch_comments_lazy("1", comment_type=1, limit=5)
    assert calls == ["", "next-1"]
    assert len(rows) == 2
    assert rows[0]["likes"] == 5


@pytest.mark.asyncio
async def test_resolve_video_aid_cid_uses_bvid_view_api():
    class FakeResp:
        def json(self):
            return {"code": 0, "data": {"aid": 425001, "pages": [{"cid": 9001}]}}

    class FakeClient:
        last_url = ""

        async def get(self, url: str):
            FakeClient.last_url = url
            return FakeResp()

    aid, cid = await bilibili_sdk.resolve_video_aid_cid(
        "https://www.bilibili.com/video/BVtest425",
        client=FakeClient(),
    )
    assert "bvid=BVtest425" in FakeClient.last_url
    assert aid == 425001
    assert cid == 9001


@pytest.mark.asyncio
async def test_fetch_video_meta_from_view_api():
    class FakeResp:
        def json(self):
            return {
                "code": 0,
                "data": {
                    "title": "Qwen 3.7 Max",
                    "desc": "国产大模型评测",
                    "owner": {"name": "浪浪妈"},
                },
            }

    class FakeClient:
        last_url = ""

        async def get(self, url: str):
            FakeClient.last_url = url
            return FakeResp()

    meta = await bilibili_sdk.fetch_video_meta(
        "https://www.bilibili.com/video/BVqwen37",
        client=FakeClient(),
    )
    assert "bvid=BVqwen37" in FakeClient.last_url
    assert meta["title"] == "Qwen 3.7 Max"
    assert meta["desc"] == "国产大模型评测"
    assert meta["author"] == "浪浪妈"


@pytest.mark.asyncio
async def test_hydrate_video_descriptions_fills_empty_content(monkeypatch):
    from osint_toolkit.models.intel_item import IntelItem

    col = BilibiliCollector()
    item = IntelItem(
        source="bilibili",
        type="video",
        url="https://www.bilibili.com/video/BVempty",
        title="国模第一梯队",
        content="",
    )

    async def fake_meta(url, *, client=None):
        assert "BVempty" in url
        return {"desc": "Qwen 3.7 Max 稳步迭代", "author": "浪浪妈"}

    monkeypatch.setattr(bilibili_sdk, "fetch_video_meta", fake_meta)
    monkeypatch.setattr(col, "_apply_subtitle_from_url", lambda _item: None)
    await col._hydrate_video_descriptions([item])
    assert item.content == "Qwen 3.7 Max 稳步迭代"
    assert item.author == "浪浪妈"


@pytest.mark.asyncio
async def test_hydrate_video_descriptions_falls_back_to_subtitle(monkeypatch):
    from osint_toolkit.models.intel_item import IntelItem

    col = BilibiliCollector()
    item = IntelItem(
        source="bilibili",
        type="video",
        url="https://www.bilibili.com/video/BVnosubdesc",
        title="国模第一梯队",
        content="",
    )

    async def fake_meta(url, *, client=None):
        return {"desc": "", "author": ""}

    async def fake_subtitle(self, target):
        assert target is item
        target.layers["subtitle"] = {"text": "AI字幕正文", "kind": "ai", "source": "view_api"}
        target.content = "[字幕:ai]\nAI字幕正文"

    monkeypatch.setattr(bilibili_sdk, "fetch_video_meta", fake_meta)
    monkeypatch.setattr(BilibiliCollector, "_apply_subtitle_from_url", fake_subtitle)
    await col._hydrate_video_descriptions([item])
    assert item.layers["subtitle"]["text"] == "AI字幕正文"
    assert "AI字幕正文" in item.content


def test_parse_video_uses_tags_when_no_desc():
    col = BilibiliCollector()
    item = col._parse_video(
        {
            "bvid": "BVtag",
            "title": "AI 模型",
            "tag": "Qwen,国模,大模型",
        }
    )
    assert item is not None
    assert item.content == "标签: Qwen 国模 大模型"


def test_parse_video_returns_none_when_no_bvid_or_aid():
    """bvid 与 aid 双空时不应产出 avNone URL，应返回 None 跳过该条目。"""
    col = BilibiliCollector()
    assert col._parse_video({"title": "无 ID 条目"}) is None
    assert col._parse_video({"bvid": "", "aid": None, "title": "x"}) is None


@pytest.mark.asyncio
async def test_fetch_subtitle_for_aid_cid_uses_wbi_player(monkeypatch):
    async def fake_wbi_get(_client, base, params):
        assert "player/wbi/v2" in base
        assert params["aid"] == 111 and params["cid"] == 222
        return {
            "code": 0,
            "data": {
                "subtitle": {
                    "subtitles": [
                        {
                            "lan_doc": "中文（自动生成）",
                            "subtitle_url_v2": "//subtitle.example.com/sub.json",
                            "ai_status": 2,
                        }
                    ]
                }
            },
        }

    async def fake_download(url):
        assert "subtitle.example.com/sub.json" in url
        return "AI字幕正文"

    monkeypatch.setattr("osint_toolkit.ingest.bilibili_wbi.wbi_get", fake_wbi_get)
    monkeypatch.setattr(bilibili_sdk, "_download_subtitle_text", fake_download)

    result = await bilibili_sdk.fetch_subtitle_for_aid_cid(111, 222)
    assert result["text"] == "AI字幕正文"
    assert result["source"] == "wbi_player"
    assert bilibili_sdk._track_label(result["track"]) == "ai"


@pytest.mark.asyncio
async def test_fetch_video_meta_ignores_placeholder_desc():
    class FakeResp:
        def json(self):
            return {"code": 0, "data": {"title": "t", "desc": "-", "owner": {"name": "up"}}}

    class FakeClient:
        async def get(self, url: str):
            return FakeResp()

    meta = await bilibili_sdk.fetch_video_meta("https://www.bilibili.com/video/BVdash", client=FakeClient())
    assert meta["desc"] == ""


def test_needs_subtitle_fallback_for_weak_desc():
    assert BilibiliCollector._needs_subtitle_fallback("-") is True
    assert BilibiliCollector._needs_subtitle_fallback("标签: Qwen") is True
    assert BilibiliCollector._needs_subtitle_fallback("完整简介") is True
    long_desc = "x" * 200 + "\n\n第二段说明"
    assert BilibiliCollector._needs_subtitle_fallback(long_desc) is False


@pytest.mark.asyncio
async def test_hydrate_video_descriptions_upgrades_short_desc(monkeypatch):
    from osint_toolkit.models.intel_item import IntelItem

    col = BilibiliCollector()
    short = "这一集简单测评了三个混合专家模型，仅供参考！"
    item = IntelItem(
        source="bilibili",
        type="video",
        url="https://www.bilibili.com/video/BVshort",
        title="混合专家小模型",
        content=short,
    )

    async def fake_meta(url, *, client=None):
        assert "BVshort" in url
        return {"desc": short, "author": "测评UP"}

    subtitle_called: list[str] = []

    async def fake_subtitle(self, target):
        subtitle_called.append(target.url)
        target.layers["subtitle"] = {"text": "口播字幕正文", "kind": "ai", "source": "view_api"}
        target.content = f"{short}\n\n[字幕:ai]\n口播字幕正文"

    monkeypatch.setattr(bilibili_sdk, "fetch_video_meta", fake_meta)
    monkeypatch.setattr(BilibiliCollector, "_apply_subtitle_from_url", fake_subtitle)
    await col._hydrate_video_descriptions([item])
    assert item.author == "测评UP"
    assert subtitle_called == [item.url]
    assert "口播字幕正文" in item.content


@pytest.mark.asyncio
async def test_fetch_subtitle_for_url_uses_matched_aid_cid(monkeypatch):
    monkeypatch.setattr(bilibili_sdk, "sdk_installed", lambda: False)

    async def fake_resolve(url, *, page_index=0, client=None):
        assert "BVdaily" in url
        return 111, 222

    async def fake_fetch(aid, cid, *, client=None):
        assert aid == 111 and cid == 222
        return {"text": "AI日报字幕", "track": {"lan_doc": "中文"}, "source": "view_api", "aid": aid, "cid": cid}

    monkeypatch.setattr(bilibili_sdk, "resolve_video_aid_cid", fake_resolve)
    monkeypatch.setattr(bilibili_sdk, "fetch_subtitle_for_aid_cid", fake_fetch)

    result = await bilibili_sdk.fetch_subtitle_for_url("https://www.bilibili.com/video/BVdaily")
    assert result["text"] == "AI日报字幕"
    assert result["source"] == "view_api"
