"""Adapters from the generic loop to the repository's real validation stack."""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any


def ai_review_exclusion_reason(review: dict[str, Any]) -> str | None:
    """Distinguish rule explanations from the mandatory candidate decision.

    A calculation with no failed/warning rules needs no rule explanations.
    It still requires a completed, genuine candidate-level model review.
    """
    candidate = review.get("candidate_review") or {}
    if candidate.get("status") != "completed" or candidate.get("source") != "llm":
        return "candidate_ai_review_incomplete"
    if review.get("review_mode") not in {
        "llm_explanations_with_rule_scores",
        "mixed_llm_and_template_explanations_with_rule_scores",
        "rule_scores_no_findings_model_not_called",
    }:
        return "rule_explanations_incomplete"
    return None


def real_reviewer(*, out_root: str | Path | None = None, checklist_id: str | None = None):
    """Return a reviewer callback backed by ``backend.validation.pipeline``.

    The callback accepts a topology payload containing either a geometry dict or
    a JSON artifact path. It forwards the result produced by the existing
    Automated Reviewer, including dimensional scores and their provenance.
    """
    from backend.validation.pipeline import run_validation

    root = Path(out_root) if out_root else None

    def review(topology: dict[str, Any]) -> dict[str, Any]:
        geometry = topology.get("geometry")
        if geometry is None:
            artifact = topology.get("artifact_path")
            if not artifact:
                raise ValueError("topology payload needs geometry or artifact_path")
            geometry = __import__("json").loads(Path(artifact).read_text(encoding="utf-8"))
        dest = root / str(topology.get("candidate_id") or "review") if root else None
        result = run_validation(
            geometry,
            out_dir=dest or Path("runs") / "_plus_validation",
            use_llm_rationale=True,
            candidate_label=str(topology.get("candidate_id") or "candidate"),
        )
        from .llm_candidate_review import review_candidate
        candidate_gate = existing_halt_gate({**result, "checklist_id": checklist_id})
        candidate_review = review_candidate(
            validation=result, gate=candidate_gate,
            artifact_path=str(topology.get("artifact_path") or ""),
        )
        candidate_review_path = None
        if result.get("out_dir"):
            candidate_review_path = Path(result["out_dir"]) / "candidate_review.json"
            candidate_review_path.write_text(
                json.dumps(candidate_review, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return {
            "overall_score": float(result["overall_score"]),
            "ai_review_scores": result.get("ai_review_scores") or {},
            "regulatory_review_scores": result.get("regulatory_review_scores") or {},
            "validation_id": result.get("validation_id"),
            "validation_dir": result.get("out_dir"),
            "llm_rationales": result.get("llm_rationales") or {},
            "rationale_review": result.get("rationale_review") or {"status": "unknown"},
            "rationale_review_path": result.get("rationale_review_path"),
            "review_mode": rationale_review_mode(result.get("rationale_review") or {}),
            "score_source": "backend.validation.pipeline:deterministic_rules",
            "checklist_id": checklist_id,
            "candidate_review": candidate_review,
            "candidate_review_path": str(candidate_review_path) if candidate_review_path else None,
        }

    return review


def rationale_review_mode(bundle: dict[str, Any]) -> str:
    """A nonempty template is never evidence of a model invocation."""
    return {
        "completed": "llm_explanations_with_rule_scores",
        "mixed": "mixed_llm_and_template_explanations_with_rule_scores",
        "fallback": "template_explanations_provider_failed",
        "unavailable": "template_explanations_model_unavailable",
        "no_findings": "rule_scores_no_findings_model_not_called",
        "disabled": "rule_scores_model_disabled",
    }.get(bundle.get("status"), "rule_scores_model_provenance_unknown")


def existing_halt_gate(review: dict[str, Any]) -> dict[str, Any]:
    """Use the same S/sub-score gate exposed by the production API."""
    from backend.orchestrator.halt import evaluate_halt_gate

    verdict = evaluate_halt_gate(
        overall_score=float(review["overall_score"]),
        ai_review_scores=review.get("ai_review_scores") or None,
        regulatory_review_scores=review.get("regulatory_review_scores") or None,
        design_checklist_id=review.get("checklist_id"),
    )
    return verdict.model_dump(mode="json")


__all__ = ["existing_halt_gate", "real_reviewer"]
