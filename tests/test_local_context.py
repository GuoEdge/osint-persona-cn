from __future__ import annotations

import json

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.context import PersonaContext
from osint_toolkit.services import knowledge
from osint_toolkit.services.local_context import build_local_context, compact_for_prompt
from osint_toolkit.storage.knowledge import log_event_deduped, save_item


def test_build_local_context_collects_local_hints(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    item = IntelItem(
        source="zhihu",
        type="answer",
        url="https://zhihu.com/question/1",
        title="MCP 本地检索经验",
        content="讨论 MCP 与本地知识库检索。",
    )
    save_item(item)
    knowledge.enrich_item(item.id)
    log_event_deduped(
        "ext_page_dwell",
        {
            "url": "https://example.com/mcp",
            "title": "MCP 长停留文章",
            "source": "web",
            "duration_ms": 120000,
        },
        "ctx|mcp",
    )
    fb = tmp_path / "feedback.jsonl"
    fb.write_text(
        json.dumps(
            {
                "target_type": "item",
                "target_id": "abc",
                "rating": "useful",
                "reason": "命中主题",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    persona = PersonaContext(
        brief="偏好本地优先工具",
        recent_topics=["mcp"],
        interest_hints=[],
        structured={"interest_domains": [{"name": "本地知识库", "weight": 2}]},
    )

    ctx = build_local_context("MCP", persona_ctx=persona)

    assert ctx["persona"]["brief"] == "偏好本地优先工具"
    assert ctx["persona"]["structured"]["interest_domains"][0]["name"] == "本地知识库"
    assert ctx["persona"]["active_projects"] == []
    assert ctx["knowledge_hits"]
    assert ctx["knowledge_concepts"]
    assert "questions" in ctx["knowledge_gaps"]
    assert ctx["behavior_samples"]
    assert ctx["linkage_summary"]["top_concepts"]
    assert "behavior_focus" in ctx["linkage_summary"]
    assert ctx["feedback_patterns"]["rating_counts"]["useful"] == 1
    assert "https://example.com/mcp" in ctx["seen_urls"]


def test_compact_for_prompt_limits_size():
    ctx = {
        "persona": {"brief": "x" * 200},
        "knowledge_hits": [],
        "knowledge_concepts": [{"name": "MCP"}],
        "knowledge_projects": [{"name": "本地知识库"}],
        "knowledge_gaps": {"questions": [{"question": "还缺什么？"}]},
        "behavior_samples": [],
        "feedback_patterns": {},
        "linkage_summary": {"top_projects": ["本地知识库"]},
    }
    text = compact_for_prompt(ctx, max_chars=50)
    assert len(text) <= 53
    assert text.endswith("...")
