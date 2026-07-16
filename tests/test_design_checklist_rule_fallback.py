"""Tests for rule-based design checklist parsing."""
from __future__ import annotations

from backend.design_requirements.rule_fallback import parse_rule_fallback


def test_rule_fallback_extracts_mw_hs_steel():
    text = "业主需求：20MW 半潜式平台，场址 Hs=12 m，钢耗目标 300 t/MW，需满足稳性与水密。"
    cl = parse_rule_fallback(text)
    assert cl.meta.parser == "rule_fallback"
    assert cl.project.target_capacity_mw == 20.0
    assert cl.site.Hs_m == 12.0
    assert cl.performance_targets.steel_intensity_t_per_MW == 300.0
    assert "c301_draft_general" in cl.regulatory.clause_ids or "c301_watertight_envelope" in cl.regulatory.clause_ids
    assert cl.job_descriptor.phase == "I"
    assert cl.job_descriptor.theta.beso.mass_goal_ratio > 0


def test_rule_fallback_defaults_when_sparse():
    from backend.design_requirements.clarifications import build_pending_clarifications

    text = "做个漂浮式基础"
    cl = parse_rule_fallback(text)
    assert cl.project.target_capacity_mw == 20.0
    assert cl.performance_targets.steel_intensity_t_per_MW == 300.0
    pending = build_pending_clarifications(text, cl)
    ids = {p["field_id"] for p in pending}
    assert "target_capacity_mw" in ids
    assert "steel_intensity_t_per_MW" in ids
