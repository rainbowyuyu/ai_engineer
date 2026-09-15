"""Provider stubs test provenance handling, not live model quality."""
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from backend.validation.llm_rationale import generate_rationale_review
from backend.engineer_plus.adapters import real_reviewer, rationale_review_mode


@pytest.fixture
def case(monkeypatch):
    def rule(rid):
        return NS(id=rid, status="fail", description_zh="强度", measured=1.3,
                  threshold="<=1", source="solver", clause_ref=None)
    score = NS(rule_results=[rule("strength"), rule("fatigue")])
    client = Mock(api_key="test-only-not-a-real-key", model="provider-test")
    monkeypatch.setattr("backend.qwen_client.QwenClient", lambda: client)
    return score, client


def response(content="请复核截面与载荷。", finish="stop"):
    return {"id": "response-test", "model": "provider-test",
            "choices": [{"finish_reason": finish, "message": {"content": content}}]}


def test_missing_key_template_never_counts_as_model(case):
    score, client = case
    client.api_key = None
    result = generate_rationale_review(score)
    assert result["rationales"]
    assert result["status"] == "unavailable"
    assert result["attempted_calls"] == result["successful_calls"] == 0
    assert all(r["source"] == "template" and r["reason"] == "no_api_key"
               for r in result["records"].values())
    assert rationale_review_mode(result) == "template_explanations_model_unavailable"
    client.chat.assert_not_called()


def test_provider_errors_not_misreported_or_leaked(case):
    score, client = case
    client.chat.side_effect = RuntimeError("private-endpoint-with-secret")
    result = generate_rationale_review(score)
    assert result["status"] == "fallback"
    assert result["attempted_calls"] == 2
    assert result["successful_calls"] == 0
    assert "private-endpoint" not in json.dumps(result)


@pytest.mark.parametrize("provider_response,reason", [
    (response("  "), "empty_response"),
    (response(finish="length"), "incomplete_response"),
    (response(finish="content_filter"), "incomplete_response"),
    ({"choices": []}, "provider_error"),
])
def test_invalid_response_uses_explicit_template(case, provider_response, reason):
    score, client = case
    client.chat.return_value = provider_response
    result = generate_rationale_review(score)
    assert result["successful_calls"] == 0
    assert all(r["reason"] == reason for r in result["records"].values())


def test_partial_failure_is_visible_per_finding(case):
    score, client = case
    client.chat.side_effect = [response(), RuntimeError("timeout")]
    result = generate_rationale_review(score)
    assert result["status"] == "mixed"
    assert result["successful_calls"] == 1
    assert result["records"]["strength"]["source"] == "llm"
    assert result["records"]["fatigue"]["source"] == "template"
    assert len(result["records"]["strength"]["prompt_sha256"]) == 64


def test_complete_response_preserves_model_identity_and_score(case):
    score, client = case
    client.chat.return_value = response()
    result = generate_rationale_review(score)
    assert result["status"] == "completed"
    assert result["successful_calls"] == 2
    assert result["records"]["strength"]["response_id"] == "response-test"
    assert result["records"]["strength"]["returned_model"] == "provider-test"
    assert score.rule_results[0].measured == 1.3
    assert result["score_authority"] == "deterministic_rules"


@pytest.mark.parametrize("enabled,status", [(False, "disabled"), (True, "no_findings")])
def test_no_model_invocation_when_unneeded(case, enabled, status):
    score, client = case
    score.rule_results = []
    result = generate_rationale_review(score, use_llm=enabled)
    assert result["status"] == status
    assert result["attempted_calls"] == 0
    client.chat.assert_not_called()


def test_adapter_exposes_template_provenance(monkeypatch, tmp_path):
    import backend.validation.pipeline as pipeline
    bundle = {"status": "unavailable", "successful_calls": 0}
    monkeypatch.setattr(pipeline, "run_validation", lambda *a, **k: {
        "overall_score": 92, "llm_rationales": {"x": "模板建议"},
        "rationale_review": bundle, "rationale_review_path": str(tmp_path / "rationale_review.json"),
    })
    result = real_reviewer(out_root=tmp_path)({"geometry": {"test": True}})
    assert result["review_mode"] == "template_explanations_model_unavailable"
    assert result["rationale_review"] == bundle
    assert result["score_source"].endswith(":deterministic_rules")


@pytest.mark.parametrize("finish", ["stop", "length", "content_filter", None])
def test_langchain_transport_keeps_provider_completion_metadata(finish):
    from backend.llm.models import langchain_to_openai_response
    raw = NS(content="model output", id="trace-1",
             response_metadata={"finish_reason": finish, "model_name": "actual-provider-model"})
    converted = langchain_to_openai_response(raw)
    assert converted["choices"][0]["finish_reason"] == finish
    assert converted["model"] == "actual-provider-model"
    assert converted["id"] == "trace-1"


def test_preflight_distinguishes_physics_from_ai(monkeypatch, tmp_path):
    from backend.engineer_plus.preflight import runtime_preflight
    for env_name in ("CALCULIX_CMD", "GMSH_CMD", "FREECAD_CMD"):
        p = tmp_path / (env_name.lower() + ".exe")
        p.write_text("placeholder")
        monkeypatch.setenv(env_name, str(p))
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    result = runtime_preflight()
    assert result["ready_for_physics"] is True
    assert result["ready_for_ai_review"] is False
    assert result["ready_for_live"] is False
    assert result["executable_sources"] == {"calculix": "CALCULIX_CMD", "gmsh": "GMSH_CMD", "freecad": "FREECAD_CMD"}


def test_candidate_review_accept_is_structured_and_provenanced(monkeypatch):
    from backend.engineer_plus.llm_candidate_review import review_candidate
    client = Mock(api_key="test", model="review-model")
    client.chat.return_value = {"id": "candidate-review-1", "model": "review-model",
        "choices": [{"message": {"content": json.dumps({
            "recommendation": "accept", "confidence": 0.82,
            "strengths": ["门控通过"], "risks": ["需要疲劳复核"],
            "required_checks": ["复核极端载荷"], "rationale": "证据满足当前筛选条件。"}, ensure_ascii=False)},
            "finish_reason": "stop"}]}
    monkeypatch.setattr("backend.qwen_client.QwenClient", lambda: client)
    result = review_candidate(validation={"validation_id": "v1", "overall_score": 91,
        "ai_review_scores": {"strength": 90}, "metrics": {"stress": 1.3},
        "rule_results": [{"id": "strength", "measured": 1.3, "threshold": "<=1"}],
        "assumptions": ["proxy fatigue"], "surrogate_context": {"enabled": False}},
        gate={"ok": True}, artifact_path="candidate.json")
    assert result["status"] == "completed"
    assert result["source"] == "llm"
    assert result["review"]["recommendation"] == "accept"
    assert result["response_id"] == "candidate-review-1"
    assert len(result["prompt_sha256"]) == 64 and len(result["response_sha256"]) == 64
    assert result["evidence"]["metrics"] == {"stress": 1.3}
    assert result["evidence"]["rule_results"][0]["threshold"] == "<=1"
    assert result["evidence"]["assumptions"] == ["proxy fatigue"]
    assert result["response_text"]


def test_candidate_review_invalid_json_cannot_select(monkeypatch):
    from backend.engineer_plus.llm_candidate_review import review_candidate
    client = Mock(api_key="test", model="review-model")
    client.chat.return_value = {"choices": [{"message": {"content": "not-json"}}]}
    monkeypatch.setattr("backend.qwen_client.QwenClient", lambda: client)
    result = review_candidate(validation={"overall_score": 91}, gate={"ok": True}, artifact_path="x")
    assert result["status"] == "invalid_response"
    assert result["source"] == "none"
