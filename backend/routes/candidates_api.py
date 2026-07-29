"""Design candidate registry API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.candidates.registry import list_candidates, register_candidate, select_best

router = APIRouter(tags=["candidates"])


class RegisterCandidateIn(BaseModel):
    task_id: str
    label: str = Field(default="candidate")
    geometry_path: str | None = None
    validation_id: str | None = None
    overall_score: float = 0.0
    version: bool = True


@router.post("/register")
def candidates_register(body: RegisterCandidateIn) -> dict:
    entry = register_candidate(
        body.task_id,
        label=body.label,
        geometry_path=body.geometry_path,
        validation_id=body.validation_id,
        overall_score=body.overall_score,
    )
    payload: dict = {"ok": True, "candidate": entry}
    if body.version:
        try:
            from backend.versions.store import commit_candidate_snapshot

            payload["version"] = commit_candidate_snapshot(
                body.task_id,
                action="register",
                candidate=entry,
                message=f"register · {body.label}",
            )
        except Exception as e:
            payload["version_error"] = str(e)[:400]
    return payload


@router.get("")
def candidates_list(task_id: str) -> dict:
    return {"ok": True, "candidates": list_candidates(task_id)}


class SelectCandidateIn(BaseModel):
    task_id: str
    candidate_id: str
    version: bool = True


@router.post("/select")
def candidates_select(body: SelectCandidateIn) -> dict:
    from backend.candidates.registry import select_candidate

    entry = select_candidate(body.task_id, body.candidate_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="候选不存在")
    payload: dict = {"ok": True, "candidate": entry}
    if body.version:
        try:
            from backend.versions.store import commit_candidate_snapshot

            payload["version"] = commit_candidate_snapshot(
                body.task_id,
                action="select_best",
                candidate=entry,
                message=f"select · {entry.get('label')}",
            )
        except Exception as e:
            payload["version_error"] = str(e)[:400]
    return payload


class SelectBestIn(BaseModel):
    task_id: str
    version: bool = True


@router.post("/select-best")
def candidates_select_best(body: SelectBestIn) -> dict:
    best = select_best(body.task_id)
    if best is None:
        raise HTTPException(status_code=404, detail="无候选记录")
    payload: dict = {"ok": True, "candidate": best, "best": best}
    if body.version:
        try:
            from backend.versions.store import commit_candidate_snapshot

            payload["version"] = commit_candidate_snapshot(
                body.task_id,
                action="select_best",
                candidate=best,
                message=f"select-best · {best.get('label')}",
            )
        except Exception as e:
            payload["version_error"] = str(e)[:400]
    return payload
