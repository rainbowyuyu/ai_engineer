"""Tests for validation scorer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.validation.geometry_metrics import extract_geometry_metrics
from backend.validation.pipeline import run_validation
from backend.validation.scorer import score_design

REPO = Path(__file__).resolve().parents[1]
SAMPLE_JSON = REPO / "rules" / "optimized_geometry.json"


@pytest.fixture
def geometry() -> dict:
    return json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))


def test_extract_metrics(geometry):
    m = extract_geometry_metrics(geometry)
    assert m.target_power_MW == 20.0
    assert m.steel_intensity_t_per_MW > 0
    assert m.leg_mean_spacing_m is not None


def test_score_design(geometry):
    m = extract_geometry_metrics(geometry)
    score = score_design(m)
    assert 0 <= score.overall_score <= 100
    assert score.grade in ("A", "B", "C", "D")
    assert len(score.rule_results) >= 26
    assert "benchmark" in score.category_scores
    assert score.overall_score < 98
    assert 72 <= score.category_scores["benchmark"] <= 95
    assert len(score.ai_review_scores) == 5
    assert "steel_per_mw" in score.ai_review_scores
    assert score.ai_review_metrics.get("capacity_mw") == 20.0
    assert score.ai_review_metrics.get("steel_per_mw") is not None


def test_run_validation_pipeline(geometry, tmp_path):
    out = tmp_path / "val_run"
    result = run_validation(geometry, out_dir=out, use_llm_rationale=False)
    assert result["overall_score"] >= 0
    assert (out / "validation_report.md").is_file()
    assert (out / "validation_score.json").is_file()
    assert (out / "fig_benchmark_position.png").is_file()
    assert (out / "fig_benchmark_capacity.png").is_file()
    assert (out / "fig_benchmark_unit_cost.png").is_file()
    assert (out / "fig_score_radar.png").is_file()
    assert (out / "fig_ai_review_validity.png").is_file()
    docx = out / "validation_report.docx"
    if docx.is_file():
        assert docx.stat().st_size > 5000


def test_fleet_table_roster_only():
    from backend.validation.benchmark_loader import load_benchmark_records
    from backend.validation.fleet_scoring import score_fleet_benchmarks

    records = load_benchmark_records()
    assert len(records) == 11
    names = {r.short_name for r in records}
    assert "Kincardine Ph1" not in names
    assert "AI" not in names
    assert "Hywind Scotland" not in names
    assert "Hywind Tampen" not in names
    assert "万宁" not in "".join(names)
    assert "WindFloat Atlantic" in names
    atlantic = next(r for r in records if r.short_name == "WindFloat Atlantic")
    assert atlantic.capacity_mw == 8.4
    assert atlantic.steel_intensity == 417.0
    points = score_fleet_benchmarks(records)
    assert len(points) == 11
