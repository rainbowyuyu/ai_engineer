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
    task_id: str | None = None
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
    # Optional task-scoped file versioning (git-like)
    task_id = str(body.task_id or "").strip() or None
    version_info = None
    if task_id and result.event:
        try:
            from backend.replan.paths import replan_root
            from backend.versions.store import commit_replan_snapshot

            ev_path = replan_root() / result.event.event_id / "replan_event.json"
            version_info = commit_replan_snapshot(
                task_id,
                event_id=result.event.event_id,
                theta_before=result.theta_before,
                theta_after=result.theta_after,
                event_path=ev_path if ev_path.is_file() else None,
                message=f"replan apply · {result.message[:80]}",
            )
        except Exception:
            version_info = None
    if version_info:
        payload["version"] = version_info
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
def replan_case_demo(case_id: str, task_id: str | None = None) -> dict[str, Any]:
    try:
        out = run_case_demo(case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"案例演示失败: {e}") from e
    tid = str(task_id or "").strip()
    if tid:
        try:
            from backend.replan.paths import replan_root
            from backend.versions.store import commit_replan_snapshot

            result = out.get("result") or {}
            event = result.get("event") or {}
            eid = event.get("event_id")
            ev_path = replan_root() / str(eid) / "replan_event.json" if eid else None
            out["version"] = commit_replan_snapshot(
                tid,
                event_id=eid,
                theta_before=result.get("theta_before"),
                theta_after=result.get("theta_after"),
                event_path=ev_path if ev_path and ev_path.is_file() else None,
                message=f"replan demo · {case_id}",
                case_id=case_id,
            )
        except Exception as e:
            out["version_error"] = str(e)[:400]
    return out


@router.get("/events/{event_id}")
def replan_get_event(event_id: str) -> dict[str, Any]:
    ev = load_event(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="重规划事件不存在")
    return {"event": ev.model_dump(mode="json")}


class ResumeIn(BaseModel):
    target: str = Field(..., description="mesh | beso | zwind | home")
    theta_after: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    scan_dir: str | None = None
    design_checklist_id: str | None = None
    task_id: str | None = None
    mass_goal_ratio: float | None = None
    filter_radius: float | None = None


@router.post("/resume")
def replan_resume(body: ResumeIn) -> dict[str, Any]:
    """Return executable payloads for front-end CTA after guided journey."""
    target = str(body.target or "home").strip().lower()
    theta = dict(body.theta_after or {})
    if target == "mesh":
        mesh_body: dict[str, Any] = {"session_id": body.session_id}
        cl = theta.get("characteristic_length_max")
        if cl is not None:
            mesh_body["characteristic_length_max"] = float(cl)
        if body.design_checklist_id:
            mesh_body["design_checklist_id"] = body.design_checklist_id
        return {"ok": True, "target": "mesh", "mesh_body": mesh_body, "api_path": "/api/oc4/design-domain/mesh"}

    if target == "beso":
        chat_body: dict[str, Any] = {
            "message": "按重规划建议重跑 BESO / CalculiX",
            "auto_start": True,
        }
        if body.scan_dir:
            chat_body["scan_dir"] = body.scan_dir
        if body.design_checklist_id:
            chat_body["design_checklist_id"] = body.design_checklist_id
        if body.task_id:
            chat_body["task_id"] = body.task_id
        mg = body.mass_goal_ratio if body.mass_goal_ratio is not None else theta.get("mass_goal_ratio")
        fr = body.filter_radius if body.filter_radius is not None else theta.get("filter_radius")
        if mg is not None:
            chat_body["mass_goal_ratio"] = float(mg)
        if fr is not None:
            chat_body["filter_radius"] = float(fr)
        solver_overrides = {
            k: theta[k]
            for k in ("max_iterations", "load_increment", "restart_increment", "load_increment_first_n")
            if k in theta
        }
        return {
            "ok": True,
            "target": "beso",
            "chat_body": chat_body,
            "solver_overrides": solver_overrides,
            "api_path": "/api/chat",
        }

    return {"ok": True, "target": target, "message": "无额外动作"}
