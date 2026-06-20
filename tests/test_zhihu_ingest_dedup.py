"""Zhihu ingest dedup tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_ingest_activities_uses_moments_api(monkeypatch, tmp_path):
    """ingest_activities 应调用 /api/v3/moments/{token}/activities 并解析 verb。"""
    from osint_toolkit.ingest import zhihu_account

    async def fake_url_token(_client=None):
        return "sankichu"

    monkeypatch.setattr(zhihu_account, "_url_token", fake_url_token)
    monkeypatch.setattr(zhihu_account, "_zhihu_section", lambda: {})
    monkeypatch.setattr(zhihu_account, "_persist_zhihu", lambda **kw: None)

    activities_resp = MagicMock()
    activities_resp.status_code = 200
    activities_resp.json.return_value = {
        "data": [
            {
                "verb": "MEMBER_VOTEUP_ANSWER",
                "type": "vote",
                "created_time": 1781920357,
                "target": {
                    "id": 123456,
                    "type": "answer",
                    "question": {"id": 789, "title": "测试问题"},
                },
                "actor": {"url_token": "sankichu"},
            }
        ],
        "paging": {"is_end": True, "next": ""},
    }

    async def fake_get(url, **kwargs):
        return activities_resp

    mock_client = MagicMock()
    mock_client.get = fake_get
    monkeypatch.setattr(zhihu_account, "HttpClient", lambda: mock_client)

    rows, endpoint = await zhihu_account.ingest_activities(limit=5)
    assert endpoint == "moments"
    assert len(rows) == 1
    assert "question/789/answer/123456" in rows[0]["url"]


@pytest.mark.asyncio
async def test_ingest_activities_no_token_returns_empty(monkeypatch):
    """无 token 时应返回空。"""
    from osint_toolkit.ingest import zhihu_account

    async def fake_url_token(_client=None):
        return ""

    monkeypatch.setattr(zhihu_account, "_url_token", fake_url_token)
    rows, endpoint = await zhihu_account.ingest_activities(limit=5)
    assert rows == []
    assert endpoint is None


@pytest.mark.asyncio
async def test_ingest_voteanswers_stub_returns_empty():
    from osint_toolkit.ingest import zhihu_account

    rows, endpoint = await zhihu_account.ingest_voteanswers(limit=5)
    assert rows == []
    assert endpoint is None
