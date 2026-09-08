"""LangChain @tool wrappers for assistant-side CAD / pipeline actions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool

_PIPELINE_TOOL_NAMES = (
    "probe_execution",
    "set_execution_mode",
    "apply_turbine_preset",
    "start_design_domain_session",
    "run_design_domain_build",
    "request_human_edit",
    "apply_geometry_patch",
    "commit_preview_to_session",
    "start_beso_job",
    "get_job_status",
    "run_sizing",
    "run_platform_restruction",
    "run_zwind_eval",
    "run_validation",
    "evaluate_halt",
    "parse_prism_design_brief",
    "start_prism_session",
    "build_prism_design_domain",
    "mesh_prism_design_domain",
    "run_prism_topology_demo",
)


def build_assistant_langchain_tools(
    *,
    workspace_root: Path,
    runs_root: Path,
    client_actions: list[dict[str, Any]],
    design_checklist_id: str | None = None,
) -> list[StructuredTool]:
    """Build LangChain tools that delegate to ``assistant_tool_loop._run_assistant_tool``."""
    from backend.assistant_tool_loop import _run_assistant_tool

    def _wrap(name: str, description: str, schema: dict[str, Any] | None = None) -> StructuredTool:
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
        _wrap("cad_convert", "Convert CAD file (step/iges/stl/brep) under workspace."),
        _wrap("open_results_viewer", "Open topology optimization results viewer for scan_dir."),
        _wrap("list_scan_dir", "List input files in scan_dir."),
        _wrap("cad_skill_help", "Return text-to-cad skill documentation."),
        _wrap("cad_skill_step", "Run build123d STEP generator script."),
        _wrap("open_cad_explorer", "Open CAD Explorer tab for a STEP file."),
        _wrap("cad_drawing_pack", "Generate engineering drawing PNG/PDF pack."),
        _wrap("export_design_deliverables", "Export INP design-space deliverables."),
        _wrap("get_design_checklist", "Read Phase I design checklist summary."),
        _wrap("update_design_checklist", "Update Phase I checklist from user reply."),
        _wrap("probe_execution", "Probe FreeCAD/CalculiX/gmsh and recommend live|preview."),
        _wrap("set_execution_mode", "Set BESO_EXECUTION_MODE to live or preview."),
        _wrap("apply_turbine_preset", "Apply 5/10/15/20 MW turbine preset to checklist/session."),
        _wrap("start_design_domain_session", "Create OC4 design-domain session from IGES upload/path."),
        _wrap("run_design_domain_build", "Build design domain, optional HITL pause before mesh."),
        _wrap("request_human_edit", "Pause for human geometry review/edit."),
        _wrap("apply_geometry_patch", "Replace session geometry and invalidate downstream."),
        _wrap("commit_preview_to_session", "Commit results-viewer preview into design-domain session."),
        _wrap("start_beso_job", "Start live CalculiX–BESO job from session or inp."),
        _wrap("get_job_status", "Poll BESO job status."),
        _wrap("run_sizing", "Steel sizing / scale optimization for target MW (includes platform_restruction)."),
        _wrap(
            "run_platform_restruction",
            "Platform-DB scale optimize (OC4/DTU/VolturnUS); opens 尺寸时域分析 UI.",
        ),
        _wrap(
            "run_zwind_eval",
            "Zwind Fig.2 envelope check; opens 尺寸时域分析 UI with figures.",
        ),
        _wrap("run_validation", "Run Automated Reviewer validation scoring."),
        _wrap("evaluate_halt", "Evaluate S≥85 halt gate."),
        _wrap(
            "parse_prism_design_brief",
            "Parse Chinese/English prompt into prism design-domain parameters (center ring load + three bottom arcs).",
        ),
        _wrap("start_prism_session", "Create prism design-domain session under runs/_prism_sessions/."),
        _wrap("build_prism_design_domain", "FreeCAD-build equilateral prism + dig-outs + load ring."),
        _wrap("mesh_prism_design_domain", "Gmsh mesh prism session to 03_for_beso.inp (skip OC4 loads)."),
        _wrap(
            "run_prism_topology_demo",
            "One-shot: parse → FreeCAD build → mesh → async live BESO (prism design domain).",
        ),
    ]
    return tools


__all__ = ["build_assistant_langchain_tools", "_PIPELINE_TOOL_NAMES"]
