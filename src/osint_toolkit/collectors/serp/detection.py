"""SERP 阻断检测 / Block and CAPTCHA detection."""

from __future__ import annotations

import re

_BLOCK_PATTERNS = re.compile(
    r"captcha|人机验证|Please verify|Just a moment|访问过于频繁|412|"
    r"请输入验证码|网络不给力|security\.baidu|unusual traffic|"
    r"confirm you're not a robot|异常流量|"
    r"duckduckgo\.com/y\.js|anomaly-modal|sogou.*验证码",
    re.I,
)


def is_blocked_response(text: str, *, status_code: int = 200) -> bool:
    if status_code in {403, 412, 429, 503}:
        return True
    if not text:
        return False
    sample = text[:8000]
    return bool(_BLOCK_PATTERNS.search(sample))
