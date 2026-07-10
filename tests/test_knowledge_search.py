from __future__ import annotations

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import knowledge
from osint_toolkit.storage.knowledge import save_item
from osint_toolkit.storage.sqlite import connect


def _setup(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")


def test_hybrid_search_ranks_richer_local_item_first(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    strong = IntelItem(
        source="web",
        type="article",
        url="https://example.test/mcp-local",
        title="MCP 本地知识库实践",
        content="把 Obsidian vault 与本地索引结合，做可解释检索。",
        summary="面向本地优先知识库的混合检索实践。",
        topics=["MCP", "知识库"],
        personal={
            "entities": ["Obsidian"],
            "tags": ["知识管理"],
            "dwell_sec": 900,
            "capture_reason": "manual_save",
            "run_id": "run-1",
        },
    )
    weak = IntelItem(
        source="web",
        type="article",
        url="https://example.test/mcp-note",
        title="MCP 备忘",
        content="简单提到一下 MCP。",
        summary="很短的说明。",
    )
    save_item(strong)
    save_item(weak)

    hits = knowledge.search("MCP 知识库", limit=5, explain=True)

    assert hits
    assert hits[0]["item"].id == strong.id
    assert any("标题" in reason or "覆盖度高" in reason for reason in hits[0]["match_reasons"])
    assert any("手动收录" in reason for reason in hits[0]["match_reasons"])


def test_hybrid_search_supports_entity_filter_and_graph_expansion(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    seed = IntelItem(
        source="web",
        type="article",
        url="https://example.test/seed",
        title="本地知识库方案",
        content="围绕 MCP 与本地知识库方案。",
        topics=["MCP"],
        personal={"entities": ["Obsidian"], "capture_reason": "manual_save"},
    )
    related = IntelItem(
        source="web",
        type="article",
        url="https://example.test/related",
        title="归档策略",
        content="只讨论归档，不直接提到查询词。",
    )
    save_item(seed)
    save_item(related)
    with connect() as conn:
        conn.execute(
            (
                "INSERT OR REPLACE INTO knowledge_links "
                "(from_item_id, to_item_id, relation, confidence, evidence) "
                "VALUES (?, ?, ?, ?, ?)"
            ),
            (seed.id, related.id, "same_topic", 0.9, "MCP"),
        )
        conn.commit()

    filtered = knowledge.search("知识库", entity="Obsidian", limit=5, explain=True)
    hits = knowledge.search("知识库", limit=5, explain=True)

    assert len(filtered) == 1
    assert filtered[0]["item"].id == seed.id
    graph_hit = next(hit for hit in hits if hit["item"].id == related.id)
    assert graph_hit["match_type"] == "graph"
    assert any("同主题关联" in reason for reason in graph_hit["match_reasons"])


def test_hybrid_search_recalls_items_from_concepts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    item = IntelItem(
        id="concept-recall-item",
        source="web",
        type="article",
        url="https://example.test/concept",
        title="Vault 实践笔记",
        content="这篇内容没有直接写目标查询词。",
    )
    save_item(item)
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_concepts (name, kind, summary, item_count) VALUES (?, ?, ?, ?)",
            ("Obsidian", "entity", "双链笔记工具", 1),
        )
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_item_concepts "
            "(item_id, concept_name, kind, confidence, evidence) VALUES (?, ?, ?, ?, ?)",
            (item.id, "Obsidian", "entity", 0.95, "frontmatter entity"),
        )
        conn.commit()

    hits = knowledge.search("Obsidian 怎么用于知识库", limit=5, explain=True)

    hit = next(row for row in hits if row["item"].id == item.id)
    assert hit["match_type"] == "concept"
    assert hit["concepts"][0]["name"] == "Obsidian"


def test_hybrid_search_expands_new_knowledge_relations(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    seed = IntelItem(
        id="relation-seed",
        source="web",
        type="article",
        url="https://example.test/seed2",
        title="知识库检索",
        content="讨论 SQLite FTS 与本地检索。",
    )
    related = IntelItem(
        id="relation-related",
        source="web",
        type="article",
        url="https://example.test/related2",
        title="图谱扩展",
        content="只讨论关系扩展。",
    )
    save_item(seed)
    save_item(related)
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_relations "
            "(id, from_type, from_id, to_type, to_id, relation, confidence, status, evidence, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("rel-1", "item", seed.id, "item", related.id, "extends", 0.9, "suggested", "延伸阅读", "test"),
        )
        conn.commit()

    hits = knowledge.search("SQLite FTS", limit=5, explain=True)

    graph_hit = next(row for row in hits if row["item"].id == related.id)
    assert graph_hit["match_type"] == "graph"
    assert any("延伸" in reason for reason in graph_hit["match_reasons"])


def test_list_filters_aggregates_recent_values(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    save_item(
        IntelItem(
            source="zhihu",
            type="answer",
            url="https://zhihu.com/question/1",
            title="知识库标签",
            content="测试 tags 与 entities。",
            topics=["知识库"],
            personal={"entities": ["SQLite"], "tags": ["检索"], "capture_reason": "run_batch"},
        )
    )

    data = knowledge.list_filters(limit=10)

    assert data["sources"][0]["value"] == "zhihu"
    assert any(row["value"] == "知识库" for row in data["topics"])
    assert any(row["value"] == "SQLite" for row in data["entities"])
    assert any(row["value"] == "检索" for row in data["tags"])
