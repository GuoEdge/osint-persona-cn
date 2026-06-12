"""Prompt 模板加载 / Prompt template loader."""

from __future__ import annotations

from pathlib import Path

from osint_toolkit.auth.paths import get_data_dir

BUILTIN_PROMPTS = {
    "summarize": "请为以下内容生成结构化摘要，列出核心观点、论据、局限。保持客观。",
    "report": (
        "请基于以下情报条目生成Markdown情报报告，含执行摘要、话题簇、信源覆盖、"
        "社区争议/补充（来自 comments_summary）、争议点、已折叠区及折叠原因。"
    ),
    "persona_sim": (
        "模拟当前用户是否会点开每条候选情报。"
        "必须结合 persona brief 中的兴趣与偏好，输出 interest/confidence/verdict/reason。"
    ),
    "alias_discover": (
        "根据联网检索到的标题与摘要，提取与查询相关的当代称呼。"
        "只能从证据文本中出现、或被证据明确支持的圈内缩写/昵称/梗/标签；"
        "不得凭训练记忆编造未在证据中出现的词。"
        "优先近期、高频、在多条证据重复出现的叫法。"
    ),
    "query_analyze": (
        "请分析用户查询意图，输出扩展检索策略。"
        "必须包含：圈内昵称、简称、罗马字/英文译名、梗称；若用户研究 ACG/角色，"
        "还应包含常见黑称/贬义称呼（标注在 aliases 中）。"
        "expanded_queries 为实际用于各平台搜索的查询词列表（含原词与别名变体）。"
        "JSON 字段: intent, expanded_queries(数组), aliases(数组,别名说明用), recommended_sources(数组)。"
    ),
}


def user_prompt_path(name: str) -> Path:
    return get_data_dir() / "prompts" / f"{name}.md"


def load_prompt(name: str) -> tuple[str, str]:
    """返回 (prompt_text, source) source 为 user 或 builtin。"""
    user_path = user_prompt_path(name)
    if user_path.exists():
        return user_path.read_text(encoding="utf-8"), "user"
    return BUILTIN_PROMPTS.get(name, ""), "builtin"


def save_user_prompt(name: str, content: str) -> Path:
    path = user_prompt_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def reset_user_prompt(name: str) -> bool:
    path = user_prompt_path(name)
    if path.exists():
        path.unlink()
        return True
    return False
