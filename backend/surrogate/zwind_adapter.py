"""Phase 2: Zwind dynamic response adapter (import + schema mapping)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_COMPARISON = _REPO / "rules" / "ai_vs_tuqiang_comparison.yaml"

# Maps ai_vs_tuqiang metric ids to internal dynamic target keys
METRIC_ID_TO_TARGET = {
    "system_frequency": "system_frequency_hz",
    "platform_motion": "platform_pitch_deg",
    "structural_strength": "structural_uc_max",
    "component_fatigue": "fatigue_damage",
    "mooring_tension": "mooring_tension_kn",
}


def load_comparison_yaml(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_COMPARISON
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def import_zwind_envelope(path: Path) -> dict[str, Any]:
    """Import external Zwind envelope JSON or YAML (Phase 2a)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    return normalize_dynamic_envelope(data)


def normalize_dynamic_envelope(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize various envelope formats to standard dynamic target dict."""
    out: dict[str, float] = {}
    if "metrics" in data and isinstance(data["metrics"], list):
        for m in data["metrics"]:
            mid = m.get("id") or ""
            key = METRIC_ID_TO_TARGET.get(mid)
            if not key:
                continue
            val = m.get("ai") if "ai" in m else m.get("value")
            if val is not None:
                out[key] = float(val)
    else:
        for src, tgt in METRIC_ID_TO_TARGET.items():
            if src in data:
                out[tgt] = float(data[src])
            elif tgt in data:
                out[tgt] = float(data[tgt])
    if "modes" in data:
        modes = data["modes"]
        if modes and isinstance(modes, list):
            out["system_frequency_hz"] = float(modes[0].get("hz", modes[0]))
    return out


def envelope_from_comparison(platform: str = "ai") -> dict[str, float]:
    """Load reference envelope from ai_vs_tuqiang_comparison.yaml."""
    raw = load_comparison_yaml()
    out: dict[str, float] = {}
    for m in raw.get("metrics") or []:
        mid = m.get("id") or ""
        key = METRIC_ID_TO_TARGET.get(mid)
        if not key:
            continue
        if mid == "system_frequency":
            modes = m.get(f"{platform}_modes") or []
            if modes:
                out[key] = float(modes[0].get("hz", 0.42))
            continue
        val = m.get(platform)
        if val is not None:
            out[key] = float(val)
    return out


def attach_dynamic_to_prediction(
    static_context: dict[str, Any],
    dynamic: dict[str, float],
) -> dict[str, Any]:
    """Merge dynamic envelope into surrogate_context for reporting."""
    ctx = dict(static_context)
    ctx["dynamic_envelope"] = dynamic
    ctx["dynamic_source"] = "zwind_import"
    return ctx
