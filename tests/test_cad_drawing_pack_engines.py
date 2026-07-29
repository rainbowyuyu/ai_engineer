"""CAD drawing pack: mesh + FreeCAD engines + GA sheet synthesis."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from backend.tools.cad_drawing_pack import (
    build_cad_drawing_pack,
    project_mesh_to_view_polylines,
    render_drawing_sheet,
    render_line_drawing_sheet,
)


@pytest.fixture
def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parents[1])).resolve()


def test_mesh_drawing_from_inp(workspace_root: Path) -> None:
    inp = workspace_root / "beso" / "wiki_files" / "example_1" / "Plane_mesh.inp"
    if not inp.is_file():
        pytest.skip(f"missing {inp}")
    out = build_cad_drawing_pack(
        "beso/wiki_files/example_1/Plane_mesh.inp",
        workspace_root=workspace_root,
        engine="mesh",
        sheet_size="A3",
        layout="ga",
    )
    assert out["ok"]
    assert out["engine"] == "mesh"
    assert out.get("sheet_size") == "A3"
    assert out.get("layout") == "ga"
    assert out.get("scale")
    sheet = workspace_root / out["sheet_url"].lstrip("/")
    assert sheet.is_file()
    pdf = workspace_root / (out.get("pdf_url") or "").lstrip("/")
    assert pdf.is_file()
    assert out["pack"].get("sheet_pdf") == "drawing_sheet.pdf"


def test_freecad_drawing_from_step(workspace_root: Path) -> None:
    step = workspace_root / "third_party" / "text-to-cad" / "STEP" / "demo_mounting_plate.step"
    if not step.is_file():
        pytest.skip(f"missing {step}")
    fc = Path(os.environ.get("FREECAD_CMD", r"D:\freecad\bin\FreeCADCmd.exe"))
    if not fc.is_file():
        pytest.skip("FreeCAD not installed")
    out = build_cad_drawing_pack(
        "third_party/text-to-cad/STEP/demo_mounting_plate.step",
        workspace_root=workspace_root,
        engine="freecad",
        title="pytest freecad",
        layout="ga",
    )
    assert out["ok"]
    assert out["engine"] == "freecad"
    sheet = workspace_root / out["sheet_url"].lstrip("/")
    assert sheet.is_file()
    assert out.get("view_svgs")
    pdf = workspace_root / (out.get("pdf_url") or "").lstrip("/")
    assert pdf.is_file()


def test_ga_sheet_from_fake_views_json(tmp_path: Path) -> None:
    """Synthesize GB/GA sheet from synthetic polylines — no FreeCAD required."""
    views = {
        "top": {
            "polylines": [
                [[0, 0], [100, 0], [100, 60], [0, 60], [0, 0]],
                [[20, 20], [80, 20]],
            ]
        },
        "front": {
            "polylines": [
                [[0, 0], [100, 0], [100, 40], [0, 40], [0, 0]],
            ]
        },
        "right": {
            "polylines": [
                [[0, 0], [60, 0], [60, 40], [0, 40], [0, 0]],
            ]
        },
        "iso": {
            "polylines": [
                [[0, 0], [80, 20], [100, 70], [20, 50], [0, 0]],
            ]
        },
    }
    meta = {
        "ok": True,
        "bbox_mm": {"dx": 100.0, "dy": 60.0, "dz": 40.0},
        "span_mm": 100.0,
        "unit_guess": "mm (test)",
    }
    views_json = tmp_path / "freecad_views.json"
    views_json.write_text(json.dumps({"meta": meta, "views": views}, ensure_ascii=False), encoding="utf-8")
    out_png = tmp_path / "drawing_sheet.png"
    out_pdf = tmp_path / "drawing_sheet.pdf"
    info = render_line_drawing_sheet(
        views_json,
        out_png=out_png,
        out_pdf=out_pdf,
        title="假数据总布置图",
        source_path="tests/fake.step",
        drawing_id="testdraw001",
        sheet_size="A3",
        layout="ga",
    )
    assert out_png.is_file() and out_png.stat().st_size > 1000
    assert out_pdf.is_file() and out_pdf.stat().st_size > 500
    assert info["sheet_size"] == "A3"
    assert info["layout"] == "ga"
    assert str(info["scale"]).startswith("1:")


def test_mesh_outline_not_triangulated_wire(tmp_path: Path) -> None:
    """Mesh path should emit silhouette/boundary edges, not every triangle edge."""
    # Unit cube: 12 triangles → many edges, but outline projection keeps few
    pts = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
        ],
        dtype=float,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [2, 3, 7],
            [2, 7, 6],
            [1, 2, 6],
            [1, 6, 5],
            [0, 3, 7],
            [0, 7, 4],
        ],
        dtype=int,
    )
    polys = project_mesh_to_view_polylines(pts, faces, "top")
    # Top view of a cube: 4 boundary sides (+ hull) — far fewer than 36 half-edges
    assert 4 <= len(polys) <= 40
    out = render_drawing_sheet(
        pts,
        faces,
        out_png=tmp_path / "cube.png",
        title="立方体轮廓",
        sheet_size="A3",
        layout="ga",
    )
    assert (tmp_path / "cube.png").is_file()
    assert (tmp_path / "cube.pdf").is_file()
    assert out["layout"] == "ga"


def test_quad_layout_still_works(tmp_path: Path) -> None:
    views = {
        "top": {"polylines": [[[0, 0], [50, 0], [50, 30], [0, 30], [0, 0]]]},
        "front": {"polylines": [[[0, 0], [50, 0], [50, 20], [0, 20], [0, 0]]]},
        "right": {"polylines": [[[0, 0], [30, 0], [30, 20], [0, 20], [0, 0]]]},
        "iso": {"polylines": [[[0, 0], [40, 10], [50, 35]]]},
    }
    views_json = tmp_path / "freecad_views.json"
    views_json.write_text(json.dumps({"meta": {}, "views": views}), encoding="utf-8")
    out_png = tmp_path / "quad.png"
    info = render_line_drawing_sheet(
        views_json,
        out_png=out_png,
        title="四等分",
        layout="quad",
        sheet_size="A3",
    )
    assert out_png.is_file()
    assert info["layout"] == "quad"
