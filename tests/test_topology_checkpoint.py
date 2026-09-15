"""Fixed-domain state transfer; all fixture solves/reviews are controlled stubs."""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.engineer_plus.topology_checkpoint import (
    inspect_checkpoint, install_checkpoint, read_literal_config, read_mesh, sha256,
)
from backend.engineer_plus.engine import DesignCandidate, DesignRequest
from backend.engineer_plus.revision import PrismRevisionPolicy, prism_spec


@pytest.fixture
def checkpoint_case(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    nodes = "*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n5,1,1,1\n"
    full = nodes + "*ELEMENT,TYPE=C3D4,ELSET=solid\n1,1,2,3,4\n2,2,3,4,5\n*ELSET,ELSET=Eall\nsolid\n"
    (source / "03_for_beso.inp").write_text(full)
    (source / "status.json").write_text('{"status":"completed"}')
    (source / "beso_conf.py").write_text(
        "file_name = '03_for_beso.inp'\nelset_name = 'Eall'\n"
        "domain_optimized[elset_name] = True\ndomain_density[elset_name] = [1e-6, 1]\n"
        "domain_material[elset_name] = ['original void', 'original solid']\n"
        "mass_goal_ratio = 0.15\nfilter_list = [['simple', 2.0]]\noptimization_base = 'stiffness'\niterations_limit = 2\n")
    for state, row in ((0, "1,1,2,3,4"), (1, "2,2,3,4,5")):
        (source / f"file002_state{state}.inp").write_text(nodes + f"*ELEMENT,TYPE=C3D4,ELSET=state{state}\n{row}\n")
    request = DesignRequest("fixed", "prism", {"workspace_root": str(tmp_path), "topology_iteration_budget": 2})
    (source / "prism_spec.json").write_text(json.dumps(prism_spec(request)))
    (source / "design_domain.FCStd").write_bytes(b"controlled CAD fixture")
    candidate = DesignCandidate("candidate", 0, "prism",
        {"artifact_path": str(source / "03_for_beso.inp"), "spec_path": str(source / "prism_spec.json"),
         "fcstd_path": str(source / "design_domain.FCStd"), "mass_goal_ratio": 0.15},
        {"source_run": str(source), "source_state1_path": str(source / "file002_state1.inp")}, {}, {})
    candidate.domain["input_sha256"] = sha256(source / "03_for_beso.inp")
    candidate.topology["topology_provenance_data"] = {"source_state1_sha256": sha256(source / "file002_state1.inp")}
    return tmp_path, source, request, candidate


def inspect(case):
    root, source, _, _ = case
    return inspect_checkpoint(source_run=source, target_input=source / "03_for_beso.inp", workspace_root=root)


def test_complete_state_partition_restores_original_configuration(checkpoint_case):
    root, source, _, _ = checkpoint_case
    checkpoint = inspect(checkpoint_case)
    assert checkpoint["states"] == {1: 0, 2: 1}
    assert checkpoint["configured_elements"] == checkpoint["elements"] == 2
    target = root / "next"
    target.mkdir()
    inp = target / "03_for_beso.inp"
    inp.write_bytes((source / inp.name).read_bytes())
    before = {p.name: sha256(p) for p in source.iterdir() if p.is_file()}
    report = install_checkpoint(checkpoint=checkpoint, run_dir=target, target_input=inp,
                                ccx_path=root / "ccx", iterations_limit=2)
    new_config = read_literal_config(target / "beso_conf.py")
    assert new_config["mass_goal_ratio"] == 0.15
    assert new_config["domain_material"] == checkpoint["config"]["domain_material"]
    assert new_config["filter_list"] == checkpoint["config"]["filter_list"]
    assert Path(new_config["continue_from"]).read_text() == "element_number,element_state\n1,0\n2,1\n"
    assert json.loads(report.read_text())["checkpoint_semantics"].startswith("element-state warm start")
    assert before == {p.name: sha256(p) for p in source.iterdir() if p.is_file()}


@pytest.mark.parametrize("old,new", [
    ("2,1,0,0", "2,2,0,0"),  # same ids, different coordinates
    ("2,2,3,4,5", "2,3,2,4,5"),  # reordered connectivity
    ("2,2,3,4,5", "1,1,2,3,4"),  # overlap with state0
    ("2,2,3,4,5", "9,2,3,4,5"),  # unknown element
    ("2,2,3,4,5", ""),  # incomplete partition
])
def test_wrong_mesh_or_partition_is_rejected(checkpoint_case, old, new):
    _, source, _, _ = checkpoint_case
    state = source / "file002_state1.inp"
    state.write_text(state.read_text().replace(old, new))
    with pytest.raises(ValueError):
        inspect(checkpoint_case)


def test_protected_elements_may_not_enter_void_state(checkpoint_case):
    _, source, _, _ = checkpoint_case
    conf = source / "beso_conf.py"
    conf.write_text(conf.read_text().replace("= True", "= False"))
    with pytest.raises(ValueError, match="protected"):
        inspect(checkpoint_case)


@pytest.mark.parametrize("status", ["running", "failed", "cancelled"])
def test_noncompleted_jobs_cannot_be_resumed(checkpoint_case, status):
    _, source, _, _ = checkpoint_case
    (source / "status.json").write_text(json.dumps({"status": status}))
    with pytest.raises(ValueError, match="completed"):
        inspect(checkpoint_case)


def test_historical_run_requires_actual_solver_terminal_markers(checkpoint_case):
    _, source, _, _ = checkpoint_case
    (source / "status.json").unlink()
    log = source / "03_for_beso.log"
    log.write_text("last iteration exported\n")
    with pytest.raises(ValueError, match="completion"):
        inspect(checkpoint_case)
    log.write_text("Finished at  2026-09-13\nTotal time 1 minute\n")
    assert inspect(checkpoint_case)["completion_evidence"] == "legacy_solver_terminal_log"


def test_changed_input_and_changed_checkpoint_fail_before_install(checkpoint_case):
    root, source, _, _ = checkpoint_case
    changed = root / "changed.inp"
    changed.write_bytes((source / "03_for_beso.inp").read_bytes() + b"** modified\n")
    with pytest.raises(ValueError, match="identical"):
        inspect_checkpoint(source_run=source, target_input=changed, workspace_root=root)
    checkpoint = inspect(checkpoint_case)
    state = source / "file002_state1.inp"
    state.write_bytes(state.read_bytes() + b"** changed after audit\n")
    with pytest.raises(ValueError, match="changed during"):
        install_checkpoint(checkpoint=checkpoint, run_dir=root / "new", target_input=source / "03_for_beso.inp", ccx_path=root / "ccx")


def test_config_is_parsed_without_executing_it(checkpoint_case):
    root, source, _, _ = checkpoint_case
    config = source / "beso_conf.py"
    config.write_text("__import__('pathlib').Path('must_not_exist').touch()")
    with pytest.raises(ValueError, match="literal"):
        inspect(checkpoint_case)
    assert not (root / "must_not_exist").exists()


def test_fixed_domain_policy_allows_only_state_continuation(checkpoint_case, monkeypatch):
    _, source, request, candidate = checkpoint_case
    policy = PrismRevisionPolicy()
    context = policy.context(request, request, candidate=candidate)
    assert context["allowed_patch"] == {"topology_continuation": ["continue"]}
    updated = policy.apply(request, request, {"topology_continuation": "continue"}, candidate=candidate)
    assert prism_spec(updated) == prism_spec(request)
    with pytest.raises(ValueError):
        policy.apply(request, request, {"prism_spec": {"side_mm": 85500}}, candidate=candidate)
    with pytest.raises(ValueError, match="did not change"):
        policy.apply(request, updated, {"topology_continuation": "continue"}, candidate=candidate)
    from backend.engineer_plus.builtin_adapters import _build_prism
    cad = Mock(side_effect=AssertionError("must reuse the exact mesh, not remesh"))
    monkeypatch.setattr("backend.tools.prism_design_domain.run_prism_build_fcstd", cad)
    domain = _build_prism(replace(updated, attempt_id="attempt-2"), candidate_index=0)
    cad.assert_not_called()
    assert Path(domain["artifact_path"]) != Path(candidate.domain["artifact_path"])
    assert sha256(Path(domain["artifact_path"])) == sha256(Path(candidate.domain["artifact_path"]))
    assert domain["mass_goal_ratio"] == 0.15
    assert json.loads(Path(domain["spec_path"]).read_text()) == prism_spec(request)


def test_multiline_high_order_connectivity_and_generated_sets(tmp_path):
    path = tmp_path / "mesh.inp"
    path.write_text("*NODE\n" + "".join(f"{i},{i},0,0\n" for i in range(1, 21)) +
                    "*ELEMENT,TYPE=C3D20\n1,1,2,3,4,5,6,7,8,9,10,\n11,12,13,14,15,16,17,18,19,20\n"
                    "*ELSET,ELSET=solid,GENERATE\n1,1,1\n")
    mesh = read_mesh(path)
    assert mesh.element_set("solid") == {1}
    assert mesh.elements[1][1] == tuple(range(1, 21))


def test_reviewed_topology_cannot_be_replaced_before_planning(checkpoint_case):
    _, source, request, candidate = checkpoint_case
    state = source / "file002_state1.inp"
    state.write_bytes(state.read_bytes() + b"** replaced after review\n")
    with pytest.raises(ValueError, match="recorded review"):
        PrismRevisionPolicy().context(request, request, candidate=candidate)


def test_fixed_domain_loop_executes_reviewer_requested_continuation(checkpoint_case, monkeypatch):
    from backend.engineer_plus.engine import ClosedLoopEngine
    from backend.engineer_plus.builtin_adapters import _build_prism
    root, source, request, fixture = checkpoint_case
    request = replace(request, candidate_count=1,
                      requirements={**request.requirements, "require_ai_review": True})
    source_hash = sha256(source / "03_for_beso.inp")
    seen = []
    def build(req, *, candidate_index):
        if "_topology_continuation" not in req.requirements:
            return dict(fixture.domain)
        return _build_prism(req, candidate_index=candidate_index)
    def solve(domain, *, candidate_index):
        seen.append(domain)
        assert sha256(Path(domain["artifact_path"])) == source_hash
        if len(seen) == 1:
            return {**fixture.topology, "artifact_path": str(source / "file002_state1.inp")}
        assert domain["continuation"]["source_state1_sha256"] == sha256(source / "file002_state1.inp")
        # Controlled new topology; only element states change, never the mesh.
        artifact = Path(domain["artifact_path"]).parent / "new_topology.json"
        artifact.write_text('{"element_states":[1,0],"test_only":true}')
        return {"artifact_path": str(artifact)}
    recommendations = iter([("revise", 76), ("accept", 91)])
    def reviewer(_):
        rec, score = next(recommendations)
        return {"overall_score": score, "score_source": "controlled_test",
                "review_mode": "rule_scores_no_findings_model_not_called",
                "candidate_review": {"status": "completed", "source": "llm", "review": {"recommendation": rec}}}
    monkeypatch.setattr("backend.engineer_plus.revision.propose_revision", lambda **_: {
        "status": "completed", "source": "llm", "proposal": {
            "action": "revise", "patch": {"topology_continuation": "continue"},
            "rationale": "Continue the incomplete optimization on the fixed mesh."}})
    result = ClosedLoopEngine(gate=lambda r: {"ok": r["overall_score"] >= 85}).run(
        request, build_domain=build, run_topology=solve, review=reviewer,
        revision_policy=PrismRevisionPolicy(), event_path=root / "events.json")
    assert result.status == "selected" and len(result.candidates) == 2
    assert result.candidates[1].selected and not result.candidates[0].selected
    assert seen[0]["artifact_path"] != seen[1]["artifact_path"]
    assert result.candidates[1].parent_candidate_id == result.candidates[0].candidate_id
    assert sha256(source / "03_for_beso.inp") == source_hash
