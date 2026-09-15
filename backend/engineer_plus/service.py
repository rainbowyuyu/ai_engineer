"""Application-facing candidate review and selection service."""
from __future__ import annotations

import json
import uuid
import re
from pathlib import Path
from typing import Any

from .adapters import existing_halt_gate, ai_review_exclusion_reason


def _safe_task_id(task_id: str) -> str:
    raw = str(task_id or "").strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", raw)[:128]
    if not safe or safe in {".", ".."}:
        raise ValueError("task_id must contain at least one safe character")
    return safe


def review_and_select(*, task_id: str, construction: str,
                      geometry_paths: list[str], workspace_root: Path,
                      checklist_id: str | None = None) -> dict[str, Any]:
    """Review actual geometry artifacts and select only a gate-passing result."""
    if not geometry_paths:
        raise ValueError("geometry_paths is required")
    if len(geometry_paths) > 32:
        raise ValueError("at most 32 candidate geometries are allowed")
    from backend.candidates.registry import register_candidate, select_candidate
    from .adapters import real_reviewer
    root = workspace_root.resolve()
    safe_task = _safe_task_id(task_id)
    reviewer = real_reviewer(out_root=root / "runs" / "_plus_validation", checklist_id=checklist_id)
    candidates: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for index, raw in enumerate(geometry_paths):
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"candidate {index}: geometry must be inside workspace") from exc
        if path.suffix.lower() != ".json" or not path.is_file():
            raise ValueError(f"candidate {index}: geometry JSON not found: {path}")
        events.append({"kind": "review_started", "index": index, "path": str(path)})
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            review = reviewer({"artifact_path": str(path), "candidate_id": f"{safe_task}-{index + 1}"})
        except Exception as exc:
            # Record the exception class, never provider messages that may
            # contain credentials. A failed candidate cannot stop its peers.
            events.append({"kind": "candidate_excluded", "index": index,
                           "path": str(path), "reason": "review_execution_failed",
                           "error_type": type(exc).__name__})
            continue
        candidate_review = review.get("candidate_review") or {}
        exclusion_reason = ai_review_exclusion_reason(review)
        if exclusion_reason:
            events.append({"kind": "candidate_excluded", "index": index,
                           "path": str(path), "reason": exclusion_reason,
                           "review_status": candidate_review.get("status") or "unavailable",
                           "review_mode": review.get("review_mode"),
                           "candidate_review": candidate_review,
                           "validation_dir": review.get("validation_dir")})
            continue
        gate = existing_halt_gate({**review, "checklist_id": checklist_id})
        entry = register_candidate(safe_task, label=f"{construction} · candidate {index + 1}",
                                   geometry_path=str(path), validation_id=review["validation_id"],
                                   overall_score=review["overall_score"], score_dims=review["ai_review_scores"],
                                   score_source="backend.validation.pipeline",
                                   notes=gate.get("reason", ""),
                                   rationale=json.dumps(candidate_review.get("review") or {}, ensure_ascii=False))
        item = {"candidate_id": entry["candidate_id"], "index": index,
                "geometry_path": str(path), "review": review, "gate": gate,
                "selected": False, "geometry_keys": sorted(payload.keys())[:20]}
        candidates.append(item)
        events.append({"kind": "review_complete", "candidate_id": entry["candidate_id"],
                       "overall_score": review["overall_score"], "gate_ok": bool(gate.get("ok"))})
    # A deterministic gate is necessary but not sufficient when this service
    # is explicitly running in AI-review mode.  Keep the same hard boundary as
    # ClosedLoopEngine: an independently completed LLM review must return an
    # explicit ``accept`` recommendation before a candidate can be selected.
    eligible = [c for c in candidates
                if c["gate"].get("ok")
                and (c["review"].get("candidate_review") or {}).get("status") == "completed"
                and (c["review"].get("candidate_review") or {}).get("source") == "llm"
                and ((c["review"].get("candidate_review") or {}).get("review") or {}).get("recommendation") == "accept"]
    excluded_by_ai = [c["candidate_id"] for c in candidates
                      if c["gate"].get("ok") and c not in eligible]
    if excluded_by_ai:
        events.append({"kind": "ai_review_excluded", "candidate_ids": excluded_by_ai,
                       "reason": "candidate-level AI recommendation was not accept"})
    selected = max(eligible, key=lambda c: c["review"]["overall_score"]) if eligible else None
    if selected:
        select_candidate(safe_task, selected["candidate_id"])
        selected["selected"] = True
        status = "selected"
        events.append({"kind": "candidate_selected", "candidate_id": selected["candidate_id"]})
    else:
        status = "review_failed" if candidates else "failed"
        events.append({"kind": "selection_blocked", "reason": "no candidate passed gate"})
    event_path = root / "runs" / "_plus_events" / safe_task / "review-select.json"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path.write_text(json.dumps({"task_id": task_id, "construction": construction,
                                      "status": status, "candidates": candidates,
                                      "events": events}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": status == "selected", "status": status, "task_id": safe_task,
            "construction": construction, "selected": selected,
            "candidates": candidates, "events": events, "event_path": str(event_path)}


def run_registered_loop(*, task_id: str, construction: str, requirements: dict[str, Any],
                        candidate_count: int, workspace_root: Path,
                        checklist_id: str | None = None) -> dict[str, Any]:
    """Execute a registered CAD→BESO→review loop using real repository adapters."""
    from .engine import ClosedLoopEngine, DesignRequest
    from .registry import default_registry
    from .adapters import real_reviewer
    from backend.candidates.registry import register_candidate, select_candidate

    brief = str(requirements.get("brief") or "")
    if not construction.strip():
        construction = DesignRequest.from_text(task_id, brief).construction
    adapter = default_registry.get(construction)
    if any(key.startswith("_") for key in requirements):
        raise ValueError("internal continuation state cannot be supplied through request requirements")
    safe_task = _safe_task_id(task_id)
    workspace_root = workspace_root.resolve()
    if adapter.name == "prism":
        # Author constraint: retain prism dimensions and prescribed physical
        # values. A model or API caller cannot reopen a geometry search here.
        requirements = {**requirements, "design_variable_bounds": {}}
    req = DesignRequest(task_id=safe_task, construction=construction,
                        requirements={**requirements, "workspace_root": str(workspace_root),
                                      "require_artifacts": True, "require_ai_review": True},
                        candidate_count=candidate_count, execution_mode="live")
    if adapter.revision_policy is not None:
        adapter.revision_policy.context(req, req)

    persisted_ids: dict[str, str] = {}

    def save_candidate(task: str, data: dict[str, Any]) -> dict[str, Any]:
        review = data["review"]
        internal_id = str(data["candidate_id"])
        entry = register_candidate(task, label=f"{construction} · plus",
                                  geometry_path=data["topology"].get("artifact_path"),
                                  validation_id=review.get("validation_id"),
                                  overall_score=float(review["overall_score"]),
                                  score_dims=review.get("ai_review_scores"),
                                  score_source="backend.validation.pipeline",
                                  rationale=json.dumps(
                                      review.get("candidate_review", {}).get("review") or {},
                                      ensure_ascii=False,
                                  ))
        persisted_ids[internal_id] = str(entry["candidate_id"])
        return entry

    def gate(review: dict[str, Any]) -> dict[str, Any]:
        return existing_halt_gate({**review, "checklist_id": checklist_id})

    out = workspace_root / "runs" / "_plus_events" / safe_task / uuid.uuid4().hex / "events.json"
    result = ClosedLoopEngine(gate=gate, registry=save_candidate).run(
        req, build_domain=adapter.build_domain, run_topology=adapter.run_topology,
        review=real_reviewer(out_root=workspace_root / "runs" / "_plus_validation",
                             checklist_id=checklist_id), revision_policy=adapter.revision_policy, event_path=out)
    if result.selected_candidate_id:
        persisted_id = persisted_ids.get(result.selected_candidate_id)
        if persisted_id:
            select_candidate(safe_task, persisted_id)
    return {"ok": result.status == "selected", "status": result.status,
            "selected_candidate_id": result.selected_candidate_id,
            "persisted_selected_candidate_id": persisted_ids.get(result.selected_candidate_id or ""),
            "candidates": [c.__dict__ for c in result.candidates], "events": result.events,
            "event_path": str(out)}
