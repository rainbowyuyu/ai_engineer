"""Zwind eval step wired to third_party/zwind_newmodel."""
from __future__ import annotations

from backend.replan.zwind_adapter import run_zwind_subprocess_placeholder
from backend.tools.zwind_eval import evaluate_zwind_bundle


def test_evaluate_zwind_bundle_import(tmp_path):
    out = evaluate_zwind_bundle(run_dir=tmp_path, platform="ai", prefer_live=False)
    assert out["ok"] is True
    assert out["mode"] == "paper_fig2_import"
    assert out["highlights"]["tower_1st_fa_hz"] == 0.487
    assert out["highlights"]["extreme_pitch_deg"] == 9.56
    assert (tmp_path / "zwind_report.json").is_file()
    assert (tmp_path / "zwind_fig2_metrics.json").is_file()
    assert out["pass_checks"]["extreme_pitch_within_limit"] is True
    assert out["pass_checks"]["mooring_within_limit"] is True
    # panels copied when available
    assert (tmp_path / "zwind_fig2").is_dir()


def test_replan_placeholder_uses_newmodel():
    out = run_zwind_subprocess_placeholder(prefer_live=False)
    assert out["ok"] is True
    assert "envelope" in out
    assert out["envelope"]["system_frequency_hz"] == 0.487
