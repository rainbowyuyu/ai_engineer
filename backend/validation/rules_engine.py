"""Load and evaluate validation rules from YAML."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backend.validation.benchmark_loader import (
    enrich_benchmark_metrics,
    filter_peers,
    load_benchmark_records,
    percentile_rank,
)
from backend.validation.geometry_metrics import GeometryMetrics, metrics_as_dict

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = _REPO_ROOT / "rules" / "validation_rules.yaml"


@dataclass
class RuleDefinition:
    id: str
    category: str
    weight: float
    source: str
    metric: str
    operator: str
    limits: dict[str, Any]
    reference: dict[str, Any]
    scoring: dict[str, Any]
    description_zh: str
    clause_ref: str | None = None
    regulation_ref: str | None = None
    unit: str | None = None


@dataclass
class RuleResult:
    id: str
    category: str
    weight: float
    source: str
    metric: str
    operator: str
    measured: float | None
    threshold: str
    score_0_100: float
    status: str
    weighted_contribution: float
    description_zh: str
    clause_ref: str | None
    regulation_ref: str | None = None
    unit: str | None = None


def load_rules(
    path: Path | None = None,
) -> tuple[list[RuleDefinition], dict[str, float], dict[str, Any]]:
    p = (path or DEFAULT_RULES).resolve()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    rules_raw = raw.get("rules") or []
    cat_weights = raw.get("category_weights") or {}
    scoring_config = dict(raw.get("scoring_config") or {})
    rules: list[RuleDefinition] = []
    for r in rules_raw:
        rules.append(
            RuleDefinition(
                id=str(r["id"]),
                category=str(r["category"]),
                weight=float(r.get("weight") or 1.0),
                source=str(r.get("source") or ""),
                metric=str(r["metric"]),
                operator=str(r["operator"]),
                limits=dict(r.get("limits") or {}),
                reference=dict(r.get("reference") or {}),
                scoring=dict(r.get("scoring") or {}),
                description_zh=str(r.get("description_zh") or r["id"]),
                clause_ref=r.get("clause_ref"),
                regulation_ref=r.get("regulation_ref"),
                unit=r.get("unit"),
            )
        )
    return rules, {str(k): float(v) for k, v in cat_weights.items()}, scoring_config


def _score_from_thresholds(score: float, scoring: dict[str, Any]) -> tuple[float, str]:
    excellent = float(scoring.get("excellent") or 90)
    good = float(scoring.get("good") or 75)
    warn = float(scoring.get("pass") or 60)
    if score >= excellent:
        return min(100.0, score), "pass"
    if score >= good:
        return score, "pass"
    if score >= warn:
        return score, "warn"
    return score, "fail"


def _eval_range(value: float | None, limits: dict[str, Any]) -> tuple[float, str]:
    if value is None:
        return 0.0, "n/a"
    lo = limits.get("min")
    hi = limits.get("max")
    target = limits.get("target")
    tol = float(limits.get("tolerance") or 0.0)
    if target is not None:
        target = float(target)
        dev = abs(value - target)
        if dev <= tol:
            return 100.0, f"target={target}±{tol}"
        span = max(tol * 3, abs(target) * 0.2, 1e-6)
        score = max(0.0, 100.0 * (1.0 - (dev - tol) / span))
        return score, f"target={target}±{tol}"
    if lo is not None and hi is not None:
        lo, hi = float(lo), float(hi)
        if lo <= value <= hi:
            return 100.0, f"[{lo}, {hi}]"
        if value < lo:
            score = max(0.0, 100.0 * (1.0 - (lo - value) / max(lo * 0.3, 1e-6)))
        else:
            score = max(0.0, 100.0 * (1.0 - (value - hi) / max(hi * 0.3, 1e-6)))
        return score, f"[{lo}, {hi}]"
    if lo is not None:
        lo = float(lo)
        if value >= lo:
            return 100.0, f">= {lo}"
        return max(0.0, 100.0 * value / lo), f">= {lo}"
    if hi is not None:
        hi = float(hi)
        if value <= hi:
            return 100.0, f"<= {hi}"
        return max(0.0, 100.0 * (1.0 - (value - hi) / max(hi * 0.5, 1e-6))), f"<= {hi}"
    return 50.0, "no limits"


def _eval_max(value: float | None, limits: dict[str, Any]) -> tuple[float, str]:
    if value is None:
        return 0.0, "n/a"
    hi = float(limits.get("max") or limits.get("target") or 0)
    if value <= hi:
        return 100.0, f"<= {hi}"
    return max(0.0, 100.0 * (1.0 - (value - hi) / max(hi * 0.5, 1e-6))), f"<= {hi}"


def _eval_min(value: float | None, limits: dict[str, Any]) -> tuple[float, str]:
    if value is None:
        return 0.0, "n/a"
    lo = float(limits.get("min") or limits.get("target") or 0)
    if value >= lo:
        return 100.0, f">= {lo}"
    return max(0.0, 100.0 * value / max(lo, 1e-6)), f">= {lo}"


def _eval_slenderness(value: float | None, limits: dict[str, Any]) -> tuple[float, str]:
    if value is None:
        return 0.0, "n/a"
    v = float(value)
    lo = float(limits.get("min") or 8)
    ideal_lo = float(limits.get("ideal_min") or 12)
    ideal_hi = float(limits.get("ideal_max") or 35)
    hi = float(limits.get("max") or 55)
    if ideal_lo <= v <= ideal_hi:
        return 100.0, f"ideal [{ideal_lo}, {ideal_hi}]"
    if lo <= v < ideal_lo:
        return 75.0 + 25.0 * (v - lo) / max(ideal_lo - lo, 1e-6), f"[{lo}, {ideal_lo})"
    if ideal_hi < v <= hi:
        return max(55.0, 100.0 - (v - ideal_hi) / max(hi - ideal_hi, 1e-6) * 45.0), f"({ideal_hi}, {hi}]"
    if v < lo:
        return max(0.0, 100.0 * v / lo), f"< {lo}"
    return max(0.0, 55.0 - (v - hi) / max(hi * 0.2, 1e-6) * 55.0), f"> {hi}"


def _eval_design_stage_ratio(
    value: float | None,
    limits: dict[str, Any],
) -> tuple[float, str]:
    """Score fleet ratios for design-stage candidates (optimistic but capped without verified mass)."""
    if value is None:
        return 0.0, "n/a"
    v = float(value)
    ref = float(limits.get("reference_ratio") or 1.0)
    hi = float(limits.get("max") or 1.15)
    cap = float(limits.get("cap_unverified") or 90.0)
    floor = float(limits.get("floor_optimistic") or 80.0)
    if v <= ref:
        bonus = min(1.0, (ref - v) / max(ref, 1e-6))
        score = min(cap, floor + bonus * (cap - floor))
        return score, f"ratio {v:.2f} ≤ {ref:.2f} (设计领先·待校核)"
    if v <= hi:
        score = max(55.0, 100.0 - (v - ref) / max(hi - ref, 1e-6) * 35.0)
        return score, f"ratio {v:.2f} in ({ref:.2f}, {hi:.2f}]"
    score = max(0.0, 55.0 - (v - hi) / max(hi * 0.2, 1e-6) * 55.0)
    return score, f"ratio {v:.2f} > {hi:.2f}"


def _eval_design_stage_mass_band(
    value: float | None,
    limits: dict[str, Any],
    metrics_dict: dict[str, float | None],
) -> tuple[float, str]:
    if value is None:
        return 0.0, "n/a"
    lo = float(limits.get("min") or 3800)
    hi = float(limits.get("max") or 9000)
    v = float(value)
    if lo <= v <= hi:
        return 100.0, f"[{lo:.0f}, {hi:.0f}]"
    if v < lo:
        conf = float(metrics_dict.get("estimation_confidence_score") or 0.62)
        ratio = v / max(lo, 1e-6)
        score = max(72.0, 68.0 + conf * 20.0 * min(ratio, 1.0))
        return score, f"< {lo:.0f} t (壳体估算·设计阶段)"
    score = max(0.0, 100.0 * (1.0 - (v - hi) / max(hi * 0.3, 1e-6)))
    return score, f"> {hi:.0f} t"


def evaluate_rule(
    rule: RuleDefinition,
    metrics: GeometryMetrics,
    metrics_dict: dict[str, float | None],
    benchmark_records: list | None = None,
) -> RuleResult:
    value = metrics_dict.get(rule.metric)
    if isinstance(value, (int, float)):
        measured: float | None = float(value)
    else:
        measured = None

    raw_score = 50.0
    threshold = "n/a"

    if rule.operator == "range":
        raw_score, threshold = _eval_range(measured, rule.limits)
    elif rule.operator == "max":
        raw_score, threshold = _eval_max(measured, rule.limits)
    elif rule.operator == "min":
        raw_score, threshold = _eval_min(measured, rule.limits)
    elif rule.operator == "percentile_rank":
        if benchmark_records is None:
            benchmark_records = load_benchmark_records()
        peers = filter_peers(
            benchmark_records,
            capacity_MW=rule.reference.get("capacity_MW"),
            peer_set=rule.reference.get("peer_set"),
        )
        sample = [
            float(r.steel_intensity)
            for r in peers
            if r.steel_intensity is not None and rule.metric == "steel_intensity_t_per_MW"
        ]
        if not sample and rule.metric == "total_steel_t":
            sample = [float(r.total_steel_t) for r in peers if r.total_steel_t is not None]
        if measured is not None and sample:
            raw_score = percentile_rank(measured, sample, lower_is_better=True)
            sample_min = min(sample)
            if float(measured) < sample_min * 0.85:
                raw_score = max(raw_score, 88.0)
                threshold = f"fleet n={len(sample)} percentile (设计领先·待校核)"
            else:
                threshold = f"fleet n={len(sample)} percentile"
        else:
            raw_score = 0.0
    elif rule.operator == "delta_vs_reference":
        if benchmark_records is None:
            benchmark_records = load_benchmark_records()
        ref_name = str(rule.reference.get("name") or "")
        ref_val = rule.limits.get("reference_value")
        if ref_val is None:
            for r in benchmark_records:
                if ref_name.lower() in r.name.lower() or ref_name in r.short_name:
                    ref_val = r.steel_intensity
                    break
        if measured is not None and ref_val is not None:
            ref_val = float(ref_val)
            delta_pct = (measured - ref_val) / ref_val * 100.0
            max_delta = float(rule.limits.get("max_delta_pct") or 15.0)
            suspicious = delta_pct < -25.0
            if delta_pct <= 0:
                if suspicious:
                    raw_score = min(92.0, 88.0 + min(4.0, (abs(delta_pct) - 25.0) * 0.06))
                else:
                    raw_score = 100.0
            elif delta_pct <= max_delta:
                raw_score = 100.0 - (delta_pct / max_delta) * 40.0
            else:
                raw_score = max(0.0, 60.0 - (delta_pct - max_delta))
            suffix = " (设计领先·待校核)" if suspicious else ""
            threshold = f"vs {ref_name} {ref_val:.1f}, Δ={delta_pct:+.1f}%{suffix}"
        else:
            raw_score = 0.0
    elif rule.operator == "target_band":
        raw_score, threshold = _eval_range(measured, rule.limits)
    elif rule.operator == "margin_below":
        if measured is None:
            raw_score = 0.0
        else:
            cap = float(rule.limits.get("cap") or rule.limits.get("max") or 300)
            margin = cap - float(measured)
            excellent = float(rule.limits.get("margin_excellent") or 50)
            good = float(rule.limits.get("margin_good") or 20)
            warn = float(rule.limits.get("margin_pass") or 0)
            capped_note = ""
            if margin >= excellent:
                raw_score = 100.0
                if margin > cap * 0.45:
                    raw_score = min(raw_score, 90.0)
                    capped_note = " (估算领先·待校核)"
            elif margin >= good:
                raw_score = 85.0 + 15.0 * (margin - good) / max(excellent - good, 1e-6)
            elif margin >= warn:
                raw_score = 65.0 + 20.0 * (margin - warn) / max(good - warn, 1e-6)
            elif float(measured) <= cap:
                raw_score = 50.0 + 15.0 * margin / max(good - warn, 1e-6)
            else:
                over = float(measured) - cap
                raw_score = max(0.0, 50.0 - over / max(cap * 0.15, 1e-6) * 50.0)
            threshold = f"cap {cap}, margin {margin:+.1f}{capped_note}"
    elif rule.operator == "design_stage_ratio":
        raw_score, threshold = _eval_design_stage_ratio(measured, rule.limits)
    elif rule.operator == "design_stage_mass_band":
        raw_score, threshold = _eval_design_stage_mass_band(measured, rule.limits, metrics_dict)
    elif rule.operator == "slenderness_tier":
        raw_score, threshold = _eval_slenderness(measured, rule.limits)

    score, status = _score_from_thresholds(raw_score, rule.scoring)
    wcontrib = score * rule.weight

    return RuleResult(
        id=rule.id,
        category=rule.category,
        weight=rule.weight,
        source=rule.source,
        metric=rule.metric,
        operator=rule.operator,
        measured=measured,
        threshold=threshold,
        score_0_100=round(score, 2),
        status=status,
        weighted_contribution=round(wcontrib, 2),
        description_zh=rule.description_zh,
        clause_ref=rule.clause_ref,
        regulation_ref=rule.regulation_ref,
        unit=rule.unit,
    )


def evaluate_all_rules(
    metrics: GeometryMetrics,
    rules_path: Path | None = None,
) -> tuple[list[RuleResult], dict[str, float], dict[str, Any]]:
    rules, cat_weights, scoring_config = load_rules(rules_path)
    md = metrics_as_dict(metrics)
    md = enrich_benchmark_metrics(
        md,
        target_power_MW=metrics.target_power_MW,
        steel_mass_t_source=metrics.steel_mass_t_source,
    )
    bench = load_benchmark_records()
    results = [evaluate_rule(r, metrics, md, bench) for r in rules]
    return results, cat_weights, scoring_config
