"""Tests for S>=85 halt gate."""
from __future__ import annotations

from backend.orchestrator.halt import evaluate_halt_gate


def test_halt_gate_fails_below_85():
    v = evaluate_halt_gate(
        overall_score=84.9,
        ai_review_scores={"a": 70, "b": 80},
    )
    assert v.ok is False
    assert v.should_archive is False


def test_halt_gate_fails_subscore_below_60():
    v = evaluate_halt_gate(
        overall_score=90.0,
        ai_review_scores={"a": 59.9, "b": 90},
    )
    assert v.ok is False


def test_halt_gate_passes():
    v = evaluate_halt_gate(
        overall_score=85.0,
        ai_review_scores={"a": 60, "b": 72},
        regulatory_review_scores={"r1": 65},
    )
    assert v.ok is True
    assert v.should_archive is True
    assert v.min_subscore >= 60


def test_halt_gate_ignores_low_regulatory_when_ai_ok():
    """Regulatory alignment scores must not veto an AI-Review pass."""
    v = evaluate_halt_gate(
        overall_score=88.0,
        ai_review_scores={"capacity_mw": 90, "steel_per_mw": 82, "unit_cost": 80},
        regulatory_review_scores={"stability": 40, "layout": 45},
    )
    assert v.ok is True
    assert v.min_subscore >= 60


def test_halt_gate_reason_mentions_weak_subscore():
    v = evaluate_halt_gate(
        overall_score=90.0,
        ai_review_scores={"capacity_mw": 50, "steel_per_mw": 88},
    )
    assert v.ok is False
    assert "子分" in v.reason
    assert "capacity_mw" in v.reason
