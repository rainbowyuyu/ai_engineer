"""Structured output chains for BESO params, Phase I checklist, validation rationale."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.llm.concurrency import with_llm_slot
from backend.llm.models import get_chat_model

logger = logging.getLogger(__name__)


class BesoParamsSchema(BaseModel):
    reasoning_summary: str = Field(description="一句话中文总结参数抽取逻辑")
    inp_path: str | None = Field(default=None, description="INP 绝对路径；未换文件时为 null")
    mass_goal_ratio: float = Field(default=0.25, ge=0.01, le=1.0)
    filter_radius: float = Field(default=2.0, gt=0)
    optimization_base: str = Field(default="failure_index")
    save_every: int = Field(default=1, ge=1)


class PhaseIChecklistPartial(BaseModel):
    reasoning_summary: str = ""
    project: dict[str, Any] | None = None
    site: dict[str, Any] | None = None
    regulatory: dict[str, Any] | None = None
    performance_targets: dict[str, Any] | None = None
    structural_assumptions: dict[str, Any] | None = None
    job_descriptor: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class RuleRationaleSchema(BaseModel):
    rationale_zh: str = Field(description="2-4 句中文工程说明与改进建议")


class Oc4LoadsNlSchema(BaseModel):
    reply: str = Field(description="中文简要说明")
    load_case: dict[str, Any] = Field(default_factory=dict)


class PrimaryInpChoiceSchema(BaseModel):
    primary_inp: str | None = Field(default=None, description="候选 INP 文件名或 null")
    reason: str = Field(default="", description="一句话理由")


class Oc4TopicChatSchema(BaseModel):
    reply: str = ""
    suggested_build: dict[str, Any] | None = None
    suggested_loads: dict[str, Any] | None = None
    suggested_mesh: dict[str, Any] | None = None
    suggested_export: dict[str, Any] | None = None


def invoke_beso_params_structured(
    *,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.2,
) -> BesoParamsSchema | None:
    try:
        llm = get_chat_model(temperature=temperature).with_structured_output(BesoParamsSchema)
        return llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
    except Exception as e:
        logger.info("structured beso params failed: %s", e)
        return None


def invoke_phase_i_partial_structured(
    *,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.15,
) -> PhaseIChecklistPartial | None:
    try:
        llm = get_chat_model(temperature=temperature).with_structured_output(PhaseIChecklistPartial)
        return llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
    except Exception as e:
        logger.info("structured phase I parse failed: %s", e)
        return None


def invoke_oc4_loads_structured(
    *,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.15,
) -> Oc4LoadsNlSchema | None:
    try:
        llm = get_chat_model(temperature=temperature).with_structured_output(Oc4LoadsNlSchema)
        return llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
    except Exception as e:
        logger.info("structured oc4 loads failed: %s", e)
        return None


def invoke_primary_inp_structured(
    *,
    system_prompt: str,
    user_content: str,
) -> PrimaryInpChoiceSchema | None:
    try:
        llm = get_chat_model(temperature=0.0).with_structured_output(PrimaryInpChoiceSchema)
        return llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
    except Exception as e:
        logger.info("structured primary inp failed: %s", e)
        return None


def invoke_oc4_topic_chat_structured(
    *,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.2,
) -> Oc4TopicChatSchema | None:
    try:
        llm = get_chat_model(temperature=temperature).with_structured_output(Oc4TopicChatSchema)
        return llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
    except Exception as e:
        logger.info("structured oc4 topic chat failed: %s", e)
        return None


async def _rationale_one(rule_id: str, prompt: str) -> tuple[str, str]:
    async def _call() -> str:
        llm = get_chat_model(temperature=0.3).with_structured_output(RuleRationaleSchema)

        async def _invoke():
            return await llm.ainvoke(
                [
                    {"role": "system", "content": "你是 DNV/IEC 海上风电规范助手，输出简洁中文。"},
                    {"role": "user", "content": prompt},
                ]
            )

        result = await with_llm_slot(_invoke)
        if isinstance(result, RuleRationaleSchema):
            return result.rationale_zh.strip()
        return str(result)

    try:
        text = await _call()
        return rule_id, text
    except Exception as e:
        logger.info("parallel rationale %s failed: %s", rule_id, e)
        return rule_id, ""


async def generate_rationales_parallel_async(prompts: dict[str, str]) -> dict[str, str]:
    if not prompts:
        return {}
    tasks = [_rationale_one(rid, p) for rid, p in prompts.items()]
    pairs = await asyncio.gather(*tasks)
    return {rid: txt for rid, txt in pairs if txt}


def generate_rationales_parallel(prompts: dict[str, str]) -> dict[str, str]:
    """Sync wrapper for parallel LLM rationale generation."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(generate_rationales_parallel_async(prompts))
    # Called from sync context inside running loop — run in new thread
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, generate_rationales_parallel_async(prompts)).result()


__all__ = [
    "BesoParamsSchema",
    "PhaseIChecklistPartial",
    "RuleRationaleSchema",
    "Oc4LoadsNlSchema",
    "PrimaryInpChoiceSchema",
    "Oc4TopicChatSchema",
    "invoke_beso_params_structured",
    "invoke_phase_i_partial_structured",
    "invoke_oc4_loads_structured",
    "invoke_primary_inp_structured",
    "invoke_oc4_topic_chat_structured",
    "generate_rationales_parallel",
    "generate_rationales_parallel_async",
]
