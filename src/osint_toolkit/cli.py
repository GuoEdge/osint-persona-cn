"""命令行入口 / CLI entry point."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess

import click
from rich.console import Console
from rich.table import Table

from osint_toolkit.ai.steering import directives_path
from osint_toolkit.services import ai_config, auth, digest, feedback, ingest, knowledge, persona, runs, tools
from osint_toolkit.services import save as save_svc
from osint_toolkit.services import search as search_svc
from osint_toolkit.services.ask import ask_question

console = Console()


@click.group()
@click.version_option()
def main() -> None:
    """OSINT Toolkit — 个人情报工具"""


@main.group()
def auth_group() -> None:
    """认证、API Key 与 Cookie 管理"""


@auth_group.command("sync-cookies")
@click.option("--browser", default=None)
@click.option("--domain", "domains", multiple=True)
def sync_cookies(browser: str | None, domains: tuple[str, ...]) -> None:
    domain_list = list(domains) if domains else None
    console.print("[bold]正在同步浏览器 Cookie...[/]")
    result = auth.sync_cookies(browser=browser, domains=domain_list)
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


@auth_group.command("test")
@click.option("--target", default="all")
def auth_test(target: str) -> None:
    table = Table(title="认证检查")
    table.add_column("项目")
    table.add_column("状态")
    table.add_column("说明")
    for entry in auth.get_auth_status(target):
        status = "[green]通过[/]" if entry["ok"] else "[red]失败[/]"
        table.add_row(entry["name"], status, entry.get("detail", ""))
    console.print(table)


@auth_group.command("show-paths")
def show_paths() -> None:
    paths = auth.get_paths()
    console.print(f"[bold]{paths['api_key_hint']}[/]")
    for p in paths["config_paths"]:
        console.print(f"  - {p}")
    console.print(f"[bold]Cookie[/] {paths['cookies_dir']}")
    console.print(f"[bold]Data[/] {paths['data_dir']}")
    console.print(f"[bold]AI directives[/] {paths['directives_path']}")


@auth_group.command("list-domains")
def list_domains() -> None:
    for d in auth.list_domains():
        console.print(d)


main.add_command(auth_group, name="auth")


@main.group()
def ai() -> None:
    """AI 导向与 prompt 管理"""


@ai.group()
def directives() -> None:
    """持久 AI 导向配置"""


@directives.command("show")
def ai_directives_show() -> None:
    import yaml

    console.print(yaml.dump(ai_config.get_directives(), allow_unicode=True, sort_keys=False))


@directives.command("edit")
def ai_directives_edit() -> None:
    path = directives_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        ai_config.update_directives(ai_config.get_directives())
    editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "nano")
    subprocess.run([editor, str(path)], check=False)


@ai.group()
def prompts() -> None:
    """Prompt 模板管理"""


@prompts.command("list")
def ai_prompts_list() -> None:
    for item in ai_config.list_prompts():
        console.print(f"{item['name']}: {item['source']}")


@prompts.command("edit")
@click.argument("name")
def ai_prompts_edit(name: str) -> None:
    from osint_toolkit.ai.prompt_loader import save_user_prompt

    prompt = ai_config.get_prompt(name)
    path = save_user_prompt(name, prompt["text"])
    editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "nano")
    subprocess.run([editor, str(path)], check=False)


@prompts.command("reset")
@click.argument("name")
def ai_prompts_reset(name: str) -> None:
    result = ai_config.reset_prompt(name)
    if result["ok"]:
        console.print(f"[green]已恢复内置模板[/] {name}")
    else:
        console.print("[yellow]无用户覆盖[/]")


@main.command("search")
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
@click.option("--comment-mine-top", default=None, type=int)
@click.option("--no-mine-comments", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def search_cmd(
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
    comment_mine_top: int | None,
    no_mine_comments: bool,
    as_json: bool,
) -> None:
    """多源搜索与情报采集。"""
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    result = asyncio.run(
        search_svc.run_search(
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
            comment_mine_top=0 if no_mine_comments else comment_mine_top,
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
    result = asyncio.run(save_svc.save_url(url, with_comments=with_comments, no_ai=no_ai))
    item = result["item"]
    console.print(f"[green]已收录[/] {item.title}")
    console.print(f"卡片: {result['card_path']}")


@main.command("recall")
@click.argument("query")
@click.option("--limit", default=20, type=int)
def recall_cmd(query: str, limit: int) -> None:
    """检索知识库。"""
    items = knowledge.recall(query, limit=limit)
    if not items:
        console.print("[yellow]未找到匹配条目[/]")
        return
    for item in items:
        console.print(f"- [{item.source}] {item.title} | {item.url}")


@main.group()
def ingest_group() -> None:
    """行为与账号数据导入"""


@ingest_group.command("browser")
@click.option("--since", "since_days", default=90, type=int)
def ingest_browser(since_days: int) -> None:
    result = ingest.ingest_browser(since_days=since_days)
    console.print(f"[green]导入浏览器历史 {result['count']} 条[/]")


@ingest_group.command("bilibili")
@click.option("--history-only", is_flag=True, help="仅拉取观看历史（默认拉取历史+收藏+点赞+关注）")
def ingest_bilibili(history_only: bool) -> None:
    result = ingest.ingest_bilibili_sync(
        include_favorites=not history_only,
        include_likes=not history_only,
    )
    console.print(f"[green]B站导入 {result['count']} 条[/]")
    for warning in result.get("warnings") or []:
        console.print(f"[yellow]{warning}[/]")


@ingest_group.command("zhihu")
def ingest_zhihu() -> None:
    result = ingest.ingest_zhihu_sync()
    console.print(f"[green]知乎导入 {result['count']} 条[/]")
    for warning in result.get("warnings") or []:
        console.print(f"[yellow]{warning}[/]")


@ingest_group.command("likes")
def ingest_likes() -> None:
    result = ingest.get_likes()
    console.print(f"认可记录: {result['count']} 条")


@ingest_group.command("browser-sync")
@click.option(
    "--platform",
    "platforms",
    multiple=True,
    type=click.Choice(["bilibili", "zhihu", "all"]),
    default=["all"],
)
@click.option("--cdp", is_flag=True, help="使用 CDP 附着已开调试端口的 Edge")
@click.option("--headed", is_flag=True, help="显示浏览器窗口（非 headless）")
def ingest_browser_sync(platforms: tuple[str, ...], cdp: bool, headed: bool) -> None:
    """Playwright 本机 Edge 会话补洞（需 pip install -e \".[browser]\"）。"""
    from osint_toolkit.services import browser_sync as browser_sync_service

    selected: tuple[str, ...]
    if "all" in platforms or not platforms:
        selected = ("bilibili", "zhihu")
    else:
        selected = tuple(p for p in platforms if p != "all")
    mode = "cdp" if cdp else None
    console.print("[cyan]浏览器会话同步中…（Persistent 模式需关闭 Edge）[/]")
    result = asyncio.run(
        browser_sync_service.execute_browser_sync(
            platforms=selected,
            mode=mode,
            headless=not headed,
        )
    )
    console.print(f"[green]写入 {result.get('accepted', 0)} 条，跳过重复 {result.get('skipped', 0)}[/]")
    for warning in result.get("warnings") or []:
        console.print(f"[yellow]{warning}[/]")
    if result.get("pages_visited"):
        console.print(f"访问页面: {len(result['pages_visited'])}")


main.add_command(ingest_group, name="ingest")


@main.group()
def persona_group() -> None:
    """心智画像管理"""


@persona_group.command("build")
@click.option("--review", is_flag=True)
def persona_build(review: bool) -> None:
    result = persona.build_persona(review=review)
    console.print(f"[green]Persona v{result['version']} 已生成[/]")
    if review:
        console.print(f"请审阅: {result['mental_model_path']}")


@persona_group.command("show")
def persona_show() -> None:
    data = persona.show_persona()
    console.print(data["mental_model"])
    console.print("\n[bold]brief[/]\n" + data["brief"])


@persona_group.command("rollback")
@click.option("--version", "ver", required=True, type=int)
def persona_rollback(ver: int) -> None:
    result = persona.rollback_persona(ver)
    if result["ok"]:
        console.print(f"[green]已回滚到 v{ver}[/]")
    else:
        console.print("[red]版本不存在[/]")


main.add_command(persona_group, name="persona")


@main.group()
def run() -> None:
    """Pipeline 运行记录"""


@run.command("list")
@click.option("--limit", default=20, type=int)
def run_list(limit: int) -> None:
    for r in runs.list_runs(limit=limit):
        console.print(f"{r.get('run_id')} | {r.get('command')} | {r.get('query', '')}")


@run.command("show")
@click.argument("run_id")
@click.option("--step", default=None)
def run_show(run_id: str, step: str | None) -> None:
    data = runs.show_run(run_id, step=step)
    console.print_json(data=data if isinstance(data, dict) else json.loads(json.dumps(data)))


@run.command("open")
@click.argument("run_id")
def run_open(run_id: str) -> None:
    from osint_toolkit.auth.paths import get_data_dir

    path = get_data_dir() / "runs" / run_id
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        console.print(str(path))


@main.command("feedback")
@click.argument("target_id")
@click.argument("rating", type=click.Choice(["useful", "noise", "entertainment", "wrong"]))
@click.option("--reason", default="")
@click.option("--run-id", default=None)
@click.option("--step", default=None)
def feedback_cmd(target_id: str, rating: str, reason: str, run_id: str | None, step: str | None) -> None:
    """提交反馈。"""
    result = feedback.submit_feedback(
        target_id=target_id,
        rating=rating,
        reason=reason,
        run_id=run_id,
        step=step,
    )
    if "step_feedback" in result:
        console.print(result["step_feedback"])
    console.print("[green]反馈已记录[/]")


@main.command("digest")
@click.option("--daily", is_flag=True)
def digest_cmd(daily: bool) -> None:
    """生成简报。"""
    if daily:
        console.print(digest.get_daily_digest())


@main.command()
@click.argument("question")
@click.option("--context", "ctx", default="last-search")
@click.option("--run-id", default=None)
def ask(question: str, ctx: str, run_id: str | None) -> None:
    """基于上下文追问（简化版）。"""
    if not run_id and ctx == "last-search":
        recent = runs.list_runs(limit=1)
        run_id = recent[0].get("run_id") if recent else None
    result = ask_question(question, run_id=run_id)
    console.print(result["answer"])


@main.command()
@click.argument("domain")
@click.option("--json", "as_json", is_flag=True)
def domain(domain: str, as_json: bool) -> None:
    """遗留: 域名 DNS 查询。"""
    result = tools.lookup_domain(domain)
    if as_json:
        console.print_json(data=result)
        return
    console.print(f"[bold cyan]Domain:[/] {result['domain']}")
    for record in result.get("dns_records", []):
        console.print(f"  [green]{record['type']}[/] {record['value']}")


@main.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8787, type=int)
def web(host: str, port: int) -> None:
    """启动 Web 控制台。"""
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException('请先安装 Web 依赖: pip install -e ".[web]"') from exc
    from osint_toolkit.web.app import create_app

    app = create_app()
    console.print(f"[green]Web 控制台:[/] http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
