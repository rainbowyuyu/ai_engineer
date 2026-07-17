"""Policy library: refine_mesh / relax_increment / reduce_timestep / stiffen_mooring."""
from __future__ import annotations

from typing import Any

from backend.replan.models import DiagnosticSignals, ReplanAction
from backend.replan.thresholds import load_thresholds


def policy_refine_mesh(theta: dict[str, Any], sig: DiagnosticSignals) -> list[ReplanAction]:
    tau = load_thresholds().get("mesh") or {}
    before = float(theta.get("characteristic_length_max") or theta.get("element_size_m") or tau.get("default_element_size_m", 2.5))
    target = float(tau.get("refined_element_size_m", 1.8))
    # Prefer paper ratio 2.5→1.8 when starting near default
    if before >= 2.4:
        after = target
    else:
        after = max(target * 0.5, before * (target / float(tau.get("default_element_size_m", 2.5))))
    local_rf = float(tau.get("local_refinement_factor", 1.4))
    quality_relaxed = float(tau.get("quality_min_relaxed", 0.20))
    return [
        ReplanAction(
            policy="refine_mesh",
            description=(
                f"Reduced target element size from {before} m to {after} m; "
                f"increased local refinement factor to {local_rf} around high-curvature regions; "
                f"relaxed quality threshold to {quality_relaxed}."
            ),
            theta_patch={
                "characteristic_length_max": after,
                "element_size_m": after,
                "local_refinement_factor": local_rf,
                "mesh_quality_threshold": quality_relaxed,
            },
        )
    ]


def policy_relax_increment(theta: dict[str, Any], sig: DiagnosticSignals) -> list[ReplanAction]:
    tau = load_thresholds().get("solver") or {}
    max_iter = int(theta.get("max_iterations") or tau.get("default_max_iterations", 100))
    new_max = int(tau.get("increased_max_iterations", 300))
    inc = float(theta.get("load_increment") or tau.get("default_load_increment", 0.05))
    new_inc = float(tau.get("relaxed_load_increment", 0.02))
    restart = int(tau.get("restart_increment", 30))
    return [
        ReplanAction(
            policy="increase_iterations",
            description=f"Increased maximum iterations from {max_iter} to {new_max}.",
            theta_patch={"max_iterations": new_max},
        ),
        ReplanAction(
            policy="relax_increment",
            description=f"Reduced load increment size from {inc} to {new_inc} for the first 50 increments.",
            theta_patch={"load_increment": new_inc, "load_increment_first_n": 50},
        ),
        ReplanAction(
            policy="reset_initial_guess",
            description=f"Reset initial guess to the converged solution at increment {restart}.",
            theta_patch={"restart_increment": restart},
        ),
    ]


def policy_zwind_recover(theta: dict[str, Any], sig: DiagnosticSignals) -> list[ReplanAction]:
    tau = load_thresholds().get("zwind") or {}
    dt = float(theta.get("dt_s") or tau.get("default_dt_s", 0.0125))
    new_dt = float(tau.get("refined_dt_s", 0.005))
    t0 = float(tau.get("extreme_wave_t_start_s", 150.0))
    t1 = float(tau.get("extreme_wave_t_end_s", 250.0))
    scale = float(tau.get("mooring_stiffness_scale", 1.05))
    return [
        ReplanAction(
            policy="reduce_timestep",
            description=(
                f"Reduced time step from {dt} s to {new_dt} s for the extreme wave group "
                f"(t = {t0}–{t1} s)."
            ),
            theta_patch={
                "dt_s": new_dt,
                "dt_s_extreme_window": [t0, t1],
            },
        ),
        ReplanAction(
            policy="stiffen_mooring",
            description=f"Increased mooring line stiffness in surge by {(scale - 1) * 100:.0f}% (fairlead pretension).",
            theta_patch={
                "mooring_stiffness_scale": scale,
                "mooring_surge_scale": scale,
            },
        ),
    ]


def select_policies(failure_kind: str, theta: dict[str, Any], sig: DiagnosticSignals) -> list[ReplanAction]:
    if failure_kind == "mesh":
        return policy_refine_mesh(theta, sig)
    if failure_kind == "solver":
        return policy_relax_increment(theta, sig)
    if failure_kind == "zwind":
        return policy_zwind_recover(theta, sig)
    return []


def apply_actions(theta: dict[str, Any], actions: list[ReplanAction]) -> dict[str, Any]:
    out = dict(theta)
    for a in actions:
        out.update(a.theta_patch or {})
    return out
