from __future__ import annotations

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import knowledge
from osint_toolkit.storage.knowledge import save_item


def _setup(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")


def test_enrich_item_creates_concepts_relations_and_questions(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    item = IntelItem(
        id="kg-item-1",
        source="web",
        type="article",
        url="https://example.test/kg",
        title="Obsidian 本地知识库与 MCP 检索",
        content="如何把 Obsidian vault 和 SQLite FTS 组合成可恢复知识库？",
        summary="本地优先知识库可以用 Markdown vault 保存长期资产。",
        key_points=["SQLite 不应作为 OneDrive 主数据源"],
        topics=["知识库", "MCP"],
        personal={"entities": ["Obsidian", "SQLite"]},
    )
    save_item(item)

    result = knowledge.enrich_item(item.id)

    assert result["item_id"] == item.id
    kinds = {row["kind"] for row in result["concepts"]}
    assert {"topic", "entity", "concept", "claim", "question"} & kinds
    assert all(row.get("evidence") for row in result["relations"])

    graph = knowledge.graph(item_id=item.id)
    assert graph["nodes"]
    assert graph["edges"]
    assert any(edge["relation"] == "mentions_entity" for edge in graph["edges"])

    concept = knowledge.get_concept("Obsidian")
    assert concept["items"][0]["item"]["id"] == item.id

    questions = knowledge.research_questions(item_id=item.id)
    assert questions["questions"]
    assert "Obsidian" in {row["name"] for row in knowledge.list_concepts(query="Obsidian")}


def test_research_from_knowledge_creates_tree_node(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    item = IntelItem(
        id="research-item-1",
        source="web",
        type="article",
        url="https://example.test/research",
        title="知识库研究入口",
        content="后续可从知识条目继续研究。",
    )
    save_item(item)

    from osint_toolkit.services import knowledge_graph

    result = knowledge_graph.create_research_from_item(item_id=item.id)

    assert result["tree"]["id"]
    assert result["node"]["kind"] == "knowledge_item"
    assert result["node"]["meta"]["item_id"] == item.id


def test_annotate_search_items_links_to_existing_knowledge(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    saved = IntelItem(
        id="saved-item-1",
        source="web",
        type="article",
        url="https://example.test/mcp-guide",
        title="MCP 本地知识库指南",
        content="Obsidian、SQLite 和本地优先知识管理的组合实践。",
        summary="介绍本地优先知识库的搭建方式。",
        topics=["知识库", "MCP"],
        personal={"entities": ["Obsidian", "SQLite"], "project": "本地知识库"},
    )
    save_item(saved)
    knowledge.enrich_item(saved.id)

    search_item = IntelItem(
        id="search-item-1",
        source="web",
        type="article",
        url="https://example.test/mcp-update",
        title="MCP 知识库补充阅读",
        content="继续讨论 Obsidian 与 SQLite 的联动。",
        summary="补充知识库检索和管理细节。",
        topics=["知识库", "MCP"],
    )

    from osint_toolkit.services import knowledge_graph

    result = knowledge_graph.annotate_search_items("MCP", [search_item])

    linkage = search_item.personal["knowledge_linkage"]
    assert result["summary"]["linked_count"] == 1
    assert linkage["supplements_existing"] is True
    assert "Obsidian" in linkage["matching_concepts"]
    assert linkage["followups"]


def test_annotate_search_items_detects_persona_overlap(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    saved = IntelItem(
        id="saved-item-2",
        source="web",
        type="article",
        url="https://example.test/local-kb",
        title="本地知识库方案",
        content="Obsidian 与 SQLite 的本地优先知识管理。",
        topics=["知识库", "MCP"],
        personal={"entities": ["Obsidian"], "project": "本地知识库"},
    )
    save_item(saved)
    knowledge.enrich_item(saved.id)

    search_item = IntelItem(
        id="search-item-2",
        source="web",
        type="article",
        url="https://example.test/local-kb-update",
        title="Obsidian 本地知识库补充",
        content="继续讨论本地知识库的恢复和图谱。",
        topics=["知识库"],
    )

    from osint_toolkit.services import knowledge_graph

    result = knowledge_graph.annotate_search_items(
        "本地知识库",
        [search_item],
        persona_structured={
            "interest_domains": [{"name": "Obsidian"}],
            "active_projects": [{"name": "本地知识库"}],
        },
    )

    linkage = search_item.personal["knowledge_linkage"]
    assert linkage["persona_overlap"]
    assert result["summary"]["persona_overlap_count"] == 1
