"""Phase transition gates — block advance when rho_p != 0."""
from __future__ import annotations

from backend.orchestrator.models import GateVerdict, WorkflowState


def can_advance(
    state: WorkflowState,
    *,
    from_phase: str,
    to_phase: str,
) -> GateVerdict:
    if state.archived and to_phase in ("II", "III"):
        return GateVerdict(ok=False, reason="任务已归档，需新建任务才能继续探索。")

    if state.rho_pending != 0:
        return GateVerdict(
            ok=False,
            reason="存在未完成的重规划恢复（ρₚ=1）。请先完成重规划旅程中的「继续」步骤，或等待网格/求解器重试成功。",
            rho_pending=state.rho_pending,
        )

    # II -> orchestrate / validation requires mesh+loads ready (checked elsewhere)
    if from_phase == "II" and to_phase in ("III", "IV") and state.rho_pending:
        return GateVerdict(ok=False, reason="Phase II 仍有待处理失败信号。", rho_pending=state.rho_pending)

    return GateVerdict(ok=True, rho_pending=state.rho_pending)


def evaluate_transition(state: WorkflowState, transition: str) -> GateVerdict:
    """Named transitions used by API/front-end."""
    mapping = {
        "design_domain_to_orchestrate": ("II", "III"),
        "orchestrate_to_validation": ("II", "IV"),
        "phase_ii_finalize": ("II", "III"),
    }
    pair = mapping.get(transition)
    if not pair:
        return GateVerdict(ok=True, rho_pending=state.rho_pending)
    return can_advance(state, from_phase=pair[0], to_phase=pair[1])
