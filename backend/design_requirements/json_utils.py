"""Shared JSON extraction from LLM outputs."""
from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Parse first JSON object from LLM text (plain or fenced)."""
    t = (text or "").strip()
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", t, flags=re.IGNORECASE):
        b = block.strip()
        if b.startswith("{"):
            try:
                o = json.loads(b)
                return o if isinstance(o, dict) else None
            except json.JSONDecodeError:
                continue
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(t[i:])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                break
    try:
        o = json.loads(t)
        return o if isinstance(o, dict) else None
    except json.JSONDecodeError:
        return None
