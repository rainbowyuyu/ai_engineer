"""Tests for surrogate feature extraction."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.surrogate.features import extract_feature_dict, feature_vector

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "rules" / "optimized_geometry.json"


def test_feature_vector_length():
    geom = json.loads(SAMPLE.read_text(encoding="utf-8"))
    fd = extract_feature_dict(geom)
    assert "target_power_MW" in fd
    x = feature_vector(geom)
    assert x.shape[0] >= 10
    assert np.all(np.isfinite(x))


def test_feature_defaults_no_crash():
    x = feature_vector({})
    assert len(x) >= 10
