"""Load replan thresholds τ from YAML."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parents[2]
THRESHOLDS_PATH = _REPO / "rules" / "replan_thresholds.yaml"


@lru_cache(maxsize=1)
def load_thresholds() -> dict[str, Any]:
    if not THRESHOLDS_PATH.is_file():
        return {}
    data = yaml.safe_load(THRESHOLDS_PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def clear_thresholds_cache() -> None:
    load_thresholds.cache_clear()
