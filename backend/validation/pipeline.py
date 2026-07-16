"""End-to-end validation pipeline."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

# Ensure matplotlib never picks TkAgg before plots module import (FreeCAD / IDE envs).
os.environ.setdefault("MPLBACKEND", "Agg")

from backend.validation.geometry_metrics import extract_geometry_metrics
from backend.validation.fleet_scoring import fleet_radar_series, score_fleet_benchmarks
from backend.validation.llm_rationale import generate_rationales
from backend.validation.plots import generate_all_plots
from backend.validation.report_builder import write_reports
from backend.validation.scorer import ValidationScore, score_design
from backend.validation.validity_eval import compute_validity_table


def run_validation(
    geometry: dict[str, Any],
    *,
    out_dir: Path,
    geometry_title: str | None = None,
    use_llm_rationale: bool = False,
    use_surrogate: bool = False,
    candidate_label: str = "Candidate",
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    validation_id = out_dir.name if out_dir.name else uuid.uuid4().hex

    from backend.surrogate.inference import predict as predict_surrogate

    surrogate_pred = predict_surrogate(geometry, use_surrogate=use_surrogate)
    metrics = extract_geometry_metrics(geometry, surrogate_prediction=surrogate_pred)
    score: ValidationScore = score_design(metrics)
    ctx = surrogate_pred.to_context()
    ctx["requested"] = use_surrogate
    if use_surrogate and surrogate_pred.enabled:
        hm = extract_geometry_metrics(geometry, surrogate_prediction=None)
        ctx["heuristic_derived"] = {
            "unit_cost_cny_per_MW": hm.unit_cost_cny_per_MW,
            "construction_years": hm.construction_years,
            "fatigue_life_years": hm.fatigue_life_years,
        }
        ctx["blended_derived"] = {
            "unit_cost_cny_per_MW": metrics.unit_cost_cny_per_MW,
            "construction_years": metrics.construction_years,
            "fatigue_life_years": metrics.fatigue_life_years,
        }
    score.surrogate_context = ctx
    title = geometry_title or str(geometry.get("title") or "Design candidate")

    fleet_points = score_fleet_benchmarks()
    validity_table = compute_validity_table(
        fleet_points,
        score=score,
        candidate_label=candidate_label,
    )
    fleet_radar = fleet_radar_series(
        score.ai_review_scores,
        candidate_label=candidate_label,
        fleet_points=fleet_points,
    )

    plot_paths = generate_all_plots(
        score,
        out_dir,
        candidate_label,
        fleet_points=fleet_points,
        validity_table=validity_table,
    )
    llm_rat = generate_rationales(score, use_llm=use_llm_rationale)

    (out_dir / "input_geometry_snapshot.json").write_text(
        json.dumps(geometry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_files = write_reports(
        score,
        out_dir,
        validation_id=validation_id,
        geometry_title=title,
        plot_artifacts=plot_paths,
        llm_rationales=llm_rat or None,
        validity_table=validity_table,
        fleet_radar=fleet_radar,
    )

    return {
        "validation_id": validation_id,
        "out_dir": str(out_dir),
        "overall_score": score.overall_score,
        "grade": score.grade,
        "regulatory_overall": score.regulatory_overall,
        "regulatory_review_scores": score.regulatory_review_scores,
        "ai_review_scores": score.ai_review_scores,
        "ai_review_metrics": score.ai_review_metrics,
        "ai_review_weights": score.ai_review_weights,
        "ai_review_labels": score.ai_review_labels,
        "category_scores": score.category_scores,
        "benchmark_context": score.benchmark_context,
        "calibration_notes": score.calibration_notes,
        "report_md": report_files["report_md"],
        "score_json": report_files["score_json"],
        "report_docx": report_files.get("report_docx"),
        "report_docx_detailed": report_files.get("report_docx_detailed"),
        "word_export_error": report_files.get("word_export_error"),
        "word_detailed_export_error": report_files.get("word_detailed_export_error"),
        "figures": plot_paths,
        "validity_table": validity_table,
        "fleet_radar": fleet_radar,
        "surrogate_context": score.surrogate_context,
    }
