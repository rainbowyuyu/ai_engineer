"""Rule-based NL parsing when Qwen is unavailable."""
from __future__ import annotations

import re
import uuid
from typing import Any

from backend.design_requirements.config import load_defaults
from backend.design_requirements.models import (
    DesignChecklist,
    ExcitationBand,
    ExcitationBands,
    JobDescriptor,
    PerformanceTargets,
    ProjectSpec,
    RegulatorySpec,
    ReviewerThreshold,
    SeaStateEnvelope,
    SiteSpec,
    StructuralAssumptions,
    ThetaSpec,
)


def _extract_float(patterns: list[str], text: str) -> float | None:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except (ValueError, IndexError):
                continue
    return None


def match_clause_ids(text: str) -> list[str]:
    defaults = load_defaults()
    kw_map: dict[str, list[str]] = dict(defaults.get("clause_keyword_map") or {})
    found: list[str] = []
    seen: set[str] = set()
    for kw, ids in kw_map.items():
        if kw in text:
            for cid in ids:
                if cid not in seen:
                    seen.add(cid)
                    found.append(cid)
    reg_default = list((defaults.get("regulatory") or {}).get("clause_ids") or [])
    for cid in reg_default:
        if cid not in seen:
            seen.add(cid)
            found.append(cid)
    return found


def parse_rule_fallback(text: str, *, checklist_id: str | None = None) -> DesignChecklist:
    t = (text or "").strip()
    defaults = load_defaults()
    cid = checklist_id or uuid.uuid4().hex

    mw = _extract_float(
        [r"(\d+(?:\.\d+)?)\s*MW", r"(\d+(?:\.\d+)?)\s*兆瓦"],
        t,
    )
    hs = _extract_float([r"Hs\s*[=≈]?\s*(\d+(?:\.\d+)?)", r"有效波高\s*(\d+(?:\.\d+)?)"], t)
    tp = _extract_float([r"Tp\s*[=≈]?\s*(\d+(?:\.\d+)?)", r"谱峰周期\s*(\d+(?:\.\d+)?)"], t)
    depth = _extract_float([r"水深\s*(\d+(?:\.\d+)?)", r"(\d+(?:\.\d+)?)\s*m\s*水深"], t)
    steel = _extract_float(
        [r"(\d+(?:\.\d+)?)\s*t\s*/\s*MW", r"钢耗[^\d]*(\d+(?:\.\d+)?)", r"(\d+(?:\.\d+)?)\s*t/MW"],
        t,
    )

    proj_d = defaults.get("project") or {}
    site_d = defaults.get("site") or {}
    reg_d = defaults.get("regulatory") or {}
    perf_d = defaults.get("performance_targets") or {}
    struct_d = defaults.get("structural_assumptions") or {}
    job_d = defaults.get("job_descriptor") or {}

    assumptions: list[str] = []
    gaps: list[str] = []

    # Missing-field notes moved to interactive clarification (clarifications.py)

    env_d = site_d.get("sea_state_envelope") or {}
    exc_d = perf_d.get("excitation_bands_hz") or {}

    cl = DesignChecklist(
        meta={
            "checklist_id": cid,
            "created_at": DesignChecklist.now_iso(),
            "source_text": t,
            "parser": "rule_fallback",
            "reasoning_summary": "规则回退：正则抽取关键数值并合并 design_checklist_defaults.yaml",
        },
        project=ProjectSpec(
            title=str(proj_d.get("title") or ""),
            owner_intent_zh=t[:200] if t else str(proj_d.get("owner_intent_zh") or ""),
            target_capacity_mw=mw if mw is not None else float(proj_d.get("target_capacity_mw") or 20),
            platform_type=str(proj_d.get("platform_type") or "semi_submersible"),
        ),
        site=SiteSpec(
            location_name=str(site_d.get("location_name") or ""),
            water_depth_m=depth if depth is not None else site_d.get("water_depth_m"),
            Hs_m=hs if hs is not None else site_d.get("Hs_m"),
            Tp_s=tp if tp is not None else site_d.get("Tp_s"),
            wind_ref_m_s=site_d.get("wind_ref_m_s"),
            sea_state_envelope=SeaStateEnvelope(
                reference=str(env_d.get("reference") or ""),
                labels=list(env_d.get("labels") or []),
                zwind_envelope_check=bool(env_d.get("zwind_envelope_check", True)),
            ),
        ),
        regulatory=RegulatorySpec(
            certification_path=str(reg_d.get("certification_path") or "CCS_AIP"),
            standards=list(reg_d.get("standards") or []),
            clause_ids=match_clause_ids(t),
            reviewer_threshold=ReviewerThreshold(**(reg_d.get("reviewer_threshold") or {})),
        ),
        performance_targets=PerformanceTargets(
            steel_intensity_t_per_MW=steel if steel is not None else float(perf_d.get("steel_intensity_t_per_MW") or 300),
            unit_cost_cny_per_MW=perf_d.get("unit_cost_cny_per_MW"),
            pitch_limit_deg=float(perf_d.get("pitch_limit_deg") or 5),
            fatigue_design_life_years=float(perf_d.get("fatigue_design_life_years") or 25),
            excitation_bands_hz=ExcitationBands(
                one_p=ExcitationBand(**(exc_d.get("one_p") or {"hz_min": 0.08, "hz_max": 0.12})),
                three_p=ExcitationBand(**(exc_d.get("three_p") or {"hz_min": 0.24, "hz_max": 0.35})),
            ),
        ),
        structural_assumptions=StructuralAssumptions(**struct_d),
        job_descriptor=JobDescriptor.model_validate(job_d),
        assumptions=assumptions,
        gaps=gaps,
    )
    return cl


def merge_partial_dict(base: DesignChecklist, partial: dict[str, Any]) -> DesignChecklist:
    """Deep-merge LLM partial dict onto base checklist."""
    merged = base.model_dump()
    for key in ("project", "site", "regulatory", "performance_targets", "structural_assumptions", "job_descriptor"):
        if key in partial and isinstance(partial[key], dict):
            section = dict(merged.get(key) or {})
            section.update(partial[key])
            merged[key] = section
    if partial.get("assumptions"):
        merged["assumptions"] = list(merged.get("assumptions") or []) + list(partial["assumptions"])
    if partial.get("gaps"):
        merged["gaps"] = list(merged.get("gaps") or []) + list(partial["gaps"])
    if partial.get("meta") and isinstance(partial["meta"], dict):
        m = dict(merged.get("meta") or {})
        m.update(partial["meta"])
        merged["meta"] = m
    return DesignChecklist.model_validate(merged)
