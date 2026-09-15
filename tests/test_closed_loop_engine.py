from backend.engineer_plus.engine import ClosedLoopEngine, DesignRequest
from backend.engineer_plus.adapters import existing_halt_gate
from backend.engineer_plus.registry import ConstructionAdapter, ConstructionRegistry
import pytest


def test_generic_loop_reviews_all_candidates_and_selects_best_passing_one():
    saved = []
    engine = ClosedLoopEngine(
        gate=lambda review: {"ok": review["overall_score"] >= 85},
        registry=lambda task, candidate: saved.append((task, candidate)),
    )
    request = DesignRequest("task-1", "cantilever", {"length": 4}, candidate_count=3)
    scores = iter([82, 91, 88])
    result = engine.run(
        request,
        build_domain=lambda req, candidate_index: {"geometry": {"i": candidate_index}},
        run_topology=lambda domain, candidate_index: {"artifact_path": f"run/{candidate_index}.inp"},
        review=lambda topology: {"overall_score": next(scores), "score_source": "real-review"},
    )
    assert result.status == "selected"
    assert result.candidates[1].selected
    assert result.selected_candidate_id == result.candidates[1].candidate_id
    assert len(saved) == 3
    assert all(e["kind"] == "review_complete" for e in result.events if e["kind"] == "review_complete")


def test_preview_cannot_claim_closed_loop_success():
    engine = ClosedLoopEngine(gate=lambda review: {"ok": True})
    request = DesignRequest("task-2", "plate", {}, execution_mode="preview")
    try:
        engine.run(request, build_domain=lambda r, candidate_index: {"geometry": {}},
                   run_topology=lambda d, candidate_index: {"geometry": {}},
                   review=lambda a: {"overall_score": 99})
    except RuntimeError as exc:
        assert "Preview" in str(exc)
    else:
        raise AssertionError("preview must not claim a completed loop")


def test_production_gate_is_used_for_real_review_payload():
    verdict = existing_halt_gate({
        "overall_score": 90,
        "ai_review_scores": {"capacity_mw": 90, "steel_per_mw": 86},
    })
    assert verdict["ok"] is True
    assert verdict["S_min"] == 85.0


def test_replan_is_bounded_and_registry_is_construction_neutral(tmp_path):
    registry = ConstructionRegistry()
    registry.register(ConstructionAdapter("frame", "generic frame", lambda r, candidate_index: {"geometry": {}},
                                          lambda d, candidate_index: {"geometry": {}}))
    assert registry.catalog()[0]["name"] == "frame"
    calls = []
    def recover(request, error, *, candidate_index, attempt):
        calls.append(attempt)
        return {"mesh": "coarser"}
    result = ClosedLoopEngine(gate=lambda r: {"ok": True}).run(
        DesignRequest("t", "frame", {}, candidate_count=1, max_replans=2),
        build_domain=lambda r, candidate_index: (_ for _ in ()).throw(ValueError("bad domain")),
        run_topology=lambda d, candidate_index: {"geometry": {}},
        review=lambda a: {"overall_score": 99}, recover=recover,
        event_path=tmp_path / "events.json")
    assert result.status == "failed" and calls == [1, 2]
    assert (tmp_path / "events.json").is_file()


def test_review_select_rejects_paths_outside_workspace(tmp_path):
    from backend.engineer_plus.service import review_and_select
    try:
        review_and_select(task_id="t", construction="plate", geometry_paths=["../outside.json"],
                          workspace_root=tmp_path)
    except ValueError as exc:
        assert "inside workspace" in str(exc)
    else:
        raise AssertionError("workspace escape must be rejected")


def test_review_without_source_or_finite_score_cannot_be_selected():
    engine = ClosedLoopEngine(gate=lambda review: {"ok": True})
    request = DesignRequest("t3", "plate", {}, candidate_count=1)
    result = engine.run(request, build_domain=lambda r, candidate_index: {"geometry": {}},
                        run_topology=lambda d, candidate_index: {"geometry": {}},
                        review=lambda a: {"overall_score": float("nan")})
    assert result.status == "failed"


def test_natural_language_request_routes_to_registered_construction():
    assert DesignRequest.from_text("t4", "请设计一个 20MW 半潜式漂浮风机基础").construction == "oc4"
    assert DesignRequest.from_text("t5", "三棱柱设计域，体积分数 5%").construction == "prism"
    assert DesignRequest.from_text("t6", "优化 model.step 的结构").construction == "cad"
    assert DesignRequest.from_text("t6b", "任意工程构型", construction="frame").construction == "frame"


def test_replan_patch_is_used_by_next_attempt():
    seen = []
    req = DesignRequest("t7", "frame", {"mesh": "fine"}, candidate_count=1, max_replans=1)
    def build(request, *, candidate_index):
        seen.append(request.requirements["mesh"])
        if len(seen) == 1:
            raise RuntimeError("mesh failed")
        return {"geometry": {"mesh": request.requirements["mesh"]}}
    result = ClosedLoopEngine(gate=lambda _: {"ok": True}).run(
        req, build_domain=build,
        run_topology=lambda d, candidate_index: {"geometry": d["geometry"]},
        review=lambda _: {"overall_score": 90, "score_source": "test"},
        recover=lambda request, error, candidate_index, attempt: {"mesh": "coarse"},
    )
    assert result.status == "selected"
    assert seen == ["fine", "coarse"]


def test_live_loop_records_hashed_artifacts_in_events(tmp_path):
    domain_file = tmp_path / "domain.inp"
    topology_file = tmp_path / "topology.inp"
    domain_file.write_text("domain", encoding="utf-8")
    topology_file.write_text("topology", encoding="utf-8")
    events = tmp_path / "events.json"
    request = DesignRequest("hashed", "frame", {
        "workspace_root": str(tmp_path),
    })

    result = ClosedLoopEngine(gate=lambda _: {"ok": True}).run(
        request,
        build_domain=lambda *_args, **_kwargs: {"artifact_path": str(domain_file)},
        run_topology=lambda *_args, **_kwargs: {"artifact_path": str(topology_file)},
        review=lambda *_args, **_kwargs: {"overall_score": 90, "score_source": "test"},
        event_path=events,
    )

    assert result.status == "selected"
    manifest = {item["path"]: item for item in result.artifact_manifest}
    assert manifest[str(domain_file.resolve())]["sha256"]
    assert manifest[str(topology_file.resolve())]["sha256"]
    payload = events.read_text(encoding="utf-8")
    assert "artifact_manifest" in payload
    assert manifest[str(domain_file.resolve())]["sha256"] in payload


def test_registry_failure_does_not_expose_phantom_candidate():
    req = DesignRequest("t8", "frame", {}, candidate_count=1)
    result = ClosedLoopEngine(
        gate=lambda _: {"ok": True},
        registry=lambda *_: (_ for _ in ()).throw(RuntimeError("registry offline")),
    ).run(req,
          build_domain=lambda *_args, **_kwargs: {"geometry": {}},
          run_topology=lambda *_args, **_kwargs: {"geometry": {}},
          review=lambda *_args, **_kwargs: {"overall_score": 90, "score_source": "test"})
    assert result.status == "failed"
    assert result.candidates == []
    assert result.events[-2]["kind"] == "candidate_failed"
    assert result.events[-1]["kind"] == "loop_failed"


def test_review_rejects_boolean_and_out_of_range_scores():
    for bad in (True, -1, 101):
        result = ClosedLoopEngine(gate=lambda _: {"ok": True}).run(
            DesignRequest("score", "frame", {}, candidate_count=1),
            build_domain=lambda *_args, **_kwargs: {"geometry": {}},
            run_topology=lambda *_args, **_kwargs: {"geometry": {}},
            review=lambda *_args, bad=bad, **_kwargs: {"overall_score": bad, "score_source": "test"},
        )
        assert result.status == "failed"


@pytest.mark.parametrize("review_mode", ["llm_explanations_with_rule_scores",
                                        "rule_scores_no_findings_model_not_called"])
def test_ai_recommendation_participates_in_formal_selection(tmp_path, review_mode):
    validation = tmp_path
    (validation / "validation_score.json").write_text("{}")
    (validation / "rationale_review.json").write_text("{}")
    (tmp_path / "topology_provenance.json").write_text("{}")
    req = DesignRequest("ai-select", "frame", {"require_artifacts": True,
        "require_ai_review": True}, candidate_count=2)
    recs = iter(["reject", "accept"])
    result = ClosedLoopEngine(gate=lambda _: {"ok": True}).run(
        req,
        build_domain=lambda *_args, **_kwargs: {"artifact_path": str(tmp_path / "topology_provenance.json")},
        run_topology=lambda *_args, **_kwargs: {"artifact_path": str(tmp_path / "topology_provenance.json"),
            "topology_provenance": str(tmp_path / "topology_provenance.json")},
        review=lambda *_args, **_kwargs: {"overall_score": 90, "score_source": "test",
            "validation_dir": str(validation), "review_mode": review_mode,
            "candidate_review": {"status": "completed", "source": "llm",
                "review": {"recommendation": next(recs)}}},
    )
    assert result.status == "selected"
    assert result.candidates[1].selected


def test_review_select_requires_ai_accept_before_persisted_selection(tmp_path, monkeypatch):
    """The direct review-select service must not bypass candidate AI review."""
    from backend.engineer_plus.service import review_and_select

    first = tmp_path / "candidate_1.json"
    second = tmp_path / "candidate_2.json"
    first.write_text('{"candidate": 1}', encoding="utf-8")
    second.write_text('{"candidate": 2}', encoding="utf-8")

    reviews = iter([
        {"overall_score": 99, "ai_review_scores": {"strength": 99},
         "validation_id": "v1", "out_dir": str(tmp_path / "v1"),
         "review_mode": "llm_explanations_with_rule_scores",
         "candidate_review": {"status": "completed", "source": "llm",
                               "review": {"recommendation": "reject"}}},
        {"overall_score": 90, "ai_review_scores": {"strength": 90},
         "validation_id": "v2", "out_dir": str(tmp_path / "v2"),
         "review_mode": "llm_explanations_with_rule_scores",
         "candidate_review": {"status": "completed", "source": "llm",
                               "review": {"recommendation": "accept"}}},
    ])
    for name in ("v1", "v2"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "validation_score.json").write_text("{}", encoding="utf-8")
        (folder / "rationale_review.json").write_text("{}", encoding="utf-8")

    class FakeReviewer:
        def __call__(self, _payload):
            return next(reviews)

    monkeypatch.setattr("backend.engineer_plus.adapters.real_reviewer",
                        lambda **_kwargs: FakeReviewer())
    monkeypatch.setattr("backend.engineer_plus.service.existing_halt_gate",
                        lambda _review: {"ok": True, "reason": "test"})
    selected = []
    monkeypatch.setattr("backend.candidates.registry.select_candidate",
                        lambda task_id, candidate_id: selected.append((task_id, candidate_id)))

    result = review_and_select(task_id="direct-select", construction="frame",
                               geometry_paths=[str(first), str(second)],
                               workspace_root=tmp_path)

    assert result["status"] == "selected"
    assert result["selected"]["index"] == 1
    assert result["candidates"][0]["selected"] is False
    assert result["candidates"][1]["selected"] is True
    assert len(selected) == 1
