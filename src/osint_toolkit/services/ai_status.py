"""AI status helpers / AI 状态与调用概况."""

from __future__ import annotations

from typing import Any

from osint_toolkit.ai.client import resolve_api_key
from osint_toolkit.ai.steering import load_directives
from osint_toolkit.ai.step_registry import AI_STEPS
from osint_toolkit.services import ai_audit, ai_config
from osint_toolkit.utils.config import get_ai_config


def _api_key_configured() -> bool:
    try:
        return bool(resolve_api_key())
    except Exception:  # noqa: BLE001
        return False


def get_ai_status() -> dict[str, Any]:
    cfg = get_ai_config()
    directives = load_directives()
    prompts = ai_config.list_prompts()
    steps = []
    for step_id, label in AI_STEPS.items():
        steps.append(
            {
                "id": step_id,
                "label": label,
                "enabled": bool((directives.get("enabled_steps") or {}).get(step_id, True)),
            }
        )
    enabled_count = len([step for step in steps if step["enabled"]])
    recent_activity = ai_audit.summarize_ai_calls(limit=200)
    return {
        "provider": str(cfg.get("provider") or "deepseek"),
        "base_url": str(cfg.get("base_url") or ""),
        "model": str(cfg.get("model") or ""),
        "timeout": float(cfg.get("timeout", 120) or 120),
        "api_key_configured": _api_key_configured(),
        "persona_inject": bool(cfg.get("persona_inject", True)),
        "dwell_save_no_ai": bool(cfg.get("dwell_save_no_ai", True)),
        "auto_persona_rebuild": str(cfg.get("auto_persona_rebuild") or "auto"),
        "auto_persona_rebuild_threshold": int(cfg.get("auto_persona_rebuild_threshold", 50) or 50),
        "auto_persona_rebuild_max_age_hours": int(cfg.get("auto_persona_rebuild_max_age_hours", 168) or 0),
        "steps": steps,
        "enabled_step_count": enabled_count,
        "total_step_count": len(steps),
        "prompt_overrides": len([prompt for prompt in prompts if prompt.get("source") == "user"]),
        "prompts": prompts,
        "recent_activity": recent_activity,
        "features": {
            "knowledge_search": {
                "ai_used": False,
                "mode": "local_hybrid_retrieval",
                "summary": "知识检索本身不调用 AI，走本地 FTS + 关键词 + 主题/实体/行为信号混合检索。",
            },
            "knowledge_ask": {
                "retrieval": "local_hybrid_retrieval",
                "answer_generation": "ai_with_local_fallback",
                "summary": "问知识库时先本地召回，再由 AI 基于命中内容生成答案；AI 不可用时退回本地证据式回答。",
            },
            "search_pipeline": {
                "local_context_used": True,
                "no_ai_switch": True,
                "summary": "搜罗管线按步骤选择性调用 AI，可整体 no_ai，也可单独关闭具体 AI 步骤。",
            },
        },
    }
