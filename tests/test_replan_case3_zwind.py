"""Case 3 — Zwind pitch abort (Table S.1)."""
from __future__ import annotations

from backend.replan.simulate_cases import case3_zwind_demo


def test_case3_zwind_replan_table_s1():
    out = case3_zwind_demo()
    assert out["ok"] is True
    before = out["feedback_before"]
    assert before["rho_p"] == 1
    assert before["failure_kind"] == "zwind"
    assert abs(float(before["signals"]["pitch_max_deg"]) - 25.3) < 0.05
    theta = out["result"]["theta_after"]
    assert abs(float(theta["dt_s"]) - 0.005) < 1e-9
    assert abs(float(theta["mooring_stiffness_scale"]) - 1.05) < 1e-9
    assert float(out["outcome"]["pitch_max"]) <= 18.0
    assert abs(float(out["outcome"]["pitch_max"]) - 16.8) < 0.05
    assert out["feedback_after"]["rho_p"] == 0
