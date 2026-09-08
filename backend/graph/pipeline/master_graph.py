"""Phase I–IV MasterGraph — unified closed-loop orchestration."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterator

from backend.graph.pipeline.checkpoint import get_pipeline_checkpointer
from backend.graph.pipeline.state import PipelineState
from backend.orchestrator.gates import can_advance, evaluate_transition
from backend.orchestrator.halt import evaluate_halt_gate
from backend.orchestrator.models import WorkflowState
from backend.orchestrator.state import load_workflow_state, save_workflow_state

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(state: PipelineState, ev: dict[str, Any]) -> dict[str, Any]:
    return {"events": [ev]}


def _phase_i_parse(state: PipelineState) -> dict[str, Any]:
    text = (state.get("design_requirements_text") or "").strip()
    preset = state.get("turbine_preset_id")
    if not text and not state.get("design_checklist_id"):
        return {**_emit(state, {"type": "phase", "phase": "I", "status": "skipped"}), "workflow_phase": "I"}
    try:
        from backend.design_requirements.nl_parser import parse_design_checklist
        from backend.pipeline.steps import step_apply_turbine_preset

        cl_id = state.get("design_checklist_id")
        if text:
            cl = parse_design_checklist(text, checklist_id=cl_id)
            cl_id = cl.meta.checklist_id
        if preset:
            applied = step_apply_turbine_preset(preset_id=preset, checklist_id=cl_id)
            cl_id = applied.get("checklist_id") or cl_id
        return {
            **_emit(state, {"type": "phase", "phase": "I", "status": "ok", "checklist_id": cl_id}),
            "design_checklist_id": cl_id,
            "workflow_phase": "II",
        }
    except Exception as e:
        logger.exception("phase_i_parse failed")
        return {**_emit(state, {"type": "phase", "phase": "I", "status": "error", "message": str(e)}), "error": str(e)}


def _phase_ii_design_domain(state: PipelineState) -> dict[str, Any]:
    from langgraph.types import interrupt

    from backend.pipeline.steps import step_run_design_domain_build, step_start_design_domain_session

    sid = state.get("oc4_session_id")
    if not sid and state.get("auto_create_session"):
        try:
            created = step_start_design_domain_session(
                design_checklist_id=state.get("design_checklist_id"),
                preset_id=state.get("turbine_preset_id"),
                task_id=state.get("task_id"),
            )
            sid = created.get("session_id")
        except Exception as e:
            logger.info("auto create design domain session skipped: %s", e)

    if not sid:
        return {
            **_emit(state, {"type": "phase", "phase": "II", "step": "design_domain", "status": "skipped"}),
            "workflow_phase": "II",
        }

    if state.get("hitl_pause") == "before_mesh":
        payload = interrupt(
            {
                "reason": "hitl_before_mesh",
                "session_id": sid,
                "message": "Review or replace geometry, then resume.",
            }
        )
        if not (isinstance(payload, dict) and (payload.get("continue") or payload.get("hitl_pause") is None)):
            return {
                **_emit(
                    state,
                    {"type": "phase", "phase": "II", "step": "design_domain", "status": "hitl_wait", "session_id": sid},
                ),
                "oc4_session_id": sid,
                "hitl_pause": "before_mesh",
                "workflow_phase": "II",
            }

    try:
        result = step_run_design_domain_build(
            session_id=sid,
            pause_before_mesh=bool(state.get("request_hitl_before_mesh")),
            execution_mode=state.get("execution_mode"),
        )
        if result.get("hitl"):
            interrupt(
                {
                    "reason": "hitl_before_mesh",
                    "session_id": sid,
                    "message": (result.get("hitl") or {}).get("message"),
                }
            )
            return {
                **_emit(
                    state,
                    {"type": "phase", "phase": "II", "step": "design_domain", "status": "hitl_wait", "session_id": sid},
                ),
                "oc4_session_id": sid,
                "hitl_pause": "before_mesh",
                "workflow_phase": "II",
            }
        if not result.get("ok", True):
            return {
                **_emit(
                    state,
                    {
                        "type": "phase",
                        "phase": "II",
                        "step": "design_domain",
                        "status": "preview_blocked" if result.get("preview") else "error",
                        "message": result.get("error"),
                        "session_id": sid,
                    },
                ),
                "oc4_session_id": sid,
                "error": result.get("error"),
                "workflow_phase": "II",
            }
    except Exception as e:
        logger.exception("phase_ii_design_domain failed")
        return {
            **_emit(
                state,
                {"type": "phase", "phase": "II", "step": "design_domain", "status": "error", "message": str(e)},
            ),
            "error": str(e),
            "oc4_session_id": sid,
            "workflow_phase": "II",
        }

    return {
        **_emit(
            state,
            {"type": "phase", "phase": "II", "step": "design_domain", "status": "ready", "session_id": sid},
        ),
        "oc4_session_id": sid,
        "hitl_pause": None,
        "workflow_phase": "II",
    }


def _phase_ii_beso(state: PipelineState) -> dict[str, Any]:
    """Start live BESO via pipeline steps; interrupt until job complete."""
    from langgraph.types import interrupt

    from backend.pipeline.steps import step_get_job_status, step_start_beso_job

    job_id = state.get("beso_job_id")
    status = (state.get("beso_status") or "").lower()
    if status == "complete":
        return {
            **_emit(state, {"type": "phase", "phase": "II", "step": "beso", "status": "complete"}),
            "beso_status": "complete",
            "workflow_phase": "III",
        }

    if not job_id and state.get("oc4_session_id"):
        try:
            started = step_start_beso_job(
                session_id=state.get("oc4_session_id"),
                design_checklist_id=state.get("design_checklist_id"),
                task_id=state.get("task_id"),
                execution_mode=state.get("execution_mode"),
            )
            if not started.get("ok"):
                return {
                    **_emit(
                        state,
                        {
                            "type": "phase",
                            "phase": "II",
                            "step": "beso",
                            "status": "preview_blocked" if started.get("preview") else "error",
                            "message": started.get("error"),
                        },
                    ),
                    "error": started.get("error"),
                    "beso_status": "blocked",
                }
            job_id = started.get("job_id")
        except Exception as e:
            logger.exception("start_beso_job failed")
            return {
                **_emit(state, {"type": "phase", "phase": "II", "step": "beso", "status": "error", "message": str(e)}),
                "error": str(e),
            }

    if job_id:
        try:
            st = step_get_job_status(job_id=job_id)
            if st.get("complete"):
                return {
                    **_emit(state, {"type": "phase", "phase": "II", "step": "beso", "status": "complete"}),
                    "beso_job_id": job_id,
                    "beso_status": "complete",
                    "workflow_phase": "III",
                }
            if st.get("failed"):
                return {
                    **_emit(
                        state,
                        {"type": "phase", "phase": "II", "step": "beso", "status": "failed", "job_id": job_id},
                    ),
                    "beso_job_id": job_id,
                    "beso_status": "failed",
                    "rho_pending": 1,
                }
        except Exception:
            pass

    payload = interrupt(
        {
            "reason": "waiting_for_beso",
            "job_id": job_id,
            "task_id": state.get("task_id"),
        }
    )
    if isinstance(payload, dict) and payload.get("beso_status") == "complete":
        return {
            **_emit(state, {"type": "phase", "phase": "II", "step": "beso", "status": "complete"}),
            "beso_job_id": job_id or payload.get("beso_job_id"),
            "beso_status": "complete",
            "workflow_phase": "III",
        }
    return {
        **_emit(state, {"type": "phase", "phase": "II", "step": "beso", "status": "waiting"}),
        "beso_job_id": job_id,
        "beso_status": "waiting",
    }


def _phase_ii_replan(state: PipelineState) -> dict[str, Any]:
    rho = int(state.get("rho_pending") or 0)
    if rho == 0:
        return {**_emit(state, {"type": "replan", "status": "skipped"}), "workflow_phase": state.get("workflow_phase", "II")}
    try:
        from backend.replan.engine import evaluate_feedback, replan

        fb = evaluate_feedback(phase="II", step="beso", logs="rho_pending=1")
        result = replan({}, fb, persist=False)
        return {
            **_emit(
                state,
                {
                    "type": "replan",
                    "status": "suggested",
                    "message": result.message,
                    "failure_kind": fb.failure_kind,
                },
            ),
            "rho_pending": 1,
            "workflow_phase": "II",
        }
    except Exception as e:
        logger.info("replan node: %s", e)
        return {**_emit(state, {"type": "replan", "status": "error", "message": str(e)})}


def _phase_iii_deliverables(state: PipelineState) -> dict[str, Any]:
    from backend.pipeline.steps import step_run_sizing

    out_extra: dict[str, Any] = {}
    try:
        sized = step_run_sizing(
            job_id=state.get("beso_job_id"),
            design_checklist_id=state.get("design_checklist_id"),
        )
        out_extra["sizing_path"] = sized.get("sized_geometry_path")
        status = "sized"
        detail = {
            "target_power_MW": sized.get("target_power_MW"),
            "steel": sized.get("steel_intensity_t_per_MW"),
        }
    except Exception as e:
        logger.info("phase_iii sizing: %s", e)
        status = "ready"
        detail = {"warning": str(e)}
    return {
        **_emit(state, {"type": "phase", "phase": "III", "status": status, **detail}),
        "workflow_phase": "IV",
        **out_extra,
    }


def _phase_iv_validation(state: PipelineState) -> dict[str, Any]:
    from backend.pipeline.steps import step_run_validation

    vid = state.get("validation_id")
    score = state.get("overall_score")
    ai_scores = state.get("ai_review_scores")
    state_updates: dict[str, Any] = {}
    geom = state.get("sizing_path")

    if score is None and geom:
        try:
            val = step_run_validation(
                geometry_path=geom,
                design_checklist_id=state.get("design_checklist_id"),
            )
            score = val.get("overall_score")
            ai_scores = val.get("ai_review_scores")
            vid = val.get("validation_id") or vid
            state_updates = {
                "overall_score": float(score) if score is not None else None,
                "ai_review_scores": ai_scores if isinstance(ai_scores, dict) else None,
                "validation_id": vid,
                "validation_dir": val.get("out_dir"),
            }
        except Exception as e:
            logger.info("phase_iv validation: %s", e)
            return {
                **_emit(state, {"type": "phase", "phase": "IV", "status": "pending", "message": str(e)}),
                "workflow_phase": "IV",
            }

    if score is None:
        return {
            **_emit(state, {"type": "phase", "phase": "IV", "status": "pending", "validation_id": vid}),
            "workflow_phase": "IV",
            **state_updates,
        }
    halt = evaluate_halt_gate(
        overall_score=float(score),
        ai_review_scores=ai_scores,
        design_checklist_id=state.get("design_checklist_id"),
    )
    return {
        **_emit(
            state,
            {
                "type": "phase",
                "phase": "IV",
                "status": "scored",
                "overall_score": float(score),
                "halt_ok": halt.ok,
                "halt_reason": halt.reason,
            },
        ),
        "halt_ok": halt.ok,
        "halt_reason": halt.reason,
        "workflow_phase": "IV",
        **state_updates,
    }


def _gate_rho(state: PipelineState) -> str:
    ws = WorkflowState(
        task_id=state.get("task_id") or "",
        workflow_phase=state.get("workflow_phase") or "II",
        rho_pending=int(state.get("rho_pending") or 0),
        design_checklist_id=state.get("design_checklist_id"),
        oc4_session_id=state.get("oc4_session_id"),
    )
    v = can_advance(ws, from_phase="II", to_phase="III")
    if not v.ok and int(state.get("rho_pending") or 0):
        return "replan"
    return "continue"


def _gate_halt(state: PipelineState) -> str:
    if state.get("halt_ok"):
        return "halt"
    if state.get("rho_pending"):
        return "replan"
    return "end"


def _node_halt(state: PipelineState) -> dict[str, Any]:
    return {
        **_emit(state, {"type": "halt", "status": "passed", "reason": state.get("halt_reason")}),
        "archived": True,
    }


def _build_master_graph():
    from langgraph.graph import END, StateGraph

    g = StateGraph(PipelineState)
    g.add_node("phase_i", _phase_i_parse)
    g.add_node("phase_ii_dd", _phase_ii_design_domain)
    g.add_node("phase_ii_beso", _phase_ii_beso)
    g.add_node("phase_ii_replan", _phase_ii_replan)
    g.add_node("phase_iii", _phase_iii_deliverables)
    g.add_node("phase_iv", _phase_iv_validation)
    g.add_node("halt", _node_halt)

    g.set_entry_point("phase_i")
    g.add_edge("phase_i", "phase_ii_dd")
    g.add_edge("phase_ii_dd", "phase_ii_beso")
    g.add_conditional_edges("phase_ii_beso", _gate_rho, {"replan": "phase_ii_replan", "continue": "phase_iii"})
    g.add_edge("phase_ii_replan", "phase_ii_dd")
    g.add_edge("phase_iii", "phase_iv")
    g.add_conditional_edges("phase_iv", _gate_halt, {"halt": "halt", "replan": "phase_ii_replan", "end": END})
    g.add_edge("halt", END)
    return g.compile(checkpointer=get_pipeline_checkpointer())


_GRAPH = None


def get_master_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_master_graph()
    return _GRAPH


def pipeline_config(task_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": task_id}}


def load_pipeline_state(task_id: str) -> PipelineState:
    graph = get_master_graph()
    snap = graph.get_state(pipeline_config(task_id))
    if snap and snap.values:
        return dict(snap.values)
    ws = load_workflow_state(task_id)
    return {
        "task_id": task_id,
        "workflow_phase": ws.workflow_phase,
        "rho_pending": ws.rho_pending,
        "design_checklist_id": ws.design_checklist_id,
        "oc4_session_id": ws.oc4_session_id,
        "archived": ws.archived,
        "archive_path": ws.archive_path,
        "validation_id": ws.last_validation_id,
        "events": [],
    }


def export_workflow_state(task_id: str) -> WorkflowState:
    """Mirror LangGraph checkpoint to orchestrator WorkflowState for /api/workflow/state."""
    ps = load_pipeline_state(task_id)
    ws = load_workflow_state(task_id)
    ws.workflow_phase = ps.get("workflow_phase") or ws.workflow_phase
    ws.rho_pending = int(ps.get("rho_pending") or ws.rho_pending)
    ws.design_checklist_id = ps.get("design_checklist_id") or ws.design_checklist_id
    ws.oc4_session_id = ps.get("oc4_session_id") or ws.oc4_session_id
    ws.archived = bool(ps.get("archived") or ws.archived)
    ws.archive_path = ps.get("archive_path") or ws.archive_path
    ws.last_validation_id = ps.get("validation_id") or ws.last_validation_id
    return ws


def invoke_pipeline_transition(task_id: str, transition: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    ws = load_workflow_state(task_id)
    verdict = evaluate_transition(ws, transition)
    if not verdict.ok:
        return {"ok": False, "verdict": verdict.model_dump(mode="json")}
    graph = get_master_graph()
    config = pipeline_config(task_id)
    init = load_pipeline_state(task_id)
    init["task_id"] = task_id
    if payload:
        init.update(payload)
    try:
        result = graph.invoke(init, config=config)
    except Exception as e:
        logger.exception("pipeline invoke failed")
        return {"ok": False, "error": str(e)}
    out_ws = export_workflow_state(task_id)
    save_workflow_state(out_ws)
    return {"ok": True, "state": out_ws.model_dump(mode="json"), "pipeline": result}


def iter_pipeline_stream(task_id: str, *, initial: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    graph = get_master_graph()
    config = pipeline_config(task_id)
    init = load_pipeline_state(task_id)
    init["task_id"] = task_id
    if initial:
        init.update(initial)
    yield {"type": "pipeline_start", "task_id": task_id, "ts": _now_iso()}
    for update in graph.stream(init, config=config, stream_mode="updates"):
        for node, delta in update.items():
            if not isinstance(delta, dict):
                continue
            for ev in delta.get("events") or []:
                yield ev
            yield {"type": "node", "node": node, "phase": delta.get("workflow_phase")}
    out_ws = export_workflow_state(task_id)
    save_workflow_state(out_ws)
    yield {"type": "pipeline_done", "state": out_ws.model_dump(mode="json")}


def resume_beso_interrupt(task_id: str, *, job_id: str, status: str = "complete") -> dict[str, Any]:
    """Resume pipeline after BESO job completes (called from job manager)."""
    from langgraph.types import Command

    graph = get_master_graph()
    config = pipeline_config(task_id)
    try:
        result = graph.invoke(
            Command(resume={"beso_job_id": job_id, "beso_status": status}),
            config=config,
        )
        out_ws = export_workflow_state(task_id)
        save_workflow_state(out_ws)
        return {"ok": True, "state": out_ws.model_dump(mode="json"), "pipeline": result}
    except Exception as e:
        logger.exception("resume_beso_interrupt failed")
        return {"ok": False, "error": str(e)}


__all__ = [
    "get_master_graph",
    "load_pipeline_state",
    "export_workflow_state",
    "invoke_pipeline_transition",
    "iter_pipeline_stream",
    "resume_beso_interrupt",
]
