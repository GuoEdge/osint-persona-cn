"""Parse JSON array from LLM output."""

from __future__ import annotations

import json
import re


def parse_json_array(text: str) -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass
    block = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if block:
        try:
            parsed = json.loads(block.group(1))
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass
    return []


def parse_json_object(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if block:
        try:
            parsed = json.loads(block.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}
