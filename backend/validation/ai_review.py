"""AI Review 五维打分：单机兆瓦数、单位兆瓦用钢量、单位造价、施工年限、疲劳寿命。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.validation.benchmark_loader import load_benchmark_records, percentile_rank
from backend.validation.geometry_metrics import GeometryMetrics
from backend.validation.rules_engine import RuleResult

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = _REPO_ROOT / "rules" / "validation_rules.yaml"

DIMENSION_KEYS = (
    "capacity_mw",
    "steel_per_mw",
    "unit_cost",
    "construction_years",
    "fatigue_life",
)

DEFAULT_LABELS_ZH = {
    "capacity_mw": "单机兆瓦数",
    "steel_per_mw": "单位兆瓦用钢量",
    "unit_cost": "单位造价",
    "construction_years": "施工年限",
    "fatigue_life": "疲劳寿命",
}

DEFAULT_UNITS = {
    "capacity_mw": "MW",
    "steel_per_mw": "t/MW",
    "unit_cost": "万元/MW",
    "construction_years": "年",
    "fatigue_life": "年",
}


@dataclass
class AiReviewResult:
    scores: dict[str, float]
    metrics: dict[str, float | None]
    metric_sources: dict[str, str]
    weights: dict[str, float]
    labels_zh: dict[str, str]
    units: dict[str, str]
    references: dict[str, Any]
    notes: list[str] = field(default_factory=list)


def load_ai_review_config(path: Path | None = None) -> dict[str, Any]:
    p = (path or DEFAULT_RULES).resolve()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    cfg = dict(raw.get("ai_review") or {})
    weights = dict(cfg.get("dimension_weights") or {})
    if not weights:
        weights = {
            "capacity_mw": 0.15,
            "steel_per_mw": 0.30,
            "unit_cost": 0.25,
            "construction_years": 0.15,
            "fatigue_life": 0.15,
        }
    wsum = sum(float(weights.get(k, 0)) for k in DIMENSION_KEYS) or 1.0
    weights = {k: float(weights.get(k, 0)) / wsum for k in DIMENSION_KEYS}
    labels = {**DEFAULT_LABELS_ZH, **(cfg.get("dimension_labels_zh") or {})}
    units = {**DEFAULT_UNITS, **(cfg.get("dimension_units") or {})}
    return {
        "primary": bool(cfg.get("primary", True)),
        "dimension_weights": weights,
        "dimension_labels_zh": labels,
        "dimension_units": units,
        "references": dict(cfg.get("references") or {}),
        "cost_proxy": dict(cfg.get("cost_proxy") or {}),
        "construction_proxy": dict(cfg.get("construction_proxy") or {}),
        "fatigue_proxy": dict(cfg.get("fatigue_proxy") or {}),
    }


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _score_capacity_mw(value: float, target: float) -> float:
    delta = abs(value - target)
    if delta <= 0.5:
        return 98.0
    if delta <= 2.0:
        return _clamp(95.0 - (delta - 0.5) * 12.0, 72.0, 98.0)
    return _clamp(72.0 - (delta - 2.0) * 8.0, 45.0, 72.0)


def _score_steel_per_mw(
    value: float,
    rule_results: list[RuleResult],
    *,
    target_power_mw: float,
) -> float:
    steel_rules = [r for r in rule_results if r.metric == "steel_intensity_t_per_MW" and r.score_0_100 > 0]
    if steel_rules:
        wsum = sum(r.weight for r in steel_rules) or 1.0
        return round(sum(r.score_0_100 * r.weight for r in steel_rules) / wsum, 2)
    bench = load_benchmark_records()
    peers = [r for r in bench if r.capacity_mw and abs(r.capacity_mw - target_power_mw) < 0.5 and r.steel_intensity]
    sample = [float(r.steel_intensity) for r in peers]
    if sample:
        return round(percentile_rank(value, sample, lower_is_better=True), 2)
    return 65.0


def _score_lower_better(value: float, ref: float, *, excellent_ratio: float = 1.0, pass_ratio: float = 1.18) -> float:
    if ref <= 0:
        return 60.0
    ratio = value / ref
    if ratio <= excellent_ratio:
        return 98.0
    if ratio <= 1.0:
        return _clamp(98.0 - (ratio - excellent_ratio) / max(1.0 - excellent_ratio, 1e-9) * 8.0, 90.0, 98.0)
    if ratio <= pass_ratio:
        return _clamp(90.0 - (ratio - 1.0) / max(pass_ratio - 1.0, 1e-9) * 30.0, 60.0, 90.0)
    return _clamp(60.0 - (ratio - pass_ratio) * 80.0, 25.0, 60.0)


def _score_higher_better(value: float, ref: float, *, pass_ratio: float = 0.88) -> float:
    if ref <= 0:
        return 60.0
    ratio = value / ref
    if ratio >= 1.0:
        return 98.0
    if ratio >= pass_ratio:
        return _clamp(60.0 + (ratio - pass_ratio) / max(1.0 - pass_ratio, 1e-9) * 38.0, 60.0, 98.0)
    return _clamp(40.0 + (ratio / pass_ratio) * 20.0, 25.0, 60.0)


def score_ai_review(
    metrics: GeometryMetrics,
    rule_results: list[RuleResult],
    *,
    config: dict[str, Any] | None = None,
) -> AiReviewResult:
    cfg = config or load_ai_review_config()
    refs = cfg.get("references") or {}
    proposed_ref = dict(refs.get("proposed") or refs.get("ai") or {})
    target_mw = float(refs.get("target_capacity_mw") or 20.0)

    scores: dict[str, float] = {}
    notes: list[str] = []

    scores["capacity_mw"] = round(_score_capacity_mw(metrics.target_power_MW, target_mw), 2)

    scores["steel_per_mw"] = _score_steel_per_mw(
        metrics.steel_intensity_t_per_MW,
        rule_results,
        target_power_mw=metrics.target_power_MW,
    )

    if metrics.unit_cost_cny_per_MW is not None:
        ref_cost = float(proposed_ref.get("unit_cost_cny_per_MW") or 2500.0)
        scores["unit_cost"] = round(_score_lower_better(metrics.unit_cost_cny_per_MW, ref_cost), 2)
    else:
        scores["unit_cost"] = 55.0
        notes.append("单位造价缺失，使用保守基础分")

    if metrics.construction_years is not None:
        ref_years = float(proposed_ref.get("construction_years") or 2.8)
        scores["construction_years"] = round(_score_lower_better(metrics.construction_years, ref_years), 2)
    else:
        scores["construction_years"] = 55.0
        notes.append("施工年限缺失，使用保守基础分")

    if metrics.fatigue_life_years is not None:
        ref_life = float(proposed_ref.get("fatigue_life_years") or 25.0)
        scores["fatigue_life"] = round(_score_higher_better(metrics.fatigue_life_years, ref_life), 2)
    else:
        scores["fatigue_life"] = 55.0
        notes.append("疲劳寿命缺失，使用保守基础分")

    weights = cfg["dimension_weights"]
    overall = sum(scores[k] * weights.get(k, 0.0) for k in DIMENSION_KEYS)

    metric_values = {
        "capacity_mw": metrics.target_power_MW,
        "steel_per_mw": metrics.steel_intensity_t_per_MW,
        "unit_cost": metrics.unit_cost_cny_per_MW,
        "construction_years": metrics.construction_years,
        "fatigue_life": metrics.fatigue_life_years,
    }
    metric_sources = {
        "capacity_mw": "optimization_info.target_power_MW",
        "steel_per_mw": metrics.steel_mass_t_source,
        "unit_cost": metrics.unit_cost_source,
        "construction_years": metrics.construction_years_source,
        "fatigue_life": metrics.fatigue_life_source,
    }

    return AiReviewResult(
        scores=scores,
        metrics=metric_values,
        metric_sources=metric_sources,
        weights=weights,
        labels_zh=cfg["dimension_labels_zh"],
        units=cfg["dimension_units"],
        references=refs,
        notes=notes,
    )


def ai_review_overall(ai: AiReviewResult) -> float:
    return round(sum(ai.scores[k] * ai.weights.get(k, 0.0) for k in DIMENSION_KEYS), 2)
