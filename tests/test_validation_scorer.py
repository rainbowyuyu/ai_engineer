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


def test_run_validation_pipeline(geometry, tmp_path):
    out = tmp_path / "val_run"
    result = run_validation(geometry, out_dir=out, use_llm_rationale=False)
    assert result["overall_score"] >= 0
    assert (out / "validation_report.md").is_file()
    assert (out / "validation_score.json").is_file()
    assert (out / "fig_benchmark_position.png").is_file()
    assert (out / "fig_score_radar.png").is_file()
