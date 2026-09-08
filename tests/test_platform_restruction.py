"""platform_restruction (restruction.py) smoke tests."""
from __future__ import annotations

from backend.tools.platform_restruction import (
    nearest_platform,
    pitch_angle_deg,
    run_platform_restruction,
)


def test_nearest_platform_20mw_is_volturn():
    base = nearest_platform(20.0)
    assert base["name"] == "VolturnUS-S"


def test_restruction_pitch_at_limit():
    out = run_platform_restruction(20.0, pitch_limit_deg=5.0)
    assert out["ok"] is True
    assert out["extra_scale_x"] > 0.4
    steel = out["steel_summary"]
    assert steel["pitch_angle_deg"] <= 5.01
    assert steel["steel_intensity_t_per_MW"] is not None
    opt = out["scaled_optimized"]
    assert opt["offset_col_dia"] > 0
    assert opt["spacing"] > 0
    # constraint satisfied at optimum
    assert pitch_angle_deg(opt, 1.0) <= 5.01
