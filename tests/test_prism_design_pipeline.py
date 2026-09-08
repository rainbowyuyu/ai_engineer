"""Prism design-domain brief parsing and preview-mode guards."""
from __future__ import annotations

import pytest


def test_parse_prism_brief_defaults():
    from backend.tools.prism_design_domain import parse_prism_design_brief

    spec = parse_prism_design_brief("")
    assert spec.side_mm == 95000.0
    assert abs(spec.force_n - 2.45e7) < 1.0
    assert abs(spec.mass_goal_ratio - 0.15) < 1e-9


def test_parse_prism_brief_chinese_overrides():
    from backend.tools.prism_design_domain import parse_prism_design_brief

    spec = parse_prism_design_brief(
        "按 beso9 做边长 80 m、挖角半径 6 m、体积分数 5%，粗网格快演示，载荷仍 2.45e7 N"
    )
    assert abs(spec.side_mm - 80000.0) < 1.0
    assert abs(spec.corner_r_mm - 6000.0) < 1.0
    assert abs(spec.mass_goal_ratio - 0.05) < 1e-9
    assert spec.fast_demo is True
    assert spec.mesh_max_mm >= 4000.0


def test_design_spec_json_fields():
    from backend.tools.prism_design_domain import (
        PrismDesignSpec,
        design_spec_json_from_prism,
    )

    spec = PrismDesignSpec(mass_goal_ratio=0.05)
    d = design_spec_json_from_prism(spec)
    assert d["side_length_mm"] == 95000.0
    assert d["mass_goal_ratio"] == 0.05
    assert d["load_application"] == "circumference_edge"
    assert len(d["sharp_vertices_xy_mm"]) == 3


def test_step_parse_and_session(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from backend.pipeline.steps import step_parse_prism_design_brief, step_start_prism_session

    parsed = step_parse_prism_design_brief(text="体积分数 10%，边长 95 m")
    assert parsed["ok"]
    assert abs(parsed["spec"]["mass_goal_ratio"] - 0.10) < 1e-9

    sess = step_start_prism_session(text="体积分数 10%")
    assert sess["ok"]
    sid = sess["session_id"]
    sdir = tmp_path / "runs" / "_prism_sessions" / sid
    assert (sdir / "prism_spec.json").is_file()
    assert (sdir / "design_spec.json").is_file()
    assert (sdir / "meta.json").is_file()


def test_prism_build_refuses_preview(tmp_path, monkeypatch):
    from backend.pipeline.execution_mode import clear_solver_probe_cache
    from backend.pipeline.steps import step_build_prism_design_domain, step_start_prism_session

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    clear_solver_probe_cache()
    monkeypatch.setenv("BESO_EXECUTION_MODE", "preview")
    sess = step_start_prism_session(text="beso9 默认")
    out = step_build_prism_design_domain(session_id=sess["session_id"], execution_mode="preview")
    assert out["ok"] is False
    assert out["preview"] is True


def test_prism_topology_demo_preview_stops_before_fake_beso(tmp_path, monkeypatch):
    from backend.pipeline.execution_mode import clear_solver_probe_cache
    from backend.pipeline.steps import step_run_prism_topology_demo

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    clear_solver_probe_cache()
    monkeypatch.setenv("BESO_EXECUTION_MODE", "preview")
    out = step_run_prism_topology_demo(text="按 beso9 体积分数 5%", execution_mode="preview")
    assert out.get("ok") is False
    assert out.get("phase") == "build" or out.get("preview") or out.get("error")
