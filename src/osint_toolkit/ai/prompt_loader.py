"""Prompt 模板加载 / Prompt template loader."""

from __future__ import annotations

from pathlib import Path

from osint_toolkit.auth.paths import get_data_dir

BUILTIN_PROMPTS = {
    "summarize": "请为以下内容生成结构化摘要，列出核心观点、论据、局限。保持客观。",
    "report": "请基于以下情报条目生成Markdown情报报告，含执行摘要、话题簇、信源覆盖、争议点、已折叠区及折叠原因。",
    "persona_sim": "请模拟用户可能如何判断以下候选情报，输出置信度与依据，不做最终裁决。",
    "query_analyze": "请分析用户查询意图，给出扩展关键词与推荐信源策略，JSON格式。",
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
