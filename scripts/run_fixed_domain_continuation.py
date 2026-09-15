"""Run genuine reviewer-directed BESO continuation on the original prism mesh.

The seed is the retained, independently reviewed 95 m candidate. No new
geometry values are proposed, no scores are supplied by fixtures, and the
original experiment is never overwritten. The loop may legitimately fail.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration-budget", default="auto")
    parser.add_argument("--max-replans", type=int, choices=range(6), default=1)
    args = parser.parse_args()
    budget = args.iteration_budget if args.iteration_budget == "auto" else int(args.iteration_budget)
    if budget != "auto" and not 1 <= budget <= 1000:
        parser.error("iteration budget must be auto or 1..1000")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    os.environ["WORKSPACE_ROOT"] = str(ROOT)
    os.environ["MPLBACKEND"] = "Agg"
    os.environ.setdefault("FREECAD_CMD", r"D:\freecad\bin\FreeCADCmd.exe")
    os.environ.setdefault("CALCULIX_CMD", r"D:\freecad\bin\ccx.exe")
    from backend.engineer_plus.engine import ClosedLoopEngine, DesignCandidate, DesignRequest
    from backend.engineer_plus.revision import PrismRevisionPolicy, propose_revision
    from backend.engineer_plus.topology_checkpoint import inspect_checkpoint, sha256
    from backend.engineer_plus.builtin_adapters import _build_prism, _run_beso_and_size
    from backend.engineer_plus.adapters import existing_halt_gate, real_reviewer
    from backend.validation.geometry_metrics import extract_geometry_metrics
    from backend.validation.scorer import score_design

    task = "fixed-domain-" + uuid.uuid4().hex
    out = ROOT / "tmp" / "results" / "fixed_domain_continuation" / task
    out.mkdir(parents=True)
    report = {"task_id": task, "pid": os.getpid(), "status": "started", "events": [],
              "scope": "fixed-domain element-state continuation; not exact optimizer replay or external certification"}

    def record(stage, **data):
        report["status"] = stage
        report["events"].append({"stage": stage, **data})
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"stage": stage, "report": str(out / "report.json"),
                          **{k: v for k, v in data.items() if k in {"job_id", "run_dir", "overall_score"}}}, ensure_ascii=False), flush=True)

    try:
        source = ROOT / "runs" / "42b2eed865554070af28855c75d5a948"
        deck = source / "03_for_beso.inp"
        matches = [p.parent for p in (ROOT / "_plus").glob("*/candidate_1/prism_spec.json")
                   if (p.parent / deck.name).is_file() and sha256(p.parent / deck.name) == sha256(deck)]
        if len(matches) != 1:
            raise ValueError("original design domain could not be uniquely identified")
        domain_root = matches[0]
        spec_path = domain_root / "prism_spec.json"
        geometry = source / "sized_geometry.json"
        retained_review_path = (ROOT / "tmp/results/live_revision" /
                               "live-revision-e5001fc2060d472bb65ac13d2ea7bd3a/report.json")
        retained = json.loads(retained_review_path.read_text(encoding="utf-8"))
        baseline_hashes = retained["events"][0]["files"]
        if any(sha256(Path(p)) != h for p, h in baseline_hashes.items()):
            raise ValueError("reviewed baseline artifacts have changed")
        model_review = next(e["candidate_review"] for e in retained["events"] if e["stage"] == "model_reviewed")
        if model_review.get("status") != "completed" or model_review.get("source") != "llm":
            raise ValueError("seed lacks a real completed candidate review")
        if model_review["review"]["recommendation"] != "revise":
            raise ValueError("seed review does not request revision")
        score = score_design(extract_geometry_metrics(json.loads(geometry.read_text(encoding="utf-8"))))
        if score.overall_score != model_review["evidence"]["overall_score"] or score.ai_review_scores != model_review["evidence"]["ai_review_scores"]:
            raise ValueError("current scoring differs from the retained review")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        checkpoint = inspect_checkpoint(source_run=source, target_input=domain_root / deck.name, workspace_root=ROOT)
        req = DesignRequest(task, "prism", {
            "workspace_root": str(ROOT), "prism_spec": spec, "design_variable_bounds": {},
            "topology_iteration_budget": budget, "require_artifacts": True, "require_ai_review": True,
        }, candidate_count=1, max_replans=args.max_replans)
        candidate = DesignCandidate(source.name, 0, "prism", {
            "artifact_path": str(domain_root / deck.name), "fcstd_path": str(domain_root / "design_domain.FCStd"),
            "spec_path": str(spec_path), "mass_goal_ratio": spec["mass_goal_ratio"],
            "input_sha256": sha256(deck),
        }, {"source_run": str(source), "source_state1_path": checkpoint["source_state1_path"],
            "topology_provenance_data": {"source_state1_sha256": checkpoint["source_state1_sha256"]}},
            {"candidate_review": model_review, "overall_score": score.overall_score}, existing_halt_gate(asdict(score)))
        policy = PrismRevisionPolicy()
        context = policy.context(req, req, candidate=candidate)
        record("seed_verified", baseline_hashes=baseline_hashes,
               retained_review_path=str(retained_review_path), retained_review_sha256=sha256(retained_review_path),
               original_spec=spec, checkpoint={k: v for k, v in checkpoint.items() if k != "states"})
        proposal = propose_revision(candidate=candidate, context=context)
        record("model_planned", proposal=proposal)
        if proposal.get("status") != "completed" or proposal.get("source") != "llm":
            record("planner_incomplete")
            return
        if proposal["proposal"]["action"] == "stop":
            record("planner_stopped")
            return
        start_request = policy.apply(req, req, proposal["proposal"]["patch"], candidate=candidate)

        def solve(domain, *, candidate_index):
            return _run_beso_and_size(domain, candidate_index=candidate_index,
                                     on_job_started=lambda job: record("beso_started", **job))

        underlying_review = real_reviewer(out_root=out / "validation")
        def review(topology):
            record("physics_completed", topology=topology)
            result = underlying_review(topology)
            record("candidate_reviewed", overall_score=result["overall_score"], review=result)
            return result

        result = ClosedLoopEngine(gate=existing_halt_gate).run(
            start_request, build_domain=_build_prism, run_topology=solve, review=review,
            revision_policy=policy, event_path=out / "events.json")
        if any(sha256(Path(p)) != h for p, h in baseline_hashes.items()):
            raise ValueError("baseline artifacts changed during continuation")
        record("loop_" + result.status, selected_candidate_id=result.selected_candidate_id,
               event_path=str(out / "events.json"), original_files_unchanged=True)
    except Exception as exc:
        record("failed", error_type=type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
