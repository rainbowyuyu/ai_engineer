"""Render design checklist as Markdown report section."""
from __future__ import annotations

from backend.design_requirements.models import DesignChecklist


def checklist_to_markdown(cl: DesignChecklist) -> str:
    lines = [
        "# 设计清单（Phase I）",
        "",
        f"**清单 ID**：`{cl.meta.checklist_id}`  ",
        f"**解析方式**：{cl.meta.parser}  ",
        f"**生成时间**：{cl.meta.created_at}",
        "",
        "## 1 项目概况",
        "",
        f"- **项目名称**：{cl.project.title}",
        f"- **业主意图**：{cl.project.owner_intent_zh}",
        f"- **目标容量**：{cl.project.target_capacity_mw} MW",
        f"- **平台型式**：{cl.project.platform_type}",
        "",
        "## 2 场址与环境",
        "",
        f"- **场址**：{cl.site.location_name or '—'}",
        f"- **水深**：{cl.site.water_depth_m if cl.site.water_depth_m is not None else '—'} m",
        f"- **有效波高 Hs**：{cl.site.Hs_m if cl.site.Hs_m is not None else '—'} m",
        f"- **谱峰周期 Tp**：{cl.site.Tp_s if cl.site.Tp_s is not None else '—'} s",
        f"- **参考风速**：{cl.site.wind_ref_m_s if cl.site.wind_ref_m_s is not None else '—'} m/s",
        f"- **海况包络**：{cl.site.sea_state_envelope.reference or '—'}",
        f"- **Zwind 包络校验**：{'是' if cl.site.sea_state_envelope.zwind_envelope_check else '否'}",
        "",
        "## 3 规范与认证",
        "",
        f"- **认证路径**：{cl.regulatory.certification_path}",
        f"- **适用规范**：{', '.join(cl.regulatory.standards) or '—'}",
        f"- **关联条款 ID**：{', '.join(cl.regulatory.clause_ids) or '—'}",
        f"- **内审终止阈值**：S ≥ {cl.regulatory.reviewer_threshold.S_min}，子分 ≥ {cl.regulatory.reviewer_threshold.subscore_min}",
        "",
        "## 4 性能目标",
        "",
        f"- **钢耗强度目标**：{cl.performance_targets.steel_intensity_t_per_MW} t/MW",
        f"- **单位造价参考**：{cl.performance_targets.unit_cost_cny_per_MW or '—'} 万元/MW",
        f"- **静倾限值**：{cl.performance_targets.pitch_limit_deg}°",
        f"- **疲劳设计寿命**：{cl.performance_targets.fatigue_design_life_years} 年",
        f"- **1P 避让频带**：{cl.performance_targets.excitation_bands_hz.one_p.hz_min}–{cl.performance_targets.excitation_bands_hz.one_p.hz_max} Hz",
        f"- **3P 避让频带**：{cl.performance_targets.excitation_bands_hz.three_p.hz_min}–{cl.performance_targets.excitation_bands_hz.three_p.hz_max} Hz",
        "",
        "## 5 结构假设",
        "",
        f"- **吃水**：{cl.structural_assumptions.draft_m} m",
        f"- **壁厚**：{cl.structural_assumptions.wall_thickness_m} m",
        f"- **水平缩放因子**：{cl.structural_assumptions.scale_factor}",
        "",
        "## 6 任务参数（job descriptor J）",
        "",
        f"- **相位**：{cl.job_descriptor.phase}",
        f"- **BESO**：mass_goal_ratio={cl.job_descriptor.theta.beso.mass_goal_ratio}, "
        f"filter_radius={cl.job_descriptor.theta.beso.filter_radius} mm, "
        f"optimization_base={cl.job_descriptor.theta.beso.optimization_base}, save_every={cl.job_descriptor.theta.beso.save_every}",
        f"- **OC4 载荷默认**：band_scale={cl.job_descriptor.theta.oc4_loads.band_scale}, "
        f"z_fix_band={cl.job_descriptor.theta.oc4_loads.z_fix_band}, cload_mag={cl.job_descriptor.theta.oc4_loads.cload_mag}",
        f"- **尺寸优化器**：{cl.job_descriptor.theta.sizing.optimizer}",
        f"- **重试策略**：max_retries={cl.job_descriptor.retry_policy.max_retries}, "
        f"mesh={cl.job_descriptor.retry_policy.on_mesh_fail}, solver={cl.job_descriptor.retry_policy.on_solver_fail}",
        "",
    ]
    if cl.meta.reasoning_summary:
        lines.extend(["## 解析说明", "", cl.meta.reasoning_summary, ""])
    if cl.assumptions:
        lines.extend(["## 7 默认与假设", ""])
        for a in cl.assumptions:
            lines.append(f"- {a}")
        lines.append("")
    if cl.gaps:
        lines.extend(["## 8 待澄清项", ""])
        for g in cl.gaps:
            lines.append(f"- {g}")
        lines.append("")
    if cl.meta.source_text:
        lines.extend(["## 附录：原始自然语言输入", "", "```", cl.meta.source_text.strip(), "```", ""])
    return "\n".join(lines)
