"""Prism / beso9-style design-domain demo API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from backend.pipeline import steps as pipe

router = APIRouter(tags=["prism-design"])


class PrismDemoRequest(BaseModel):
    text: str = Field(..., description="Natural-language design brief (Chinese/English)")
    task_id: str | None = None
    checklist_id: str | None = None
    start_beso: bool = True
    auto_start: bool = True
    execution_mode: str | None = None


class PrismParseRequest(BaseModel):
    text: str


@router.post("/parse")
def parse_brief(body: PrismParseRequest) -> dict[str, Any]:
    try:
        return pipe.step_parse_prism_design_brief(text=body.text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/demo")
def run_demo(body: PrismDemoRequest = Body(...)) -> dict[str, Any]:
    """One-shot prism topology demo: parse → FreeCAD build → mesh → async BESO."""
    text = str(body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    try:
        out = pipe.step_run_prism_topology_demo(
            text=text,
            task_id=body.task_id,
            design_checklist_id=body.checklist_id,
            start_beso=body.start_beso,
            auto_start=body.auto_start,
            execution_mode=body.execution_mode,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if not out.get("ok") and out.get("preview"):
        raise HTTPException(status_code=409, detail=out.get("error") or "preview mode")
    return out


@router.post("/session")
def start_session(body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    try:
        return pipe.step_start_prism_session(
            text=str(body.get("text") or "").strip() or None,
            spec=body.get("spec") if isinstance(body.get("spec"), dict) else None,
            task_id=str(body.get("task_id") or "").strip() or None,
            design_checklist_id=str(body.get("checklist_id") or "").strip() or None,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/build/{session_id}")
def build_session(session_id: str, execution_mode: str | None = None) -> dict[str, Any]:
    try:
        out = pipe.step_build_prism_design_domain(session_id=session_id, execution_mode=execution_mode)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if not out.get("ok") and out.get("preview"):
        raise HTTPException(status_code=409, detail=out.get("error") or "preview mode")
    return out


@router.post("/mesh/{session_id}")
def mesh_session(session_id: str, execution_mode: str | None = None) -> dict[str, Any]:
    try:
        out = pipe.step_mesh_prism_design_domain(session_id=session_id, execution_mode=execution_mode)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if not out.get("ok") and out.get("preview"):
        raise HTTPException(status_code=409, detail=out.get("error") or "preview mode")
    return out
