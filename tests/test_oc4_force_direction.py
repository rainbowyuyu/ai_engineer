"""Unit tests for BESO9-aligned force direction → *CLOAD mapping."""

from backend.tools.oc4_force_direction import (
    force_direction_label_zh,
    load_case_from_force_direction,
    merge_force_direction_into_load_case,
    normalize_force_direction,
)


def test_normalize_and_beso9_minus_z():
    assert normalize_force_direction("down") == "-Z"
    lc = load_case_from_force_direction("-Z")
    assert lc["cload_dof"] == 3
    assert lc["cload_mag"] < 0
    assert lc["cload_mode"] == "beso9_ring"
    assert lc["fix_mode"] == "beso9_arcs"


def test_horizontal_plus_x():
    lc = load_case_from_force_direction("+X", total_force_n=1e6)
    assert lc["cload_dof"] == 1
    assert lc["cload_mag"] == 1e6


def test_merge_preserves_band():
    merged = merge_force_direction_into_load_case({"band_scale": 1.5, "z_fix_band": 900}, "-Z")
    assert merged["band_scale"] == 1.5
    assert merged["z_fix_band"] == 900
    assert merged["force_direction"] == "-Z"
    label = force_direction_label_zh("-Z")
    assert "竖直向下" in label or "重力" in label
