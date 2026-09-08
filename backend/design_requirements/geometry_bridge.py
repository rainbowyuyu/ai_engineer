"""Apply design checklist to geometry dict for validation / downstream."""
from __future__ import annotations

from typing import Any

from backend.design_requirements.models import DesignChecklist


def apply_checklist_to_geometry(
    geometry: dict[str, Any],
    checklist: DesignChecklist,
    *,
    capacity_policy: str = "checklist",
) -> dict[str, Any]:
    """Inject validation_overrides and design_checklist snapshot.

    ``capacity_policy``:
      - ``checklist`` (default): scoring / optimization_info follow checklist capacity.
      - ``geometry``: keep native geometry capacity (legacy soft-align when drift > 3 MW).
      - ``warn``: use checklist but record drift warnings when |Δ| > 3 MW.
    """
    out = dict(geometry)
    opt0 = dict(out.get("optimization_info") or {})
    native_power = float(opt0.get("target_power_MW") or checklist.project.target_capacity_mw or 20.0)
    cl_cap = float(checklist.project.target_capacity_mw or native_power)
    drift = abs(cl_cap - native_power)
    policy = (capacity_policy or "checklist").strip().lower()
    if policy == "geometry":
        score_cap = native_power if drift > 3.0 else cl_cap
    else:
        score_cap = cl_cap

    vo = dict(out.get("validation_overrides") or {})
    vo["target_power_MW"] = score_cap
    vo["validation_target_mw"] = score_cap
    if drift > 3.0:
        vo["checklist_capacity_mw"] = cl_cap
        vo["geometry_native_capacity_mw"] = native_power
        vo["capacity_drift_mw"] = drift
        vo["capacity_policy"] = policy
        if policy == "checklist":
            vo["capacity_warning"] = (
                f"Checklist capacity {cl_cap:g} MW differs from geometry native {native_power:g} MW; "
                "using checklist (re-run sizing / scale geometry to match)."
            )
        elif policy == "geometry":
            vo["capacity_aligned_from_mw"] = native_power
    if checklist.performance_targets.steel_intensity_t_per_MW:
        vo.setdefault("steel_intensity_t_per_MW", checklist.performance_targets.steel_intensity_t_per_MW)
    if checklist.performance_targets.unit_cost_cny_per_MW:
        vo.setdefault("unit_cost_cny_per_MW", checklist.performance_targets.unit_cost_cny_per_MW)
    if checklist.performance_targets.fatigue_design_life_years:
        vo.setdefault("fatigue_life_years", checklist.performance_targets.fatigue_design_life_years)
    out["validation_overrides"] = vo
    opt = dict(opt0)
    opt["target_power_MW"] = score_cap
    opt["wall_thickness_m"] = checklist.structural_assumptions.wall_thickness_m
    opt["scale_factor"] = checklist.structural_assumptions.scale_factor
    opt["draft_m"] = checklist.structural_assumptions.draft_m
    if checklist.structural_assumptions.scale_factor:
        opt.setdefault("base_rated_power_MW", 5.0)
    out["optimization_info"] = opt
    out["design_checklist"] = checklist.model_dump(mode="json")
    return out


def checklist_assumption_notes(checklist: DesignChecklist | None) -> list[str]:
    if checklist is None:
        return []
    notes = [
        f"Phase I 设计清单约束（id={checklist.meta.checklist_id[:8]}…，parser={checklist.meta.parser}）",
    ]
    if checklist.project.target_capacity_mw:
        notes.append(f"目标容量 {checklist.project.target_capacity_mw:g} MW")
    if checklist.performance_targets.steel_intensity_t_per_MW:
        notes.append(f"钢耗目标 {checklist.performance_targets.steel_intensity_t_per_MW} t/MW")
    if checklist.site.Hs_m is not None:
        notes.append(f"场址 Hs={checklist.site.Hs_m} m, Tp={checklist.site.Tp_s} s（参考）")
    notes.extend(checklist.assumptions[:5])
    return notes
