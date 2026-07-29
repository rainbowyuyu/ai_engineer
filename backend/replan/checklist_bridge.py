"""Bridge DesignChecklist J into replan retry policy and session/run context."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.design_requirements.paths import load_checklist


def load_checklist_from_session(sdir: Path) -> Any | None:
    try:
        from backend.oc4_design_domain_service import read_session_meta

        meta = read_session_meta(sdir)
        cid = str(meta.get("design_checklist_id") or "").strip()
        if cid:
            return load_checklist(cid)
    except Exception:
        pass
    return None


def load_checklist_from_run_dir(run_dir: Path) -> Any | None:
    for name in ("job_context.json", "replan_context.json"):
        p = run_dir / name
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                cid = str(data.get("design_checklist_id") or "").strip()
                if cid:
                    cl = load_checklist(cid)
                    if cl is not None:
                        return cl
            except Exception:
                pass
    manifest = run_dir / "task_manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            cid = str(data.get("design_checklist_id") or "").strip()
            if cid:
                return load_checklist(cid)
        except Exception:
            pass
    return None


def retry_max_from_checklist(checklist: Any | None, default: int = 3) -> int:
    if checklist is None:
        return int(default)
    try:
        return int(checklist.job_descriptor.retry_policy.max_retries)
    except Exception:
        return int(default)


def link_oc4_session_to_task(
    session_id: str,
    sdir: Path,
    *,
    task_id: str | None = None,
    design_checklist_id: str | None = None,
) -> None:
    """Bind OC4 session meta + workflow state to a landing task."""
    from backend.oc4_design_domain_service import merge_session_meta

    patch: dict[str, Any] = {}
    tid = str(task_id or "").strip()
    cid = str(design_checklist_id or "").strip()
    if tid:
        patch["task_id"] = tid
    if cid:
        patch["design_checklist_id"] = cid
    if patch:
        merge_session_meta(sdir, patch)
    if not tid:
        return
    try:
        from backend.orchestrator.state import load_workflow_state, save_workflow_state

        st = load_workflow_state(tid, oc4_session_id=session_id, design_checklist_id=cid or None)
        st.oc4_session_id = session_id
        if cid:
            st.design_checklist_id = cid
        save_workflow_state(st)
    except Exception:
        pass


def write_job_context(run_dir: Path, *, design_checklist_id: str | None = None, **extra: Any) -> None:
    p = run_dir / "job_context.json"
    cur: dict[str, Any] = {}
    if p.is_file():
        try:
            cur = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    if design_checklist_id:
        cur["design_checklist_id"] = design_checklist_id
    cur.update({k: v for k, v in extra.items() if v is not None})
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


def beso_theta_defaults_from_checklist(
    checklist: Any | None,
    *,
    mass_goal_ratio: float = 0.15,
    filter_radius: float = 2.0,
    optimization_base: str = "stiffness",
) -> dict[str, Any]:
    """BESO θ for finalize / chat — checklist overrides Chen-style defaults."""
    out = {
        "mass_goal_ratio": float(mass_goal_ratio),
        "filter_radius": float(filter_radius),
        "optimization_base": str(optimization_base or "stiffness"),
        "source": "chen2026_default",
    }
    if checklist is None:
        return out
    try:
        beso = checklist.job_descriptor.theta.beso
        if beso.mass_goal_ratio is not None:
            out["mass_goal_ratio"] = max(0.05, min(0.99, float(beso.mass_goal_ratio)))
        if beso.filter_radius is not None:
            out["filter_radius"] = float(beso.filter_radius)
        if beso.optimization_base:
            out["optimization_base"] = str(beso.optimization_base)
        out["source"] = f"design_checklist:{getattr(checklist.meta, 'checklist_id', '')}"
        out["checklist_id"] = str(getattr(checklist.meta, "checklist_id", "") or "")
    except Exception:
        pass
    return out


def maybe_commit_live_replan_version(
    task_id: str | None,
    *,
    event_id: str | None,
    theta_before: dict[str, Any] | None,
    theta_after: dict[str, Any] | None,
    message: str,
    case_id: str | None = None,
) -> dict[str, Any] | None:
    """Best-effort git-like version snapshot for live mesh/solver replan (not demo-only)."""
    tid = str(task_id or "").strip()
    if not tid or not event_id:
        return None
    try:
        from backend.replan.paths import replan_root
        from backend.versions.store import commit_replan_snapshot

        ev_path = replan_root() / str(event_id) / "replan_event.json"
        return commit_replan_snapshot(
            tid,
            event_id=str(event_id),
            theta_before=theta_before,
            theta_after=theta_after,
            event_path=ev_path if ev_path.is_file() else None,
            message=message[:200],
            case_id=case_id,
        )
    except Exception:
        return None
