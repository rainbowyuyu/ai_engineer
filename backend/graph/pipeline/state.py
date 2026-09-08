"""LangGraph pipeline state (mirrors orchestrator WorkflowState)."""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict


def _merge_events(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return left + right


WorkflowPhase = Literal["I", "II", "III", "IV"]


class PipelineState(TypedDict, total=False):
    task_id: str
    workflow_phase: WorkflowPhase
    rho_pending: int
    design_checklist_id: str | None
    oc4_session_id: str | None
    design_requirements_text: str | None
    beso_job_id: str | None
    beso_status: str | None
    validation_id: str | None
    overall_score: float | None
    ai_review_scores: dict[str, float] | None
    archived: bool
    archive_path: str | None
    halt_ok: bool | None
    halt_reason: str | None
    events: Annotated[list[dict[str, Any]], _merge_events]
    error: str | None
    seed: int | None
    model_version: str | None
    turbine_preset_id: str | None
    execution_mode: str | None
    hitl_pause: str | None
    sizing_path: str | None
    validation_dir: str | None
    auto_create_session: bool
    request_hitl_before_mesh: bool
