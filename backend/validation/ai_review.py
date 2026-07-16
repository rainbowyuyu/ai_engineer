"""AI Review 五维打分：单机兆瓦数、单位兆瓦用钢量、单位造价、施工年限、疲劳寿命。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.validation.benchmark_loader import load_benchmark_records, percentile_rank
from backend.validation.geometry_metrics import GeometryMetrics
from backend.validation.review_common import (
    DIMENSION_KEYS,
    DEFAULT_LABELS_ZH,
    DEFAULT_UNITS,
    innovation_bonus_higher,
    innovation_bonus_lower,
    score_capacity_mw,
    score_higher_better,
    score_lower_better,
    with_innovation_bonus,
)
from backend.validation.rules_engine import RuleResult

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = _REPO_ROOT / "rules" / "validation_rules.yaml"

_DEFAULT_BLEND = {
    "steel_per_mw": 0.52,
    "unit_cost": 0.58,
    "construction_years": 0.48,
    "fatigue_life": 0.42,
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
    align = dict(cfg.get("regulatory_alignment") or {})
    blend_raw = dict(align.get("blend_weights") or {})
    blend_weights = {k: float(blend_raw.get(k, _DEFAULT_BLEND[k])) for k in _DEFAULT_BLEND}
    return {
        "primary": bool(cfg.get("primary", True)),
        "dimension_weights": weights,
        "dimension_labels_zh": labels,
        "dimension_units": units,
        "references": dict(cfg.get("references") or {}),
        "cost_proxy": dict(cfg.get("cost_proxy") or {}),
        "construction_proxy": dict(cfg.get("construction_proxy") or {}),
        "fatigue_proxy": dict(cfg.get("fatigue_proxy") or {}),
        "regulatory_alignment": {
            "enabled": bool(align.get("enabled", True)),
            "innovation_bonus_max": float(align.get("innovation_bonus_max") or 6.0),
            "blend_weights": blend_weights,
        },
    }


def _blend_reg_ai(
    reg_score: float,
    ai_score: float,
    *,
    reg_weight: float,
    bonus: float = 0.0,
) -> float:
    w = max(0.0, min(1.0, reg_weight))
    blended = w * reg_score + (1.0 - w) * ai_score
    return with_innovation_bonus(blended, bonus)


def _score_steel_ai_native(
    value: float,
    rule_results: list[RuleResult],
    *,
    target_power_mw: float,
) -> float:
    """AI-native: fleet percentile with rule fallback (not full regulatory composite)."""
    bench = load_benchmark_records()
    peers = [r for r in bench if r.capacity_mw and abs(r.capacity_mw - target_power_mw) < 0.5 and r.steel_intensity]
    sample = [float(r.steel_intensity) for r in peers]
    if sample:
        return round(percentile_rank(value, sample, lower_is_better=True), 2)
    steel_rules = [r for r in rule_results if r.metric == "steel_intensity_t_per_MW" and r.score_0_100 > 0]
    if steel_rules:
        wsum = sum(r.weight for r in steel_rules) or 1.0
        return round(sum(r.score_0_100 * r.weight for r in steel_rules) / wsum, 2)
    return 65.0


def _score_steel_per_mw(
    value: float,
    rule_results: list[RuleResult],
    *,
    target_power_mw: float,
    align_regulatory: bool,
    proposed_ref: float,
    max_bonus: float,
    reg_weight: float,
) -> float:
    ai_native = _score_steel_ai_native(value, rule_results, target_power_mw=target_power_mw)
    if not align_regulatory:
        return ai_native

    from backend.validation.regulatory_review import _score_steel_regulatory

    reg_score, _ = _score_steel_regulatory(rule_results)
    return _blend_reg_ai(
        reg_score,
        ai_native,
        reg_weight=reg_weight,
        bonus=innovation_bonus_lower(value, proposed_ref, max_bonus=max_bonus),
    )


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
    align_cfg = cfg.get("regulatory_alignment") or {}
    align_reg = bool(align_cfg.get("enabled", True))
    max_bonus = float(align_cfg.get("innovation_bonus_max") or 6.0)
    blend_weights: dict[str, float] = align_cfg.get("blend_weights") or _DEFAULT_BLEND

    scores: dict[str, float] = {}
    notes: list[str] = []
    if align_reg:
        notes.append(
            "AI Review = 法规锚定分 × 混合权重 + AI 原生分（机队分位/本方案目标）× (1−权重)；"
            "优于本方案目标时叠加创新奖励"
        )

    scores["capacity_mw"] = round(score_capacity_mw(metrics.target_power_MW, target_mw), 2)

    scores["steel_per_mw"] = _score_steel_per_mw(
        metrics.steel_intensity_t_per_MW,
        rule_results,
        target_power_mw=metrics.target_power_MW,
        align_regulatory=align_reg,
        proposed_ref=float(proposed_ref.get("steel_intensity_t_per_MW") or 255.5),
        max_bonus=max_bonus,
        reg_weight=float(blend_weights.get("steel_per_mw", 0.52)),
    )

    if metrics.unit_cost_cny_per_MW is not None:
        prop = float(proposed_ref.get("unit_cost_cny_per_MW") or 2500.0)
        ai_native = round(score_lower_better(metrics.unit_cost_cny_per_MW, prop), 2)
        if align_reg:
            from backend.validation.regulatory_review import _score_cost_regulatory, load_regulatory_review_config

            reg_th = load_regulatory_review_config().get("thresholds") or {}
            reg_score, _ = _score_cost_regulatory(metrics, reg_th.get("unit_cost") or {})
            scores["unit_cost"] = _blend_reg_ai(
                reg_score,
                ai_native,
                reg_weight=float(blend_weights.get("unit_cost", 0.58)),
                bonus=innovation_bonus_lower(metrics.unit_cost_cny_per_MW, prop, max_bonus=max_bonus),
            )
        else:
            scores["unit_cost"] = ai_native
    else:
        scores["unit_cost"] = 55.0
        notes.append("单位造价缺失，使用保守基础分")

    if metrics.construction_years is not None:
        prop = float(proposed_ref.get("construction_years") or 2.8)
        ai_native = round(score_lower_better(metrics.construction_years, prop), 2)
        if align_reg:
            from backend.validation.regulatory_review import _score_construction_regulatory, load_regulatory_review_config

            reg_th = load_regulatory_review_config().get("thresholds") or {}
            reg_score, _ = _score_construction_regulatory(metrics, reg_th.get("construction_years") or {})
            scores["construction_years"] = _blend_reg_ai(
                reg_score,
                ai_native,
                reg_weight=float(blend_weights.get("construction_years", 0.48)),
                bonus=innovation_bonus_lower(metrics.construction_years, prop, max_bonus=max_bonus),
            )
        else:
            scores["construction_years"] = ai_native
    else:
        scores["construction_years"] = 55.0
        notes.append("施工年限缺失，使用保守基础分")

    if metrics.fatigue_life_years is not None:
        prop = float(proposed_ref.get("fatigue_life_years") or 25.0)
        ai_native = round(score_higher_better(metrics.fatigue_life_years, prop), 2)
        if align_reg:
            from backend.validation.regulatory_review import _score_fatigue_regulatory, load_regulatory_review_config

            reg_th = load_regulatory_review_config().get("thresholds") or {}
            reg_score, _ = _score_fatigue_regulatory(metrics, rule_results, reg_th.get("fatigue_life") or {})
            scores["fatigue_life"] = _blend_reg_ai(
                reg_score,
                ai_native,
                reg_weight=float(blend_weights.get("fatigue_life", 0.42)),
                bonus=innovation_bonus_higher(metrics.fatigue_life_years, prop, max_bonus=max_bonus),
            )
        else:
            scores["fatigue_life"] = ai_native
    else:
        scores["fatigue_life"] = 55.0
        notes.append("疲劳寿命缺失，使用保守基础分")

    weights = cfg["dimension_weights"]

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
