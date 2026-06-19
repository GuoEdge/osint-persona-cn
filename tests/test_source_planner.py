"""AI 信源规划测试."""

from osint_toolkit.ai.source_planner import _normalize_plan, detect_cryptic_query, extract_ai_score_map
from osint_toolkit.collectors.source_resolve import blend_rule_and_ai_scores
from osint_toolkit.collectors.source_routing import compute_source_scores


def test_normalize_plan_reasoning_chain():
    raw = {
        "reasoning_chain": [
            {"id": "u", "title": "理解", "content": "用户在问某梗"},
            {"id": "k", "title": "关键词", "content": "核心词 A"},
        ],
        "topic_keywords": ["梗", "黑话"],
        "topic_summary": "亚文化梗解析",
        "is_cryptic": True,
        "source_scores": {
            "zhihu": {"score": 80, "tier": "strong", "reason": "讨论多"},
            "weixin": {"score": 5, "tier": "skip", "reason": "不相关"},
        },
    }
    plan = _normalize_plan(raw)
    assert len(plan["reasoning_chain"]) == 2
    assert plan["is_cryptic"] is True
    assert plan["source_scores"]["zhihu"]["score"] == 80


def test_extract_ai_score_map():
    plan = {"source_scores": {"github": {"score": 90}, "web": {"score": 40}}}
    assert extract_ai_score_map(plan)["github"] == 90.0


def test_blend_prefers_ai_on_cryptic():
    rule = compute_source_scores("某圈内黑话", ai_priority=None)
    ai_plan = {
        "is_cryptic": True,
        "source_scores": {
            "zhihu": {"score": 85, "reason": "圈内讨论"},
            "tieba": {"score": 70, "reason": "贴吧梗"},
        },
    }
    blended, breakdown = blend_rule_and_ai_scores(rule, ai_plan, is_cryptic=True)
    assert blended["zhihu"] > rule.get("zhihu", 0)
    assert breakdown["zhihu"]["ai"] == 85.0


def test_detect_cryptic_low_rule_scores():
    rule = {"web": 22, "zhihu": 18}
    assert detect_cryptic_query("神秘缩写 XYZ", rule) is True
