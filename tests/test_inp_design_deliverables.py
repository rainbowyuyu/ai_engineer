"""Design deliverables export + download resolve."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.tools.inp_design_deliverables import build_inp_design_deliverables


@pytest.fixture
def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parents[1])).resolve()


def test_build_inp_design_deliverables(workspace_root: Path) -> None:
    inp = workspace_root / "beso" / "wiki_files" / "example_1" / "Plane_mesh.inp"
    if not inp.is_file():
        pytest.skip(f"missing {inp}")
    out = build_inp_design_deliverables(
        "beso/wiki_files/example_1/Plane_mesh.inp",
        workspace_root=workspace_root,
        runs_root=workspace_root / "runs",
    )
    assert out.get("pack_id")
    files = out.get("files") or {}
    for name in (
        "design_space_preview.png",
        "design_space_nodes.csv",
        "design_space_elements.csv",
        "design_space_surface.stl",
    ):
        assert name in files
        rel = files[name].lstrip("/")
        assert (workspace_root / rel).is_file()
