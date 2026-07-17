"""Case 2 — CalculiX residual plateau (Table S.1)."""
from __future__ import annotations

from backend.replan.simulate_cases import case2_solver_demo


def test_case2_solver_replan_table_s1():
    out = case2_solver_demo()
    assert out["ok"] is True
    before = out["feedback_before"]
    assert before["rho_p"] == 1
    assert before["failure_kind"] == "solver"
    assert abs(float(before["signals"]["residual_norm"]) - 1.2e-3) < 1e-9
    theta = out["result"]["theta_after"]
    assert int(theta["max_iterations"]) == 300
    assert abs(float(theta["load_increment"]) - 0.02) < 1e-9
    assert int(theta["restart_increment"]) == 30
    assert out["outcome"]["residual_norm"] < 1e-6
    assert out["feedback_after"]["rho_p"] == 0
