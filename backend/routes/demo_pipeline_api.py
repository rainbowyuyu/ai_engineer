"""BESO7 live pipeline demo API — drives main workbench end-to-end story."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.demo.beso7_live_pipeline import (
    bootstrap_beso7_live_demo,
    build_pipeline_deliverables_summary,
    build_task_version_tree,
    check_finalize_gate,
    confirm_candidate_selection,
    run_candidate_select_step,
    run_drawing_step,
    run_finalize_step,
    run_mesh_replan_step,
    run_orchestrate_job_step,
    run_reconstruction_step,
    run_review_replan_step,
    run_sizing_step,
    run_solver_replan_step,
    run_validation_step,
    seed_beso7_job_artifacts,
)

router = APIRouter(tags=["demo-pipeline"])


def _workspace_root() -> Path:
    import os

    return Path(os.environ.get("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()


class BootstrapIn(BaseModel):
    task_id: str | None = Field(default=None, description="主页任务 ID；空则自动生成")


class MeshReplanIn(BaseModel):
    task_id: str
    session_id: str | None = None


class FinalizeIn(BaseModel):
    task_id: str
    session_id: str
    clear_rho: bool = True


class OrchestrateIn(BaseModel):
    task_id: str
    checklist_id: str | None = None
    scan_dir: str
    mass_goal_ratio: float | None = 0.15
    filter_radius: float | None = 2.0


class SolverReplanIn(BaseModel):
    task_id: str
    job_id: str | None = None


@router.post("/beso7-live-pipeline/bootstrap")
def demo_beso7_bootstrap(body: BootstrapIn | None = None) -> dict[str, Any]:
    body = body or BootstrapIn()
    try:
        return bootstrap_beso7_live_demo(_workspace_root(), task_id=body.task_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"bootstrap 失败: {e}") from e


@router.post("/beso7-live-pipeline/mesh-replan")
def demo_beso7_mesh_replan(body: MeshReplanIn) -> dict[str, Any]:
    try:
        return run_mesh_replan_step(body.task_id, session_id=body.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"mesh replan 失败: {e}") from e


class GateIn(BaseModel):
    task_id: str


@router.post("/beso7-live-pipeline/check-gate")
def demo_beso7_check_gate(body: GateIn) -> dict[str, Any]:
    try:
        return check_finalize_gate(body.task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"gate 检查失败: {e}") from e


@router.post("/beso7-live-pipeline/finalize")
def demo_beso7_finalize(body: FinalizeIn) -> dict[str, Any]:
    try:
        return run_finalize_step(
            _workspace_root(),
            session_id=body.session_id,
            task_id=body.task_id,
            clear_rho=body.clear_rho,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"finalize 失败: {e}") from e


@router.post("/beso7-live-pipeline/orchestrate")
def demo_beso7_orchestrate(body: OrchestrateIn) -> dict[str, Any]:
    try:
        return run_orchestrate_job_step(
            scan_dir=body.scan_dir,
            task_id=body.task_id,
            checklist_id=body.checklist_id,
            mass_goal_ratio=float(body.mass_goal_ratio if body.mass_goal_ratio is not None else 0.15),
            filter_radius=float(body.filter_radius if body.filter_radius is not None else 2.0),
            seed_artifacts=True,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"orchestrate 失败: {e}") from e


class ReconstructIn(BaseModel):
    task_id: str | None = None
    job_id: str


@router.post("/beso7-live-pipeline/reconstruct")
def demo_beso7_reconstruct(body: ReconstructIn) -> dict[str, Any]:
    try:
        return run_reconstruction_step(
            _workspace_root(),
            job_id=body.job_id,
            task_id=body.task_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"reconstruct 失败: {e}") from e


class SizingIn(BaseModel):
    task_id: str | None = None
    job_id: str
    target_power_mw: float | None = 20.0


@router.post("/beso7-live-pipeline/sizing")
def demo_beso7_sizing(body: SizingIn) -> dict[str, Any]:
    try:
        return run_sizing_step(
            _workspace_root(),
            job_id=body.job_id,
            task_id=body.task_id,
            target_power_mw=body.target_power_mw,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"sizing 失败: {e}") from e


class SeedIn(BaseModel):
    job_id: str
    task_id: str | None = None

@router.post("/beso7-live-pipeline/seed-artifacts")
def demo_beso7_seed(body: SeedIn) -> dict[str, Any]:
    try:
        return seed_beso7_job_artifacts(_workspace_root(), job_id=body.job_id, task_id=body.task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"seed 失败: {e}") from e


class CandidateIn(BaseModel):
    task_id: str
    auto_select: bool = False


@router.post("/beso7-live-pipeline/candidates")
def demo_beso7_candidates(body: CandidateIn) -> dict[str, Any]:
    try:
        return run_candidate_select_step(body.task_id, auto_select=bool(body.auto_select))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"candidates 失败: {e}") from e


class SelectCandidateIn(BaseModel):
    task_id: str
    candidate_id: str


@router.post("/beso7-live-pipeline/select-candidate")
def demo_beso7_select_candidate(body: SelectCandidateIn) -> dict[str, Any]:
    try:
        return confirm_candidate_selection(body.task_id, body.candidate_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"select 失败: {e}") from e


@router.get("/beso7-live-pipeline/version-tree")
def demo_beso7_version_tree(task_id: str) -> dict[str, Any]:
    try:
        return build_task_version_tree(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"version-tree 失败: {e}") from e


@router.post("/beso7-live-pipeline/solver-replan")
def demo_beso7_solver_replan(body: SolverReplanIn) -> dict[str, Any]:
    try:
        return run_solver_replan_step(body.task_id, job_id=body.job_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"solver replan 失败: {e}") from e


class ValidationStepIn(BaseModel):
    task_id: str
    checklist_id: str | None = None
    candidate_label: str | None = None


@router.post("/beso7-live-pipeline/validate")
def demo_beso7_validate(body: ValidationStepIn) -> dict[str, Any]:
    try:
        return run_validation_step(
            body.task_id,
            checklist_id=body.checklist_id,
            candidate_label=body.candidate_label or "BESO7 · 选定方案",
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"validation 失败: {e}") from e


class ReviewReplanIn(BaseModel):
    task_id: str
    checklist_id: str | None = None
    candidate_label: str | None = None
    previous_validation: dict[str, Any] | None = None


@router.post("/beso7-live-pipeline/review-replan")
def demo_beso7_review_replan(body: ReviewReplanIn) -> dict[str, Any]:
    try:
        return run_review_replan_step(
            body.task_id,
            checklist_id=body.checklist_id,
            candidate_label=body.candidate_label or "BESO7 · 重规划后方案",
            previous_validation=body.previous_validation,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"review replan 失败: {e}") from e


class DrawingStepIn(BaseModel):
    task_id: str
    job_id: str | None = None
    session_id: str | None = None


@router.post("/beso7-live-pipeline/drawing")
def demo_beso7_drawing(body: DrawingStepIn) -> dict[str, Any]:
    try:
        return run_drawing_step(
            _workspace_root(),
            task_id=body.task_id,
            job_id=body.job_id,
            session_id=body.session_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"drawing 失败: {e}") from e


class DeliverablesIn(BaseModel):
    task_id: str
    job_id: str | None = None
    session_id: str | None = None
    selected_label: str | None = None
    validation: dict[str, Any] | None = None
    drawing: dict[str, Any] | None = None


@router.post("/beso7-live-pipeline/deliverables")
def demo_beso7_deliverables(body: DeliverablesIn) -> dict[str, Any]:
    try:
        return build_pipeline_deliverables_summary(
            _workspace_root(),
            task_id=body.task_id,
            job_id=body.job_id,
            session_id=body.session_id,
            validation=body.validation,
            drawing=body.drawing,
            selected_label=body.selected_label,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"deliverables 失败: {e}") from e


@router.post("/beso7-live-pipeline/run-all")
def demo_beso7_run_all(body: BootstrapIn | None = None) -> dict[str, Any]:
    """Server-side full chain (for smoke / demo_hub). Frontend prefers step-by-step + UI."""
    body = body or BootstrapIn()
    boot = demo_beso7_bootstrap(body)
    mesh = demo_beso7_mesh_replan(MeshReplanIn(task_id=boot["task_id"], session_id=boot["session_id"]))
    gate_blocked = check_finalize_gate(boot["task_id"])
    fin = demo_beso7_finalize(
        FinalizeIn(task_id=boot["task_id"], session_id=boot["session_id"], clear_rho=True)
    )
    gate_ok = check_finalize_gate(boot["task_id"])
    orch = demo_beso7_orchestrate(
        OrchestrateIn(
            task_id=boot["task_id"],
            checklist_id=boot["checklist_id"],
            scan_dir=fin["scan_dir"],
            mass_goal_ratio=float((fin.get("beso_theta") or {}).get("mass_goal_ratio") or 0.15),
            filter_radius=float((fin.get("beso_theta") or {}).get("filter_radius") or 2.0),
        )
    )
    recon = demo_beso7_reconstruct(ReconstructIn(task_id=boot["task_id"], job_id=orch["job_id"]))
    sizing = demo_beso7_sizing(
        SizingIn(task_id=boot["task_id"], job_id=orch["job_id"], target_power_mw=20.0)
    )
    solver = demo_beso7_solver_replan(SolverReplanIn(task_id=boot["task_id"], job_id=orch["job_id"]))
    return {
        "ok": True,
        "bootstrap": boot,
        "mesh_replan": mesh,
        "gate_blocked": gate_blocked,
        "finalize": fin,
        "gate_ok": gate_ok,
        "orchestrate": orch,
        "reconstruct": recon,
        "sizing": sizing,
        "solver_replan": solver,
        "pipeline": [
            {"id": "bootstrap", "title": boot.get("process", {}).get("title"), "io": boot.get("io")},
            {"id": "mesh", "title": mesh.get("process", {}).get("title"), "io": mesh.get("io")},
            {"id": "gate_block", "title": gate_blocked.get("process", {}).get("title"), "io": gate_blocked.get("io")},
            {"id": "finalize", "title": fin.get("process", {}).get("title"), "io": fin.get("io")},
            {"id": "orchestrate", "title": orch.get("process", {}).get("title"), "io": orch.get("io")},
            {"id": "reconstruct", "title": recon.get("process", {}).get("title"), "io": recon.get("io")},
            {"id": "sizing", "title": sizing.get("process", {}).get("title"), "io": sizing.get("io")},
            {"id": "solver", "title": solver.get("process", {}).get("title"), "io": solver.get("io")},
        ],
    }
