"""Assistant tool: cad_drawing_pack."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.assistant_tool_loop import _run_assistant_tool


@pytest.fixture
def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parents[1])).resolve()


def test_cad_drawing_pack_tool_generates_sheet(workspace_root: Path) -> None:
    inp = workspace_root / "beso" / "wiki_files" / "example_1" / "Plane_mesh.inp"
    if not inp.is_file():
        pytest.skip(f"missing fixture inp: {inp}")

    client_actions: list = []
    ok, summary, extra = _run_assistant_tool(
        "cad_drawing_pack",
        {"input_path": "beso/wiki_files/example_1/Plane_mesh.inp", "title": "test sheet"},
        workspace_root=workspace_root,
        runs_root=workspace_root / "runs",
        client_actions=client_actions,
    )
    assert ok, summary
    assert extra.get("sheet_url", "").startswith("/runs/_cad_drawings/")
    assert extra.get("pdf_url", "").startswith("/runs/_cad_drawings/")
    assert extra.get("source_path") == "beso/wiki_files/example_1/Plane_mesh.inp"
    assert extra.get("scale")
    assert client_actions and client_actions[0]["type"] == "show_cad_drawing"
    assert client_actions[0]["sheet_url"] == extra["sheet_url"]
    assert client_actions[0].get("pdf_url") == extra["pdf_url"]
