"""Interactive clarification / post-lock edit for design checklist fields."""
from __future__ import annotations

import re
from typing import Any

from backend.design_requirements.config import load_defaults
from backend.design_requirements.models import DesignChecklist
from backend.design_requirements.rule_fallback import _extract_float

_SKIP_RE = re.compile(
    r"不知道|不清楚|暂未|待定|跳过|用默认|默认值|随你|你定|不详|无要求|不限",
    re.IGNORECASE,
)
_USE_ALL_DEFAULTS_RE = re.compile(
    r"^(全部|都|其余|其它|其他)?\s*(用|按)?\s*默认|直接默认|默认即可|都默认",
    re.IGNORECASE,
)

CLARIFICATION_SPECS: list[dict[str, Any]] = [
    {
        "field_id": "target_capacity_mw",
        "section": "project",
        "attr": ("project", "target_capacity_mw"),
        "question": "目标单机容量是多少 MW？",
        "unit": "MW",
        "patterns": [r"(\d+(?:\.\d+)?)\s*MW", r"(\d+(?:\.\d+)?)\s*兆瓦"],
    },
    {
        "field_id": "Hs_m",
        "section": "site",
        "attr": ("site", "Hs_m"),
        "question": "场址设计有效波高 Hs 是多少？",
        "unit": "m",
        "patterns": [r"Hs\s*[=≈]?\s*(\d+(?:\.\d+)?)", r"有效波高\s*(\d+(?:\.\d+)?)"],
    },
    {
        "field_id": "Tp_s",
        "section": "site",
        "attr": ("site", "Tp_s"),
        "question": "谱峰周期 Tp 是多少？",
        "unit": "s",
        "patterns": [r"Tp\s*[=≈]?\s*(\d+(?:\.\d+)?)", r"谱峰周期\s*(\d+(?:\.\d+)?)"],
    },
    {
        "field_id": "water_depth_m",
        "section": "site",
        "attr": ("site", "water_depth_m"),
        "question": "场址设计水深是多少？",
        "unit": "m",
        "patterns": [r"水深\s*[=≈]?\s*(\d+(?:\.\d+)?)", r"(\d+(?:\.\d+)?)\s*m\s*水深"],
    },
    {
        "field_id": "wind_ref_m_s",
        "section": "site",
        "attr": ("site", "wind_ref_m_s"),
        "question": "参考风速（轮毂高度）是多少？",
        "unit": "m/s",
        "patterns": [r"风速\s*[=≈]?\s*(\d+(?:\.\d+)?)", r"(\d+(?:\.\d+)?)\s*m\s*/\s*s"],
    },
    {
        "field_id": "steel_intensity_t_per_MW",
        "section": "performance",
        "attr": ("performance_targets", "steel_intensity_t_per_MW"),
        "question": "钢耗强度目标是多少 t/MW？",
        "unit": "t/MW",
        "patterns": [
            r"(\d+(?:\.\d+)?)\s*t\s*/\s*MW",
            r"钢耗[^\d]*(\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)\s*t/MW",
        ],
    },
    {
        "field_id": "unit_cost_cny_per_MW",
        "section": "performance",
        "attr": ("performance_targets", "unit_cost_cny_per_MW"),
        "question": "单位造价目标是多少（万元/MW）？",
        "unit": "万元/MW",
        "patterns": [r"造价[^\d]*(\d+(?:\.\d+)?)", r"(\d+(?:\.\d+)?)\s*万\s*/?\s*MW"],
    },
    {
        "field_id": "pitch_limit_deg",
        "section": "performance",
        "attr": ("performance_targets", "pitch_limit_deg"),
        "question": "静倾角限值是多少度？",
        "unit": "°",
        "patterns": [r"静倾[^\d]*(\d+(?:\.\d+)?)", r"(\d+(?:\.\d+)?)\s*度"],
    },
    {
        "field_id": "fatigue_design_life_years",
        "section": "performance",
        "attr": ("performance_targets", "fatigue_design_life_years"),
        "question": "疲劳设计寿命是多少年？",
        "unit": "年",
        "patterns": [r"疲劳[^\d]*(\d+(?:\.\d+)?)\s*年", r"设计寿命[^\d]*(\d+(?:\.\d+)?)"],
    },
]


def _default_for_field(field_id: str) -> Any:
    d = load_defaults()
    mapping = {
        "target_capacity_mw": (d.get("project") or {}).get("target_capacity_mw", 20.0),
        "Hs_m": (d.get("site") or {}).get("Hs_m"),
        "Tp_s": (d.get("site") or {}).get("Tp_s"),
        "water_depth_m": (d.get("site") or {}).get("water_depth_m"),
        "wind_ref_m_s": (d.get("site") or {}).get("wind_ref_m_s"),
        "steel_intensity_t_per_MW": (d.get("performance_targets") or {}).get("steel_intensity_t_per_MW", 300.0),
        "unit_cost_cny_per_MW": (d.get("performance_targets") or {}).get("unit_cost_cny_per_MW"),
        "pitch_limit_deg": (d.get("performance_targets") or {}).get("pitch_limit_deg", 5.0),
        "fatigue_design_life_years": (d.get("performance_targets") or {}).get("fatigue_design_life_years", 25.0),
    }
    return mapping.get(field_id)


def audit_fields_from_text(text: str) -> dict[str, bool]:
    t = (text or "").strip()
    out: dict[str, bool] = {}
    for spec in CLARIFICATION_SPECS:
        val = _extract_float(list(spec["patterns"]), t)
        out[spec["field_id"]] = val is not None
    return out


def build_pending_clarifications(text: str, checklist: DesignChecklist) -> list[dict[str, Any]]:
    """Fields not mentioned in source text — ask user before locking defaults."""
    parsed = audit_fields_from_text(text)
    already = set(checklist.clarified_field_ids or [])
    pending: list[dict[str, Any]] = []
    for spec in CLARIFICATION_SPECS:
        fid = spec["field_id"]
        if parsed.get(fid) or fid in already:
            continue
        default = _default_for_field(fid)
        if default is None:
            continue
        unit = spec.get("unit") or ""
        pending.append(
            {
                "field_id": fid,
                "question": spec["question"],
                "default_value": default,
                "default_display": f"{default} {unit}".strip(),
                "section": spec.get("section", ""),
            }
        )
    return pending


def _set_checklist_field(cl: DesignChecklist, field_id: str, value: float) -> DesignChecklist:
    d = cl.model_dump()
    for spec in CLARIFICATION_SPECS:
        if spec["field_id"] != field_id:
            continue
        sec, key = spec["attr"]
        section = dict(d.get(sec) or {})
        section[key] = value
        d[sec] = section
        break
    return DesignChecklist.model_validate(d)


def _get_checklist_field(cl: DesignChecklist, field_id: str) -> Any:
    d = cl.model_dump()
    for spec in CLARIFICATION_SPECS:
        if spec["field_id"] != field_id:
            continue
        sec, key = spec["attr"]
        return (d.get(sec) or {}).get(key)
    return None


def extract_field_updates(reply: str) -> dict[str, float]:
    """Parse explicit numeric field updates from user text (any of the known fields)."""
    text = (reply or "").strip()
    out: dict[str, float] = {}
    if not text:
        return out
    for spec in CLARIFICATION_SPECS:
        val = _extract_float(list(spec["patterns"]), text)
        if val is not None:
            out[spec["field_id"]] = float(val)
    return out


def apply_clarification_reply(
    checklist: DesignChecklist,
    reply: str,
    *,
    pending_field_ids: list[str] | None = None,
    mode: str = "clarify",
) -> tuple[DesignChecklist, list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Merge user clarification or post-lock edit.

    ``mode``:
    - ``clarify``: fill pending fields (numeric / 用默认); also apply any explicit
      numeric updates found in the reply (including already-set fields).
    - ``edit``: only apply explicit numeric updates; never auto-fill defaults for
      unspecified pending fields.

    Returns: (checklist, assumptions, remaining_pending, updated_field_records)
    """
    text = (reply or "").strip()
    mode_norm = str(mode or "clarify").strip().lower()
    if mode_norm not in ("clarify", "edit"):
        mode_norm = "clarify"

    pending_ids = list(pending_field_ids or [])
    if mode_norm == "clarify" and not pending_ids:
        pending_ids = [p["field_id"] for p in build_pending_clarifications(checklist.meta.source_text, checklist)]

    assumptions: list[str] = list(checklist.assumptions or [])
    clarified = set(checklist.clarified_field_ids or [])
    use_all_defaults = bool(_USE_ALL_DEFAULTS_RE.search(text)) and mode_norm == "clarify"
    cl = checklist
    updated_records: list[dict[str, Any]] = []

    # 1) Explicit numeric updates from the whole reply (allows changing locked values)
    explicit = extract_field_updates(text)
    for fid, val in explicit.items():
        spec = next((s for s in CLARIFICATION_SPECS if s["field_id"] == fid), None)
        if not spec:
            continue
        prev = _get_checklist_field(cl, fid)
        cl = _set_checklist_field(cl, fid, float(val))
        clarified.add(fid)
        unit = spec.get("unit") or ""
        updated_records.append(
            {
                "field_id": fid,
                "value": float(val),
                "previous": prev,
                "unit": unit,
                "source": "explicit",
            }
        )
        if mode_norm == "edit" and prev is not None and float(prev) != float(val):
            assumptions.append(f"用户修订：{spec['question'].rstrip('？')} → {val} {unit}".strip())

    # 2) Clarify mode: fill remaining pending with defaults / skip phrasing
    if mode_norm == "clarify":
        for fid in pending_ids:
            if fid in explicit:
                continue
            spec = next((s for s in CLARIFICATION_SPECS if s["field_id"] == fid), None)
            if not spec:
                continue
            unit = spec.get("unit") or ""
            if use_all_defaults or _SKIP_RE.search(text):
                default = _default_for_field(fid)
                if default is not None:
                    cl = _set_checklist_field(cl, fid, float(default))
                    assumptions.append(
                        f"{spec['question'].rstrip('？')} 未提供，采用默认 {default} {unit}".strip()
                    )
                    clarified.add(fid)
                    updated_records.append(
                        {
                            "field_id": fid,
                            "value": float(default),
                            "previous": None,
                            "unit": unit,
                            "source": "default",
                        }
                    )

    cl = cl.model_copy(
        update={
            "assumptions": assumptions,
            "gaps": [],
            "clarified_field_ids": sorted(clarified),
        }
    )
    remaining = build_pending_clarifications(cl.meta.source_text, cl)
    return cl, assumptions, remaining, updated_records


def clarification_complete(pending: list[dict[str, Any]]) -> bool:
    return len(pending) == 0


def checklist_context_block(checklist: DesignChecklist | None) -> str:
    """Compact Chinese summary for assistant system prompt / tool replies."""
    if checklist is None:
        return ""
    proj = checklist.project
    site = checklist.site
    perf = checklist.performance_targets
    struct = checklist.structural_assumptions
    cid = checklist.meta.checklist_id or ""
    pending = build_pending_clarifications(checklist.meta.source_text, checklist)
    lines = [
        "【当前设计清单·会话上下文】",
        f"checklist_id={cid}",
        f"容量={proj.target_capacity_mw} MW · 型式={proj.platform_type or '—'}",
        f"场址={site.location_name or '—'} · Hs={site.Hs_m} m · Tp={site.Tp_s} s · 水深={site.water_depth_m} m · 风速={site.wind_ref_m_s} m/s",
        f"钢耗目标={perf.steel_intensity_t_per_MW} t/MW · 静倾≤{perf.pitch_limit_deg}° · 疲劳寿命={perf.fatigue_design_life_years} 年",
        f"吃水假设={struct.draft_m} m · 壁厚={struct.wall_thickness_m} m",
    ]
    if pending:
        qs = "；".join(p["question"] for p in pending[:6])
        lines.append(f"待确认参数（{len(pending)}）：{qs}")
        lines.append("用户答复后系统会写回清单；你可提醒用户用「钢耗改为 280」等方式继续修改。")
    else:
        lines.append(
            "清单已可带入任务。用户可用自然语言修改参数（如「水深改成 55 m」「钢耗 280 t/MW」），"
            "前端/工具会调用 clarify?mode=edit 写回同一 checklist_id。"
        )
    return "\n".join(lines)
