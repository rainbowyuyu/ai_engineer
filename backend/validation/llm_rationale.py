"""Optional LLM rationale for failed/warn rules (does not affect scoring)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from backend.validation.rules_engine import RuleResult
from backend.validation.scorer import ValidationScore

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUSE_INDEX = _REPO_ROOT / "rules" / "dnv_clause_index.yaml"


def _clause_text(clause_ref: str | None) -> str:
    if not clause_ref or not CLAUSE_INDEX.is_file():
        return ""
    raw = yaml.safe_load(CLAUSE_INDEX.read_text(encoding="utf-8"))
    for c in raw.get("clauses") or []:
        if c.get("id") == clause_ref:
            parts = [c.get("summary_zh") or "", c.get("excerpt") or ""]
            return "\n".join(p for p in parts if p).strip()
    return ""


def generate_rationales(
    score: ValidationScore,
    *,
    use_llm: bool = True,
) -> dict[str, str]:
    if not use_llm:
        return {}
    try:
        from backend.qwen_client import QwenClient
    except ImportError:
        return {}

    qwen = QwenClient()
    if not qwen.api_key:
        return _fallback_rationales(score)

    out: dict[str, str] = {}
    for r in score.rule_results:
        if r.status not in ("fail", "warn"):
            continue
        clause = _clause_text(r.clause_ref)
        prompt = (
            f"你是海上风电漂浮式基础验船师助手。规则「{r.description_zh}」状态为 {r.status}。\n"
            f"实测: {r.measured}\n阈值: {r.threshold}\n来源: {r.source}\n"
            f"相关条款:\n{clause or '（无摘录）'}\n\n"
            "请用 2–4 句中文说明：为何出现 warn/fail、工程改进建议；不要改变数值结论。"
        )
        try:
            resp = qwen.chat(
                [
                    {"role": "system", "content": "你是 DNV/IEC 海上风电规范助手，输出简洁中文。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            text = resp["choices"][0]["message"]["content"].strip()
            out[r.id] = text
        except Exception as e:
            logger.info("llm rationale for %s failed: %s", r.id, e)
            out[r.id] = _fallback_line(r)
    return out


def _fallback_line(r: RuleResult) -> str:
    measured = f"{r.measured:.3f}" if r.measured is not None else "缺失"
    return f"实测 {measured} 未满足 {r.threshold}（{r.source}）。建议复核几何参数或对照 DNV 条款原文。"


def _fallback_rationales(score: ValidationScore) -> dict[str, str]:
    return {r.id: _fallback_line(r) for r in score.rule_results if r.status in ("fail", "warn")}
