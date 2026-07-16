"""Tests for physics-informed penalty terms."""
from __future__ import annotations

import numpy as np

from backend.surrogate.config import feature_keys, static_target_keys
from backend.surrogate.physics_loss import (
    analytical_steel_mass_kg,
    combined_physics_residual,
    physics_penalties,
)


def test_analytical_steel_mass_positive():
    m = analytical_steel_mass_kg(9.0, 50.0, 0.06)
    assert m > 1000


def test_physics_penalties_bounded():
    fk = feature_keys()
    tk = static_target_keys()
    x = np.array([20.0, 0.06, 9.0, 50.0, 5.5, 150.0, 35.0, 1.0, 1.2, 40.0, 12.0, 1.3][: len(fk)], dtype=float)
    if len(x) < len(fk):
        x = np.pad(x, (0, len(fk) - len(x)))
    y = np.array([0.8, 2.5, 5100.0, 3.5][: len(tk)], dtype=float)
    if len(y) < len(tk):
        y = np.pad(y, (0, len(tk) - len(y)))
    pen = physics_penalties(y, x, feat_keys=fk, tgt_keys=tk)
    res = combined_physics_residual(pen)
    assert res >= 0.0
    assert "mass" in pen
