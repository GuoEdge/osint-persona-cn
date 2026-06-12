"""命令行入口 / CLI entry point."""

import click
from rich.console import Console

from osint_toolkit.collectors.domain import collect_domain_info

console = Console()


@click.group()
@click.version_option()
def main() -> None:
    """OSINT Toolkit — 开源信息情报工具"""


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
