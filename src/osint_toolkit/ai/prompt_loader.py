"""Prompt 模板加载 / Prompt template loader."""

from __future__ import annotations

from pathlib import Path

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.utils.atomic_write import atomic_write_text
from osint_toolkit.utils.safe_path import assert_prompt_name, resolve_under

BUILTIN_PROMPTS = {
    "summarize": (
        "请为以下内容生成结构化摘要，列出核心观点、论据、局限。保持客观。\n"
        "严格遵守：仅基于下方提供的标题、来源、正文和社区观点进行总结；"
        "不得引入原文未提及的事件、人物、产品或观点；不要编造不存在的事实。\n"
        "严禁直接复制或改述原文句子——必须提炼压缩为要点，每条不超过 60 字。"
        "如果原文信息量极少，只输出 1-2 条即可，不要为了凑数而重复。"
    ),
    "report": (
        "请基于以下情报 JSON 生成一份**完整、易读、可扫读**的 Markdown 情报报告。\n\n"
        "必须包含以下一级章节（用 ## 标题，顺序保持一致）：\n"
        "1. **执行摘要** — 3–6 条要点，概括话题核心结论与信息完整度\n"
        "2. **话题脉络** — 按时间或逻辑梳理事件/概念发展（可用小标题分段）\n"
        "3. **分主题深度分析** — 每个子话题独立小节：事实、各方观点、证据来源\n"
        "4. **信源覆盖与可信度** — 表格或列表说明各来源贡献、互补与盲区\n"
        "5. **社区与评论视角** — 综合 comments_summary，标注支持与反对观点\n"
        "6. **争议与待核实** — 明确列出矛盾信息、营销嫌疑、需二次验证的点\n"
        "7. **阅读清单** — 按优先级列出 5–10 条最值得深读的条目（标题 + 一句话理由 + 链接）\n"
        "8. **后续建议** — 若继续研究，建议的下一步关键词或角度\n\n"
        "写作要求：中文、客观中立、段落不宜过长（每段 2–4 句）；重要结论用 **粗体**；"
        "执行摘要用有序列表；分主题分析用小标题 ###；表格列宽适中；"
        "引用具体条目时标注来源类型（知乎/B站/IT之家等）；不要编造 JSON 中不存在的事实。"
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
    "foreign_expand": (
        "为 GitHub、Reddit、Hacker News 等国际信源生成英文检索词。"
        "输出 JSON：en_queries（英文检索词数组）、romanization（罗马字/日文等，可选）、confidence（0-1）。"
        "若用户查询为中文实体/作品名，给出常用英文官方译名或罗马字；"
        "若查询已是英文产品名，给出常见变体（大小写、连字符）。"
        "禁止编造无依据的译名；不确定时降低 confidence 并少输出。"
    ),
    "query_analyze": (
        "请分析用户查询意图，输出扩展检索策略。"
        "必须包含：圈内昵称、简称、罗马字/英文译名、梗称；若用户研究 ACG/角色，"
        "还应包含常见黑称/贬义称呼（标注在 aliases 中）。"
        "expanded_queries 为实际用于各平台搜索的查询词列表（含原词与别名变体）。"
        "JSON 字段: intent, expanded_queries(数组), aliases(数组), recommended_sources(数组)。"
        "recommended_sources：按话题相关性列出信源 ID（可含用户未勾选项），用于系统加权；"
        "强相关放前面，弱相关或不相关不要列入。"
        "可选信源 ID 见用户消息中的「可选扩展信源」列表。"
        "结合意图举例：开源大模型→github,hackernews,juejin,zhihu；"
        "Cursor/Composer 编程模型→github,v2ex,juejin,zhihu,bilibili,web（勿按音乐作曲软件理解 composer）；"
        "音乐歌曲→bilibili,netease_music,qq_music；舆情→weibo,xiaohongshu；游戏→nga,gcores。"
        "expanded_queries 勿引入与原意图无关的领域词（如技术查询中不要生成「音乐生成」「AI作曲」类检索词）。"
    ),
    "source_plan": (
        "你是情报搜罗助手，需用链式思考分析用户查询，并规划信源。"
        "先逐步推理，再给出结构化 JSON（不要输出 JSON 以外的正文）。"
        "JSON 字段："
        "reasoning_chain(数组，每项含 id/title/content，至少 5 步：理解查询、提取关键词、判断信息域、"
        "区分综合性平台与垂直站、信源策略)；"
        "topic_keywords(数组，3-8 个检索关键词/圈内词)；"
        "topic_summary(一句话话题摘要)；"
        "query_substance(字符串 substantive|cryptic|nonsense，查询是否有实质检索价值；"
        "随机字符/纯灌水/无法推断意图→nonsense)；"
        "is_cryptic(布尔，查询是否隐晦/需圈内知识才能理解)；"
        "auto_enable(数组，建议系统自动启用且用户未勾选、且确有价值的信源 id，最多 6 个；"
        "优先垂直站、SERP、GitHub、B站等；勿列入音乐流媒体除非明确歌曲话题；"
        "用户已勾选的 id 不要重复列入)；"
        "source_scores(对象，key 为信源 id，value 含 score 0-100、tier strong|medium|weak|skip、reason 一句话)。"
        "只评价与话题可能相关的信源；强相关 score≥70，中等 40-69，弱 15-39，应跳过 <15。"
        "规则分偏低但话题有实质内容时，应依据平台内容形态（讨论/教程/开源/资讯）给 bilibili、github、"
        "垂直社区、web 等合理高分，并在 auto_enable 中明确建议。"
        "nonsense 查询时 source_scores 全低、auto_enable 为空。"
    ),
}


def user_prompt_path(name: str) -> Path:
    safe_name = assert_prompt_name(name)
    return resolve_under(get_data_dir() / "prompts", f"{safe_name}.md")


def load_prompt(name: str) -> tuple[str, str]:
    """返回 (prompt_text, source) source 为 user 或 builtin。"""
    user_path = user_prompt_path(name)
    if user_path.exists():
        return user_path.read_text(encoding="utf-8"), "user"
    return BUILTIN_PROMPTS.get(name, ""), "builtin"


def save_user_prompt(name: str, content: str) -> Path:
    path = user_prompt_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, content)
    return path


def reset_user_prompt(name: str) -> bool:
    path = user_prompt_path(name)
    if path.exists():
        path.unlink()
        return True
    return False
