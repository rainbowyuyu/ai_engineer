"""Load design checklist defaults and clause index."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parents[2]
DEFAULTS_PATH = _REPO / "rules" / "design_checklist_defaults.yaml"
CLAUSE_INDEX_PATH = _REPO / "rules" / "dnv_clause_index.yaml"


@lru_cache(maxsize=1)
def load_defaults() -> dict[str, Any]:
    if not DEFAULTS_PATH.is_file():
        return {}
    return yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def load_clause_index() -> list[dict[str, Any]]:
    if not CLAUSE_INDEX_PATH.is_file():
        return []
    data = yaml.safe_load(CLAUSE_INDEX_PATH.read_text(encoding="utf-8")) or {}
    return list(data.get("clauses") or [])


def clause_summaries_for_prompt(max_items: int = 12) -> str:
    lines: list[str] = []
    for c in load_clause_index()[:max_items]:
        cid = c.get("id") or ""
        summ = c.get("summary_zh") or ""
        if cid:
            lines.append(f"- {cid}: {summ}")
    return "\n".join(lines)
