"""Independent advisory review of an already-computed candidate."""
from __future__ import annotations
import hashlib
import json
from typing import Any

def review_candidate(*, validation: dict[str, Any], gate: dict[str, Any], artifact_path: str) -> dict[str, Any]:
    payload = {"overall_score": validation.get("overall_score"),
               "ai_review_scores": validation.get("ai_review_scores") or {},
               "metrics": validation.get("metrics") or {},
               "rule_results": validation.get("rule_results") or [],
               "assumptions": validation.get("assumptions") or [],
               "surrogate_context": validation.get("surrogate_context") or {},
               "regulatory_review_scores": validation.get("regulatory_review_scores") or {},
               "gate_ok": bool(gate.get("ok")), "gate_reason": gate.get("reason"),
               "artifact_path": str(artifact_path), "validation_id": validation.get("validation_id")}
    schema = {"recommendation": "accept|revise|reject", "confidence": "0..1",
              "strengths": ["string"], "risks": ["string"],
              "required_checks": ["string"], "rationale": "string"}
    messages = [{"role": "system", "content": "你是工程候选方案审阅助手。只依据给定计算证据；不得修改分数、宣称认证通过或补造未提供计算。只输出 JSON。"},
                {"role": "user", "content": "按以下 schema 审阅候选方案：\nSCHEMA=" + json.dumps(schema, ensure_ascii=False) + "\nEVIDENCE=" + json.dumps(payload, ensure_ascii=False)}]
    result = {"status": "unavailable", "source": "none", "evidence": payload,
              "prompt_sha256": hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
    try:
        from backend.qwen_client import QwenClient
        client = QwenClient()
    except Exception:
        result["reason"] = "client_initialization_failed"; return result
    result["model"] = getattr(client, "model", None)
    if not getattr(client, "api_key", None):
        result["reason"] = "no_api_key"; return result
    try:
        response = client.chat(messages, temperature=0.1)
        content = response["choices"][0]["message"]["content"]
        result.update(response_id=response.get("id"), returned_model=response.get("model"),
                      finish_reason=response["choices"][0].get("finish_reason"), response_text=content,
                      response_sha256=hashlib.sha256(content.encode()).hexdigest())
        if response["choices"][0].get("finish_reason") != "stop":
            raise ValueError("incomplete model response")
        parsed = json.loads(content)
        if parsed.get("recommendation") not in {"accept", "revise", "reject"}:
            raise ValueError("invalid recommendation")
        confidence = float(parsed.get("confidence"))
        if not 0 <= confidence <= 1:
            raise ValueError("invalid confidence")
        for key in ("strengths", "risks", "required_checks"):
            if not isinstance(parsed.get(key), list) or not all(isinstance(x, str) for x in parsed[key]):
                raise ValueError(f"invalid {key}")
        if not isinstance(parsed.get("rationale"), str) or not parsed["rationale"].strip():
            raise ValueError("invalid rationale")
        result.update(status="completed", source="llm", response_id=response.get("id"),
                      returned_model=response.get("model"), review=parsed,
                      response_sha256=hashlib.sha256(content.encode()).hexdigest())
    except Exception as exc:
        result.update(status="invalid_response", reason=type(exc).__name__)
    return result
