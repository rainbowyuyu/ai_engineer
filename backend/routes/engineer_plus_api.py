"""Unified API for the construction-neutral plus runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.engineer_plus.registry import default_registry
from backend.engineer_plus.service import review_and_select, run_registered_loop
from backend.engineer_plus.preflight import runtime_preflight

router = APIRouter(tags=["engineer-plus"])


class ReviewSelectIn(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128)
    construction: str = Field(..., min_length=1, max_length=128)
    geometry_paths: list[str] = Field(..., min_length=1, max_length=32)
    checklist_id: str | None = None


class RunLoopIn(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128)
    construction: str = Field(default="", max_length=128)
    requirements: dict[str, Any] = Field(default_factory=dict)
    candidate_count: int = Field(default=1, ge=1, le=8)
    checklist_id: str | None = None


@router.get("/constructions")
def constructions() -> dict[str, Any]:
    return {"ok": True, "constructions": default_registry.catalog(),
            "registration_errors": default_registry.registration_errors()}


@router.get("/preflight")
def preflight() -> dict[str, Any]:
    return {"ok": True, **runtime_preflight()}


@router.post("/run")
def run_loop(body: RunLoopIn) -> dict[str, Any]:
    root = Path(os.environ.get("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
    readiness = runtime_preflight()
    if not readiness["ready_for_live"]:
        raise HTTPException(status_code=424, detail={"message": "正式闭环尚未具备运行条件，未启动任务", "missing": readiness["missing"], "ready_for_physics": readiness["ready_for_physics"], "ready_for_ai_review": readiness["ready_for_ai_review"]})
    try:
        return run_registered_loop(task_id=body.task_id, construction=body.construction,
                                   requirements=body.requirements, candidate_count=body.candidate_count,
                                   workspace_root=root, checklist_id=body.checklist_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"closed loop failed: {exc}") from exc


@router.post("/review-select")
def review_select(body: ReviewSelectIn) -> dict[str, Any]:
    root = Path(os.environ.get("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
    readiness = runtime_preflight()
    if not readiness["ready_for_ai_review"]:
        raise HTTPException(status_code=424, detail={"message": "真实 AI review 未配置，未执行候选选择", "missing": readiness["missing"]})
    try:
        return review_and_select(task_id=body.task_id, construction=body.construction,
                                 geometry_paths=body.geometry_paths, workspace_root=root,
                                 checklist_id=body.checklist_id)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"review-select failed: {exc}") from exc
