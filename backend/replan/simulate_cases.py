"""Table S.1 fixture-driven demos: fail → replan → simulated success."""
from __future__ import annotations

from typing import Any

from backend.replan.engine import evaluate_feedback, replan
from backend.replan.guided import attach_guided
from backend.replan.models import ReplanEvent
from backend.replan.paths import save_event
from backend.replan.thresholds import load_thresholds


def case1_mesh_demo() -> dict[str, Any]:
    """Gmsh inverted elements → refine_mesh → quality recovered."""
    tau = load_thresholds().get("mesh") or {}
    logs = (
        'Gmsh mesh generation failed with error "surface mesh contains inverted elements '
        '(quality < 0.15)" after BESO topology update produced a slender brace configuration. '
        "mesh_quality_min = 0.12; mesh_error_code = -5"
    )
    theta0 = {
        "characteristic_length_max": float(tau.get("default_element_size_m", 2.5)),
        "element_size_m": float(tau.get("default_element_size_m", 2.5)),
        "local_refinement_factor": 1.0,
        "mesh_quality_threshold": float(tau.get("quality_min_threshold", 0.30)),
    }
    fb = evaluate_feedback(phase="II", step="4", logs=logs, metrics={"mesh_quality_min": 0.12, "mesh_error_code": -5})
    result = replan(theta0, fb, case_id="case1", persist=True)
    # Simulated re-mesh outcome (paper: min quality 0.28)
    sim_quality = 0.28
    outcome = {
        "status": "success",
        "mesh_quality_min": sim_quality,
        "mesh_ok": True,
        "note": "Mesh generated successfully (min quality 0.28); downstream CalculiX solver ran to completion.",
    }
    if result.event:
        result.event.outcome = outcome
        result.event.rho_after = 0
        save_event(result.event)
    fb_after = evaluate_feedback(
        phase="II",
        step="4",
        logs=f"mesh regenerated; mesh_quality_min = {sim_quality}",
        metrics={"mesh_quality_min": sim_quality},
    )
    return {
        "case_id": "case1",
        "title": "Case 1 — Gmsh inverted elements / mesh quality",
        "feedback_before": fb.model_dump(mode="json"),
        "feedback_after": fb_after.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "outcome": outcome,
        "ok": fb.rho_p == 1 and fb_after.rho_p == 0 and abs(float(result.theta_after.get("characteristic_length_max", 0)) - 1.8) < 0.05,
    }


def case2_solver_demo() -> dict[str, Any]:
    """CalculiX residual plateau → relax increment / more iters → converged."""
    tau = load_thresholds().get("solver") or {}
    logs = (
        "CalculiX static solver failed to converge at increment 47 of 100 during compliance "
        "minimisation, with residual norm plateauing at 1.2e-3 (tolerance 1e-6). "
        "convergence_flag = 1; residual_norm = 1.2e-3; no decrease over 15 iterations; "
        "element_distortion_warning for 23 elements."
    )
    theta0 = {
        "max_iterations": int(tau.get("default_max_iterations", 100)),
        "load_increment": float(tau.get("default_load_increment", 0.05)),
        "restart_increment": 0,
    }
    fb = evaluate_feedback(
        phase="II",
        step="5",
        logs=logs,
        metrics={
            "convergence_flag": 1,
            "residual_norm": 1.2e-3,
            "residual_plateau_iters": 15,
            "element_distortion_count": 23,
        },
    )
    result = replan(theta0, fb, case_id="case2", persist=True)
    residual_final = 9.8e-7
    outcome = {
        "status": "success",
        "residual_norm": residual_final,
        "converged_increment": 274,
        "note": "Solver converged to tolerance 9.8e-7 at increment 274; compliance validated.",
    }
    if result.event:
        result.event.outcome = outcome
        result.event.rho_after = 0
        save_event(result.event)
    fb_after = evaluate_feedback(
        phase="II",
        step="5",
        logs=f"converged; residual_norm = {residual_final}",
        metrics={"residual_norm": residual_final, "convergence_flag": 0},
    )
    ok = (
        fb.rho_p == 1
        and result.theta_after.get("max_iterations") == 300
        and abs(float(result.theta_after.get("load_increment", 0)) - 0.02) < 1e-9
        and int(result.theta_after.get("restart_increment", 0)) == 30
        and fb_after.rho_p == 0
    )
    return {
        "case_id": "case2",
        "title": "Case 2 — CalculiX residual plateau / non-convergence",
        "feedback_before": fb.model_dump(mode="json"),
        "feedback_after": fb_after.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "outcome": outcome,
        "ok": ok,
    }


def case3_zwind_demo() -> dict[str, Any]:
    """Zwind pitch abort → reduce dt + stiffen mooring → pitch OK."""
    tau = load_thresholds().get("zwind") or {}
    logs = (
        "Zwind 3.0 time-domain simulation aborted at t = 187 s under extreme sea state "
        "(Hs = 12 m, Tp = 14 s) with floating platform pitch exceeding 25° (acceptable limit 18°). "
        "simulation_abort = 1; pitch_max = 25.3°; timestep_stability_CFL warning at t = 178 s."
    )
    theta0 = {
        "dt_s": float(tau.get("default_dt_s", 0.0125)),
        "mooring_stiffness_scale": 1.0,
        "Hs_m": 12.0,
        "Tp_s": 14.0,
    }
    fb = evaluate_feedback(
        phase="II",
        step="7",
        logs=logs,
        metrics={"simulation_abort": 1, "pitch_max": 25.3, "timestep_cfl_warning": True},
    )
    result = replan(theta0, fb, case_id="case3", persist=True)
    pitch_ok = float(tau.get("pitch_success_example_deg", 16.8))
    outcome = {
        "status": "success",
        "pitch_max": pitch_ok,
        "simulation_complete": True,
        "note": f"Simulation completed; pitch_max reduced to {pitch_ok}°; all stability criteria satisfied.",
    }
    if result.event:
        result.event.outcome = outcome
        result.event.rho_after = 0
        save_event(result.event)
    fb_after = evaluate_feedback(
        phase="II",
        step="7",
        logs=f"simulation complete; pitch_max = {pitch_ok}",
        metrics={"pitch_max": pitch_ok, "simulation_abort": 0},
    )
    ok = (
        fb.rho_p == 1
        and abs(float(result.theta_after.get("dt_s", 0)) - 0.005) < 1e-9
        and abs(float(result.theta_after.get("mooring_stiffness_scale", 0)) - 1.05) < 1e-9
        and fb_after.rho_p == 0
        and pitch_ok <= float(tau.get("pitch_limit_deg", 18.0))
    )
    return {
        "case_id": "case3",
        "title": "Case 3 — Zwind pitch exceedance / time-domain abort",
        "feedback_before": fb.model_dump(mode="json"),
        "feedback_after": fb_after.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "outcome": outcome,
        "ok": ok,
    }


CASE_DEMOS = {
    "case1": case1_mesh_demo,
    "case2": case2_solver_demo,
    "case3": case3_zwind_demo,
}


def run_case_demo(case_id: str) -> dict[str, Any]:
    key = str(case_id or "").strip().lower()
    if key not in CASE_DEMOS:
        raise ValueError(f"未知案例: {case_id}（支持 case1/case2/case3）")
    return attach_guided(CASE_DEMOS[key]())
