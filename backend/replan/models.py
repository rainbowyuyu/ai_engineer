"""Pydantic models for failure-driven replanning (F_p, actions, audit)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class DiagnosticSignals(BaseModel):
    mesh_quality_min: float | None = None
    mesh_error_code: int | None = None
    convergence_flag: int | None = None
    residual_norm: float | None = None
    residual_plateau_iters: int | None = None
    element_distortion_count: int | None = None
    simulation_abort: int | None = None
    pitch_max_deg: float | None = None
    timestep_cfl_warning: bool = False
    raw_excerpt: str = ""


class FeedbackTuple(BaseModel):
    """F_p = (L_p, M_p, ρ_p)."""

    phase: str = "II"
    step: str = ""
    L_p: list[str] = Field(default_factory=list, description="Structured logs / diagnostics")
    M_p: dict[str, Any] = Field(default_factory=dict, description="Quantitative metrics")
    rho_p: Literal[0, 1] = 0
    signals: DiagnosticSignals = Field(default_factory=DiagnosticSignals)
    failure_kind: str | None = None  # mesh | solver | zwind | None


class ReplanAction(BaseModel):
    policy: str
    description: str = ""
    theta_patch: dict[str, Any] = Field(default_factory=dict)


class ReplanEvent(BaseModel):
    event_id: str = ""
    created_at: str = ""
    phase: str = "II"
    case_id: str | None = None
    failure_kind: str | None = None
    signals_before: DiagnosticSignals = Field(default_factory=DiagnosticSignals)
    actions: list[ReplanAction] = Field(default_factory=list)
    theta_before: dict[str, Any] = Field(default_factory=dict)
    theta_after: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)
    rho_after: Literal[0, 1] = 0

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReplanResult(BaseModel):
    feedback: FeedbackTuple
    actions: list[ReplanAction] = Field(default_factory=list)
    theta_before: dict[str, Any] = Field(default_factory=dict)
    theta_after: dict[str, Any] = Field(default_factory=dict)
    event: ReplanEvent | None = None
    message: str = ""
