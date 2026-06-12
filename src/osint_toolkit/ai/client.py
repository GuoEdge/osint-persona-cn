"""DeepSeek API 客户端（OpenAI 兼容）/ DeepSeek API client."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from osint_toolkit.utils.config import get_ai_config

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


@dataclass
class AIClientConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = 120.0


class DeepSeekClient:
    """DeepSeek Chat Completions 封装。"""

    def __init__(self, config: AIClientConfig | None = None) -> None:
        self.config = config or load_ai_client_config()
        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> str:
        """发送对话请求并返回 assistant 文本内容。"""
        response = self._client.chat.completions.create(
            model=model or self.config.model,
            messages=messages,
            stream=stream,
            **kwargs,
        )
        if stream:
            raise ValueError("stream=True 时请使用 chat_stream()")
        content = response.choices[0].message.content
        return content or ""

    def test_connection(self) -> dict[str, Any]:
        """最小请求，用于验证 API Key 与连通性。"""
        content = self.chat(
            messages=[
                {"role": "system", "content": "Reply with exactly: ok"},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=8,
        )
        return {
            "ok": "ok" in content.lower(),
            "model": self.config.model,
            "base_url": self.config.base_url,
            "reply": content.strip(),
        }


def resolve_api_key(explicit: str | None = None) -> str:
    """从参数、配置或环境变量解析 API Key。"""
    if explicit:
        return explicit
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key:
        return env_key
    ai_cfg = get_ai_config()
    key = ai_cfg.get("api_key")
    if key:
        return str(key)
    raise ValueError(
        "未找到 DeepSeek API Key。请设置环境变量 DEEPSEEK_API_KEY，"
        "或在 config/config.yaml 的 ai.api_key 中配置。"
    )


def load_ai_client_config() -> AIClientConfig:
    ai_cfg = get_ai_config()
    return AIClientConfig(
        api_key=resolve_api_key(),
        base_url=str(ai_cfg.get("base_url", DEFAULT_BASE_URL)),
        model=str(ai_cfg.get("model", DEFAULT_MODEL)),
        timeout=float(ai_cfg.get("timeout", 120)),
    )
