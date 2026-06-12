"""命令行入口 / CLI entry point."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess

import click
from rich.console import Console
from rich.table import Table

from osint_toolkit.ai.client import DeepSeekClient, resolve_api_key
from osint_toolkit.ai.prompt_loader import (
    BUILTIN_PROMPTS,
    load_prompt,
    reset_user_prompt,
    save_user_prompt,
)
from osint_toolkit.ai.steering import directives_path, load_directives, save_directives
from osint_toolkit.auth.cookie_sync import (
    DEFAULT_DOMAINS,
    sync_browser_cookies,
    validate_domain_cookie,
)
from osint_toolkit.auth.paths import get_config_paths, get_cookies_dir, get_data_dir
from osint_toolkit.collectors.domain import collect_domain_info
from osint_toolkit.exporters.digest import generate_daily_digest
from osint_toolkit.feedback.apply import apply_step_feedback
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.ingest.bilibili_account import ingest_history
from osint_toolkit.ingest.browser import ingest_browser_history
from osint_toolkit.ingest.likes import list_endorsements
from osint_toolkit.ingest.zhihu_account import ingest_votes
from osint_toolkit.persona.builder import build_persona_draft
from osint_toolkit.persona.store import (
    load_mental_model,
    load_persona_brief,
    mental_model_path,
    rollback_version,
)
from osint_toolkit.services.runs import list_runs, show_run
from osint_toolkit.services.save import save_url
from osint_toolkit.services.search import run_search
from osint_toolkit.storage.knowledge import recall

console = Console()


@click.group()
@click.version_option()
def main() -> None:
    """OSINT Toolkit — 个人情报工具"""


@main.group()
def auth() -> None:
    """认证、API Key 与 Cookie 管理"""


@auth.command("sync-cookies")
@click.option("--browser", default=None)
@click.option("--domain", "domains", multiple=True)
def sync_cookies(browser: str | None, domains: tuple[str, ...]) -> None:
    domain_list = list(domains) if domains else None
    console.print("[bold]正在同步浏览器 Cookie...[/]")
    result = sync_browser_cookies(browser=browser, domains=domain_list)
    for err in result.errors:
        console.print(f"[red]{err}[/]")
    if result.domains_synced:
        table = Table(title="Cookie 同步结果")
        table.add_column("域名")
        table.add_column("数量", justify="right")
        for d in result.domains_synced:
            table.add_row(d, str(result.cookie_counts.get(d, 0)))
        console.print(table)
        console.print(f"[green]已写入[/] {result.output_dir}")


@auth.command("test")
@click.option("--target", default="all")
def auth_test(target: str) -> None:
    target = target.lower()
    table = Table(title="认证检查")
    table.add_column("项目")
    table.add_column("状态")
    table.add_column("说明")
    if target in {"all", "deepseek"}:
        try:
            resolve_api_key()
            result = DeepSeekClient().test_connection()
            status = "[green]通过[/]" if result["ok"] else "[yellow]异常[/]"
            table.add_row("DeepSeek API", status, f"model={result['model']}")
        except Exception as exc:  # noqa: BLE001
            table.add_row("DeepSeek API", "[red]失败[/]", str(exc))
    if target in {"all", "bilibili"}:
        r = validate_domain_cookie("bilibili.com")
        table.add_row("bilibili.com", "[green]通过[/]" if r["ok"] else "[red]失败[/]", r["reason"])
    if target in {"all", "zhihu"}:
        r = validate_domain_cookie("zhihu.com")
        table.add_row("zhihu.com", "[green]通过[/]" if r["ok"] else "[red]失败[/]", r["reason"])
    console.print(table)


@auth.command("show-paths")
def show_paths() -> None:
    console.print("[bold]DEEPSEEK_API_KEY[/] 环境变量或 config ai.api_key")
    for p in get_config_paths():
        console.print(f"  - {p}")
    console.print(f"[bold]Cookie[/] {get_cookies_dir()}")
    console.print(f"[bold]Data[/] {get_data_dir()}")
    console.print(f"[bold]AI directives[/] {directives_path()}")


@auth.command("list-domains")
def list_domains() -> None:
    for d in DEFAULT_DOMAINS:
        console.print(d)


@main.group()
def ai() -> None:
    """AI 导向与 prompt 管理"""


@ai.group()
def directives() -> None:
    """持久 AI 导向配置"""


@directives.command("show")
def ai_directives_show() -> None:
    import yaml

    console.print(yaml.dump(load_directives(), allow_unicode=True, sort_keys=False))


@directives.command("edit")
def ai_directives_edit() -> None:
    path = directives_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_directives(load_directives())
    editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "nano")
    subprocess.run([editor, str(path)], check=False)


@ai.group()
def prompts() -> None:
    """Prompt 模板管理"""


@prompts.command("list")
def ai_prompts_list() -> None:
    for name in BUILTIN_PROMPTS:
        _, source = load_prompt(name)
        console.print(f"{name}: {source}")


@prompts.command("edit")
@click.argument("name")
def ai_prompts_edit(name: str) -> None:
    text, _ = load_prompt(name)
    path = save_user_prompt(name, text)
    editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "nano")
    subprocess.run([editor, str(path)], check=False)


@prompts.command("reset")
@click.argument("name")
def ai_prompts_reset(name: str) -> None:
    if reset_user_prompt(name):
        console.print(f"[green]已恢复内置模板[/] {name}")
    else:
        console.print("[yellow]无用户覆盖[/]")


@main.command()
@click.argument("query")
@click.option("--sources", default="zhihu,bilibili,web")
@click.option("--limit", default=10, type=int)
@click.option("--digest", is_flag=True)
@click.option("--trace", is_flag=True)
@click.option("--profile", default="default")
@click.option("--ai-instruct", default="")
@click.option("--no-ai", is_flag=True)
@click.option("--no-simulate", is_flag=True)
@click.option("--no-ai-step", multiple=True)
@click.option("--deep-top", default=0, type=int)
@click.option("--json", "as_json", is_flag=True)
def search(
    query: str,
    sources: str,
    limit: int,
    digest: bool,
    trace: bool,
    profile: str,
    ai_instruct: str,
    no_ai: bool,
    no_simulate: bool,
    no_ai_step: tuple[str, ...],
    deep_top: int,
    as_json: bool,
) -> None:
    """多源搜索与情报采集。"""
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    result = asyncio.run(
        run_search(
            query,
            sources=source_list,
            limit=limit,
            digest=digest,
            trace=trace,
            profile=profile,
            ai_instruct=ai_instruct,
            no_ai=no_ai,
            no_simulate=no_simulate,
            disabled_ai_steps=list(no_ai_step),
            deep_top=deep_top,
        )
    )
    if as_json:
        payload = {
            "run_id": result["run_id"],
            "items": [i.to_dict() for i in result["items"]],
            "report_path": result["report_path"],
            "simulations": result["simulations"],
        }
        console.print_json(data=payload)
        return
    table = Table(title=f"搜索结果: {query}")
    table.add_column("来源")
    table.add_column("标题")
    table.add_column("相关度", justify="right")
    for item in result["items"][:20]:
        table.add_row(item.source, item.title[:60], str(item.signals.relevance))
    console.print(table)
    console.print(f"run_id: [cyan]{result['run_id']}[/]")
    if result["report_path"]:
        console.print(f"报告: [green]{result['report_path']}[/]")


@main.command()
@click.argument("url")
@click.option("--with-comments", is_flag=True)
@click.option("--no-ai", is_flag=True)
def save(url: str, with_comments: bool, no_ai: bool) -> None:
    """收录 URL 到知识库。"""
    result = asyncio.run(save_url(url, with_comments=with_comments, no_ai=no_ai))
    item = result["item"]
    console.print(f"[green]已收录[/] {item.title}")
    console.print(f"卡片: {result['card_path']}")


@main.command()
@click.argument("query")
@click.option("--limit", default=20, type=int)
def recall_cmd(query: str, limit: int) -> None:
    """检索知识库。"""
    items = recall(query, limit=limit)
    if not items:
        console.print("[yellow]未找到匹配条目[/]")
        return
    for item in items:
        console.print(f"- [{item.source}] {item.title} | {item.url}")


@main.group()
def ingest() -> None:
    """行为与账号数据导入"""


@ingest.command("browser")
@click.option("--since", "since_days", default=90, type=int)
def ingest_browser(since_days: int) -> None:
    rows = ingest_browser_history(since_days=since_days)
    console.print(f"[green]导入浏览器历史 {len(rows)} 条[/]")


@ingest.command("bilibili")
@click.option("--history", is_flag=True)
def ingest_bilibili(history: bool) -> None:
    if history:
        rows = asyncio.run(ingest_history())
        console.print(f"[green]导入 B站观看历史 {len(rows)} 条[/]")


@ingest.command("zhihu")
@click.option("--votes", is_flag=True)
def ingest_zhihu(votes: bool) -> None:
    if votes:
        rows = asyncio.run(ingest_votes())
        console.print(f"[green]导入知乎赞同 {len(rows)} 条[/]")


@ingest.command("likes")
def ingest_likes() -> None:
    rows = list_endorsements()
    console.print(f"认可记录: {len(rows)} 条")


@main.group()
def persona() -> None:
    """心智画像管理"""


@persona.command("build")
@click.option("--review", is_flag=True)
def persona_build(review: bool) -> None:
    draft = build_persona_draft()
    console.print(f"[green]Persona v{draft['mental_model'].get('version')} 已生成[/]")
    if review:
        console.print(f"请审阅: {mental_model_path()}")


@persona.command("show")
def persona_show() -> None:
    console.print(load_mental_model())
    console.print("\n[bold]brief[/]\n" + load_persona_brief())


@persona.command("rollback")
@click.option("--version", "ver", required=True, type=int)
def persona_rollback(ver: int) -> None:
    if rollback_version(ver):
        console.print(f"[green]已回滚到 v{ver}[/]")
    else:
        console.print("[red]版本不存在[/]")


@main.group()
def run() -> None:
    """Pipeline 运行记录"""


@run.command("list")
@click.option("--limit", default=20, type=int)
def run_list(limit: int) -> None:
    for r in list_runs(limit=limit):
        console.print(f"{r.get('run_id')} | {r.get('command')} | {r.get('query', '')}")


@run.command("show")
@click.argument("run_id")
@click.option("--step", default=None)
def run_show(run_id: str, step: str | None) -> None:
    data = show_run(run_id, step=step)
    console.print_json(data=data if isinstance(data, dict) else json.loads(json.dumps(data)))


@run.command("open")
@click.argument("run_id")
def run_open(run_id: str) -> None:
    path = get_data_dir() / "runs" / run_id
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        console.print(str(path))


@main.command()
@click.argument("target_id")
@click.argument("rating", type=click.Choice(["useful", "noise", "entertainment", "wrong"]))
@click.option("--reason", default="")
@click.option("--run-id", default=None)
@click.option("--step", default=None)
def feedback(target_id: str, rating: str, reason: str, run_id: str | None, step: str | None) -> None:
    """提交反馈。"""
    if step:
        result = apply_step_feedback(rating, reason, step=step)
        console.print(result)
    store = FeedbackStore()
    store.add(target_type="item", target_id=target_id, rating=rating, reason=reason, run_id=run_id, step=step)
    console.print("[green]反馈已记录[/]")


@main.command()
@click.option("--daily", is_flag=True)
def digest(daily: bool) -> None:
    """生成简报。"""
    if daily:
        text = generate_daily_digest()
        console.print(text)


@main.command()
@click.argument("question")
@click.option("--context", "ctx", default="last-search")
def ask(question: str, ctx: str) -> None:
    """基于上下文追问（简化版）。"""
    runs = list_runs(limit=1)
    context = runs[0] if runs else {}
    client = DeepSeekClient()
    answer = client.chat(
        messages=[
            {"role": "system", "content": "你是个人情报助手，基于给定搜索上下文回答追问。"},
            {"role": "user", "content": f"上下文:{json.dumps(context, ensure_ascii=False)[:4000]}\n问题:{question}"},
        ]
    )
    console.print(answer)


@main.command()
@click.argument("domain")
@click.option("--json", "as_json", is_flag=True)
def domain(domain: str, as_json: bool) -> None:
    """遗留: 域名 DNS 查询。"""
    result = collect_domain_info(domain)
    if as_json:
        console.print_json(data=result)
        return
    console.print(f"[bold cyan]Domain:[/] {result['domain']}")
    for record in result.get("dns_records", []):
        console.print(f"  [green]{record['type']}[/] {record['value']}")


if __name__ == "__main__":
    main()
