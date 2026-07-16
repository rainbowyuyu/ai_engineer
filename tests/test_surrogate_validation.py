"""Integration test: validation with surrogate model."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.validation.pipeline import run_validation

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "rules" / "optimized_geometry.json"
MODEL_DIR = REPO / "runs" / "_surrogate_models"


@pytest.fixture
def geometry() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def trained_surrogate():
    if not (MODEL_DIR / "meta.json").is_file():
        subprocess.check_call(
            [sys.executable, str(REPO / "scripts" / "generate_surrogate_dataset.py"), "-n", "20"],
            cwd=str(REPO),
        )
        subprocess.check_call(
            [sys.executable, str(REPO / "scripts" / "train_surrogate.py")],
            cwd=str(REPO),
        )
    return MODEL_DIR


def test_validation_with_surrogate(trained_surrogate, tmp_path):
    geom = json.loads(SAMPLE.read_text(encoding="utf-8"))
    out = tmp_path / "surrogate_val"
    result = run_validation(geom, out_dir=out, use_surrogate=True)
    ctx = result.get("surrogate_context") or {}
    assert ctx.get("enabled") is True
    assert "static_predictions" in ctx


def test_validation_without_surrogate_regression(geometry, tmp_path):
    out = tmp_path / "baseline"
    result = run_validation(geometry, out_dir=out, use_surrogate=False)
    ctx = result.get("surrogate_context") or {}
    assert ctx.get("enabled") is False
