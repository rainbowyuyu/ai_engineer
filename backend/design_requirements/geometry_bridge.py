"""Apply design checklist to geometry dict for validation / downstream."""
from __future__ import annotations

from typing import Any

from backend.design_requirements.models import DesignChecklist


def apply_checklist_to_geometry(geometry: dict[str, Any], checklist: DesignChecklist) -> dict[str, Any]:
    """Inject validation_overrides and design_checklist snapshot."""
    out = dict(geometry)
    vo = dict(out.get("validation_overrides") or {})
    vo["target_power_MW"] = checklist.project.target_capacity_mw
    if checklist.performance_targets.steel_intensity_t_per_MW:
        vo.setdefault("steel_intensity_t_per_MW", checklist.performance_targets.steel_intensity_t_per_MW)
    if checklist.performance_targets.unit_cost_cny_per_MW:
        vo.setdefault("unit_cost_cny_per_MW", checklist.performance_targets.unit_cost_cny_per_MW)
    if checklist.performance_targets.fatigue_design_life_years:
        vo.setdefault("fatigue_life_years", checklist.performance_targets.fatigue_design_life_years)
    out["validation_overrides"] = vo
    opt = dict(out.get("optimization_info") or {})
    opt["target_power_MW"] = checklist.project.target_capacity_mw
    opt["wall_thickness_m"] = checklist.structural_assumptions.wall_thickness_m
    opt["scale_factor"] = checklist.structural_assumptions.scale_factor
    opt["draft_m"] = checklist.structural_assumptions.draft_m
    out["optimization_info"] = opt
    out["design_checklist"] = checklist.model_dump(mode="json")
    return out


def checklist_assumption_notes(checklist: DesignChecklist | None) -> list[str]:
    if checklist is None:
        return []
    notes = [
        f"Phase I 设计清单约束（id={checklist.meta.checklist_id[:8]}…，parser={checklist.meta.parser}）",
    ]
    if checklist.performance_targets.steel_intensity_t_per_MW:
        notes.append(f"钢耗目标 {checklist.performance_targets.steel_intensity_t_per_MW} t/MW")
    if checklist.site.Hs_m is not None:
        notes.append(f"场址 Hs={checklist.site.Hs_m} m, Tp={checklist.site.Tp_s} s（参考）")
    notes.extend(checklist.assumptions[:5])
    return notes
