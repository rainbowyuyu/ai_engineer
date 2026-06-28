"""Aggregate rule scores into dimension and overall grades."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.validation.benchmark_loader import find_reference, load_benchmark_records, percentile_rank
from backend.validation.geometry_metrics import GeometryMetrics
from backend.validation.rules_engine import RuleResult, evaluate_all_rules


@dataclass
class ValidationScore:
    overall_score: float
    grade: str
    category_scores: dict[str, float]
    rule_results: list[RuleResult]
    metrics: dict[str, Any]
    benchmark_context: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    calibration_notes: list[str] = field(default_factory=list)
    scoring_config: dict[str, Any] = field(default_factory=dict)


def _grade(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def _apply_overall_calibration(
    overall: float,
    metrics: GeometryMetrics,
    scoring_config: dict[str, Any],
) -> tuple[float, list[str]]:
    notes: list[str] = []
    source = metrics.steel_mass_t_source
    if source == "validation_overrides.steel_mass_t":
        return overall, notes

    if source == "shell_surface_model":
        cap = float(scoring_config.get("max_overall_shell_estimate") or 92.0)
        if overall > cap:
            notes.append(
                str(
                    scoring_config.get("shell_estimate_note_zh")
                    or f"壳体估算未校核，综合分上限 {cap:.0f}"
                )
            )
            overall = cap
    elif source == "volume_proxy":
        cap = float(scoring_config.get("max_overall_volume_proxy") or 96.0)
        if overall > cap:
            notes.append(f"体积代理估算，综合分上限 {cap:.0f}")
            overall = cap

    return overall, notes


def score_design(
    metrics: GeometryMetrics,
    *,
    rules_path=None,
) -> ValidationScore:
    rule_results, cat_weights, scoring_config = evaluate_all_rules(metrics, rules_path)

    by_cat: dict[str, list[RuleResult]] = {}
    for rr in rule_results:
        by_cat.setdefault(rr.category, []).append(rr)

    category_scores: dict[str, float] = {}
    for cat, items in by_cat.items():
        wsum = sum(r.weight for r in items) or 1.0
        category_scores[cat] = round(sum(r.score_0_100 * r.weight for r in items) / wsum, 2)

    default_weights = {
        "benchmark": 0.40,
        "stability_watertight": 0.25,
        "structural_layout": 0.25,
        "detailing_fatigue_proxy": 0.10,
    }
    weights = {**default_weights, **cat_weights}
    w_total = sum(weights.get(c, 0.0) for c in category_scores) or 1.0
    overall = sum(category_scores[c] * weights.get(c, 0.0) for c in category_scores) / w_total

    overall, calibration_notes = _apply_overall_calibration(overall, metrics, scoring_config)

    bench = load_benchmark_records()
    peers_20 = [r for r in bench if r.capacity_mw and abs(r.capacity_mw - metrics.target_power_MW) < 0.5]
    sample_si = [float(r.steel_intensity) for r in peers_20 if r.steel_intensity is not None]
    tuqiang = find_reference(bench, "Tuqiang", "图强")
    ai_ref = find_reference(bench, "AI")

    benchmark_context: dict[str, Any] = {
        "percentile_vs_fleet_20mw": round(
            percentile_rank(metrics.steel_intensity_t_per_MW, sample_si, lower_is_better=True),
            1,
        )
        if sample_si
        else None,
        "fleet_median_intensity_20mw": round(sorted(sample_si)[len(sample_si) // 2], 1) if sample_si else None,
        "delta_vs_tuqiang_pct": round(
            (metrics.steel_intensity_t_per_MW - tuqiang.steel_intensity) / tuqiang.steel_intensity * 100.0,
            1,
        )
        if tuqiang and tuqiang.steel_intensity
        else None,
        "delta_vs_ai_pct": round(
            (metrics.steel_intensity_t_per_MW - ai_ref.steel_intensity) / ai_ref.steel_intensity * 100.0,
            1,
        )
        if ai_ref and ai_ref.steel_intensity
        else None,
        "target_line_300_t_per_MW": 300.0,
        "steel_mass_t_source": metrics.steel_mass_t_source,
        "estimation_confidence_score": {
            "validation_overrides.steel_mass_t": 1.0,
            "shell_surface_model": 0.62,
            "volume_proxy": 0.72,
            "missing_geometry": 0.0,
        }.get(metrics.steel_mass_t_source, 0.5),
    }

    from backend.validation.geometry_metrics import metrics_as_dict

    assumptions = list(metrics.assumptions)
    if calibration_notes:
        assumptions.extend(calibration_notes)

    return ValidationScore(
        overall_score=round(overall, 2),
        grade=_grade(overall),
        category_scores=category_scores,
        rule_results=rule_results,
        metrics={
            **metrics_as_dict(metrics),
            "steel_mass_t_source": metrics.steel_mass_t_source,
        },
        benchmark_context=benchmark_context,
        assumptions=assumptions,
        calibration_notes=calibration_notes,
        scoring_config=scoring_config,
    )
