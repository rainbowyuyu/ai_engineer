"""Score fleet benchmark projects on the five AI Review dimensions."""
from __future__ import annotations

from dataclasses import dataclass

from backend.validation.ai_review import (
    DIMENSION_KEYS,
    ai_review_overall,
    load_ai_review_config,
    score_ai_review,
)
from backend.validation.benchmark_loader import BenchmarkRecord, load_benchmark_records
from backend.validation.geometry_metrics import GeometryMetrics
from backend.validation.regulatory_review import (
    regulatory_review_overall,
    score_regulatory_review,
)
from backend.validation.scorer import score_design


@dataclass
class FleetReviewPoint:
    name: str
    short_name: str
    year: int | None
    year_status: str
    region: str
    scores: dict[str, float]
    metrics: dict[str, float | None]
    overall: float
    regulatory_overall: float
    regulatory_scores: dict[str, float]


def metrics_from_benchmark(record: BenchmarkRecord) -> GeometryMetrics:
    """Build geometry metrics from fleet benchmark row — no proxy fill for missing public data."""
    cap = float(record.capacity_mw or 20.0)
    si = float(record.steel_intensity) if record.steel_intensity is not None else 300.0
    total = float(record.total_steel_t) if record.total_steel_t is not None else si * cap

    unit_cost = float(record.unit_cost_cny_per_MW) if record.unit_cost_cny_per_MW is not None else None
    cost_src = record.metrics_source or "fleet_reference"
    construction = float(record.construction_years) if record.construction_years is not None else None
    const_src = record.metrics_source or "fleet_reference"
    fatigue = float(record.fatigue_life_years) if record.fatigue_life_years is not None else None
    fatigue_src = record.metrics_source or "fleet_reference"

    notes = [f"机队基准：{record.short_name}"]
    notes.extend(record.metrics_notes)

    wall = 0.06
    dt = 3.5 / wall if wall > 0 else 80.0

    return GeometryMetrics(
        target_power_MW=cap,
        draft_m=12.0,
        wall_thickness_m=wall,
        steel_density_kgpm3=7850.0,
        assembly_volume_m3=None,
        bbox_z_m=80.0,
        bbox_xy_span_m=45.0,
        leg_mean_diameter_m=3.5,
        leg_min_diameter_m=3.0,
        leg_max_diameter_m=4.0,
        leg_mean_length_m=55.0,
        leg_slenderness_L_over_D=15.0,
        leg_diameter_uniformity_pct=12.0,
        leg_taper_ratio=1.25,
        leg_mean_spacing_m=28.0,
        leg_hub_spacing_mean_m=26.0,
        beso3_column_spacing_m=28.0,
        design_domain_span_m=30.0,
        leg_layout_angle_deg_std=5.0,
        top_plate_diameter_m=12.0,
        top_plate_thickness_m=0.8,
        plate_to_leg_diameter_ratio=3.4,
        dt_ratio=dt,
        hub_elevation_m=30.0,
        freeboard_proxy_m=18.0,
        scale_factor=1.0,
        steel_mass_t_est=total,
        steel_mass_t_source="fleet_benchmark",
        steel_intensity_t_per_MW=float(record.steel_intensity) if record.steel_intensity is not None else si,
        total_steel_t=total,
        unit_cost_cny_per_MW=unit_cost,
        unit_cost_source=cost_src,
        construction_years=construction,
        construction_years_source=const_src,
        fatigue_life_years=fatigue,
        fatigue_life_source=fatigue_src,
        assumptions=notes,
    )


def score_fleet_point(record: BenchmarkRecord) -> FleetReviewPoint | None:
    if record.capacity_mw is None:
        return None
    display_metrics = {
        "capacity_mw": record.capacity_mw,
        "steel_per_mw": record.steel_intensity,
        "unit_cost": record.unit_cost_cny_per_MW,
        "construction_years": record.construction_years,
        "fatigue_life": record.fatigue_life_years,
    }
    metrics = metrics_from_benchmark(record)
    full = score_design(metrics)
    ai = score_ai_review(metrics, full.rule_results)
    reg = score_regulatory_review(metrics, full.rule_results)
    ai_scores = {k: round(float(v), 1) for k, v in ai.scores.items()}
    reg_scores = {k: round(float(v), 1) for k, v in reg.scores.items()}
    if record.steel_intensity is None:
        ai_scores["steel_per_mw"] = None  # type: ignore[assignment]
        reg_scores["steel_per_mw"] = None  # type: ignore[assignment]
    if record.unit_cost_cny_per_MW is None:
        ai_scores["unit_cost"] = None  # type: ignore[assignment]
        reg_scores["unit_cost"] = None  # type: ignore[assignment]
    if record.construction_years is None:
        ai_scores["construction_years"] = None  # type: ignore[assignment]
        reg_scores["construction_years"] = None  # type: ignore[assignment]
    if record.fatigue_life_years is None:
        ai_scores["fatigue_life"] = None  # type: ignore[assignment]
        reg_scores["fatigue_life"] = None  # type: ignore[assignment]

    weights = ai.weights
    scored_dims = [k for k in DIMENSION_KEYS if ai_scores.get(k) is not None]
    wsum = sum(weights.get(k, 0.0) for k in scored_dims) or 1.0
    overall = (
        round(sum(float(ai_scores[k]) * weights.get(k, 0.0) for k in scored_dims) / wsum, 1)
        if scored_dims
        else 0.0
    )
    reg_scored = [k for k in DIMENSION_KEYS if reg_scores.get(k) is not None]
    rwsum = sum(weights.get(k, 0.0) for k in reg_scored) or 1.0
    reg_overall = (
        round(sum(float(reg_scores[k]) * weights.get(k, 0.0) for k in reg_scored) / rwsum, 1)
        if reg_scored
        else 0.0
    )
    return FleetReviewPoint(
        name=record.name,
        short_name=record.short_name,
        year=record.year,
        year_status=record.year_status,
        region=record.region,
        scores=ai_scores,
        metrics=display_metrics,
        overall=overall,
        regulatory_overall=reg_overall,
        regulatory_scores=reg_scores,
    )


def score_fleet_benchmarks(
    records: list[BenchmarkRecord] | None = None,
) -> list[FleetReviewPoint]:
    records = records or load_benchmark_records()
    out: list[FleetReviewPoint] = []
    for rec in records:
        pt = score_fleet_point(rec)
        if pt is not None:
            out.append(pt)
    return out


def fleet_radar_series(
    candidate: dict[str, float],
    *,
    candidate_label: str = "本方案",
    fleet_points: list[FleetReviewPoint] | None = None,
) -> dict[str, object]:
    """Serialize radar overlay data for plots and JSON export."""
    fleet_points = fleet_points or score_fleet_benchmarks()
    cfg = load_ai_review_config()
    labels = cfg.get("dimension_labels_zh") or {}
    return {
        "dimension_keys": list(DIMENSION_KEYS),
        "dimension_labels": [labels.get(k, k) for k in DIMENSION_KEYS],
        "candidate": {
            "label": candidate_label,
            "scores": candidate,
        },
        "fleet": [
            {
                "name": p.short_name,
                "region": p.region,
                "year": p.year,
                "year_status": p.year_status,
                "scores": p.scores,
                "metrics": p.metrics,
                "overall": p.overall,
            }
            for p in fleet_points
        ],
    }
