"""DeepSeek API 客户端（OpenAI 兼容）/ DeepSeek API client."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from osint_toolkit.utils.config import get_ai_config

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


def _default_extra_body(model: str) -> dict[str, Any] | None:
    """V4 默认 thinking 会占满 max_tokens，导致 content 为空；OSINT 任务用非 thinking。"""
    if model.startswith("deepseek-v4") or model in {"deepseek-chat", "deepseek-reasoner"}:
        return {"thinking": {"type": "disabled"}}
    return None


def _merge_extra_body(model: str, extra_body: dict[str, Any] | None) -> dict[str, Any] | None:
    default = _default_extra_body(model)
    if not default:
        return extra_body
    if not extra_body:
        return default
    merged = dict(default)
    merged.update(extra_body)
    return merged


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
        model = model or self.config.model
        extra_body = _merge_extra_body(model, kwargs.pop("extra_body", None))
        if extra_body is not None:
            kwargs["extra_body"] = extra_body
        response = self._client.chat.completions.create(
            model=model,
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
            max_tokens=32,
        )
        text = content.strip()
        return {
            "ok": bool(text),
            "model": self.config.model,
            "base_url": self.config.base_url,
            "reply": text,
        }


def resolve_api_key(explicit: str | None = None) -> str:
    """从参数、环境变量或 ~/.osint/config.yaml 解析 API Key。"""
    from osint_toolkit.utils.secrets import resolve_secret

    return resolve_secret("deepseek", explicit=explicit)


def load_ai_client_config() -> AIClientConfig:
    ai_cfg = get_ai_config()
    return AIClientConfig(
        api_key=resolve_api_key(),
        base_url=str(ai_cfg.get("base_url", DEFAULT_BASE_URL)),
        model=str(ai_cfg.get("model", DEFAULT_MODEL)),
        timeout=float(ai_cfg.get("timeout", 120)),
    )
