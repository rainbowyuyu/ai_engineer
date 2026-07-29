"""Aggregate workflow state from task, OC4 session, and replan events."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.orchestrator.models import WorkflowState
from backend.orchestrator.paths import workflow_state_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tasks_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve() / "runs" / "_tasks"


def _load_task(task_id: str) -> dict[str, Any]:
    p = _tasks_root() / f"{task_id}.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_workflow_state(
    task_id: str,
    *,
    oc4_session_id: str | None = None,
    design_checklist_id: str | None = None,
) -> WorkflowState:
    tid = str(task_id or "").strip()
    if not tid:
        return WorkflowState(task_id="")

    saved: dict[str, Any] = {}
    sp = workflow_state_path(tid)
    if sp.is_file():
        try:
            saved = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            saved = {}

    task = _load_task(tid)
    sid = oc4_session_id or task.get("oc4_design_domain_session_id") or saved.get("oc4_session_id")
    cid = design_checklist_id or saved.get("design_checklist_id")

    rho = int(saved.get("rho_pending") or 0)
    last_ev = saved.get("last_replan_event_id")

    # BESO job may set rho_pending in job_context.json under latest run dir
    scan_dir = str(task.get("scan_dir") or "").strip()
    if scan_dir:
        try:
            root = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()
            ctx_path = root / scan_dir.replace("/", os.sep) / "job_context.json"
            if ctx_path.is_file():
                jctx = json.loads(ctx_path.read_text(encoding="utf-8"))
                if int(jctx.get("rho_pending") or 0):
                    rho = 1
                if jctx.get("last_replan_event_id") and not last_ev:
                    last_ev = jctx.get("last_replan_event_id")
        except Exception:
            pass

    if sid:
        try:
            from backend.oc4_design_domain_service import read_session_meta

            sdir = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve() / "runs" / "_oc4_dd" / str(sid)
            if sdir.is_dir():
                meta = read_session_meta(sdir)
                cid = cid or meta.get("design_checklist_id")
                ev = meta.get("last_replan_event_id")
                if ev and not last_ev:
                    last_ev = ev
                # If mesh replan just succeeded, rho clears
                if meta.get("mesh_replan_event_ids") and meta.get("has_for_beso_inp"):
                    rho = 0
        except Exception:
            pass

    phase: str = saved.get("workflow_phase") or "I"
    if task.get("oc4_design_domain_session_id"):
        phase = "II"
    if str(task.get("ui_stage") or "").lower() == "orchestrate":
        phase = "II"
    if saved.get("archived"):
        phase = "IV"

    return WorkflowState(
        task_id=tid,
        workflow_phase=phase if phase in ("I", "II", "III", "IV") else "I",
        rho_pending=rho,
        last_replan_event_id=str(last_ev) if last_ev else None,
        archived=bool(saved.get("archived")),
        archive_path=saved.get("archive_path"),
        last_validation_id=saved.get("last_validation_id"),
        design_checklist_id=str(cid) if cid else None,
        oc4_session_id=str(sid) if sid else None,
        updated_at=saved.get("updated_at"),
    )


def save_workflow_state(state: WorkflowState) -> WorkflowState:
    sp = workflow_state_path(state.task_id)
    sp.parent.mkdir(parents=True, exist_ok=True)
    data = state.model_dump(mode="json")
    data["updated_at"] = _now_iso()
    sp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def mark_rho_pending(task_id: str, *, event_id: str | None = None, rho: int = 1) -> WorkflowState:
    st = load_workflow_state(task_id)
    st.rho_pending = int(rho)
    if event_id:
        st.last_replan_event_id = event_id
    return save_workflow_state(st)


def clear_rho_pending(task_id: str) -> WorkflowState:
    st = load_workflow_state(task_id)
    st.rho_pending = 0
    return save_workflow_state(st)
