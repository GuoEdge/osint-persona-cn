"""命令行入口 / CLI entry point."""

from __future__ import annotations

import os

import click
from rich.console import Console
from rich.table import Table

from osint_toolkit.ai.client import DeepSeekClient, resolve_api_key
from osint_toolkit.auth.cookie_sync import (
    DEFAULT_DOMAINS,
    sync_browser_cookies,
    validate_domain_cookie,
)
from osint_toolkit.auth.paths import get_config_paths, get_cookies_dir, get_data_dir
from osint_toolkit.collectors.domain import collect_domain_info

console = Console()


@click.group()
@click.version_option()
def main() -> None:
    """OSINT Toolkit — 个人情报工具"""


@main.group()
def auth() -> None:
    """认证、API Key 与 Cookie 管理"""


@auth.command("sync-cookies")
@click.option("--browser", default=None, help="浏览器：edge / chrome / firefox 等")
@click.option(
    "--domain",
    "domains",
    multiple=True,
    help="仅同步指定域名，可多次指定；默认使用配置中的域名列表",
)
def sync_cookies(browser: str | None, domains: tuple[str, ...]) -> None:
    """从本机浏览器同步 Cookie 到本地文件（Windows Edge 推荐）。"""
    domain_list = list(domains) if domains else None
    console.print("[bold]正在同步浏览器 Cookie...[/]")
    if os.name == "nt":
        console.print("[dim]提示：若失败，请先完全关闭 Edge 后重试。[/]")
    else:
        console.print("[dim]提示：Cookie 同步需在 Windows 本机执行。[/]")

    result = sync_browser_cookies(browser=browser, domains=domain_list)
    if result.errors:
        for err in result.errors:
            console.print(f"[red]错误:[/] {err}")

    if result.domains_synced:
        table = Table(title="Cookie 同步结果")
        table.add_column("域名")
        table.add_column("Cookie 数量", justify="right")
        for domain in result.domains_synced:
            table.add_row(domain, str(result.cookie_counts.get(domain, 0)))
        console.print(table)
        console.print(f"[green]已写入:[/] {result.output_dir}")
    elif not result.errors:
        console.print("[yellow]未找到匹配域名的 Cookie。请确认已在浏览器登录相关网站。[/]")


@auth.command("test")
@click.option(
    "--target",
    type=click.Choice(["all", "deepseek", "bilibili", "zhihu"], case_sensitive=False),
    default="all",
    help="测试目标",
)
def auth_test(target: str) -> None:
    """测试 DeepSeek API 与已同步的站点 Cookie。"""
    target = target.lower()
    table = Table(title="认证检查")
    table.add_column("项目")
    table.add_column("状态")
    table.add_column("说明")

    if target in {"all", "deepseek"}:
        try:
            resolve_api_key()
            client = DeepSeekClient()
            result = client.test_connection()
            status = "[green]通过[/]" if result["ok"] else "[yellow]异常[/]"
            detail = f"model={result['model']}, reply={result['reply']}"
            table.add_row("DeepSeek API", status, detail)
        except Exception as exc:  # noqa: BLE001
            table.add_row("DeepSeek API", "[red]失败[/]", str(exc))

    if target in {"all", "bilibili"}:
        result = validate_domain_cookie("bilibili.com")
        status = "[green]通过[/]" if result["ok"] else "[red]失败[/]"
        table.add_row("bilibili.com", status, result["reason"])

    if target in {"all", "zhihu"}:
        result = validate_domain_cookie("zhihu.com")
        status = "[green]通过[/]" if result["ok"] else "[red]失败[/]"
        table.add_row("zhihu.com", status, result["reason"])

    console.print(table)


@auth.command("show-paths")
def show_paths() -> None:
    """显示 API Key 与 Cookie 的配置位置。"""
    console.print("[bold]DeepSeek API Key[/]")
    console.print("  1. 推荐：Windows 用户环境变量 [cyan]DEEPSEEK_API_KEY[/]")
    console.print("  2. 或：配置文件中的 [cyan]ai.api_key[/]")
    for path in get_config_paths():
        console.print(f"     - {path.resolve()}")
    console.print("  官方文档: https://api-docs.deepseek.com/zh-cn/")
    console.print()
    console.print("[bold]Cookie 本地存储[/]")
    console.print(f"  目录: [cyan]{get_cookies_dir()}[/]")
    console.print("  同步命令: [cyan]osint auth sync-cookies --browser edge[/]")
    console.print()
    console.print("[bold]本地数据目录[/]")
    console.print(f"  [cyan]{get_data_dir()}[/]")
    console.print("  可通过环境变量 [cyan]OSINT_DATA_DIR[/] 覆盖")


@auth.command("list-domains")
def list_domains() -> None:
    """列出默认同步的 Cookie 域名。"""
    for domain in DEFAULT_DOMAINS:
        console.print(domain)


@main.command()
@click.argument("domain")
@click.option("--json", "as_json", is_flag=True, help="以 JSON 格式输出")
def domain(domain: str, as_json: bool) -> None:
    """收集域名公开信息 / Collect public domain information."""
    result = collect_domain_info(domain)

    if as_json:
        console.print_json(data=result)
        return

    console.print(f"[bold cyan]Domain:[/] {result['domain']}")
    for record in result.get("dns_records", []):
        console.print(f"  [green]{record['type']}[/] {record['value']}")


if __name__ == "__main__":
    main()
