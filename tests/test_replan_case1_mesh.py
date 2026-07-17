"""Case 1 — mesh quality / inverted elements (Table S.1)."""
from __future__ import annotations

from backend.replan.simulate_cases import case1_mesh_demo


def test_case1_mesh_replan_table_s1():
    out = case1_mesh_demo()
    assert out["ok"] is True
    before = out["feedback_before"]
    assert before["rho_p"] == 1
    assert before["failure_kind"] == "mesh"
    assert before["signals"]["mesh_quality_min"] == 0.12
    theta = out["result"]["theta_after"]
    assert abs(float(theta["characteristic_length_max"]) - 1.8) < 0.05
    assert float(theta["local_refinement_factor"]) >= 1.3
    assert out["outcome"]["mesh_quality_min"] >= 0.28
    assert out["feedback_after"]["rho_p"] == 0
