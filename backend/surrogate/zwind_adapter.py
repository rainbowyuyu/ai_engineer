"""Phase 2: Zwind dynamic response adapter (import + schema mapping).

Paper alignment: flagship Fig. 2b–e metrics live in
``third_party/zwind_newmodel/paper_fig2_metrics.json`` (Zwind / OpenSees
time-domain campaign for the 20 MW AI foundation vs TuQiang).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_COMPARISON = _REPO / "rules" / "ai_vs_tuqiang_comparison.yaml"
PAPER_FIG2_METRICS = _REPO / "third_party" / "zwind_newmodel" / "paper_fig2_metrics.json"

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


def load_paper_fig2_metrics(path: Path | None = None) -> dict[str, Any]:
    """Load canonical Fig. 2b–e numbers from the integrated Zwind newmodel bundle."""
    p = path or PAPER_FIG2_METRICS
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def envelope_from_paper_fig2(platform: str = "ai") -> dict[str, float]:
    """Map paper Fig. 2 panels to the surrogate dynamic envelope keys.

    Uses extreme DLC 6.1 pitch / mooring for limit-state screening, and
    tower 1st FA frequency for the resonance gate.
    """
    raw = load_paper_fig2_metrics()
    if not raw:
        return {}
    plat = "ai" if platform.lower() in {"ai", "a"} else "tuqiang"
    out: dict[str, float] = {}
    freq = (raw.get("fig2b") or {}).get("tower_frequencies_hz") or {}
    modes = freq.get(plat) or {}
    if "1st_fa" in modes:
        out["system_frequency_hz"] = float(modes["1st_fa"])
    extreme = raw.get("fig2d") or {}
    pitch = extreme.get("pitch_deg") or {}
    if plat in pitch:
        out["platform_pitch_deg"] = float(pitch[plat])
    loads = raw.get("fig2e") or {}
    moor = loads.get("max_mooring_tension_kn") or {}
    if plat in moor:
        out["mooring_tension_kn"] = float(moor[plat])
    return out


def import_zwind_envelope(path: Path) -> dict[str, Any]:
    """Import external Zwind envelope JSON or YAML (Phase 2a)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    # Paper Fig. 2 bundle uses nested fig2b/c/d/e blocks
    if "fig2b" in data or "fig2d" in data:
        plat = str(data.get("platform") or "ai")
        return envelope_from_paper_fig2(plat)
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
    """Load reference envelope: prefer paper Fig. 2 metrics, else comparison YAML."""
    paper = envelope_from_paper_fig2(platform)
    if paper:
        # Fill remaining keys from the economic / UC / fatigue YAML if present
        raw = load_comparison_yaml()
        for m in raw.get("metrics") or []:
            mid = m.get("id") or ""
            key = METRIC_ID_TO_TARGET.get(mid)
            if not key or key in paper:
                continue
            if mid == "system_frequency":
                continue
            val = m.get(platform)
            if val is not None:
                paper[key] = float(val)
        return paper

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
    ctx["dynamic_source"] = "zwind_paper_fig2" if PAPER_FIG2_METRICS.is_file() else "zwind_import"
    return ctx
