"""Zhihu ingest dedup tests."""

from __future__ import annotations

import pytest


async def _async_none():
    return {}


async def _async_token(_client=None):
    return "token"


@pytest.mark.asyncio
async def test_ingest_activities_skips_answer_votes_when_requested(monkeypatch):
    from osint_toolkit.ingest import zhihu_account

    sample = {
        "type": "answer_vote",
        "target": {
            "type": "answer",
            "id": 9,
            "question": {"id": 1, "title": "Q"},
            "url": "https://www.zhihu.com/question/1/answer/9",
        },
    }

    monkeypatch.setattr(zhihu_account, "ingest_profile_meta", _async_none)
    monkeypatch.setattr(zhihu_account, "_url_token", _async_token)
    monkeypatch.setattr(zhihu_account, "iter_api_data_items", lambda _d: [sample])
    monkeypatch.setattr(
        zhihu_account,
        "activity_entry_from_item",
        lambda item, via="api": {
            "source": "zhihu",
            "title": "Q",
            "url": "https://www.zhihu.com/question/1/answer/9",
            "event_kind": "answer_vote",
            "via": via,
        },
    )
    monkeypatch.setattr(zhihu_account, "classify_activity", lambda _item: ("zhihu_vote", "answer_vote"))

    logged: list[tuple[str, dict]] = []

    def track_dedup(event_type, entry, _key):
        logged.append((event_type, entry))
        return True

    monkeypatch.setattr(zhihu_account, "log_event_deduped", track_dedup)
    monkeypatch.setattr(zhihu_account, "_zhihu_section", lambda: {})
    monkeypatch.setattr(zhihu_account, "_persist_zhihu", lambda **_k: None)
    monkeypatch.setattr(zhihu_account, "save_endorsement", lambda **_k: None)

    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [sample]}

    class FakeClient:
        async def get(self, _url):
            return FakeResp()

    monkeypatch.setattr(zhihu_account, "HttpClient", lambda: FakeClient())

    rows = await zhihu_account.ingest_activities(limit=5, skip_answer_votes=True)
    assert rows == []
    assert logged == []

    rows2 = await zhihu_account.ingest_activities(limit=5, skip_answer_votes=False)
    assert len(rows2) == 1
    assert logged and logged[0][0] == "zhihu_vote"
