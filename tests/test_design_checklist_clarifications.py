"""Tests for interactive design checklist clarifications."""
from __future__ import annotations

from backend.design_requirements.clarifications import (
    apply_clarification_reply,
    build_pending_clarifications,
)
from backend.design_requirements.rule_fallback import parse_rule_fallback


def test_pending_asks_missing_fields_not_silent_defaults():
    text = "阳江三山 20MW 半潜 Hs=12 Tp=14 钢耗 300 t/MW CCS AIP"
    cl = parse_rule_fallback(text)
    pending = build_pending_clarifications(text, cl)
    ids = {p["field_id"] for p in pending}
    assert "target_capacity_mw" not in ids
    assert "Hs_m" not in ids
    assert "steel_intensity_t_per_MW" not in ids
    assert "water_depth_m" in ids
    assert "wind_ref_m_s" in ids
    assert "fatigue_design_life_years" in ids


def test_clarify_use_defaults_locks_remaining():
    text = "20MW Hs=12 钢耗 300 t/MW"
    cl = parse_rule_fallback(text)
    pending = build_pending_clarifications(text, cl)
    assert pending
    updated, assumptions, remaining = apply_clarification_reply(
        cl,
        "用默认",
        pending_field_ids=[p["field_id"] for p in pending],
    )
    assert remaining == []
    assert updated.clarified_field_ids
    assert any("默认" in a for a in assumptions)


def test_clarify_partial_numeric_reply():
    text = "20MW Hs=12 钢耗 300 t/MW"
    cl = parse_rule_fallback(text)
    pending = build_pending_clarifications(text, cl)
    updated, _, remaining = apply_clarification_reply(
        cl,
        "水深 50 m，风速 12 m/s",
        pending_field_ids=[p["field_id"] for p in pending],
    )
    assert updated.site.water_depth_m == 50.0
    assert updated.site.wind_ref_m_s == 12.0
    rem_ids = {p["field_id"] for p in remaining}
    assert "water_depth_m" not in rem_ids
    assert "wind_ref_m_s" not in rem_ids
    assert "fatigue_design_life_years" in rem_ids
