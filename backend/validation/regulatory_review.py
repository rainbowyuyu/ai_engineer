"""法规五维打分：与 AI Review 相同的五项指标，按 DNV / 行业阈值与规则合成分维。

与 AI Review 的区别：
- AI：机队分位、AI/图强参考线、经济性代理（偏前瞻对标）
- 法规：DNV-ST-0437/C301/RP-0286 规则、300 t/MW 国策目标、25 年设计寿命、示范 EPC/工期上限
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.validation.review_common import (
    DIMENSION_KEYS,
    DEFAULT_LABELS_ZH,
    DEFAULT_UNITS,
    score_capacity_mw,
    score_higher_better,
    score_lower_better,
)
from backend.validation.geometry_metrics import GeometryMetrics
from backend.validation.rules_engine import RuleResult

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = _REPO_ROOT / "rules" / "validation_rules.yaml"

_STEEL_METRICS = frozenset(
    {
        "steel_intensity_t_per_MW",
        "total_steel_t",
        "intensity_ratio_vs_tuqiang",
        "total_steel_ratio_vs_fleet_median",
        "estimation_confidence_score",
    }
)


@dataclass
class RegulatoryReviewResult:
    scores: dict[str, float]
    metrics: dict[str, float | None]
    metric_sources: dict[str, str]
    weights: dict[str, float]
    labels_zh: dict[str, str]
    units: dict[str, str]
    rule_contributions: dict[str, list[str]]
    notes: list[str] = field(default_factory=list)


def load_regulatory_review_config(path: Path | None = None) -> dict[str, Any]:
    p = (path or DEFAULT_RULES).resolve()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    cfg = dict(raw.get("regulatory_review") or {})
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
        "dimension_weights": weights,
        "dimension_labels_zh": labels,
        "dimension_units": units,
        "thresholds": dict(cfg.get("thresholds") or {}),
        "sources_zh": dict(cfg.get("sources_zh") or {}),
    }


def _weighted_rules(
    rule_results: list[RuleResult],
    *,
    categories: frozenset[str] | None = None,
    metrics: frozenset[str] | None = None,
) -> tuple[float | None, list[str]]:
    picked = [
        r
        for r in rule_results
        if r.score_0_100 > 0
        and (categories is None or r.category in categories)
        and (metrics is None or r.metric in metrics)
    ]
    if not picked:
        return None, []
    wsum = sum(r.weight for r in picked) or 1.0
    score = sum(r.score_0_100 * r.weight for r in picked) / wsum
    refs = [f"{r.id}({r.regulation_ref or r.source})" for r in picked[:4]]
    return round(score, 2), refs


def _score_capacity_regulatory(metrics: GeometryMetrics, thresholds: dict[str, Any]) -> tuple[float, str]:
    target = float(thresholds.get("target_mw") or 20.0)
    tol = float(thresholds.get("tolerance_mw") or 2.0)
    score = score_capacity_mw(metrics.target_power_MW, target)
    if abs(metrics.target_power_MW - target) <= tol:
        score = max(score, 92.0)
    return round(score, 2), str(thresholds.get("basis") or "DNV-ST-0437 20 MW 设计基点")


def _score_steel_regulatory(rule_results: list[RuleResult]) -> tuple[float, list[str]]:
    score, refs = _weighted_rules(
        rule_results,
        categories=frozenset({"benchmark"}),
        metrics=_STEEL_METRICS,
    )
    if score is None:
        return 60.0, []
    return score, refs


def _score_cost_regulatory(
    metrics: GeometryMetrics,
    thresholds: dict[str, Any],
) -> tuple[float, str]:
    if metrics.unit_cost_cny_per_MW is None:
        return 55.0, "missing"
    excellent = float(thresholds.get("excellent_cny_per_MW") or 3600.0)
    pass_cap = float(thresholds.get("pass_cap_cny_per_MW") or 4800.0)
    score = score_lower_better(
        metrics.unit_cost_cny_per_MW,
        pass_cap,
        excellent_ratio=excellent / pass_cap if pass_cap > 0 else 0.75,
        pass_ratio=1.0,
    )
    return round(score, 2), str(thresholds.get("basis") or "示范工程 EPC 投资强度上限")


def _score_construction_regulatory(
    metrics: GeometryMetrics,
    thresholds: dict[str, Any],
) -> tuple[float, str]:
    if metrics.construction_years is None:
        return 55.0, "missing"
    excellent = float(thresholds.get("excellent_years") or 2.5)
    pass_cap = float(thresholds.get("pass_cap_years") or 3.5)
    score = score_lower_better(
        metrics.construction_years,
        pass_cap,
        excellent_ratio=excellent / pass_cap if pass_cap > 0 else 0.72,
        pass_ratio=1.0,
    )
    return round(score, 2), str(thresholds.get("basis") or "漂浮式示范项目管理工期惯例")


def _score_fatigue_regulatory(
    metrics: GeometryMetrics,
    rule_results: list[RuleResult],
    thresholds: dict[str, Any],
) -> tuple[float, str]:
    min_life = float(thresholds.get("min_design_years") or 25.0)
    life_score = 55.0
    if metrics.fatigue_life_years is not None:
        life_score = score_higher_better(metrics.fatigue_life_years, min_life)

    proxy_score, _ = _weighted_rules(
        rule_results,
        categories=frozenset({"detailing_fatigue_proxy"}),
    )
    if proxy_score is None:
        return round(life_score, 2), str(thresholds.get("basis") or "DNV 25 年设计寿命")

    blended = 0.55 * life_score + 0.45 * proxy_score
    return round(blended, 2), str(thresholds.get("basis") or "DNV 设计寿命 + RP-0286 疲劳细节")


def score_regulatory_review(
    metrics: GeometryMetrics,
    rule_results: list[RuleResult],
    *,
    config: dict[str, Any] | None = None,
) -> RegulatoryReviewResult:
    cfg = config or load_regulatory_review_config()
    th = cfg.get("thresholds") or {}
    sources = cfg.get("sources_zh") or {}

    scores: dict[str, float] = {}
    rule_contrib: dict[str, list[str]] = {}
    notes: list[str] = []
    metric_sources: dict[str, str] = {}

    cap_score, cap_src = _score_capacity_regulatory(metrics, th.get("capacity_mw") or {})
    scores["capacity_mw"] = cap_score
    metric_sources["capacity_mw"] = sources.get("capacity_mw") or cap_src

    steel_score, steel_refs = _score_steel_regulatory(rule_results)
    scores["steel_per_mw"] = steel_score
    rule_contrib["steel_per_mw"] = steel_refs
    metric_sources["steel_per_mw"] = sources.get("steel_per_mw") or "benchmark 规则合成分"

    cost_score, cost_src = _score_cost_regulatory(metrics, th.get("unit_cost") or {})
    scores["unit_cost"] = cost_score
    metric_sources["unit_cost"] = sources.get("unit_cost") or cost_src

    const_score, const_src = _score_construction_regulatory(metrics, th.get("construction_years") or {})
    scores["construction_years"] = const_score
    metric_sources["construction_years"] = sources.get("construction_years") or const_src

    fatigue_score, fatigue_src = _score_fatigue_regulatory(
        metrics,
        rule_results,
        th.get("fatigue_life") or {},
    )
    scores["fatigue_life"] = fatigue_score
    metric_sources["fatigue_life"] = sources.get("fatigue_life") or fatigue_src

    metric_values = {
        "capacity_mw": metrics.target_power_MW,
        "steel_per_mw": metrics.steel_intensity_t_per_MW,
        "unit_cost": metrics.unit_cost_cny_per_MW,
        "construction_years": metrics.construction_years,
        "fatigue_life": metrics.fatigue_life_years,
    }

    return RegulatoryReviewResult(
        scores=scores,
        metrics=metric_values,
        metric_sources=metric_sources,
        weights=cfg["dimension_weights"],
        labels_zh=cfg["dimension_labels_zh"],
        units=cfg["dimension_units"],
        rule_contributions=rule_contrib,
        notes=notes,
    )


def regulatory_review_overall(result: RegulatoryReviewResult) -> float:
    return round(
        sum(result.scores[k] * result.weights.get(k, 0.0) for k in DIMENSION_KEYS),
        2,
    )
