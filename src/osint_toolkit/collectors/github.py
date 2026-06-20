"""GitHub 采集器 / GitHub search via REST API."""

from __future__ import annotations

from urllib.parse import quote

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.collectors.github_filters import is_blocked_github_repo
from osint_toolkit.collectors.serp.engine import SerpEngine, hits_to_items
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem


class GithubCollector(BaseCollector):
    name = "github"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()
        self._warnings: list[str] = []

    def consume_warnings(self) -> list[str]:
        out = list(self._warnings)
        self._warnings.clear()
        return out

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        items: list[IntelItem] = []
        api = (
            "https://api.github.com/search/repositories"
            f"?q={quote(query)}&per_page={min(limit, 30)}"
        )
        try:
            resp = await self.client.get(api, headers={"Accept": "application/vnd.github+json"})
            if resp.status_code == 200:
                payload = resp.json()
                for repo in payload.get("items") or []:
                    if not isinstance(repo, dict):
                        continue
                    url = str(repo.get("html_url") or "")
                    full_name = str(repo.get("full_name") or "")
                    if not url or is_blocked_github_repo(url, full_name=full_name):
                        continue
                    desc = str(repo.get("description") or "")
                    stars = repo.get("stargazers_count")
                    items.append(
                        IntelItem(
                            source="github",
                            type="repo",
                            url=url,
                            title=str(repo.get("full_name") or url),
                            content=desc,
                            personal={
                                "stars": stars,
                                "language": repo.get("language"),
                                "via": "github_api",
                            },
                        )
                    )
                    if len(items) >= limit:
                        break
            elif resp.status_code == 403:
                self._warnings.append("GitHub API 速率限制，将尝试 SERP 回退")
        except Exception as exc:  # noqa: BLE001
            self._warnings.append(f"GitHub API 失败: {exc}")

        if len(items) < max(3, limit // 2):
            engine = SerpEngine(client=self.client)
            hits, _ = await engine.site_search("github.com", query, limit=limit)
            for item in hits_to_items(hits, source="github"):
                if is_blocked_github_repo(item.url, full_name=str(item.title or "")):
                    continue
                if item.url not in {i.url for i in items}:
                    item.personal["via"] = "serp_fallback"
                    items.append(item)
                if len(items) >= limit:
                    break
        return items[:limit]

    async def fetch(self, url: str) -> IntelItem:
        from osint_toolkit.collectors.web import WebCollector

        item = await WebCollector(self.client).fetch(url)
        item.source = "github"
        return item
