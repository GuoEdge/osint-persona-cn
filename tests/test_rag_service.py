from __future__ import annotations

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import rag
from osint_toolkit.storage.knowledge import save_item
from osint_toolkit.storage.sqlite import connect


def _setup(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")


def test_rag_empty_library_returns_stable_suggestions(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    result = rag.retrieve("完全不存在的问题", limit=5)

    assert result["count"] == 0
    assert result["evidence"] == []
    assert result["suggestions"]["follow_up_questions"]


def test_rag_retrieve_includes_direct_and_relation_evidence(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    seed = IntelItem(
        id="rag-seed",
        source="web",
        type="article",
        url="https://example.test/rag-seed",
        title="SQLite FTS 知识库",
        content="本地知识库使用 SQLite FTS 做全文检索。",
    )
    related = IntelItem(
        id="rag-related",
        source="web",
        type="article",
        url="https://example.test/rag-related",
        title="RAG 图谱扩展",
        content="Graph-RAG 会沿关系寻找延伸阅读。",
    )
    save_item(seed)
    save_item(related)
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_relations "
            "(id, from_type, from_id, to_type, to_id, relation, confidence, status, evidence, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("rag-rel-1", "item", seed.id, "item", related.id, "extends", 0.9, "confirmed", "延伸阅读", "test"),
        )
        conn.commit()

    result = rag.retrieve("SQLite FTS", limit=5)

    ids = [row["item_id"] for row in result["evidence"]]
    assert seed.id in ids
    assert related.id in ids
    related_ev = next(row for row in result["evidence"] if row["item_id"] == related.id)
    assert related_ev["source_channel"] == "relation_confirmed"
    assert "延伸" in related_ev["relation_reason"]


def test_rag_contradiction_is_marked_for_verification(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    a = IntelItem(
        id="rag-a",
        source="web",
        type="article",
        url="https://a.test",
        title="本地 RAG",
        content="RAG 本地运行。",
    )
    b = IntelItem(
        id="rag-b",
        source="web",
        type="article",
        url="https://b.test",
        title="相反观点",
        content="需要核查。",
    )
    save_item(a)
    save_item(b)
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_relations "
            "(id, from_type, from_id, to_type, to_id, relation, confidence, status, evidence, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("rag-rel-2", "item", a.id, "item", b.id, "contradicts", 0.8, "suggested", "说法冲突", "test"),
        )
        conn.commit()

    result = rag.retrieve("本地 RAG", limit=5)

    ev = next(row for row in result["evidence"] if row["item_id"] == b.id)
    assert ev["needs_verification"] is True


def test_rag_ask_falls_back_without_ai(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    save_item(
        IntelItem(
            source="web",
            type="article",
            url="https://example.test/local-rag",
            title="Local RAG note",
            content="Local RAG evidence for fallback.",
        )
    )

    class BrokenClient:
        def __init__(self, *args, **kwargs):
            raise ValueError("missing api key")

    monkeypatch.setattr("osint_toolkit.services.rag.DeepSeekClient", BrokenClient)

    result = rag.ask("Local RAG")

    assert result["ok"] is True
    assert result["ai_used"] is False
    assert result["fallback"] == "local_rag"
    assert result["evidence"]
    assert "Local RAG note" in result["answer"]
