"""FTS knowledge recall tests."""

from __future__ import annotations

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.storage import knowledge


def test_fts_recall_and_update(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)

    item = IntelItem(source="web", type="article", url="https://a.test/1", title="MCP 协议入门", content="模型上下文协议")
    knowledge.save_item(item)
    hits = knowledge.recall("MCP", limit=5)
    assert any(h.title == "MCP 协议入门" for h in hits)

    item2 = IntelItem(
        id=item.id,
        source="web",
        type="article",
        url="https://a.test/1",
        title="MCP 协议进阶",
        content="更新后的内容",
    )
    knowledge.save_item(item2)
    hits2 = knowledge.recall("进阶", limit=5)
    assert len(hits2) == 1
    assert hits2[0].title == "MCP 协议进阶"
