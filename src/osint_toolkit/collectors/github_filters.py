"""GitHub 仓库过滤：排除已知 SEO/宣传垃圾库。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_BLOCKED_OWNERS = frozenset({"cirosantilli"})

# 镜像/备份仓库常用拼写变体（dictatroship、cihna-dictattorshrip 等）
_DICTATORSHIP_SLUG = re.compile(
    r"china[-_.]?dictat|cihna[-_.]?dictat|dictat[o0]?rship",
    re.I,
)

_GITHUB_REPO_PATH = re.compile(r"^/([^/]+)/([^/]+?)(?:/|$)", re.I)


def parse_github_full_name(url: str, *, full_name: str = "") -> tuple[str, str]:
    """Return (owner, repo) from full_name or github.com URL."""
    if full_name and "/" in full_name:
        owner, _, repo = full_name.partition("/")
        return owner.strip(), repo.strip()
    try:
        path = urlparse(url).path or ""
    except Exception:  # noqa: BLE001
        return "", ""
    match = _GITHUB_REPO_PATH.match(path)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def is_blocked_github_repo(url: str, *, full_name: str = "") -> bool:
    """True if repo should be dropped from search results."""
    owner, repo = parse_github_full_name(url, full_name=full_name)
    if not owner:
        return False
    if owner.lower() in _BLOCKED_OWNERS:
        return True
    slug = f"{owner}/{repo}" if repo else owner
    return bool(_DICTATORSHIP_SLUG.search(slug))
