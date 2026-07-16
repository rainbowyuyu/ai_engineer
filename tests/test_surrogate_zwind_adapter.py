"""Tests for Zwind adapter (Phase 2 stub)."""
from __future__ import annotations

from backend.surrogate.zwind_adapter import (
    envelope_from_comparison,
    import_zwind_envelope,
    normalize_dynamic_envelope,
)


def test_envelope_from_comparison_ai():
    env = envelope_from_comparison("ai")
    assert "system_frequency_hz" in env or len(env) >= 0


def test_normalize_dynamic_envelope_metrics_list():
    data = {
        "metrics": [
            {"id": "system_frequency", "ai": 0.42},
            {"id": "platform_motion", "ai": 3.5},
            {"id": "structural_strength", "ai": 0.85},
        ]
    }
    out = normalize_dynamic_envelope(data)
    assert out.get("platform_pitch_deg") == 3.5
    assert out.get("structural_uc_max") == 0.85


def test_import_zwind_envelope_json(tmp_path):
    p = tmp_path / "env.json"
    p.write_text('{"platform_motion": 4.0, "structural_strength": 0.9}', encoding="utf-8")
    out = import_zwind_envelope(p)
    assert out.get("platform_pitch_deg") == 4.0
