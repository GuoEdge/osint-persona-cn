"""Save service routing tests."""

from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_save_url_routes_weixin(monkeypatch):
    from osint_toolkit.services import save as save_svc

    class FakeCollector:
        async def fetch(self, url):
            from osint_toolkit.models.intel_item import IntelItem

            return IntelItem(source="weixin", type="article", url=url, title="t", content="c")

    monkeypatch.setattr(save_svc, "WeixinCollector", lambda: FakeCollector())
    monkeypatch.setattr(save_svc, "save_item", lambda item: 1)
    monkeypatch.setattr(save_svc, "export_card", lambda item, path: path / "card.md")

    result = await save_svc.save_url("https://mp.weixin.qq.com/s/abc", no_ai=True)
    assert result["item"].source == "weixin"


@pytest.mark.asyncio
async def test_save_url_enriches_bilibili_video(monkeypatch):
    from osint_toolkit.models.intel_item import IntelItem
    from osint_toolkit.services import save as save_svc

    enriched = {"called": False}

    class FakeCollector:
        async def fetch(self, url):
            return IntelItem(
                source="bilibili",
                type="video",
                url=url,
                title="t",
                content="c",
            )

        async def enrich_video(self, item):
            enriched["called"] = True
            item.layers["subtitle"] = {"text": "sub"}

    monkeypatch.setattr(save_svc, "BilibiliCollector", lambda: FakeCollector())
    monkeypatch.setattr(save_svc, "save_item", lambda item: 1)
    monkeypatch.setattr(save_svc, "export_card", lambda item, path: path / "card.md")

    await save_svc.save_url("https://www.bilibili.com/video/BV1", no_ai=True)
    assert enriched["called"] is True


def test_bilibili_fetch_type_from_url():
    from osint_toolkit.collectors.bilibili import BilibiliCollector

    assert BilibiliCollector._type_from_url("https://www.bilibili.com/read/cv123") == "article"
    assert BilibiliCollector._type_from_url("https://www.bilibili.com/opus/456") == "article"
    assert BilibiliCollector._type_from_url("https://www.bilibili.com/video/BV1") == "video"


def test_save_run_items_prefers_final_artifact_with_comments(tmp_path, monkeypatch):
    from osint_toolkit.services import save as save_svc

    run_id = "20260101-120000-abcd1234"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    base = {
        "source": "web",
        "type": "snippet",
        "url": "https://example.test/a",
        "title": "t",
        "content": "c",
        "signals": {"relevance": 0.8},
    }
    (run_dir / "01_items_dedup.json").write_text(json.dumps([base]), encoding="utf-8")
    final = dict(base)
    final["layers"] = {
        "comments": [{"author": "u", "content": "保留评论", "likes": 3}],
        "comments_summary": "社区观点归纳：保留",
    }
    (run_dir / "items_final.json").write_text(json.dumps([final], ensure_ascii=False), encoding="utf-8")
    saved = []

    monkeypatch.setattr("osint_toolkit.services.run_session.auth_paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(save_svc, "save_item", lambda item: saved.append(item))

    result = save_svc.save_run_items(run_id)

    assert result["saved_count"] == 1
    assert saved[0].layers["comments"][0]["content"] == "保留评论"
    assert saved[0].layers["comments_summary"] == "社区观点归纳：保留"
