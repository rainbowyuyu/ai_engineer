"""End-to-end validation pipeline."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from backend.validation.geometry_metrics import extract_geometry_metrics
from backend.validation.llm_rationale import generate_rationales
from backend.validation.plots import generate_all_plots
from backend.validation.report_builder import write_reports
from backend.validation.scorer import ValidationScore, score_design


def run_validation(
    geometry: dict[str, Any],
    *,
    out_dir: Path,
    geometry_title: str | None = None,
    use_llm_rationale: bool = False,
    candidate_label: str = "Candidate",
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    validation_id = out_dir.name if out_dir.name else uuid.uuid4().hex

    metrics = extract_geometry_metrics(geometry)
    score: ValidationScore = score_design(metrics)
    title = geometry_title or str(geometry.get("title") or "Design candidate")

    plot_paths = generate_all_plots(score, out_dir, candidate_label)
    llm_rat = generate_rationales(score, use_llm=use_llm_rationale)
    report_files = write_reports(
        score,
        out_dir,
        validation_id=validation_id,
        geometry_title=title,
        plot_artifacts=plot_paths,
        llm_rationales=llm_rat or None,
    )

    (out_dir / "input_geometry_snapshot.json").write_text(
        json.dumps(geometry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "validation_id": validation_id,
        "out_dir": str(out_dir),
        "overall_score": score.overall_score,
        "grade": score.grade,
        "category_scores": score.category_scores,
        "benchmark_context": score.benchmark_context,
        "calibration_notes": score.calibration_notes,
        "report_md": report_files["report_md"],
        "score_json": report_files["score_json"],
        "figures": plot_paths,
    }
