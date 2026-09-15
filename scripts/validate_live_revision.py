"""Audit real model review and planning against a fixed prism specification.

Reads credentials from process configuration or the local .env, never records
them. This is a continuation experiment, not a claim of design convergence.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    os.environ["WORKSPACE_ROOT"] = str(ROOT)
    os.environ["MPLBACKEND"] = "Agg"
    from backend.engineer_plus.engine import DesignCandidate, DesignRequest
    from backend.engineer_plus.revision import PrismRevisionPolicy, propose_revision
    from backend.engineer_plus.llm_candidate_review import review_candidate
    from backend.engineer_plus.adapters import existing_halt_gate
    from backend.validation.geometry_metrics import extract_geometry_metrics
    from backend.validation.scorer import score_design

    run_id = "live-revision-" + uuid.uuid4().hex
    output = ROOT / "tmp" / "results" / "live_revision" / run_id
    output.mkdir(parents=True)
    report = {"run_id": run_id, "status": "started", "events": [],
              "limitations": ["fixed prism geometry; no new solver run", "historical BESO capped at two iterations; not convergence evidence",
                              "validation includes proxy metrics; not certification"]}

    def record(stage, **data):
        report["status"] = stage
        report["events"].append({"stage": stage, **data})
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"stage": stage, "report": str(output / "report.json")}, ensure_ascii=False), flush=True)

    try:
        previous = ROOT / "runs" / "42b2eed865554070af28855c75d5a948"
        original_deck = previous / "03_for_beso.inp"
        source_dirs = [p.parent for p in (ROOT / "_plus").glob("*/candidate_1/prism_spec.json")
                       if (p.parent / "03_for_beso.inp").is_file()
                       and digest(p.parent / "03_for_beso.inp") == digest(original_deck)]
        if len(source_dirs) != 1:
            raise ValueError("cannot unambiguously match original solved deck to a design specification")
        spec_path = source_dirs[0] / "prism_spec.json"
        original_spec = json.loads(spec_path.read_text(encoding="utf-8"))
        geometry_path = previous / "sized_geometry.json"
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
        baseline_hashes = {str(p): digest(p) for p in (original_deck, spec_path, geometry_path)}
        score = score_design(extract_geometry_metrics(geometry))
        validation = {**asdict(score), "validation_id": previous.name}
        gate = existing_halt_gate(validation)
        record("baseline_verified", files=baseline_hashes, score=validation["overall_score"], gate=gate)
        review = review_candidate(validation=validation, gate=gate, artifact_path=str(geometry_path))
        record("model_reviewed", candidate_review=review)
        if review.get("status") != "completed" or review.get("source") != "llm":
            record("review_incomplete")
            return
        recommendation = review["review"]["recommendation"]
        if recommendation == "reject" or (recommendation == "accept" and gate["ok"]):
            record("no_revision_requested", recommendation=recommendation)
            return
        original = DesignRequest(run_id, "prism", {"workspace_root": str(ROOT), "prism_spec": original_spec}, candidate_count=1)
        candidate = DesignCandidate(previous.name, 0, "prism", {"spec_path": str(spec_path)},
                                    {"artifact_path": str(geometry_path)},
                                    {"candidate_review": review, "overall_score": score.overall_score}, gate)
        policy = PrismRevisionPolicy()
        context = policy.context(original, original)
        proposal = propose_revision(candidate=candidate, context=context)
        record("revision_proposed", proposal=proposal)
        if proposal.get("status") != "completed" or proposal.get("source") != "llm":
            record("planner_incomplete")
            return
        if proposal["proposal"]["action"] == "stop":
            record("planner_stopped")
            return
        # A nonempty geometric patch must fail under the locked contract.
        try:
            policy.apply(original, original, proposal["proposal"]["patch"])
        except ValueError:
            record("geometry_change_rejected")
        else:
            raise ValueError("fixed geometry contract unexpectedly accepted a revision")
        if any(digest(p) != h for p, h in baseline_hashes.items()):
            raise ValueError("historical evidence changed")
        record("completed_requested_stages", original_files_unchanged=True, selected=False)
    except Exception as exc:
        record("failed", error_type=type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
