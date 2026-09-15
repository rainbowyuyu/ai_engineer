"""Batch decisions stay auditable when rule explanations are unnecessary or fail."""
import json
from pathlib import Path

import pytest

from backend.engineer_plus.service import review_and_select


def review_payload(mode="rule_scores_no_findings_model_not_called", status="completed",
                   source="llm", recommendation="accept", score=90):
    return {"overall_score": score, "ai_review_scores": {"strength": score},
            "validation_id": "unit-test", "review_mode": mode,
            "candidate_review": {"status": status, "source": source,
                                 "review": {"recommendation": recommendation}}}


def batch(tmp_path, monkeypatch, outcomes, gate_ok=True):
    registered, selected, calls = [], [], []
    iterator = iter(outcomes)
    def reviewer(payload):
        calls.append(payload)
        outcome = next(iterator)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    def register(task, **kwargs):
        registered.append(kwargs)
        return {"candidate_id": f"candidate-{len(registered)}"}
    monkeypatch.setattr("backend.engineer_plus.adapters.real_reviewer", lambda **kw: reviewer)
    monkeypatch.setattr("backend.engineer_plus.service.existing_halt_gate",
                        lambda r: {"ok": gate_ok, "reason": "test gate"})
    monkeypatch.setattr("backend.candidates.registry.register_candidate", register)
    monkeypatch.setattr("backend.candidates.registry.select_candidate",
                        lambda task, cid: selected.append(cid))
    paths = []
    for i in range(len(outcomes)):
        path = tmp_path / f"geometry-{i}.json"
        path.write_text(json.dumps({"index": i}), encoding="utf-8")
        paths.append(str(path))
    result = review_and_select(task_id="unit-batch", construction="prism",
                               geometry_paths=paths, workspace_root=tmp_path)
    saved = json.loads(Path(result["event_path"]).read_text(encoding="utf-8"))
    assert saved["events"] == result["events"]
    return result, registered, selected, calls


def test_candidate_exception_does_not_abort_peers_or_leak_message(tmp_path, monkeypatch):
    result, registered, selected, calls = batch(tmp_path, monkeypatch,
        [TimeoutError("private-provider-detail"), review_payload()])
    assert len(calls) == 2
    assert result["status"] == "selected"
    assert result["selected"]["index"] == 1
    assert len(registered) == len(selected) == 1
    excluded = next(e for e in result["events"] if e["kind"] == "candidate_excluded")
    assert excluded["error_type"] == "TimeoutError"
    assert excluded["reason"] == "review_execution_failed"
    assert "private-provider-detail" not in Path(result["event_path"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("failed,reason", [
    (review_payload(status="unavailable", source="none"), "candidate_ai_review_incomplete"),
    (review_payload(source="template"), "candidate_ai_review_incomplete"),
    (review_payload(mode="template_explanations_provider_failed"), "rule_explanations_incomplete"),
])
def test_missing_review_cannot_select_even_with_high_score(tmp_path, monkeypatch, failed, reason):
    failed["overall_score"] = 99
    result, registered, selected, calls = batch(tmp_path, monkeypatch, [failed, review_payload()])
    assert len(calls) == 2 and len(registered) == len(selected) == 1
    assert result["selected"]["index"] == 1
    excluded = next(e for e in result["events"] if e["kind"] == "candidate_excluded")
    assert excluded["reason"] == reason
    assert excluded["candidate_review"] == failed["candidate_review"]


@pytest.mark.parametrize("recommendation,gate_ok", [("revise", True), ("reject", True), ("accept", False)])
def test_no_findings_never_bypasses_ai_decision_or_gate(tmp_path, monkeypatch, recommendation, gate_ok):
    result, _, selected, _ = batch(tmp_path, monkeypatch,
        [review_payload(recommendation=recommendation)], gate_ok=gate_ok)
    assert result["status"] == "review_failed"
    assert result["selected"] is None and selected == []


def test_all_excluded_still_produces_failure_audit(tmp_path, monkeypatch):
    result, registered, selected, calls = batch(tmp_path, monkeypatch,
        [TimeoutError(), review_payload(status="invalid_response")])
    assert len(calls) == 2
    assert result["status"] == "failed"
    assert registered == selected == []
    assert sum(e["kind"] == "candidate_excluded" for e in result["events"]) == 2
