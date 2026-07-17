"""Closed-loop replan engine: evaluate F_p and replan(θ, F_p)."""
from __future__ import annotations

from typing import Any

from backend.replan.diagnostics import classify_failure, parse_diagnostics
from backend.replan.models import FeedbackTuple, ReplanEvent, ReplanResult
from backend.replan.paths import new_event_id, save_event
from backend.replan.policies import apply_actions, select_policies
from backend.replan.thresholds import load_thresholds


def evaluate_feedback(
    *,
    phase: str = "II",
    step: str = "",
    logs: str | list[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> FeedbackTuple:
    sig = parse_diagnostics(logs, metrics)
    kind = classify_failure(sig)
    log_lines: list[str] = []
    if isinstance(logs, list):
        log_lines = [str(x) for x in logs]
    elif logs:
        log_lines = [str(logs)]
    m = dict(metrics or {})
    if sig.mesh_quality_min is not None:
        m.setdefault("mesh_quality_min", sig.mesh_quality_min)
    if sig.residual_norm is not None:
        m.setdefault("residual_norm", sig.residual_norm)
    if sig.pitch_max_deg is not None:
        m.setdefault("pitch_max", sig.pitch_max_deg)
    return FeedbackTuple(
        phase=phase,
        step=step,
        L_p=log_lines,
        M_p=m,
        rho_p=1 if kind else 0,
        signals=sig,
        failure_kind=kind,
    )


def _retry_policy_from_checklist(checklist: Any | None) -> dict[str, Any]:
    if checklist is None:
        return dict(load_thresholds().get("retry") or {})
    try:
        rp = checklist.job_descriptor.retry_policy
        return {
            "max_retries": rp.max_retries,
            "on_mesh_fail": rp.on_mesh_fail,
            "on_solver_fail": rp.on_solver_fail,
        }
    except Exception:
        return dict(load_thresholds().get("retry") or {})


def replan(
    theta: dict[str, Any] | None,
    feedback: FeedbackTuple,
    *,
    checklist: Any | None = None,
    case_id: str | None = None,
    persist: bool = True,
) -> ReplanResult:
    theta_before = dict(theta or {})
    if feedback.rho_p == 0 or not feedback.failure_kind:
        return ReplanResult(
            feedback=feedback,
            theta_before=theta_before,
            theta_after=theta_before,
            message="ρ_p=0：无需重规划，可进入下一阶段。",
        )

    actions = select_policies(feedback.failure_kind, theta_before, feedback.signals)
    # Honour checklist retry_policy names when present
    rp = _retry_policy_from_checklist(checklist)
    if feedback.failure_kind == "mesh" and rp.get("on_mesh_fail") and actions:
        actions[0].policy = str(rp["on_mesh_fail"])
    if feedback.failure_kind == "solver" and rp.get("on_solver_fail"):
        for a in actions:
            if a.policy == "relax_increment":
                a.policy = str(rp["on_solver_fail"])
                break

    theta_after = apply_actions(theta_before, actions)
    event = ReplanEvent(
        event_id=new_event_id(),
        created_at=ReplanEvent.now_iso(),
        phase=feedback.phase,
        case_id=case_id,
        failure_kind=feedback.failure_kind,
        signals_before=feedback.signals,
        actions=actions,
        theta_before=theta_before,
        theta_after=theta_after,
        rho_after=0,
        outcome={"status": "planned"},
    )
    if persist:
        save_event(event)

    msg = f"检测到 {feedback.failure_kind} 失败，已应用 {len(actions)} 项策略并更新 θ。"
    return ReplanResult(
        feedback=feedback,
        actions=actions,
        theta_before=theta_before,
        theta_after=theta_after,
        event=event,
        message=msg,
    )
