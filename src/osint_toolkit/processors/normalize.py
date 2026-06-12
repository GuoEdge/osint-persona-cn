"""文本归一化 / Text normalization."""

from __future__ import annotations

import re

import html2text
from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    if not html.strip():
        return ""
    if "<" in html and ">" in html:
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.body_width = 0
        text = converter.handle(html)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    return html.strip()


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)
