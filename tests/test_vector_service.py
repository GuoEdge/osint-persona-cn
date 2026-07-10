from __future__ import annotations

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import rag, vector
from osint_toolkit.storage.knowledge import save_item


def _setup(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")


def test_vector_status_is_stable_when_optional_dependencies_missing(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr("osint_toolkit.services.vector._optional_imports", lambda: (None, None, "missing"))

    data = vector.status()

    assert data["dependencies_ready"] is False
    assert data["import_error"] == "missing"
    assert data["indexed_chunks"] == 0


def test_vector_search_disabled_returns_empty(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "osint_toolkit.services.vector.get_vector_config",
        lambda: {
            "enabled": False,
            "provider": "qdrant",
            "url": "http://127.0.0.1:6333",
            "collection": "osint_knowledge",
            "embedding_provider": "fastembed",
            "embedding_model": "test",
            "chunk_chars": 900,
            "top_k": 8,
        },
    )

    assert vector.search("anything") == []


def test_rag_merges_semantic_channel(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    item = IntelItem(
        id="semantic-item",
        source="web",
        type="article",
        url="https://example.test/semantic",
        title="语义召回条目",
        content="这条内容用于测试 Qdrant 语义召回。",
    )
    save_item(item)
    monkeypatch.setattr(
        "osint_toolkit.services.vector.search",
        lambda query, limit=None: [
            {
                "item_id": item.id,
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "text": "语义向量命中的片段",
                "score": 0.88,
                "source_channel": "semantic",
            }
        ],
    )

    result = rag.retrieve("意思相近但关键词不同", limit=5)

    assert result["evidence"][0]["source_channel"] == "semantic"
    assert result["evidence"][0]["match_reason"] == "向量语义召回"
