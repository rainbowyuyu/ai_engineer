"""Design candidate registry (MVP)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.orchestrator.paths import candidates_registry_path


def _load_registry(task_id: str) -> dict[str, Any]:
    p = candidates_registry_path(task_id)
    if not p.is_file():
        return {"task_id": task_id, "candidates": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"task_id": task_id, "candidates": []}


def _save_registry(task_id: str, data: dict[str, Any]) -> None:
    p = candidates_registry_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def register_candidate(
    task_id: str,
    *,
    label: str,
    geometry_path: str | None = None,
    validation_id: str | None = None,
    overall_score: float = 0.0,
    archived_at: str | None = None,
    preview_url: str | None = None,
    curve_url: str | None = None,
    score_dims: dict[str, float] | None = None,
    notes: str | None = None,
    score_source: str | None = None,
    prediction_label: str | None = None,
    score_basis: list[dict[str, Any]] | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    reg = _load_registry(task_id)
    cid = uuid.uuid4().hex[:12]
    entry = {
        "candidate_id": cid,
        "label": label,
        "geometry_path": geometry_path,
        "validation_id": validation_id,
        "overall_score": float(overall_score),
        "preview_url": preview_url,
        "curve_url": curve_url,
        "score_dims": dict(score_dims or {}),
        "notes": notes or "",
        "score_source": score_source or "ai_agent_predicted",
        "prediction_label": prediction_label
        or "AI Review 智能体预测分（非 Phase V 实测验证分）",
        "score_basis": list(score_basis or []),
        "rationale": rationale or "",
        "selected": False,
        "archived_at": archived_at or datetime.now(timezone.utc).isoformat(),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    reg.setdefault("candidates", []).append(entry)
    _save_registry(task_id, reg)
    return entry


def list_candidates(task_id: str) -> list[dict[str, Any]]:
    reg = _load_registry(task_id)
    arr = list(reg.get("candidates") or [])
    arr.sort(key=lambda x: float(x.get("overall_score") or 0), reverse=True)
    return arr


def get_selected(task_id: str) -> dict[str, Any] | None:
    for c in list_candidates(task_id):
        if c.get("selected"):
            return c
    return None


def select_candidate(task_id: str, candidate_id: str) -> dict[str, Any] | None:
    """Mark one candidate as user/system selection; clear others."""
    reg = _load_registry(task_id)
    cid = str(candidate_id or "").strip()
    found = None
    for c in reg.get("candidates") or []:
        if str(c.get("candidate_id") or "") == cid:
            c["selected"] = True
            c["selected_at"] = datetime.now(timezone.utc).isoformat()
            found = c
        else:
            c["selected"] = False
    if found is None:
        return None
    _save_registry(task_id, reg)
    return found


def select_best(task_id: str) -> dict[str, Any] | None:
    arr = list_candidates(task_id)
    if not arr:
        return None
    return select_candidate(task_id, str(arr[0].get("candidate_id") or ""))
