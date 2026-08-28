"""Tests for paper Fig. 2 Zwind envelope adapter."""
from __future__ import annotations

from backend.surrogate.zwind_adapter import (
    PAPER_FIG2_METRICS,
    envelope_from_comparison,
    envelope_from_paper_fig2,
    load_paper_fig2_metrics,
)


def test_paper_fig2_metrics_file_exists():
    assert PAPER_FIG2_METRICS.is_file()
    raw = load_paper_fig2_metrics()
    assert "fig2b" in raw and "fig2e" in raw


def test_envelope_from_paper_fig2_ai():
    env = envelope_from_paper_fig2("ai")
    assert env["system_frequency_hz"] == 0.487
    assert env["platform_pitch_deg"] == 9.56
    assert env["mooring_tension_kn"] == 13037.0


def test_envelope_from_comparison_prefers_paper_fig2():
    env = envelope_from_comparison("ai")
    assert env["system_frequency_hz"] == 0.487
    # UC / fatigue still filled from comparison YAML
    assert "structural_uc_max" in env
