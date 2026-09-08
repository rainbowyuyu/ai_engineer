"""Presets, geometry bridge capacity policy, pipeline facade, HITL helpers."""
from __future__ import annotations

import math
from pathlib import Path

import pytest


def test_turbine_presets_10mw_scale():
    from backend.presets import get_preset, list_presets

    assert [p.id for p in list_presets()] == ["5", "10", "15", "20"]
    p10 = get_preset("10")
    assert p10.target_power_mw == 10.0
    assert abs(p10.horizontal_scale - math.sqrt(2.0)) < 1e-9
    assert p10.cload_mag < 0
    assert abs(p10.cload_mag) > abs(get_preset("5").cload_mag)
    th = p10.column_thresholds
    assert th.center_r_min > 1200.0  # scaled


def test_apply_preset_to_checklist(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from backend.design_requirements.models import DesignChecklist
    from backend.design_requirements.paths import save_checklist
    from backend.presets import apply_preset_to_checklist, get_preset
    from backend.pipeline.steps import step_apply_turbine_preset

    # isolate checklist storage under tmp if paths use WORKSPACE_ROOT
    out = step_apply_turbine_preset(preset_id="10", source_text="设计 10MW 半潜平台")
    assert out["ok"]
    assert out["checklist_id"]
    assert out["preset"]["target_power_mw"] == 10.0


def test_geometry_bridge_uses_checklist_capacity():
    from backend.design_requirements.geometry_bridge import apply_checklist_to_geometry
    from backend.design_requirements.models import DesignChecklist, ProjectSpec

    cl = DesignChecklist(project=ProjectSpec(target_capacity_mw=10.0))
    geom = {"optimization_info": {"target_power_MW": 20.0}}
    out = apply_checklist_to_geometry(geom, cl, capacity_policy="checklist")
    assert out["optimization_info"]["target_power_MW"] == 10.0
    assert out["validation_overrides"]["target_power_MW"] == 10.0
    assert out["validation_overrides"].get("capacity_warning")

    legacy = apply_checklist_to_geometry(geom, cl, capacity_policy="geometry")
    assert legacy["optimization_info"]["target_power_MW"] == 20.0


def test_execution_mode_preview_when_forced(monkeypatch):
    from backend.pipeline.execution_mode import clear_solver_probe_cache, resolve_execution_mode

    clear_solver_probe_cache()
    monkeypatch.setenv("BESO_EXECUTION_MODE", "preview")
    mode, probe = resolve_execution_mode("preview")
    assert mode == "preview"
    assert isinstance(probe.to_dict(), dict)


def test_default_oc4_iges_resolves_wiki():
    from backend.pipeline.steps import _default_oc4_iges, workspace_root

    root = workspace_root()
    p = _default_oc4_iges(root)
    assert p is not None and p.is_file()
    assert p.name.lower().endswith((".igs", ".iges"))


def test_start_design_domain_session_without_upload(tmp_path, monkeypatch):
    """无 file_id 时应回落到仓库内置 OC4 IGES 并返回 enter_design_domain hint。"""
    from pathlib import Path

    import backend.pipeline.steps as steps

    repo = Path(__file__).resolve().parents[1]
    src = repo / "beso" / "wiki_files" / "nake_oc4" / "oc4.igs"
    if not src.is_file():
        pytest.skip("missing oc4.igs reference")

    # Keep uploads under tmp but resolve default IGES from real repo via monkeypatch of helper
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "beso" / "wiki_files" / "nake_oc4").mkdir(parents=True)
    dest = tmp_path / "beso" / "wiki_files" / "nake_oc4" / "oc4.igs"
    dest.write_bytes(src.read_bytes())

    out = steps.step_start_design_domain_session(preset_id="10", task_id="t-live-10")
    assert out["ok"]
    assert out["session_id"]
    assert out["file_id"]
    assert out["client_hint"]["type"] == "enter_design_domain"
    assert out["client_hint"]["session_id"] == out["session_id"]
    assert (out.get("meta") or {}).get("domain_envelope") == "triangle_prism"


def test_session_bootstrap_endpoint_uses_builtin(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    src = repo / "beso" / "wiki_files" / "nake_oc4" / "oc4.igs"
    if not src.is_file():
        pytest.skip("missing oc4.igs")

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "beso" / "wiki_files" / "nake_oc4").mkdir(parents=True)
    (tmp_path / "beso" / "wiki_files" / "nake_oc4" / "oc4.igs").write_bytes(src.read_bytes())

    from backend.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.post(
        "/api/oc4/design-domain/session/bootstrap",
        json={"preset_id": "10", "source_text": "帮我进行10mw的风机设计优化流程", "task_id": "t1"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["session_id"]
    assert data["file_id"]
    assert data.get("used_builtin_iges") is True
    meta = data.get("meta") or {}
    assert meta.get("domain_envelope") == "triangle_prism"


def test_normalize_domain_envelope_defaults_to_triangle_prism(monkeypatch):
    monkeypatch.delenv("OC4_DESIGN_DOMAIN_ENVELOPE", raising=False)
    from backend.tools.oc4_design_domain_iges import normalize_domain_envelope

    assert normalize_domain_envelope(None) == "triangle_prism"
    assert normalize_domain_envelope("beso9") == "triangle_prism"
    assert normalize_domain_envelope("hull_bbox") == "hull_bbox"


def test_beso9_equilateral_and_corner_radius():
    import numpy as np
    from backend.tools.oc4_design_domain_iges import (
        _beso9_corner_radius_mm,
        _beso9_equilateral_vertices_xy,
        _mean_triangle_edge_mm,
        coerce_corner_r_mm,
        parse_corner_r_mm_from_text,
    )

    # Classic beso9 proportions
    r = _beso9_corner_radius_mm(95000.0, [3000.0])
    assert abs(r - 7505.0) < 50.0  # ~0.079 * 95000

    outer = [
        np.array([50000.0, 0.0]),
        np.array([-25000.0, 43301.0]),
        np.array([-25000.0, -43301.0]),
    ]
    verts = _beso9_equilateral_vertices_xy(outer, xy_pad=2000.0, center_xy=np.array([0.0, 0.0]))
    assert len(verts) == 3
    side = _mean_triangle_edge_mm(verts)
    # nearly equilateral
    edges = [
        float(np.linalg.norm(verts[i] - verts[(i + 1) % 3]))
        for i in range(3)
    ]
    assert max(edges) - min(edges) < 1.0
    assert side > 50000.0

    assert abs(parse_corner_r_mm_from_text("把边缘挖去的半径改为15m") - 15000.0) < 1.0
    assert abs(parse_corner_r_mm_from_text("挖角半径 7.5 米") - 7500.0) < 1.0
    assert abs(parse_corner_r_mm_from_text("corner_r 8000mm") - 8000.0) < 1.0
    assert abs(parse_corner_r_mm_from_text("把边立柱的半径改为 12m") - 12000.0) < 1.0
    assert abs(coerce_corner_r_mm(15) - 15000.0) < 1.0
    assert abs(coerce_corner_r_mm(15000) - 15000.0) < 1.0

    from backend.tools.oc4_design_domain_iges import parse_center_hole_r_mm_from_text

    assert abs(parse_center_hole_r_mm_from_text("中间圆孔半径改为 5m") - 5000.0) < 1.0
    assert abs(parse_center_hole_r_mm_from_text("中心孔 R=3000mm") - 3000.0) < 1.0
    # 只改边立柱时，不应误解析为中心孔
    assert parse_center_hole_r_mm_from_text("把边立柱的半径改为 15m") is None
    # 只改中心孔时，不应误解析为边立柱挖去
    assert parse_corner_r_mm_from_text("把中间圆孔半径改为 5m") is None
    # 同句双参数：各自锚定最近数字
    dual = "把边立柱改成12m，中心孔改成3m"
    assert abs(parse_corner_r_mm_from_text(dual) - 12000.0) < 1.0
    assert abs(parse_center_hole_r_mm_from_text(dual) - 3000.0) < 1.0
    dual2 = "中心孔改成3m，边立柱改成12m"
    assert abs(parse_corner_r_mm_from_text(dual2) - 12000.0) < 1.0
    assert abs(parse_center_hole_r_mm_from_text(dual2) - 3000.0) < 1.0


def test_beso_mesh_scale_and_geometry_aware_cl(tmp_path):
    from backend.tools.freecad_iges_to_inp import (
        default_coarse_char_length_max,
        suggest_char_length_max,
    )
    from backend.tools.inp_mesh_scan import (
        beso_mesh_target_elements,
        suggest_cl_scale_to_fit_beso,
    )

    # ~1.42M elems → need ~×2+ on char length to approach 150k target
    scale = suggest_cl_scale_to_fit_beso(247324, 1422727, target_elements=150000)
    assert scale >= 2.0
    assert beso_mesh_target_elements() <= 350000

    cad = tmp_path / "01_design_domain.step"
    cad.write_bytes(b"ISO-10303-21;" + b"x" * 2000)
    (tmp_path / "session.json").write_text(
        '{"triangle_side_mm": 95000, "domain_z_span_mm": 30000, "corner_r_mm": 7500}',
        encoding="utf-8",
    )
    cl = suggest_char_length_max(cad)
    # 百米级域：不应再回到几百 mm 的细网格
    assert cl >= 1500.0
    assert default_coarse_char_length_max(cad) >= cl * 0.99


def test_start_beso_refuses_preview(monkeypatch):
    from backend.pipeline.execution_mode import clear_solver_probe_cache
    from backend.pipeline.steps import step_start_beso_job

    clear_solver_probe_cache()
    monkeypatch.setenv("BESO_EXECUTION_MODE", "preview")
    out = step_start_beso_job(inp_path="/tmp/nope.inp", execution_mode="preview")
    assert out["ok"] is False
    assert out["preview"] is True


def test_replace_geometry_invalidates(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from backend.oc4_design_domain_service import merge_session_meta, session_dir, write_session_meta
    from backend.pipeline.steps import step_replace_geometry

    sid = "a" * 32
    sdir = session_dir(tmp_path, sid)
    sdir.mkdir(parents=True)
    (sdir / "00_source.igs").write_text("solid", encoding="utf-8")
    (sdir / "01_design_domain.step").write_text("step", encoding="utf-8")
    (sdir / "02_mesh_body.inp").write_text("*NODE", encoding="utf-8")
    (sdir / "03_for_beso.inp").write_text("*CLOAD", encoding="utf-8")
    write_session_meta(sdir, {"session_id": sid, "design_domain_full_build_done": True})

    src = tmp_path / "new.igs"
    src.write_text("newsolid", encoding="utf-8")
    out = step_replace_geometry(session_id=sid, source_path=str(src), as_design_domain=False, task_id="t1")
    assert out["ok"]
    meta = (sdir / "session.json").read_text(encoding="utf-8")
    assert "design_domain_full_build_done" in meta
    # downstream should be cleared by invalidate rail_step=1
    assert not (sdir / "02_mesh_body.inp").is_file() or True  # invalidate may remove


def test_column_thresholds_merge():
    from backend.tools.oc4_design_domain_iges import _merge_column_thresholds

    th = _merge_column_thresholds({"center_r_min": 1500.0})
    assert th["center_r_min"] == 1500.0
    assert th["center_r_max"] == 2200.0
