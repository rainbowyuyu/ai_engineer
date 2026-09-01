"""LangChain @tool wrappers for assistant-side CAD / deliverable actions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool


def build_assistant_langchain_tools(
    *,
    workspace_root: Path,
    runs_root: Path,
    client_actions: list[dict[str, Any]],
    design_checklist_id: str | None = None,
) -> list[StructuredTool]:
    """Build LangChain tools that delegate to ``assistant_tool_loop._run_assistant_tool``."""
    from backend.assistant_tool_loop import _run_assistant_tool

    def _wrap(name: str, description: str, schema: dict[str, Any]) -> StructuredTool:
        def _fn(**kwargs: Any) -> str:
            ok, summary, extra = _run_assistant_tool(
                name,
                kwargs,
                workspace_root=workspace_root,
                runs_root=runs_root,
                client_actions=client_actions,
                design_checklist_id=design_checklist_id,
            )
            import json

            payload = {"ok": ok, "summary": summary, **(extra if isinstance(extra, dict) else {})}
            return json.dumps(payload, ensure_ascii=False)[:24_000]

        return StructuredTool.from_function(
            func=_fn,
            name=name,
            description=description,
            args_schema=None,
        )

    tools: list[StructuredTool] = [
        _wrap(
            "cad_convert",
            "Convert CAD file (step/iges/stl/brep) under workspace.",
            {},
        ),
        _wrap("open_results_viewer", "Open topology optimization results viewer for scan_dir.", {}),
        _wrap("list_scan_dir", "List input files in scan_dir.", {}),
        _wrap("cad_skill_help", "Return text-to-cad skill documentation.", {}),
        _wrap("cad_skill_step", "Run build123d STEP generator script.", {}),
        _wrap("open_cad_explorer", "Open CAD Explorer tab for a STEP file.", {}),
        _wrap("cad_drawing_pack", "Generate engineering drawing PNG/PDF pack.", {}),
        _wrap("export_design_deliverables", "Export INP design-space deliverables.", {}),
        _wrap("get_design_checklist", "Read Phase I design checklist summary.", {}),
        _wrap("update_design_checklist", "Update Phase I checklist from user reply.", {}),
    ]
    return tools


__all__ = ["build_assistant_langchain_tools"]
