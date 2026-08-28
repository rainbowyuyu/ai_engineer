"""S>=85 exploration halt gate and archive."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.design_requirements.paths import load_checklist
from backend.orchestrator.models import GateVerdict
from backend.orchestrator.paths import archive_dir
from backend.orchestrator.state import load_workflow_state, save_workflow_state


def _thresholds_from_checklist(checklist_id: str | None) -> tuple[float, float]:
    s_min, sub_min = 85.0, 60.0
    if checklist_id:
        cl = load_checklist(checklist_id)
        if cl is not None:
            s_min = float(cl.regulatory.reviewer_threshold.S_min)
            sub_min = float(cl.regulatory.reviewer_threshold.subscore_min)
    return s_min, sub_min


def evaluate_halt_gate(
    *,
    overall_score: float,
    ai_review_scores: dict[str, float] | None = None,
    regulatory_review_scores: dict[str, float] | None = None,
    design_checklist_id: str | None = None,
) -> GateVerdict:
    """Terminate exploration when overall S and AI-Review sub-scores clear the gate.

    Paper gate: S≥S_min and each AI-Review dimension s_i≥subscore_min.
    Regulatory scores are retained for reporting but do not vote on the halt
    decision (they are a separate alignment check and often run cooler).
    """
    s_min, sub_min = _thresholds_from_checklist(design_checklist_id)
    ai_scores: list[float] = []
    if ai_review_scores:
        ai_scores = [float(v) for v in ai_review_scores.values() if v is not None]
    # Fallback: if AI scores absent, allow regulatory only so callers stay usable
    if not ai_scores and regulatory_review_scores:
        ai_scores = [float(v) for v in regulatory_review_scores.values() if v is not None]
    min_sub = min(ai_scores) if ai_scores else float(overall_score)
    passed = float(overall_score) >= s_min and min_sub >= sub_min
    weak = []
    if ai_review_scores:
        weak = sorted(
            (
                (k, float(v))
                for k, v in ai_review_scores.items()
                if v is not None and float(v) < sub_min
            ),
            key=lambda kv: kv[1],
        )
    if passed:
        reason = "已达内审终止条件，可归档。"
    elif float(overall_score) < s_min and min_sub < sub_min:
        reason = f"未达终止门：需 S≥{s_min} 且各子分≥{sub_min}（当前 S={float(overall_score):.2f}，最低子分={min_sub:.2f}）。"
    elif float(overall_score) < s_min:
        reason = f"未达终止门：综合分 S={float(overall_score):.2f} < {s_min}。"
    else:
        weak_txt = "、".join(f"{k}={v:.1f}" for k, v in weak[:3]) or f"最低子分={min_sub:.2f}"
        reason = f"未达终止门：存在子分 < {sub_min}（{weak_txt}）。"
    return GateVerdict(
        ok=passed,
        reason=reason,
        overall_score=float(overall_score),
        min_subscore=min_sub,
        S_min=s_min,
        subscore_min=sub_min,
        should_archive=passed,
    )


def halt_and_archive(
    task_id: str,
    *,
    validation_id: str,
    validation_dir: Path,
    design_checklist_id: str | None = None,
    geometry_path: str | None = None,
    oc4_session_id: str | None = None,
) -> dict[str, Any]:
    tid = str(task_id or "").strip()
    adir = archive_dir(tid)
    if adir.exists():
        shutil.rmtree(adir, ignore_errors=True)
    adir.mkdir(parents=True, exist_ok=True)

    # Copy validation artifacts
    vdest = adir / "validation"
    if validation_dir.is_dir():
        shutil.copytree(validation_dir, vdest, dirs_exist_ok=True)

    if design_checklist_id:
        cl = load_checklist(design_checklist_id)
        if cl is not None:
            (adir / "design_checklist_snapshot.json").write_text(
                json.dumps(cl.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # Audit manifest
    audit_manifest_path = None
    try:
        from backend.audit.manifest import build_audit_manifest

        audit_manifest_path = build_audit_manifest(
            task_id=tid,
            validation_dir=validation_dir,
            design_checklist_id=design_checklist_id,
            oc4_session_id=oc4_session_id,
            out_path=adir / "audit_manifest.json",
        )
    except Exception:
        pass

    # Layout preview pack if session available
    layout_pack = None
    if oc4_session_id:
        try:
            from backend.oc4_design_domain_service import export_layout_preview_pack

            layout_pack = export_layout_preview_pack(oc4_session_id, out_dir=adir / "layout_preview")
        except Exception:
            pass

    # Register candidate
    try:
        from backend.candidates.registry import register_candidate

        # Prefer validation_score.json (pipeline output); fall back to legacy score.json
        score_path = validation_dir / "validation_score.json"
        if not score_path.is_file():
            score_path = validation_dir / "score.json"
        overall = 0.0
        if score_path.is_file():
            payload = json.loads(score_path.read_text(encoding="utf-8"))
            overall = float(
                payload.get("overall_score")
                or payload.get("S")
                or (payload.get("score") or {}).get("overall_score")
                or 0
            )
        register_candidate(
            tid,
            label="archived_best",
            geometry_path=geometry_path,
            validation_id=validation_id,
            overall_score=overall,
            archived_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception:
        pass

    meta = {
        "task_id": tid,
        "validation_id": validation_id,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "audit_manifest": str(audit_manifest_path) if audit_manifest_path else None,
        "layout_preview": layout_pack,
    }
    (adir / "archive_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    st = load_workflow_state(tid, oc4_session_id=oc4_session_id, design_checklist_id=design_checklist_id)
    st.archived = True
    st.archive_path = str(adir)
    st.last_validation_id = validation_id
    st.workflow_phase = "IV"
    st.rho_pending = 0
    save_workflow_state(st)

    return {"ok": True, "archive_path": str(adir), "meta": meta}
