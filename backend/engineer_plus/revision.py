"""Model-proposed revisions constrained by adapter-owned geometry contracts.

Bounds are design-search limits, not a claim of physical feasibility. Every
accepted patch must pass the builder, solver and independent reviewer again.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from typing import Any, Protocol
from pathlib import Path

from .engine import DesignCandidate, DesignRequest


class RevisionPolicy(Protocol):
    def context(self, original: DesignRequest, current: DesignRequest,
                *, candidate: DesignCandidate | None = None) -> dict[str, Any]: ...
    def apply(self, original: DesignRequest, current: DesignRequest,
              patch: dict[str, Any], *, candidate: DesignCandidate | None = None) -> DesignRequest: ...


def prism_spec(request: DesignRequest) -> dict[str, Any]:
    from backend.tools.prism_design_domain import parse_prism_design_brief
    spec = parse_prism_design_brief(str(request.requirements.get("brief") or "prism")).to_dict()
    override = request.requirements.get("prism_spec", {})
    if not isinstance(override, dict) or set(override) - set(spec):
        raise ValueError("unknown prism specification fields")
    spec.update(override)
    for key, value in spec.items():
        if key.endswith("_mm") or key in {"force_n", "mass_goal_ratio"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"prism specification requires positive finite {key}")
            spec[key] = float(value)
    if spec["mesh_min_mm"] > spec["mesh_max_mm"] or spec["mass_goal_ratio"] >= 1:
        raise ValueError("invalid mesh limits or mass ratio")
    if spec["corner_r_mm"] >= spec["side_mm"] / 2:
        raise ValueError("corner cut-outs overlap")
    if spec["load_diameter_mm"] / 2 >= spec["side_mm"] * math.sqrt(3) / 6:
        raise ValueError("load ring does not fit inside the prism")
    if spec["ring_wall_mm"] >= spec["load_diameter_mm"] / 2:
        raise ValueError("ring wall must be smaller than its outer radius")
    return spec


class PrismRevisionPolicy:
    fields = ("side_mm", "height_above_mm", "height_below_mm", "corner_r_mm")

    def context(self, original: DesignRequest, current: DesignRequest,
                *, candidate: DesignCandidate | None = None) -> dict[str, Any]:
        baseline, active = prism_spec(original), prism_spec(current)
        declared = original.requirements.get("design_variable_bounds")
        # Physical dimensions are fixed by default. Reusable adapter callers
        # must explicitly authorize every free variable; the production prism
        # service currently locks all geometry per the author's instruction.
        bounds = declared if declared is not None else {}
        if not isinstance(bounds, dict) or set(bounds) - set(self.fields):
            raise ValueError("only declared prism geometry variables can change")
        for key, limits in bounds.items():
            if not isinstance(limits, (list, tuple)) or len(limits) != 2:
                raise ValueError("each design variable needs lower and upper bounds")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in limits):
                raise ValueError("design variable bounds must be finite numbers")
            if not 0 < limits[0] <= baseline[key] <= limits[1]:
                raise ValueError("bounds must contain the original positive geometry")
        context = {"current_spec": active, "original_spec": baseline,
                "allowed_patch": {"prism_spec": deepcopy(bounds)},
                "units": "mm", "bounds_source": "explicit_contract" if declared is not None else "geometry_locked",
                "immutable": "all other requirements, loads, materials, mesh, supports, targets and acceptance gates"}
        if not bounds and candidate is not None and candidate.topology.get("source_run"):
            if active != baseline:
                raise ValueError("fixed-domain continuation may not change the prism specification")
            from .topology_checkpoint import inspect_checkpoint
            checkpoint = inspect_checkpoint(
                source_run=Path(candidate.topology["source_run"]),
                target_input=Path(candidate.domain["artifact_path"]),
                workspace_root=Path(original.requirements["workspace_root"]),
                state1=Path(candidate.topology["source_state1_path"]),
            )
            if candidate.domain.get("input_sha256") != checkpoint["input_sha256"]:
                raise ValueError("design-domain input changed after its recorded execution")
            recorded = candidate.topology.get("topology_provenance_data") or {}
            if recorded.get("source_state1_sha256") != checkpoint["source_state1_sha256"]:
                raise ValueError("topology checkpoint changed after its recorded review")
            token = {key: checkpoint[key] for key in (
                "source_run", "source_state1_path", "source_state1_sha256", "input_sha256", "state_partition_sha256")}
            budget = original.requirements.get("topology_iteration_budget", "auto")
            if budget != "auto" and (type(budget) is not int or not 1 <= budget <= 1000):
                raise ValueError("invalid topology iteration budget")
            token["iteration_budget"] = budget
            context.update(
                current_spec={"prism_spec": active, "previous_state_partition":
                              (current.requirements.get("_topology_continuation") or {}).get("state_partition_sha256")},
                allowed_patch={"topology_continuation": ["continue"]},
                checkpoint={**{k: checkpoint[k] for k in ("nodes", "configured_elements", "retained_elements", "protected_elements")},
                            "mass_goal_ratio": checkpoint["config"]["mass_goal_ratio"],
                            "source_iteration_limit": checkpoint["config"].get("iterations_limit", "auto"),
                            "completion_is_not_convergence": True},
                continuation_token=token,
                action_description="Continue element-state optimization on the identical full-precision mesh; preserve dimensions, loads, materials and target. Sensitivity history is reset; this is a warm start, not exact optimizer replay.",
            )
        return context

    def apply(self, original: DesignRequest, current: DesignRequest,
              patch: dict[str, Any], *, candidate: DesignCandidate | None = None) -> DesignRequest:
        if patch == {"topology_continuation": "continue"}:
            context = self.context(original, current, candidate=candidate)
            token = context.get("continuation_token")
            if token is None or candidate is None:
                raise ValueError("no validated fixed-domain checkpoint is available")
            previous = current.requirements.get("_topology_continuation") or {}
            if previous.get("state_partition_sha256") == token["state_partition_sha256"]:
                raise ValueError("topology did not change since the previous continuation")
            return replace(current, requirements={**deepcopy(current.requirements),
                                                  "_topology_continuation": token,
                                                  "_fixed_domain": deepcopy(candidate.domain)})
        if not isinstance(patch, dict) or set(patch) != {"prism_spec"}:
            raise ValueError("revision must contain only prism_spec")
        context = self.context(original, current)
        values = patch["prism_spec"]
        bounds = context["allowed_patch"]["prism_spec"]
        if not isinstance(values, dict) or not values or set(values) - set(bounds):
            raise ValueError("revision contains no allowed geometry change")
        spec = context["current_spec"]
        for key, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("revision values must be finite numbers")
            if not bounds[key][0] <= value <= bounds[key][1]:
                raise ValueError("revision exceeds original design bounds")
        if all(math.isclose(spec[key], value, rel_tol=1e-9) for key, value in values.items()):
            raise ValueError("revision does not change geometry")
        updated = replace(current, requirements={**deepcopy(current.requirements),
                                                "prism_spec": {**spec, **values}})
        prism_spec(updated)
        return updated


def propose_revision(*, candidate: DesignCandidate, context: dict[str, Any]) -> dict[str, Any]:
    """One real model call; no template patch or score-based canned retry."""
    evidence = {"candidate_id": candidate.candidate_id, "gate": candidate.gate,
                "candidate_review": candidate.review.get("candidate_review"),
                "design_contract": context}
    messages = [
        {"role": "system", "content": (
            "你是工程修订规划器。依据计算证据和独立审阅意见，在允许动作中选择可复算的下一步。"
            "只能修改 design_contract.allowed_patch 内变量且遵守上下界；不得修改载荷、材料、门槛、分数或验证结果。"
            "这些边界只是搜索范围，不保证可行。证据含代理估计时须说明不确定性。"
            "修改效果只能作为定性假设；不得编造历史敏感性实验、改进百分比、预测分数或误差区间。"
            "若当前变量不能解决问题，返回 action=stop，不要盲目重试。只返回 JSON。")},
        {"role": "user", "content": json.dumps({"schema": {
            "action": "revise|stop", "patch": "Use only design_contract.allowed_patch. For fixed-domain continuation: {topology_continuation: continue}. For an explicitly allowed geometry change: {prism_spec: {allowed_variable: number}}. For stop: exactly {}.",
            "rationale": "why this change addresses the recorded evidence; or why stop",
        }, "evidence": evidence}, ensure_ascii=False)},
    ]
    result: dict[str, Any] = {
        "status": "unavailable", "source": "none", "evidence": evidence,
        "rationale_role": "unverified_model_hypothesis",
        "prompt_sha256": hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    }
    try:
        from backend.qwen_client import QwenClient
        client = QwenClient()
        result["model"] = getattr(client, "model", None)
        if not getattr(client, "api_key", None):
            result["reason"] = "no_api_key"
            return result
        response = client.chat(messages, temperature=0.1)
        choice = response["choices"][0]
        content = choice["message"]["content"]
        result.update(response_id=response.get("id"), returned_model=response.get("model"),
                      finish_reason=choice.get("finish_reason"), response_text=content,
                      response_sha256=hashlib.sha256(content.encode()).hexdigest())
        if choice.get("finish_reason") != "stop":
            raise ValueError("incomplete model response")
        parsed = json.loads(content)
        if not isinstance(parsed, dict) or set(parsed) != {"action", "patch", "rationale"}:
            raise ValueError("invalid revision schema")
        if parsed["action"] not in {"revise", "stop"} or not isinstance(parsed["patch"], dict):
            raise ValueError("invalid revision action")
        if not isinstance(parsed["rationale"], str) or not parsed["rationale"].strip():
            raise ValueError("revision requires an evidence-based rationale")
        if parsed["action"] == "stop" and parsed["patch"]:
            raise ValueError("stop must not contain a patch")
        result.update(status="completed", source="llm", proposal=parsed,
                      response_id=response.get("id"), returned_model=response.get("model"),
                      response_sha256=hashlib.sha256(content.encode()).hexdigest())
    except Exception as exc:
        result.update(status="invalid_response", reason=type(exc).__name__)
    return result
