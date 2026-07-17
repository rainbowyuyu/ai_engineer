"""Replan API — evaluate F_p, apply replan(θ,F_p), Table S.1 demos."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.replan.engine import evaluate_feedback, replan
from backend.replan.guided import attach_guided, build_guided_steps
from backend.replan.paths import load_event
from backend.replan.simulate_cases import run_case_demo

router = APIRouter(tags=["replan"])


class EvaluateIn(BaseModel):
    phase: str = "II"
    step: str = ""
    logs: str | list[str] | None = None
    metrics: dict[str, Any] | None = None


class ApplyIn(BaseModel):
    theta: dict[str, Any] = Field(default_factory=dict)
    feedback: dict[str, Any] | None = None
    phase: str = "II"
    step: str = ""
    logs: str | list[str] | None = None
    metrics: dict[str, Any] | None = None
    design_checklist_id: str | None = None
    persist: bool = True


@router.post("/evaluate")
def replan_evaluate(body: EvaluateIn) -> dict[str, Any]:
    fb = evaluate_feedback(phase=body.phase, step=body.step, logs=body.logs, metrics=body.metrics)
    return {"feedback": fb.model_dump(mode="json")}


@router.post("/apply")
def replan_apply(body: ApplyIn) -> dict[str, Any]:
    checklist = None
    if body.design_checklist_id:
        from backend.design_requirements.paths import load_checklist

        checklist = load_checklist(body.design_checklist_id)
        if checklist is None:
            raise HTTPException(status_code=404, detail=f"设计清单不存在: {body.design_checklist_id}")

    if body.feedback:
        from backend.replan.models import FeedbackTuple

        fb = FeedbackTuple.model_validate(body.feedback)
    else:
        fb = evaluate_feedback(phase=body.phase, step=body.step, logs=body.logs, metrics=body.metrics)

    result = replan(body.theta, fb, checklist=checklist, persist=body.persist)
    payload = {
        "ok": True,
        "message": result.message,
        "feedback": result.feedback.model_dump(mode="json"),
        "actions": [a.model_dump(mode="json") for a in result.actions],
        "theta_before": result.theta_before,
        "theta_after": result.theta_after,
        "event": result.event.model_dump(mode="json") if result.event else None,
        "event_id": result.event.event_id if result.event else None,
    }
    guided = attach_guided(
        {
            "case_id": None,
            "title": "流程内失败驱动重规划",
            "feedback_before": payload["feedback"],
            "feedback_after": {"rho_p": 0},
            "result": {
                "actions": payload["actions"],
                "theta_before": payload["theta_before"],
                "theta_after": payload["theta_after"],
                "event": payload["event"],
            },
            "outcome": {"note": result.message, "status": "planned"},
            "ok": True,
        }
    )
    payload["guided_steps"] = guided.get("guided_steps")
    payload["resume"] = guided.get("resume")
    return payload


@router.post("/cases/{case_id}/demo")
def replan_case_demo(case_id: str) -> dict[str, Any]:
    try:
        out = run_case_demo(case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"案例演示失败: {e}") from e
    return out


@router.get("/events/{event_id}")
def replan_get_event(event_id: str) -> dict[str, Any]:
    ev = load_event(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="重规划事件不存在")
    return {"event": ev.model_dump(mode="json")}
