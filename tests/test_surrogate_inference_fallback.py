"""Graceful fallback when surrogate backend deps are missing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.surrogate.inference import predict


@pytest.fixture
def geometry():
    p = Path(__file__).resolve().parents[1] / "rules" / "optimized_geometry.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_predict_fallback_on_missing_backend(geometry, monkeypatch):
    from backend.surrogate import inference as inf_mod

    def _boom(*_a, **_k):
        raise ModuleNotFoundError("No module named 'joblib'")

    monkeypatch.setattr(inf_mod, "predict_array", _boom)
    pred = inf_mod.predict(geometry, use_surrogate=True)
    assert pred.enabled is False
    assert pred.source == "heuristic"
    assert any("joblib" in a for a in pred.assumptions)
