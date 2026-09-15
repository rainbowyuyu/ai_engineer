"""platform_restruction (restruction6) smoke tests."""
from __future__ import annotations

from backend.tools.platform_restruction import (
    nearest_platform,
    run_platform_restruction,
)


def test_nearest_platform_points_to_geometry():
    base = nearest_platform(20.0)
    assert "geometry" in base["name"] or base["name"].endswith(".json")


def test_restruction_pitch_at_limit():
    out = run_platform_restruction(20.0, pitch_limit_deg=5.0)
    assert out["ok"] is True
    assert out["source"] == "restruction6"
    assert out["extra_scale_x"] > 0.4
    steel = out["steel_summary"]
    assert steel["pitch_angle_deg"] <= 5.01
    assert steel["steel_intensity_t_per_MW"] is not None
    opt = out["scaled_optimized"]
    assert opt.get("offset_col_dia") or opt.get("main_col_dia") or opt.get("spacing")
    assert float(steel["pitch_angle_deg"]) <= 5.01
