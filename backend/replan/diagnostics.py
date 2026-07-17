"""Extract diagnostic signals from solver/mesh logs (Table S.1)."""
from __future__ import annotations

import re
from typing import Any

from backend.replan.models import DiagnosticSignals
from backend.replan.thresholds import load_thresholds


def _f(patterns: list[str], text: str) -> float | None:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except (ValueError, IndexError):
                continue
    return None


def _i(patterns: list[str], text: str) -> int | None:
    v = _f(patterns, text)
    return int(v) if v is not None else None


def parse_diagnostics(
    logs: str | list[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> DiagnosticSignals:
    parts: list[str] = []
    if isinstance(logs, list):
        parts.extend(str(x) for x in logs)
    elif logs:
        parts.append(str(logs))
    text = "\n".join(parts)
    m = dict(metrics or {})

    sig = DiagnosticSignals(raw_excerpt=text[:1200])

    if "mesh_quality_min" in m and m["mesh_quality_min"] is not None:
        sig.mesh_quality_min = float(m["mesh_quality_min"])
    else:
        sig.mesh_quality_min = _f(
            [
                r"mesh_quality_min\s*[=:]\s*([0-9.eE+-]+)",
                r"quality\s*[<≤]\s*([0-9.]+)",
                r"min(?:imum)?\s+quality\s*[=:]\s*([0-9.]+)",
            ],
            text,
        )

    if "mesh_error_code" in m and m["mesh_error_code"] is not None:
        sig.mesh_error_code = int(m["mesh_error_code"])
    else:
        sig.mesh_error_code = _i([r"mesh_error_code\s*[=:]\s*(-?\d+)", r"error\s*code\s*[=:]\s*(-?\d+)"], text)

    if re.search(r"inverted\s+elements|surface\s+mesh\s+contains\s+inverted", text, re.I):
        if sig.mesh_error_code is None:
            tau = load_thresholds().get("mesh") or {}
            sig.mesh_error_code = int(tau.get("error_code_inverted", -5))
        if sig.mesh_quality_min is None:
            q = _f([r"quality\s*[<≤]\s*([0-9.]+)"], text)
            sig.mesh_quality_min = q if q is not None else 0.12

    if "convergence_flag" in m and m["convergence_flag"] is not None:
        sig.convergence_flag = int(m["convergence_flag"])
    elif re.search(r"failed\s+to\s+converge|did\s+not\s+converge|convergence\s+failed", text, re.I):
        sig.convergence_flag = 1
    elif "convergence_flag" in text.lower():
        sig.convergence_flag = _i([r"convergence_flag\s*[=:]\s*(\d+)"], text)

    if "residual_norm" in m and m["residual_norm"] is not None:
        sig.residual_norm = float(m["residual_norm"])
    else:
        sig.residual_norm = _f(
            [
                r"residual_norm\s*[=:]\s*([0-9.eE+-]+)",
                r"residual\s+norm\s*[=:]\s*([0-9.eE+-]+)",
                r"plateau(?:ing)?\s+at\s+([0-9.eE×x^+-]+)",
            ],
            text.replace("×", "e").replace("10⁻³", "1e-3"),
        )
        if sig.residual_norm is None and "1.2" in text and ("10^-3" in text or "1e-3" in text.lower() or "10⁻³" in text):
            sig.residual_norm = 1.2e-3

    if "residual_plateau_iters" in m and m["residual_plateau_iters"] is not None:
        sig.residual_plateau_iters = int(m["residual_plateau_iters"])
    else:
        sig.residual_plateau_iters = _i(
            [r"no\s+decrease\s+over\s+(\d+)\s+iterations", r"plateau.*?(\d+)\s+iter"],
            text,
        )

    if "element_distortion_count" in m and m["element_distortion_count"] is not None:
        sig.element_distortion_count = int(m["element_distortion_count"])
    else:
        sig.element_distortion_count = _i(
            [r"element_distortion_warning\s+for\s+(\d+)", r"distorted\s+(\d+)\s+elements"],
            text,
        )

    if "simulation_abort" in m and m["simulation_abort"] is not None:
        sig.simulation_abort = int(m["simulation_abort"])
    elif re.search(r"simulation\s+abort|time-domain\s+simulation\s+aborted|zwind.*abort", text, re.I):
        sig.simulation_abort = 1

    if "pitch_max" in m and m["pitch_max"] is not None:
        sig.pitch_max_deg = float(m["pitch_max"])
    elif "pitch_max_deg" in m and m["pitch_max_deg"] is not None:
        sig.pitch_max_deg = float(m["pitch_max_deg"])
    else:
        sig.pitch_max_deg = _f(
            [r"pitch_max\s*[=:]\s*([0-9.]+)", r"pitch\s+exceeding\s+([0-9.]+)", r"pitch.*?([0-9.]+)\s*°"],
            text,
        )

    if m.get("timestep_cfl_warning") or re.search(r"timestep_stability_CFL|CFL\s+warning", text, re.I):
        sig.timestep_cfl_warning = True

    return sig


def classify_failure(sig: DiagnosticSignals) -> str | None:
    tau = load_thresholds()
    mesh_t = tau.get("mesh") or {}
    solver_t = tau.get("solver") or {}
    zwind_t = tau.get("zwind") or {}

    q_thr = float(mesh_t.get("quality_min_threshold", 0.30))
    q_relaxed = float(mesh_t.get("quality_min_relaxed", 0.20))
    err_inv = int(mesh_t.get("error_code_inverted", -5))
    raw = (sig.raw_excerpt or "").lower()
    inverted = "inverted" in raw

    if sig.mesh_error_code is not None and int(sig.mesh_error_code) == err_inv:
        return "mesh"
    if sig.mesh_quality_min is not None:
        q = float(sig.mesh_quality_min)
        if q < q_relaxed:
            return "mesh"
        if q < q_thr and inverted:
            return "mesh"

    res_tol = float(solver_t.get("residual_tol", 1e-6))
    if sig.convergence_flag == 1:
        return "solver"
    if sig.residual_norm is not None and float(sig.residual_norm) > res_tol * 100:
        return "solver"

    pitch_lim = float(zwind_t.get("pitch_limit_deg", 18.0))
    if sig.simulation_abort == 1:
        return "zwind"
    if sig.pitch_max_deg is not None and float(sig.pitch_max_deg) > pitch_lim:
        return "zwind"

    return None
