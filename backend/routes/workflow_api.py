"""Workflow state and halt-and-archive API."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.llm.routing import use_langgraph_pipeline
from backend.orchestrator.gates import evaluate_transition
from backend.orchestrator.halt import evaluate_halt_gate, halt_and_archive
from backend.orchestrator.state import clear_rho_pending, load_workflow_state, save_workflow_state
from backend.validation.paths import find_validation_dir

router = APIRouter(tags=["workflow"])


def _load_state(task_id: str, **kwargs):
    if use_langgraph_pipeline():
        try:
            from backend.graph.pipeline.master_graph import export_workflow_state

            return export_workflow_state(task_id)
        except Exception:
            pass
    return load_workflow_state(task_id, **kwargs)


class HaltArchiveIn(BaseModel):
    task_id: str
    validation_id: str
    design_checklist_id: str | None = None
    geometry_path: str | None = None
    oc4_session_id: str | None = None


@router.get("/state")
def workflow_state(
    task_id: str,
    oc4_session_id: str | None = None,
    design_checklist_id: str | None = None,
) -> dict:
    st = _load_state(task_id, oc4_session_id=oc4_session_id, design_checklist_id=design_checklist_id)
    return {"ok": True, "state": st.model_dump(mode="json")}


@router.get("/can-advance")
def workflow_can_advance(task_id: str, transition: str) -> dict:
    st = _load_state(task_id)
    verdict = evaluate_transition(st, transition)
    return {"ok": verdict.ok, "verdict": verdict.model_dump(mode="json")}


@router.post("/clear-rho")
def workflow_clear_rho(task_id: str) -> dict:
    st = clear_rho_pending(task_id)
    return {"ok": True, "state": st.model_dump(mode="json")}


@router.post("/mark-rho")
def workflow_mark_rho(task_id: str, event_id: str | None = None) -> dict:
    """Demo helper: set rho_pending=1 for workflow gate UX."""
    from backend.orchestrator.state import mark_rho_pending

    st = mark_rho_pending(task_id, event_id=event_id, rho=1)
    return {"ok": True, "state": st.model_dump(mode="json")}


@router.post("/halt-and-archive")
def workflow_halt_and_archive(body: HaltArchiveIn) -> dict:
    vdir = find_validation_dir(body.validation_id)
    if vdir is None:
        raise HTTPException(status_code=404, detail="Validation run not found")
    out = halt_and_archive(
        body.task_id,
        validation_id=body.validation_id,
        validation_dir=vdir,
        design_checklist_id=body.design_checklist_id,
        geometry_path=body.geometry_path,
        oc4_session_id=body.oc4_session_id,
    )
    return out


class EvaluateHaltIn(BaseModel):
    overall_score: float
    ai_review_scores: dict[str, float] | None = None
    regulatory_review_scores: dict[str, float] | None = None
    design_checklist_id: str | None = None


@router.post("/evaluate-halt-gate")
def workflow_evaluate_halt(body: EvaluateHaltIn) -> dict:
    verdict = evaluate_halt_gate(
        overall_score=body.overall_score,
        ai_review_scores=body.ai_review_scores,
        regulatory_review_scores=body.regulatory_review_scores,
        design_checklist_id=body.design_checklist_id,
    )
    return {"ok": True, "halt_gate": verdict.model_dump(mode="json")}


class PipelineRunIn(BaseModel):
    task_id: str
    design_requirements_text: str | None = None
    oc4_session_id: str | None = None
    design_checklist_id: str | None = None


@router.post("/run/stream")
def workflow_run_stream(body: PipelineRunIn):
    """NDJSON stream of Phase I–IV MasterGraph progress (optional internal endpoint)."""
    if not use_langgraph_pipeline():
        raise HTTPException(status_code=400, detail="USE_LANGGRAPH_PIPELINE 未开启或 LangGraph 未安装")

    from backend.graph.pipeline.master_graph import iter_pipeline_stream

    def gen():
        initial = {
            k: v
            for k, v in body.model_dump(mode="json").items()
            if v is not None and k != "task_id"
        }
        for ev in iter_pipeline_stream(body.task_id, initial=initial):
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/invoke-transition")
def workflow_invoke_transition(task_id: str, transition: str) -> dict:
    if not use_langgraph_pipeline():
        st = _load_state(task_id)
        verdict = evaluate_transition(st, transition)
        return {"ok": verdict.ok, "verdict": verdict.model_dump(mode="json"), "state": st.model_dump(mode="json")}

    from backend.graph.pipeline.master_graph import invoke_pipeline_transition

    return invoke_pipeline_transition(task_id, transition)
