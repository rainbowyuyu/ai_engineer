"""Tests for interactive design checklist clarifications and post-lock edits."""
from __future__ import annotations

from backend.design_requirements.clarifications import (
    apply_clarification_reply,
    build_pending_clarifications,
    checklist_context_block,
    extract_field_updates,
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
    updated, assumptions, remaining, updated_fields = apply_clarification_reply(
        cl,
        "用默认",
        pending_field_ids=[p["field_id"] for p in pending],
    )
    assert remaining == []
    assert updated.clarified_field_ids
    assert any("默认" in a for a in assumptions)
    assert updated_fields


def test_clarify_partial_numeric_reply():
    text = "20MW Hs=12 钢耗 300 t/MW"
    cl = parse_rule_fallback(text)
    pending = build_pending_clarifications(text, cl)
    updated, _, remaining, updated_fields = apply_clarification_reply(
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
    assert {u["field_id"] for u in updated_fields} >= {"water_depth_m", "wind_ref_m_s"}


def test_clarify_can_revise_already_set_field():
    text = "20MW Hs=12 钢耗 300 t/MW"
    cl = parse_rule_fallback(text)
    pending = build_pending_clarifications(text, cl)
    updated, _, _, updated_fields = apply_clarification_reply(
        cl,
        "水深 50，钢耗改为 280 t/MW",
        pending_field_ids=[p["field_id"] for p in pending],
        mode="clarify",
    )
    assert updated.site.water_depth_m == 50.0
    assert updated.performance_targets.steel_intensity_t_per_MW == 280.0
    assert any(u["field_id"] == "steel_intensity_t_per_MW" for u in updated_fields)


def test_edit_mode_updates_locked_checklist():
    text = "20MW Hs=12 Tp=14 水深50 风速11 钢耗 300 t/MW 静倾5 疲劳25年"
    cl = parse_rule_fallback(text)
    # lock all via clarify defaults/mentions
    pending = build_pending_clarifications(text, cl)
    if pending:
        cl, _, remaining, _ = apply_clarification_reply(
            cl, "用默认", pending_field_ids=[p["field_id"] for p in pending]
        )
        assert remaining == []
    updated, assumptions, remaining, fields = apply_clarification_reply(
        cl,
        "钢耗改为 260 t/MW，水深 60",
        mode="edit",
    )
    assert remaining == []
    assert updated.performance_targets.steel_intensity_t_per_MW == 260.0
    assert updated.site.water_depth_m == 60.0
    assert len(fields) >= 2
    assert any("修订" in a for a in assumptions)


def test_edit_mode_without_numbers_returns_empty_updates():
    text = "20MW Hs=12 钢耗 300 t/MW"
    cl = parse_rule_fallback(text)
    _, _, _, fields = apply_clarification_reply(cl, "请帮我看看清单怎么样", mode="edit")
    assert fields == []


def test_extract_field_updates_and_context_block():
    ups = extract_field_updates("静倾改为 4 度，疲劳 30 年")
    assert ups.get("pitch_limit_deg") == 4.0
    assert ups.get("fatigue_design_life_years") == 30.0
    cl = parse_rule_fallback("20MW Hs=12 钢耗 300 t/MW")
    block = checklist_context_block(cl)
    assert "checklist_id=" in block
    assert "钢耗" in block or "t/MW" in block
