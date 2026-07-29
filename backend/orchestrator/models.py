"""Workflow orchestrator models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WorkflowPhase = Literal["I", "II", "III", "IV"]


class GateVerdict(BaseModel):
    ok: bool
    reason: str = ""
    rho_pending: int = 0
    overall_score: float | None = None
    min_subscore: float | None = None
    S_min: float = 85.0
    subscore_min: float = 60.0
    should_archive: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class WorkflowState(BaseModel):
    task_id: str
    workflow_phase: WorkflowPhase = "I"
    rho_pending: int = 0
    last_replan_event_id: str | None = None
    archived: bool = False
    archive_path: str | None = None
    last_validation_id: str | None = None
    design_checklist_id: str | None = None
    oc4_session_id: str | None = None
    updated_at: str | None = None
