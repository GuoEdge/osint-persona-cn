"""行为解读 / Behavior insights with cache."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.persona.behavior_signals import load_ranked_behavior_samples
from osint_toolkit.persona.context import maybe_load_persona_context

_CACHE_FILE = "behavior_insights.json"
_TTL = timedelta(hours=1)


def _cache_path() -> Path:
    path = get_data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path / _CACHE_FILE


def _read_cache() -> dict[str, Any] | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(str(data.get("generated_at", "")).replace("Z", "+00:00"))
        if datetime.now(UTC) - generated < _TTL:
            return data
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    return None


def _write_cache(insights: str) -> None:
    payload = {"generated_at": datetime.now(UTC).isoformat(), "insights": insights}
    _cache_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_behavior_insights(*, refresh: bool = False, no_ai: bool = False) -> dict[str, Any]:
    if not refresh:
        cached = _read_cache()
        if cached:
            return {"insights": cached.get("insights", ""), "cached": True, "generated_at": cached.get("generated_at")}

    samples = load_ranked_behavior_samples(sample_limit=30)
    persona_ctx = maybe_load_persona_context()

    if no_ai or not is_step_enabled("report", no_ai=no_ai):
        lines = ["近期高权重行为："]
        for s in samples[:10]:
            lines.append(f"- [{s.get('event_type')}] {s.get('title') or s.get('url')}")
        insights = "\n".join(lines)
        return {"insights": insights, "cached": False}

    client = DeepSeekClient()
    insights = client.chat(
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(
                    task="行为解读",
                    persona_brief=persona_ctx.brief if persona_ctx else "",
                ),
            },
            {
                "role": "user",
                "content": (
                    "用 3-5 句话总结用户近期兴趣与浏览模式，指出 2 个可能的研究方向。\n"
                    f"行为样本:\n{json.dumps(samples, ensure_ascii=False)[:8000]}"
                ),
            },
        ]
    )
    _write_cache(insights)
    return {"insights": insights, "cached": False, "generated_at": datetime.now(UTC).isoformat()}
