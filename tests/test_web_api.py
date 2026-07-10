"""Web API 测试."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_page_workspace(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "搜罗" in r.text
    assert "nav_groups" not in r.text  # rendered, not variable name
    assert "个人情报" in r.text


def test_api_health_sets_cookie(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("ok") == "true"
    # Cookie may be set when web auth is enabled (default in tests)
    if "osint_token" in r.cookies:
        assert len(r.cookies["osint_token"]) > 8


def test_page_routes(client):
    for path in ["/save", "/knowledge", "/digest", "/persona", "/ingest", "/behavior", "/runs", "/ai", "/settings"]:
        r = client.get(path)
        assert r.status_code == 200, path


def test_auth_status(client):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data


def test_setup_status(client):
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert "steps" in data
    assert "ready" in data


def test_ingest_capabilities(client):
    r = client.get("/api/ingest/capabilities")
    assert r.status_code == 200
    assert "items" in r.json()


def test_auth_paths(client):
    r = client.get("/api/auth/paths")
    assert r.status_code == 200
    assert "data_dir" in r.json()


def test_knowledge_items(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    r = client.get("/api/knowledge/items?limit=5")
    assert r.status_code == 200
    assert "items" in r.json()


def test_knowledge_health_api_empty_db(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")

    r = client.get("/api/knowledge/health")

    assert r.status_code == 200
    body = r.json()
    assert body["db_readable"] is True
    assert "item_count" in body
    assert "fts_ok" in body
    assert body["suggestions"]


def test_knowledge_search_empty_result_has_suggestions(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")

    r = client.get("/api/knowledge/search?q=不存在的自然语言问题&mode=hybrid")

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["suggestions"]["follow_up_questions"]


def test_knowledge_search_and_links_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    from osint_toolkit.storage.knowledge import save_item
    from osint_toolkit.storage.sqlite import connect

    primary = IntelItem(
        source="web",
        type="article",
        url="https://example.test/mcp",
        title="MCP 本地知识库",
        content="结合 Obsidian 与本地检索。",
        topics=["MCP"],
        personal={"entities": ["Obsidian"], "tags": ["知识管理"], "capture_reason": "manual_save"},
    )
    linked = IntelItem(
        source="web",
        type="article",
        url="https://example.test/archive",
        title="归档方案",
        content="关联知识整理。",
    )
    save_item(primary)
    save_item(linked)
    with connect() as conn:
        conn.execute(
            (
                "INSERT OR REPLACE INTO knowledge_links "
                "(from_item_id, to_item_id, relation, confidence, evidence) "
                "VALUES (?, ?, ?, ?, ?)"
            ),
            (primary.id, linked.id, "same_topic", 0.9, "MCP"),
        )
        conn.commit()

    r = client.get("/api/knowledge/search?q=MCP&mode=hybrid&entity=Obsidian&explain=1")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert body["hits"][0]["item"]["id"] == primary.id
    assert body["hits"][0]["match_reasons"]

    r2 = client.get(f"/api/knowledge/items/{primary.id}/links?limit=5")
    assert r2.status_code == 200
    assert r2.json()["links"][0]["item"]["id"] == linked.id


def test_knowledge_graph_concepts_and_research_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    from osint_toolkit.storage.knowledge import save_item

    item = IntelItem(
        id="api-kg-item",
        source="web",
        type="article",
        url="https://example.test/api-kg",
        title="Obsidian 知识图谱",
        content="如何从 Obsidian 笔记继续研究？",
        topics=["知识图谱"],
        personal={"entities": ["Obsidian"]},
    )
    save_item(item)

    enrich = client.post(f"/api/knowledge/items/{item.id}/enrich")
    assert enrich.status_code == 200
    assert enrich.json()["relations"]

    graph = client.get(f"/api/knowledge/items/{item.id}/graph")
    assert graph.status_code == 200
    assert graph.json()["edges"]

    concepts = client.get("/api/knowledge/concepts?q=Obsidian")
    assert concepts.status_code == 200
    assert concepts.json()["concepts"]

    detail = client.get("/api/knowledge/concepts/Obsidian")
    assert detail.status_code == 200
    assert detail.json()["items"][0]["item"]["id"] == item.id

    questions = client.post("/api/knowledge/research-questions", json={"item_id": item.id})
    assert questions.status_code == 200
    assert questions.json()["questions"]

    research = client.post("/api/research/from-knowledge", json={"item_id": item.id})
    assert research.status_code == 200
    assert research.json()["node"]["kind"] == "knowledge_item"


def test_research_from_search_api(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.research.tree.get_data_dir", lambda: tmp_path)
    payload = {
        "item": {
            "id": "search-item-1",
            "source": "web",
            "url": "https://example.test/search-item",
            "title": "本地知识库补充阅读",
            "summary": "用于把搜索结果直接挂到研究树。",
            "personal": {"knowledge_linkage": {"project": "本地知识库"}},
        }
    }
    r = client.post("/api/research/from-search", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["node"]["kind"] == "knowledge_item"
    assert body["tree"]["id"]


def test_knowledge_ask_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    from osint_toolkit.storage.knowledge import save_item

    save_item(
        IntelItem(
            source="web",
            type="article",
            url="https://example.test/obsidian",
            title="Obsidian 本地知识库",
            content="讲述本地优先知识库。",
            topics=["知识库"],
            personal={"entities": ["Obsidian"], "capture_reason": "manual_save"},
        )
    )

    class FakeClient:
        def chat(self, messages):
            assert messages
            return "可优先用 Obsidian 管理本地知识库 [k1]"

    monkeypatch.setattr("osint_toolkit.services.rag.DeepSeekClient", FakeClient)

    r = client.post("/api/knowledge/ask", json={"question": "Obsidian 知识库方案是什么？"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "[k1]" in body["answer"]
    assert body["hits"][0]["citation"] == "k1"
    assert body["ai_used"] is True


def test_knowledge_ask_api_falls_back_without_ai(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    from osint_toolkit.storage.knowledge import save_item

    save_item(
        IntelItem(
            source="web",
            type="article",
            url="https://example.test/local",
            title="Local knowledge note",
            content="Local knowledge evidence for fallback answer.",
            topics=["knowledge"],
        )
    )

    class BrokenClient:
        def __init__(self, *args, **kwargs):
            raise ValueError("missing api key")

    monkeypatch.setattr("osint_toolkit.services.rag.DeepSeekClient", BrokenClient)

    r = client.post("/api/knowledge/ask", json={"question": "local knowledge fallback"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["ai_used"] is False
    assert body["fallback"] == "local_rag"
    assert "Local knowledge note" in body["answer"]


def test_knowledge_rag_api_retrieve_context_and_ask(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    from osint_toolkit.storage.knowledge import save_item

    save_item(
        IntelItem(
            source="web",
            type="article",
            url="https://example.test/rag-api",
            title="Graph RAG API",
            content="Graph RAG 使用本地证据回答问题。",
            topics=["RAG"],
        )
    )

    class FakeClient:
        def chat(self, messages):
            assert "RAG 上下文" in messages[-1]["content"]
            return "Graph RAG 可以基于本地证据回答 [k1]"

    monkeypatch.setattr("osint_toolkit.services.rag.DeepSeekClient", FakeClient)

    retrieve = client.get("/api/knowledge/rag/retrieve?q=Graph%20RAG")
    assert retrieve.status_code == 200
    assert retrieve.json()["evidence"][0]["source_channel"]

    context = client.get("/api/knowledge/rag/context?q=Graph%20RAG")
    assert context.status_code == 200
    assert context.json()["context"]["evidence"]

    ask = client.post("/api/knowledge/rag/ask", json={"question": "Graph RAG 怎么回答？"})
    assert ask.status_code == 200
    body = ask.json()
    assert body["ai_used"] is True
    assert body["evidence"][0]["citation"] == "k1"


def test_legacy_knowledge_ask_uses_rag_shape(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    from osint_toolkit.storage.knowledge import save_item

    save_item(
        IntelItem(
            source="web",
            type="article",
            url="https://example.test/legacy-rag",
            title="Legacy RAG",
            content="旧问答接口现在复用 RAG。",
        )
    )

    class BrokenClient:
        def __init__(self, *args, **kwargs):
            raise ValueError("missing api key")

    monkeypatch.setattr("osint_toolkit.services.rag.DeepSeekClient", BrokenClient)

    r = client.post("/api/knowledge/ask", json={"question": "Legacy RAG"})

    assert r.status_code == 200
    body = r.json()
    assert body["fallback"] == "local_rag"
    assert body["evidence"]


def test_knowledge_vector_api_status_and_search(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.vector.status",
        lambda: {"enabled": False, "dependencies_ready": False, "indexed_chunks": 0},
    )
    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.vector.search",
        lambda q, limit=8: [{"item_id": "i1", "title": "semantic", "score": 0.8}],
    )

    status = client.get("/api/knowledge/vector/status")
    assert status.status_code == 200
    assert status.json()["dependencies_ready"] is False

    search = client.get("/api/knowledge/vector/search?q=semantic")
    assert search.status_code == 200
    assert search.json()["hits"][0]["item_id"] == "i1"


def test_runs_list(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
    r = client.get("/api/runs")
    assert r.status_code == 200
    assert r.json()["runs"] == []


def test_search_async(client, monkeypatch):
    async def fake_search(**kwargs):
        return {
            "run_id": kwargs.get("run_id", "test-run"),
            "items": [
                IntelItem(source="web", type="test", url="https://x.com", title="Test", content="c"),
            ],
            "report": "",
            "report_path": None,
            "simulations": [],
            "run_dir": "/tmp",
        }

    async def fake_execute(run_id, **kwargs):
        from osint_toolkit.web import tasks

        tasks._jobs[run_id] = {"status": "done", "result": await fake_search(**kwargs, run_id=run_id), "error": None}

    def fake_start(**kwargs):
        from osint_toolkit.web import tasks

        run_id = "20260101-120000-abcd1234"
        tasks._jobs[run_id] = {"status": "running", "result": None, "error": None}
        import asyncio

        asyncio.get_event_loop().create_task(fake_execute(run_id, **kwargs))
        return {"run_id": run_id, "status": "running"}

    monkeypatch.setattr("osint_toolkit.web.routes.api.start_search_job", fake_start)

    r = client.post("/api/search", json={"query": "test", "sources": ["web"], "no_ai": True})
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert "run_id" in r.json()


def test_ai_directives(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.ai.steering.directives_path", lambda: tmp_path / "ai_directives.yaml")
    r = client.get("/api/ai/directives")
    assert r.status_code == 200
    body = {"data": {"hard_constraints": ["test"], "soft_preferences": {}}}
    r2 = client.put("/api/ai/directives", json=body)
    assert r2.status_code == 200


def test_ai_status(client, monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.ai_status.get_ai_status",
        lambda: {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key_configured": False,
            "enabled_step_count": 3,
            "total_step_count": 5,
            "prompt_overrides": 1,
        },
    )
    r = client.get("/api/ai/status")
    assert r.status_code == 200
    assert r.json()["model"] == "deepseek-chat"


def test_ai_calls(client, monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.ai_audit.list_ai_calls",
        lambda limit=50: [{"task": "查询分析", "success": True, "model": "deepseek-chat"}],
    )
    r = client.get("/api/ai/calls?limit=5")
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["calls"][0]["task"] == "查询分析"


def test_ai_prompts(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.ai.prompt_loader.get_data_dir", lambda: tmp_path)
    r = client.get("/api/ai/prompts")
    assert r.status_code == 200
    assert "prompts" in r.json()


def test_persona_structured_api(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    r = client.get("/api/persona/structured")
    assert r.status_code == 200
    body = r.json()
    assert "structured" in body
    assert "knowledge_goals" in body["structured"]


def test_persona_api_includes_console_data(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.persona.store.get_data_dir", lambda: tmp_path)
    from osint_toolkit.persona.store import save_mental_model, save_persona_brief

    save_mental_model(
        {
            "version": 2,
            "built_at": "2026-07-09T00:00:00+00:00",
            "events_at_last_build": 88,
            "recent_sources": {"zhihu": 12, "bilibili": 5},
            "recent_event_types": {"zhihu_browse": 9},
            "event_breakdown": {"recent_activity_7d": {"zhihu_browse": 4}},
            "high_interest_hints": [{"title": "本地知识库", "source": "zhihu", "event_type": "zhihu_browse"}],
        }
    )
    save_persona_brief("test brief")

    r = client.get("/api/persona")
    assert r.status_code == 200
    body = r.json()
    assert "console" in body
    assert body["console"]["recent_sources"]["zhihu"] == 12
    assert body["console"]["high_interest_hints"][0]["title"] == "本地知识库"
    assert body["console"]["version_retention"] == 10
    assert "dedup_note" in body["console"]
    assert "ranked_behavior_samples" in body["console"]
    assert "behavior_category_summary" in body["console"]
    assert "behavior_workbench" in body["console"]
    assert isinstance(body["console"]["behavior_workbench"], list)


def test_feedback(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.feedback.store.get_data_dir", lambda: tmp_path)
    r = client.post(
        "/api/feedback",
        json={"target_id": "item-1", "rating": "useful", "run_id": "run-1"},
    )
    assert r.status_code == 200
    assert "entry" in r.json()

    r2 = client.get("/api/feedback/recent?target_ids=item-1")
    assert r2.status_code == 200
    assert r2.json()["feedback"]["item:item-1"] == "useful"


def test_sim_override_persists_current_simulation_artifact(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-abcd1234"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text('{"status":"done"}', encoding="utf-8")
    (run_dir / "simulations.json").write_text(
        json.dumps([
            {"item_id": "item-1", "interest": "skip", "confidence": 0.99, "verdict": "AI 判定无价值"}
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "items_final.json").write_text(
        json.dumps(
            [
                {
                    "id": "item-1",
                    "source": "web",
                    "type": "snippet",
                    "title": "t",
                    "url": "https://x.test",
                    "signals": {"relevance": 0.1, "fold_reason": "低相关"},
                }
            ]
        ),
        encoding="utf-8",
    )

    r = client.post(
        f"/api/runs/{run_id}/sim-override",
        json={"item_id": "item-1", "interest": "interested"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["updated_simulation"] is True
    sims = json.loads((run_dir / "simulations.json").read_text(encoding="utf-8"))
    assert sims[0]["interest"] == "interested"
    assert sims[0]["overridden"] is True
    assert sims[0]["ai_original"]["interest"] == "skip"
    items = json.loads((run_dir / "items_final.json").read_text(encoding="utf-8"))
    assert items[0]["signals"]["relevance"] == 0.7
    assert "fold_reason" not in items[0]["signals"]


def test_sim_override_returns_failure_when_item_missing(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-abcd1234"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "simulations.json").write_text('[{"item_id":"other"}]', encoding="utf-8")

    r = client.post(
        f"/api/runs/{run_id}/sim-override",
        json={"item_id": "item-1", "interest": "skip"},
    )

    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_sim_override_rejects_invalid_interest(client):
    r = client.post(
        "/api/runs/20260101-120000-abcd1234/sim-override",
        json={"item_id": "item-1", "interest": "bad"},
    )

    assert r.status_code == 422


def test_aicu_status(client, monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.utils.config.load_config",
        lambda: {"ingest": {"aicu_enabled": True}},
    )
    r = client.get("/api/ingest/aicu-status")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_ingest_recognition_api(client):
    r = client.get("/api/ingest/recognition")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert "recent" in body
    assert "inventory" in body


def test_run_detail_rejects_invalid_run_id(client):
    r = client.get("/api/runs/bad%run")
    assert r.status_code == 400


def test_run_detail_skips_list_artifacts(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_dir = tmp_path / "runs" / "20260101-120000-abcd1234"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        '{"run_id":"20260101-120000-abcd1234","command":"search","query":"x","steps":[]}',
        encoding="utf-8",
    )
    (run_dir / "01_collect_all.json").write_text('{"step":"collect_all","status":"ok"}', encoding="utf-8")
    (run_dir / "items_raw.json").write_text("[{}]", encoding="utf-8")
    r = client.get("/api/runs/20260101-120000-abcd1234")
    assert r.status_code == 200
    assert len(r.json()["steps"]) == 1


def test_sse_scan_reemits_changed_step_file(tmp_path, monkeypatch):
    from osint_toolkit.web.routes.api import _scan_run_dir

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-abcd1234"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    step_path = run_dir / "01_demo.json"
    step_path.write_text('{"step":"demo","status":"running"}', encoding="utf-8")

    first = _scan_run_dir(run_id, {})
    assert first["new_steps"][0]["data"]["status"] == "running"

    step_path.write_text('{"step":"demo","status":"ok"}', encoding="utf-8")
    stat = step_path.stat()
    os.utime(step_path, ns=(stat.st_atime_ns + 1_000_000, stat.st_mtime_ns + 1_000_000))
    second = _scan_run_dir(run_id, first["new_file_versions"])

    assert second["new_steps"][0]["data"]["status"] == "ok"
