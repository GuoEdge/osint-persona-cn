"""Citations, batch save, diff, and source warnings tests."""

from __future__ import annotations

import json

import pytest

from osint_toolkit.ai.report import _build_report_payload, _fallback_report
from osint_toolkit.analyzers.citations import assign_citation_ids, build_citation_urls
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import save as save_svc
from osint_toolkit.services.runs import diff_run_urls


def test_assign_citation_ids():
    items = [
        IntelItem(source="web", type="t", url="https://a", title="a", content=""),
        IntelItem(source="web", type="t", url="https://b", title="b", content=""),
    ]
    cmap = assign_citation_ids(items)
    assert items[0].personal["citation_id"] == "c1"
    assert items[1].personal["citation_id"] == "c2"
    assert cmap == {"c1": items[0].id, "c2": items[1].id}


def test_report_payload_has_citation_fields():
    item = IntelItem(source="zhihu", type="answer", url="https://z", title="t", content="c")
    item.personal["citation_id"] = "c1"
    item.personal["matched_queries"] = ["q1", "q2"]
    payload = _build_report_payload("q", [item])
    row = payload["top_stories"][0]
    assert row["citation_id"] == "c1"
    assert row["matched_queries"] == ["q1", "q2"]
    assert "citation_instruction" in payload


def test_build_citation_urls():
    items = [
        IntelItem(source="web", type="t", url="https://example.com/a", title="a", content=""),
        IntelItem(source="web", type="t", url="", title="no url", content=""),
    ]
    assign_citation_ids(items)
    urls = build_citation_urls(items)
    assert urls == {"c1": "https://example.com/a"}
    assert "c2" not in urls


def test_fallback_report_uses_citation_refs():
    item = IntelItem(source="web", type="t", url="https://x", title="title", content="body")
    assign_citation_ids([item])
    text = _fallback_report("q", [item], "run-1")
    assert "[c1]" in text


def test_save_run_items_filters_relevance(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(save_svc, "get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-f1a2b3c4"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    high = IntelItem(source="web", type="t", url="https://h", title="h", content="c")
    high.signals.relevance = 0.8
    low = IntelItem(source="web", type="t", url="https://l", title="l", content="c")
    low.signals.relevance = 0.1
    (run_dir / "03_items_dedup.json").write_text(
        json.dumps([high.to_dict(), low.to_dict()]), encoding="utf-8"
    )
    saved: list[str] = []

    def fake_save(item):
        saved.append(item.id)

    monkeypatch.setattr(save_svc, "save_item", fake_save)
    result = save_svc.save_run_items(run_id, min_relevance=0.25)
    assert result["saved_count"] == 1
    assert saved == [high.id]


def test_diff_run_urls(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)

    def write_run(rid: str, urls: list[str]) -> None:
        run_dir = tmp_path / "runs" / rid
        run_dir.mkdir(parents=True)
        items = [
            {"id": f"id-{i}", "url": u, "source": "web", "type": "t", "title": u, "content": ""}
            for i, u in enumerate(urls)
        ]
        (run_dir / "05_items_dedup.json").write_text(json.dumps(items), encoding="utf-8")

    write_run("20260101-120000-aaa00001", ["https://a", "https://b"])
    write_run("20260101-120000-aaa00002", ["https://b", "https://c"])
    diff = diff_run_urls("20260101-120000-aaa00002", "20260101-120000-aaa00001")
    assert diff["new_count"] == 1
    assert diff["new_urls"] == ["https://c"]
    assert diff["removed_count"] == 1
    assert diff["removed_urls"] == ["https://a"]


@pytest.mark.asyncio
async def test_collect_source_orphan_warnings(monkeypatch):
    from osint_toolkit.services import search as search_mod

    class WarnCollector:
        async def search(self, query, limit=10):
            return []

        def consume_warnings(self):
            return ["API 无结果"]

    monkeypatch.setitem(search_mod.COLLECTORS, "testsrc", WarnCollector)
    items, orphan = await search_mod._collect_source("testsrc", "q", 5)
    assert items == []
    assert orphan == ["API 无结果"]
