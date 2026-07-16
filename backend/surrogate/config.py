"""Load surrogate_config.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = _REPO / "rules" / "surrogate_config.yaml"


@lru_cache(maxsize=1)
def load_surrogate_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if not cfg_path.is_file():
        return {}
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


def model_bundle_dir(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_surrogate_config()
    rel = str(cfg.get("model_dir") or "runs/_surrogate_models")
    p = Path(rel)
    if not p.is_absolute():
        p = _REPO / p
    return p.resolve()


def feature_keys(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_surrogate_config()
    return list(cfg.get("features") or [])


def static_target_keys(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_surrogate_config()
    return list(cfg.get("static_targets") or [])
