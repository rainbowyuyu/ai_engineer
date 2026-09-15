"""Controlled end-to-end revision tests; these are not live solver/model results."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.engineer_plus.engine import ClosedLoopEngine, DesignRequest
from backend.engineer_plus.revision import PrismRevisionPolicy, prism_spec


def reply(patch=None, action="revise"):
    return {"status": "completed", "source": "llm", "proposal": {
        "action": action, "patch": patch if patch is not None else {"prism_spec": {"side_mm": 90000}},
        "rationale": "Reduce the footprint and recompute the recorded steel-intensity failure.",
    }}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    request = DesignRequest("revision", "prism", {
        "workspace_root": str(tmp_path), "require_artifacts": True, "require_ai_review": True,
        "design_variable_bounds": {"side_mm": [76000, 114000]},
    }, candidate_count=1, max_replans=2)
    events = tmp_path / "events.json"
    calls = []
    decisions = ["revise", "accept"]

    def build(req, *, candidate_index):
        # The production callback is used with external CAD/mesher stubs, so
        # this exercises actual spec consumption and attempt folder routing.
        from backend.engineer_plus.builtin_adapters import _build_prism
        calls.append(prism_spec(req))
        return _build_prism(req, candidate_index=candidate_index)

    def cad(*, spec, out_fcstd):
        out_fcstd.write_text(json.dumps(spec.to_dict()))
        return out_fcstd

    def mesh(*, fcstd, out_inp, spec):
        assert json.loads(fcstd.read_text())["side_mm"] == spec.side_mm
        out_inp.write_text(json.dumps(spec.to_dict()))
        return out_inp

    monkeypatch.setattr("backend.tools.prism_design_domain.run_prism_build_fcstd", cad)
    monkeypatch.setattr("backend.tools.prism_design_domain.run_prism_mesh_inp", mesh)

    def solve(domain, *, candidate_index):
        root = Path(domain["artifact_path"]).parent
        # The simulated solver output depends on the newly built domain.
        side = json.loads(Path(domain["artifact_path"]).read_text())["side_mm"]
        artifact = root / "sized.json"
        artifact.write_text(json.dumps({"side_mm": side}))
        provenance = root / "topology_provenance.json"
        provenance.write_text(json.dumps({"domain_sha256": hashlib.sha256(Path(domain["artifact_path"]).read_bytes()).hexdigest()}))
        return {"artifact_path": str(artifact), "topology_provenance": str(provenance)}

    def review(topology):
        assert json.loads(events.read_text())["events"][-1]["kind"] == "topology_ready"
        geometry = json.loads(Path(topology["artifact_path"]).read_text())
        score = 76 if geometry["side_mm"] == 95000 else 91
        dest = Path(topology["artifact_path"]).parent / "validation"
        dest.mkdir()
        (dest / "validation_score.json").write_text(json.dumps({"overall_score": score}))
        (dest / "rationale_review.json").write_text('{}')
        return {"overall_score": score, "score_source": "controlled_test",
                "validation_dir": str(dest), "review_mode": "rule_scores_no_findings_model_not_called",
                "candidate_review": {"status": "completed", "source": "llm",
                                     "review": {"recommendation": decisions.pop(0)}}}

    def run(**kwargs):
        return ClosedLoopEngine(gate=lambda r: {"ok": r["overall_score"] >= 85}).run(
            request, build_domain=build, run_topology=solve, review=review,
            revision_policy=PrismRevisionPolicy(), event_path=events, **kwargs)

    monkeypatch.setattr("backend.engineer_plus.revision.propose_revision", lambda **_: reply())
    return request, run, calls, decisions, events


def test_revise_rebuild_solve_review_select_retains_every_attempt(harness):
    request, run, calls, _, events = harness
    result = run()
    assert result.status == "selected"
    assert [s["side_mm"] for s in calls] == [95000, 90000]
    assert calls[0]["force_n"] == calls[1]["force_n"]
    assert "prism_spec" not in request.requirements
    first, second = result.candidates
    assert second.parent_candidate_id == first.candidate_id
    assert [first.attempt, second.attempt] == [0, 1]
    assert not first.selected and second.selected
    assert first.domain["artifact_path"] != second.domain["artifact_path"]
    assert first.review["validation_dir"] != second.review["validation_dir"]
    for item in result.artifact_manifest:
        if item["kind"] == "file":
            assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
    assert json.loads(events.read_text())["status"] == "selected"


@pytest.mark.parametrize("patch", [
    {"require_ai_review": False}, {"workspace_root": "elsewhere"},
    {"prism_spec": {"force_n": 1}}, {"prism_spec": {"mass_goal_ratio": 0.01}},
    {"prism_spec": {"side_mm": 20000}}, {"prism_spec": {"side_mm": 95000}},
    {"prism_spec": {"side_mm": float("nan")}}, {"prism_spec": {"side_mm": True}},
])
def test_invalid_model_patch_never_reaches_a_second_build(harness, monkeypatch, patch):
    _, run, calls, _, _ = harness
    monkeypatch.setattr("backend.engineer_plus.revision.propose_revision", lambda **_: reply(patch))
    result = run()
    assert result.status == "review_failed" and len(calls) == 1
    assert any(e.get("reason") == "invalid_revision" for e in result.events)


@pytest.mark.parametrize("proposal", [
    {"status": "invalid_response", "source": "none"}, reply({}, "stop"),
])
def test_planner_unavailable_or_stop_does_not_retry(harness, monkeypatch, proposal):
    _, run, calls, _, _ = harness
    monkeypatch.setattr("backend.engineer_plus.revision.propose_revision", lambda **_: proposal)
    assert run().status == "review_failed"
    assert len(calls) == 1


def test_reject_is_terminal_even_when_revision_policy_exists(harness):
    _, run, calls, decisions, _ = harness
    decisions[:] = ["reject"]
    assert run().status == "review_failed"
    assert len(calls) == 1


def test_locked_geometry_stops_without_requesting_an_impossible_patch(harness, monkeypatch):
    request, run, calls, _, _ = harness
    request.requirements["design_variable_bounds"] = {}
    planner = Mock()
    monkeypatch.setattr("backend.engineer_plus.revision.propose_revision", planner)
    result = run()
    planner.assert_not_called()
    assert result.status == "review_failed" and len(calls) == 1
    assert any(e.get("reason") == "no_authorized_revision_variables" for e in result.events)


def test_return_to_prior_spec_is_blocked(harness, monkeypatch):
    _, run, calls, decisions, _ = harness
    decisions[:] = ["revise", "revise"]
    proposals = iter([reply(), reply({"prism_spec": {"side_mm": 95000}})])
    monkeypatch.setattr("backend.engineer_plus.revision.propose_revision", lambda **_: next(proposals))
    assert run().status == "review_failed"
    assert len(calls) == 2


def test_bounds_are_original_not_compounded_and_can_lock_geometry():
    policy = PrismRevisionPolicy()
    original = DesignRequest("bounds", "prism", {"design_variable_bounds": {"side_mm": [76000, 114000]}})
    current = policy.apply(original, original, {"prism_spec": {"side_mm": 110000}})
    with pytest.raises(ValueError):
        policy.apply(original, current, {"prism_spec": {"side_mm": 120000}})
    locked = replace(original, requirements={"design_variable_bounds": {}})
    with pytest.raises(ValueError):
        policy.apply(locked, locked, {"prism_spec": {"side_mm": 90000}})


def test_default_contract_preserves_original_prism_values():
    policy = PrismRevisionPolicy()
    original = DesignRequest("locked", "prism", {})
    assert policy.context(original, original)["allowed_patch"] == {"prism_spec": {}}
    for name in policy.fields:
        with pytest.raises(ValueError):
            policy.apply(original, original, {"prism_spec": {name: prism_spec(original)[name] * 0.9}})


def test_recovery_cannot_mutate_authority_or_leak_error(tmp_path):
    req = DesignRequest("recover", "prism", {"require_ai_review": True}, candidate_count=1)
    def recover(request, error, **_):
        request.requirements["require_ai_review"] = False
        return {"require_ai_review": False}
    result = ClosedLoopEngine(gate=lambda _: {"ok": True}).run(
        req, build_domain=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("private credential")),
        run_topology=Mock(), review=Mock(), recover=recover)
    assert result.status == "failed"
    assert req.requirements["require_ai_review"] is True
    assert "private credential" not in json.dumps(result.events)


def test_production_service_connects_policy_and_uses_safe_task(tmp_path, monkeypatch):
    from backend.engineer_plus.service import run_registered_loop
    from backend.engineer_plus.engine import LoopResult
    captured = []
    def execute(self, request, **kwargs):
        captured.append((request, kwargs))
        return LoopResult(task_id=request.task_id, status="review_failed")
    monkeypatch.setattr(ClosedLoopEngine, "run", execute)
    monkeypatch.setattr("backend.engineer_plus.adapters.real_reviewer", lambda **_: Mock())
    for _ in range(2):
        run_registered_loop(task_id="folder/task", construction="prism",
                            requirements={"design_variable_bounds": {"side_mm": [1, 1e9]}},
                            candidate_count=1, workspace_root=tmp_path)
    assert captured[0][0].task_id == "folder_task"
    assert captured[0][0].requirements["design_variable_bounds"] == {}
    assert isinstance(captured[0][1]["revision_policy"], PrismRevisionPolicy)
    assert captured[0][1]["event_path"] != captured[1][1]["event_path"]


def test_real_planner_schema_provenance_and_evidence(monkeypatch):
    from backend.engineer_plus.engine import DesignCandidate
    from backend.engineer_plus.revision import propose_revision
    candidate = DesignCandidate("test", 0, "prism", {}, {},
                                {"candidate_review": {"evidence": {"metrics": {"steel": 289}}}}, {"ok": False})
    client = Mock(api_key="test", model="test")
    client.chat.return_value = {"id": "r1", "model": "test", "choices": [{
        "finish_reason": "stop", "message": {"content": json.dumps(reply()["proposal"])}}]}
    monkeypatch.setattr("backend.qwen_client.QwenClient", lambda: client)
    result = propose_revision(candidate=candidate, context={"allowed_patch": {}})
    assert result["status"] == "completed" and result["source"] == "llm"
    assert result["response_id"] == "r1"
    assert len(result["response_sha256"]) == 64
    assert '289' in client.chat.call_args.args[0][1]["content"]
    client.chat.return_value["choices"][0]["finish_reason"] = "length"
    invalid = propose_revision(candidate=candidate, context={})
    assert invalid["status"] == "invalid_response"
    assert invalid["finish_reason"] == "length" and invalid["response_text"]
