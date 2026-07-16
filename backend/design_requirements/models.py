"""Pydantic models for Phase I design checklist."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ChecklistMeta(BaseModel):
    checklist_id: str = ""
    created_at: str = ""
    source_text: str = ""
    parser: Literal["qwen", "rule_fallback"] = "rule_fallback"
    reasoning_summary: str = ""


class ProjectSpec(BaseModel):
    title: str = ""
    owner_intent_zh: str = ""
    target_capacity_mw: float = 20.0
    platform_type: str = "semi_submersible"

    @field_validator("target_capacity_mw")
    @classmethod
    def clamp_mw(cls, v: float) -> float:
        return max(5.0, min(50.0, float(v)))


class SeaStateEnvelope(BaseModel):
    reference: str = ""
    labels: list[str] = Field(default_factory=list)
    zwind_envelope_check: bool = True


class SiteSpec(BaseModel):
    location_name: str = ""
    water_depth_m: float | None = None
    Hs_m: float | None = None
    Tp_s: float | None = None
    wind_ref_m_s: float | None = None
    sea_state_envelope: SeaStateEnvelope = Field(default_factory=SeaStateEnvelope)

    @field_validator("Hs_m")
    @classmethod
    def clamp_hs(cls, v: float | None) -> float | None:
        if v is None:
            return None
        return max(0.0, min(20.0, float(v)))

    @field_validator("Tp_s")
    @classmethod
    def clamp_tp(cls, v: float | None) -> float | None:
        if v is None:
            return None
        return max(1.0, min(30.0, float(v)))


class ReviewerThreshold(BaseModel):
    S_min: float = 85.0
    subscore_min: float = 60.0


class RegulatorySpec(BaseModel):
    certification_path: str = "CCS_AIP"
    standards: list[str] = Field(default_factory=list)
    clause_ids: list[str] = Field(default_factory=list)
    reviewer_threshold: ReviewerThreshold = Field(default_factory=ReviewerThreshold)


class ExcitationBand(BaseModel):
    hz_min: float = 0.0
    hz_max: float = 0.0


class ExcitationBands(BaseModel):
    one_p: ExcitationBand = Field(default_factory=lambda: ExcitationBand(hz_min=0.08, hz_max=0.12))
    three_p: ExcitationBand = Field(default_factory=lambda: ExcitationBand(hz_min=0.24, hz_max=0.35))


class PerformanceTargets(BaseModel):
    steel_intensity_t_per_MW: float = 300.0
    unit_cost_cny_per_MW: float | None = None
    pitch_limit_deg: float = 5.0
    fatigue_design_life_years: float = 25.0
    excitation_bands_hz: ExcitationBands = Field(default_factory=ExcitationBands)


class StructuralAssumptions(BaseModel):
    draft_m: float = 20.0
    wall_thickness_m: float = 0.06
    scale_factor: float = 1.0


class BesoTheta(BaseModel):
    mass_goal_ratio: float = 0.15
    filter_radius: float = 2.0
    optimization_base: str = "stiffness"
    save_every: int = 1


class Oc4LoadsTheta(BaseModel):
    band_scale: float = 1.22
    z_fix_band: float = 800.0
    cload_mag: float = -5.0e6


class SizingTheta(BaseModel):
    optimizer: str = "SLSQP"


class ThetaSpec(BaseModel):
    beso: BesoTheta = Field(default_factory=BesoTheta)
    oc4_loads: Oc4LoadsTheta = Field(default_factory=Oc4LoadsTheta)
    sizing: SizingTheta = Field(default_factory=SizingTheta)


class RetryPolicy(BaseModel):
    max_retries: int = 3
    on_mesh_fail: str = "refine_mesh"
    on_solver_fail: str = "relax_increment"


class JobDescriptor(BaseModel):
    phase: str = "I"
    theta: ThetaSpec = Field(default_factory=ThetaSpec)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)


class DesignChecklist(BaseModel):
    meta: ChecklistMeta = Field(default_factory=ChecklistMeta)
    project: ProjectSpec = Field(default_factory=ProjectSpec)
    site: SiteSpec = Field(default_factory=SiteSpec)
    regulatory: RegulatorySpec = Field(default_factory=RegulatorySpec)
    performance_targets: PerformanceTargets = Field(default_factory=PerformanceTargets)
    structural_assumptions: StructuralAssumptions = Field(default_factory=StructuralAssumptions)
    job_descriptor: JobDescriptor = Field(default_factory=JobDescriptor)
    assumptions: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    # field_ids the user answered or accepted as default during clarification
    clarified_field_ids: list[str] = Field(default_factory=list)

    def model_dump_json_safe(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
