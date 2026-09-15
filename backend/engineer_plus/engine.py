"""A construction-independent closed loop for engineering design.

The language model may produce a structured request and choose registered
tools. It never supplies a score or promotes a candidate. Builders and
solvers return artifacts; the validation callback is the only source of
review metrics used by the gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
import uuid
import json
import math
import hashlib
from pathlib import Path
from copy import deepcopy
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .revision import RevisionPolicy


class DesignDomainBuilder(Protocol):
    def __call__(self, request: "DesignRequest", *, candidate_index: int) -> dict[str, Any]: ...


class TopologyRunner(Protocol):
    def __call__(self, domain: dict[str, Any], *, candidate_index: int) -> dict[str, Any]: ...


class RealReviewer(Protocol):
    def __call__(self, artifact: dict[str, Any]) -> dict[str, Any]: ...


class FailureRecovery(Protocol):
    def __call__(self, request: "DesignRequest", error: Exception,
                 *, candidate_index: int, attempt: int) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class DesignRequest:
    """Normalized, geometry-neutral requirements produced by Phase I."""

    task_id: str
    construction: str
    requirements: dict[str, Any]
    candidate_count: int = 3
    execution_mode: str = "live"
    max_replans: int = 1
    attempt_id: str = ""

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.task_id) or self.task_id in {".", ".."}:
            raise ValueError("task_id must be a safe path component")
        if not self.construction.strip():
            raise ValueError("construction is required")
        if self.candidate_count < 1 or self.candidate_count > 32:
            raise ValueError("candidate_count must be between 1 and 32")
        if self.execution_mode not in {"live", "preview"}:
            raise ValueError("execution_mode must be live or preview")
        if self.max_replans < 0 or self.max_replans > 5:
            raise ValueError("max_replans must be between 0 and 5")

    @classmethod
    def from_text(cls, task_id: str, text: str, *, candidate_count: int = 1,
                  execution_mode: str = "live", construction: str | None = None,
                  **requirements: Any) -> "DesignRequest":
        """Normalize a brief, or use an explicitly selected adapter route.

        Natural-language detection is intentionally conservative. New
        construction families should register an adapter and pass its explicit
        name instead of being silently routed to a physically incompatible
        heuristic.
        """
        raw = str(text or "").strip()
        low = raw.lower()
        if construction and str(construction).strip():
            route = str(construction).strip().lower()
        elif any(token in low for token in ("oc4", "半潜", "floating wind", "漂浮风")):
            route = "oc4"
        elif any(token in low for token in ("prism", "棱柱", "三棱柱")):
            route = "prism"
        elif any(token in low for token in (".igs", ".iges", ".step", ".stp", "cad", "模型")):
            route = "cad"
        else:
            raise ValueError("无法识别构型；请说明 OC4、棱柱或提供 IGES/STEP CAD 路径")
        return cls(task_id=task_id, construction=route,
                   requirements={"brief": raw, **requirements},
                   candidate_count=candidate_count, execution_mode=execution_mode)


@dataclass
class DesignCandidate:
    candidate_id: str
    index: int
    construction: str
    domain: dict[str, Any]
    topology: dict[str, Any]
    review: dict[str, Any]
    gate: dict[str, Any]
    selected: bool = False
    attempt: int = 0
    parent_candidate_id: str | None = None


@dataclass
class LoopResult:
    task_id: str
    status: str
    candidates: list[DesignCandidate] = field(default_factory=list)
    selected_candidate_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    artifact_manifest: list[dict[str, Any]] = field(default_factory=list)


def _event(kind: str, **data: Any) -> dict[str, Any]:
    return {"event_id": uuid.uuid4().hex, "time": datetime.now(timezone.utc).isoformat(),
            "kind": kind, **data}


def _existing_artifact(payload: dict[str, Any], label: str,
                       *, workspace_root: Path | None = None) -> Path:
    """Require a concrete file artifact before a phase can advance."""
    raw = payload.get("artifact_path")
    if not raw:
        raise ValueError(f"{label} must return artifact_path")
    path = Path(str(raw)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} artifact does not exist: {path}")
    if workspace_root is not None:
        try:
            path.relative_to(workspace_root.resolve())
        except ValueError as exc:
            raise ValueError(f"{label} artifact must be inside workspace: {path}") from exc
    return path


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_records(payload: dict[str, Any], *, role: str,
                      workspace_root: Path | None = None) -> list[dict[str, Any]]:
    """Return deterministic evidence records for paths emitted by a stage."""
    records: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for key, raw in payload.items():
        if key != "artifact_path" and not key.endswith("_path") and key not in {
            "topology_provenance", "validation_dir"
        }:
            continue
        if not isinstance(raw, (str, Path)) or not str(raw).strip():
            continue
        path = Path(str(raw)).expanduser().resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        if workspace_root is not None:
            try:
                relative = path.relative_to(workspace_root.resolve())
            except ValueError as exc:
                raise ValueError(f"{role} artifact must be inside workspace: {path}") from exc
        else:
            relative = None
        if path.is_file():
            records.append({
                "role": role,
                "key": key,
                "path": str(path),
                "relative_path": str(relative) if relative is not None else None,
                "kind": "file",
                "size": path.stat().st_size,
                "sha256": _hash_file(path),
            })
            continue
        if path.is_dir():
            children = []
            for child in sorted(p for p in path.rglob("*") if p.is_file()):
                child_relative = child.relative_to(path).as_posix()
                children.append({"path": child_relative, "size": child.stat().st_size,
                                 "sha256": _hash_file(child)})
            manifest = hashlib.sha256(
                json.dumps(children, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            records.append({
                "role": role,
                "key": key,
                "path": str(path),
                "relative_path": str(relative) if relative is not None else None,
                "kind": "directory",
                "file_count": len(children),
                "sha256": manifest,
                "files": children,
            })
    return records


class ClosedLoopEngine:
    """Run the same review-and-select protocol for any registered construction."""

    def __init__(self, *, gate: Callable[[dict[str, Any]], dict[str, Any]],
                 registry: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None):
        self._gate = gate
        self._registry = registry

    def run(self, request: DesignRequest, *, build_domain: DesignDomainBuilder,
            run_topology: TopologyRunner, review: RealReviewer,
            recover: FailureRecovery | None = None,
            revision_policy: "RevisionPolicy | None" = None,
            event_path: str | Path | None = None) -> LoopResult:
        if request.execution_mode != "live":
            raise RuntimeError("Preview mode cannot claim a completed closed-loop design")
        result = LoopResult(task_id=request.task_id, status="running")
        # A callback receives its own copy: neither a planner nor a recovery
        # function may silently mutate the original acceptance requirements.
        request = deepcopy(request)
        def emit(event: dict[str, Any]) -> None:
            result.events.append(event)
            if event_path:
                path = Path(event_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                pending = path.with_suffix(".pending")
                pending.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
                pending.replace(path)
        workspace_raw = request.requirements.get("workspace_root")
        workspace_root = Path(str(workspace_raw)).expanduser().resolve() if workspace_raw else None
        emit(_event("loop_started", construction=request.construction,
                                    candidate_count=request.candidate_count))
        for index in range(request.candidate_count):
            attempt = 0
            active_request = deepcopy(request)
            parent_id = None
            seen_specs: set[str] = set()
            while True:
                cid = f"{index + 1}-a{attempt}-{uuid.uuid4().hex}"
                active_request = replace(active_request, attempt_id=cid)
                try:
                    emit(_event("design_domain_started", candidate_id=cid, index=index,
                                attempt=attempt, parent_candidate_id=parent_id))
                    domain = build_domain(deepcopy(active_request), candidate_index=index)
                    if active_request.requirements.get("require_artifacts", False):
                        _existing_artifact(domain, "design-domain builder", workspace_root=workspace_root)
                    elif not domain.get("artifact_path") and not domain.get("geometry"):
                        raise ValueError("design-domain builder returned no artifact")
                    domain = {**domain, "candidate_id": cid}
                    domain_records = _artifact_records(domain, role="design_domain",
                                                       workspace_root=workspace_root)
                    domain["input_sha256"] = next((r["sha256"] for r in domain_records if r["key"] == "artifact_path"), None)
                    result.artifact_manifest.extend(domain_records)
                    emit(_event("design_domain_ready", candidate_id=cid,
                                                artifacts=domain_records))
                    topology = run_topology(domain, candidate_index=index)
                    if active_request.requirements.get("require_artifacts", False):
                        _existing_artifact(topology, "topology runner", workspace_root=workspace_root)
                    elif not topology.get("artifact_path") and not topology.get("geometry"):
                        raise ValueError("topology runner returned no artifact")
                    topology = {**topology, "candidate_id": cid}
                    topology_records = _artifact_records(topology, role="topology",
                                                         workspace_root=workspace_root)
                    result.artifact_manifest.extend(topology_records)
                    emit(_event("topology_ready", candidate_id=cid,
                                                artifacts=topology_records))
                    review_payload = review(topology)
                    score = review_payload.get("overall_score")
                    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
                        raise ValueError("review must return a numeric overall_score")
                    if not 0.0 <= float(score) <= 100.0:
                        raise ValueError("review overall_score must be between 0 and 100")
                    gate_payload = self._gate(review_payload)
                    if not isinstance(gate_payload, dict) or not isinstance(gate_payload.get("ok"), bool):
                        raise ValueError("gate must return an explicit boolean ok")
                    if not str(review_payload.get("score_source") or "").strip():
                        raise ValueError("review must declare score_source")
                    if request.requirements.get("require_artifacts", False):
                        validation_dir = review_payload.get("validation_dir")
                        if not validation_dir or not Path(str(validation_dir)).expanduser().is_dir():
                            raise ValueError("review must return an existing validation_dir")
                        validation_root = Path(str(validation_dir)).expanduser().resolve()
                        required_evidence = [validation_root / "validation_score.json",
                                             validation_root / "rationale_review.json"]
                        for evidence in required_evidence:
                            if not evidence.is_file():
                                raise FileNotFoundError(f"review evidence missing: {evidence}")
                            try:
                                json.loads(evidence.read_text(encoding="utf-8"))
                            except (OSError, json.JSONDecodeError) as exc:
                                raise ValueError(f"review evidence is not valid JSON: {evidence}") from exc
                        topo_provenance = Path(str(topology.get("topology_provenance") or "")).expanduser()
                        if not topo_provenance.is_file():
                            raise FileNotFoundError("topology provenance evidence missing")
                        try:
                            json.loads(topo_provenance.read_text(encoding="utf-8"))
                        except (OSError, json.JSONDecodeError) as exc:
                            raise ValueError("topology provenance is not valid JSON") from exc
                    if request.requirements.get("require_ai_review", False):
                        from .adapters import ai_review_exclusion_reason
                        exclusion_reason = ai_review_exclusion_reason(review_payload)
                        if exclusion_reason:
                            raise RuntimeError(exclusion_reason)
                    review_records = _artifact_records(review_payload, role="review",
                                                       workspace_root=workspace_root)
                    result.artifact_manifest.extend(review_records)
                    candidate = DesignCandidate(cid, index, request.construction, domain,
                                                topology, review_payload, gate_payload,
                                                attempt=attempt, parent_candidate_id=parent_id)
                    if self._registry:
                        self._registry(active_request.task_id, {"candidate_id": cid,
                            **asdict(candidate)})
                    result.candidates.append(candidate)
                    emit(_event("review_complete", candidate_id=cid,
                                            overall_score=float(score),
                                                gate_ok=bool(gate_payload.get("ok")),
                                                artifacts=review_records))
                    decision = review_payload.get("candidate_review") or {}
                    recommendation = (decision.get("review") or {}).get("recommendation")
                    needs_revision = recommendation == "revise" or (
                        recommendation == "accept" and not gate_payload["ok"])
                    if needs_revision and decision.get("status") == "completed" and decision.get("source") == "llm":
                        if revision_policy is None or attempt >= request.max_replans:
                            emit(_event("revision_stopped", candidate_id=cid,
                                        reason="no_revision_policy" if revision_policy is None else "revision_budget_exhausted"))
                            break
                        from .revision import propose_revision
                        try:
                            context = revision_policy.context(deepcopy(request), deepcopy(active_request), candidate=deepcopy(candidate))
                            if not any(context.get("allowed_patch", {}).values()):
                                emit(_event("revision_stopped", candidate_id=cid, reason="no_authorized_revision_variables"))
                                break
                            seen_specs.add(json.dumps(context["current_spec"], sort_keys=True))
                            proposal = propose_revision(candidate=deepcopy(candidate), context=deepcopy(context))
                            emit(_event("revision_proposed", candidate_id=cid, proposal=proposal))
                            if proposal.get("status") != "completed" or proposal.get("source") != "llm":
                                emit(_event("revision_stopped", candidate_id=cid, reason="planner_incomplete"))
                                break
                            action = proposal["proposal"]
                            if action["action"] == "stop":
                                emit(_event("revision_stopped", candidate_id=cid, reason="planner_stop"))
                                break
                            updated = revision_policy.apply(deepcopy(request), deepcopy(active_request), action["patch"], candidate=deepcopy(candidate))
                            next_spec = revision_policy.context(deepcopy(request), deepcopy(updated), candidate=deepcopy(candidate))["current_spec"]
                            if json.dumps(next_spec, sort_keys=True) in seen_specs:
                                raise ValueError("revision repeats a previously evaluated specification")
                        except Exception as exc:
                            emit(_event("revision_stopped", candidate_id=cid, reason="invalid_revision",
                                        error_type=type(exc).__name__))
                            break
                        parent_id = cid
                        attempt += 1
                        active_request = updated
                        emit(_event("revision_applied", candidate_id=cid, next_attempt=attempt,
                                    patch=action["patch"], rationale=action["rationale"]))
                        continue
                    break
                except Exception as exc:
                    if recover is None or attempt >= request.max_replans:
                        emit(_event("candidate_failed", candidate_id=cid,
                                    error_type=type(exc).__name__, attempts=attempt + 1))
                        break
                    attempt += 1
                    try:
                        patch = recover(deepcopy(active_request), exc, candidate_index=index, attempt=attempt)
                        # Exception recovery may tune numerics, never physical
                        # requirements, artifact enforcement or gate authority.
                        if not isinstance(patch, dict) or not patch or set(patch) - {
                            "mesh", "char_length_min", "char_length_max", "element_order", "timeout_s"
                        }:
                            raise ValueError("invalid recovery patch")
                    except Exception as recovery_error:
                        emit(_event("candidate_failed", candidate_id=cid,
                                    error_type=type(recovery_error).__name__, attempts=attempt))
                        break
                    emit(_event("candidate_replanned", candidate_id=cid,
                                                attempt=attempt, patch=patch))
                    parent_id = cid
                    active_request = replace(
                        active_request,
                        requirements={**active_request.requirements, **patch},
                    )
        eligible = [c for c in result.candidates if c.gate.get("ok") and (
            not request.requirements.get("require_ai_review", False)
            or (c.review.get("candidate_review") or {}).get("review", {}).get("recommendation") == "accept"
        )]
        if request.requirements.get("require_ai_review", False):
            rejected = [c.candidate_id for c in result.candidates
                        if c.gate.get("ok") and c not in eligible]
            if rejected:
                emit(_event("ai_review_excluded", candidate_ids=rejected,
                                            reason="recommendation was not accept"))
        if eligible:
            selected = max(eligible, key=lambda c: float(c.review["overall_score"]))
            selected.selected = True
            result.selected_candidate_id = selected.candidate_id
            result.status = "selected"
            emit(_event("candidate_selected", candidate_id=selected.candidate_id))
        elif result.candidates:
            result.status = "review_failed"
            emit(_event("selection_blocked", reason="no candidate passed gate and required AI review"))
        else:
            result.status = "failed"
            emit(_event("loop_failed", reason="all candidates failed before review"))
        return result
