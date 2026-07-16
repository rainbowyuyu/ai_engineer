"""Natural language → structured design checklist."""
from __future__ import annotations

import json
import uuid
from typing import Any

from backend.design_requirements.config import clause_summaries_for_prompt, load_defaults
from backend.design_requirements.json_utils import parse_json_object
from backend.design_requirements.markdown import checklist_to_markdown
from backend.design_requirements.models import DesignChecklist
from backend.design_requirements.rule_fallback import merge_partial_dict, parse_rule_fallback
from backend.oc4_methodology_chen2026 import LLM_CONTEXT_BLOCK_ZH
from backend.qwen_client import QwenClient

SYSTEM_PROMPT = """你是「AI Engineer」Phase I 设计需求形式化模块。
将业主自然语言需求转为**一个** JSON 对象（不要 Markdown 围栏，不要其它文字）。

JSON 顶层键（可省略未提及字段，未提及的由系统填默认）：
- reasoning_summary: string 中文一句话
- project: { title, owner_intent_zh, target_capacity_mw, platform_type }
- site: { location_name, water_depth_m, Hs_m, Tp_s, wind_ref_m_s, sea_state_envelope: { reference, labels, zwind_envelope_check } }
- regulatory: { certification_path, standards, clause_ids, reviewer_threshold: { S_min, subscore_min } }
- performance_targets: { steel_intensity_t_per_MW, unit_cost_cny_per_MW, pitch_limit_deg, fatigue_design_life_years }
- structural_assumptions: { draft_m, wall_thickness_m, scale_factor }
- job_descriptor: { phase:"I", theta: { beso:{mass_goal_ratio,filter_radius,optimization_base,save_every}, oc4_loads:{band_scale,z_fix_band,cload_mag}, sizing:{optimizer} }, retry_policy:{max_retries,on_mesh_fail,on_solver_fail} }
- assumptions: string[] 未从用户文本得到而采用默认的说明
- gaps: string[] 模糊或冲突项

约定：
- 20 MW 漂浮式半潜为默认语境；钢耗目标常引用 300 t/MW；认证路径 CCS AIP。
- 海况可引用阳江三山 III H1–H6 包络；极限工况用于 Zwind 校验。
- clause_ids 从下列条款索引中选择相关 id（可多个）。

条款索引摘要：
{clause_summaries}

{methodology_block}
"""


def parse_design_checklist(
    text: str,
    *,
    qwen: QwenClient | None = None,
    checklist_id: str | None = None,
) -> DesignChecklist:
    t = (text or "").strip()
    if not t:
        raise ValueError("设计需求文本为空")

    cid = checklist_id or uuid.uuid4().hex
    base = parse_rule_fallback(t, checklist_id=cid)

    qwen = qwen or QwenClient()
    if not qwen.api_key:
        return base

    system = (
        SYSTEM_PROMPT.replace("{clause_summaries}", clause_summaries_for_prompt()).replace(
            "{methodology_block}", LLM_CONTEXT_BLOCK_ZH
        )
    )
    defaults_hint = json.dumps(load_defaults(), ensure_ascii=False)[:4000]
    user = f"系统默认（未提及字段可沿用）:\n{defaults_hint}\n\n用户设计需求:\n{t}"

    try:
        resp = qwen.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.15,
        )
        content = resp["choices"][0]["message"]["content"]
        partial = parse_json_object(content) or {}
        merged = merge_partial_dict(base, partial)
        merged.meta.parser = "qwen"
        rs = partial.get("reasoning_summary") or merged.meta.reasoning_summary
        merged.meta = merged.meta.model_copy(
            update={
                "reasoning_summary": str(rs) if rs else merged.meta.reasoning_summary,
                "checklist_id": cid,
                "source_text": t,
                "parser": "qwen",
            }
        )
        if not merged.regulatory.clause_ids:
            from backend.design_requirements.rule_fallback import match_clause_ids

            merged.regulatory.clause_ids = match_clause_ids(t)
        return merged
    except Exception:
        base.meta.reasoning_summary = "Qwen 解析失败，已回退规则模式"
        return base


def parse_and_render(text: str, **kwargs: Any) -> tuple[DesignChecklist, str]:
    cl = parse_design_checklist(text, **kwargs)
    return cl, checklist_to_markdown(cl)
