"""Build Markdown and JSON validation reports."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from backend.validation.paths import artifact_urls as build_artifact_urls
from backend.validation.scorer import ValidationScore

_REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUSE_INDEX = _REPO_ROOT / "rules" / "dnv_clause_index.yaml"

CATEGORY_LABELS = {
    "benchmark": "基准对标",
    "stability_watertight": "稳性/水密 (C301)",
    "structural_layout": "结构布局 (ST-0437)",
    "detailing_fatigue_proxy": "疲劳/细节 (RP-0286)",
}


def _load_clause_map() -> dict[str, dict[str, Any]]:
    if not CLAUSE_INDEX.is_file():
        return {}
    raw = yaml.safe_load(CLAUSE_INDEX.read_text(encoding="utf-8"))
    return {c["id"]: c for c in (raw.get("clauses") or [])}


def build_markdown_report(
    score: ValidationScore,
    *,
    validation_id: str,
    geometry_title: str = "Design candidate",
    llm_rationales: dict[str, str] | None = None,
) -> str:
    clauses = _load_clause_map()
    lines = [
        f"# 验证报告 — {geometry_title}",
        "",
        f"**验证 ID**: `{validation_id}`",
        "",
        "## 执行摘要",
        "",
        f"- **综合得分**: {score.overall_score:.1f} / 100",
        f"- **等级**: {score.grade}",
        f"- **钢耗强度**: {score.metrics.get('steel_intensity_t_per_MW', 0):.1f} t/MW",
        f"- **估算总钢量**: {score.metrics.get('steel_mass_t_est', 0):.0f} t",
        f"- **估算方法**: {score.metrics.get('steel_mass_t_source', 'n/a')}",
        "",
    ]
    bc = score.benchmark_context
    if bc:
        lines.extend([
            "### 基准对比",
            "",
            f"- 20 MW 机队分位: {bc.get('percentile_vs_fleet_20mw', '—')}%",
            f"- 机队中位钢耗: {bc.get('fleet_median_intensity_20mw', '—')} t/MW",
            f"- 相对图强: {bc.get('delta_vs_tuqiang_pct', '—')}%",
            f"- 相对 AI 方案: {bc.get('delta_vs_ai_pct', '—')}%",
            "",
        ])

    lines.extend(["## 维度得分", "", "| 维度 | 得分 |", "|---|---:|"])
    for cat, val in score.category_scores.items():
        lines.append(f"| {CATEGORY_LABELS.get(cat, cat)} | {val:.1f} |")
    lines.append("")

    lines.extend(["## 指标实测", "", "| 指标 | 数值 |", "|---|---:|"])
    metric_labels = {
        "target_power_MW": "目标容量 (MW)",
        "steel_intensity_t_per_MW": "钢耗强度 (t/MW)",
        "steel_mass_t_est": "估算钢量 (t)",
        "total_steel_t": "总用钢量 (t)",
        "draft_m": "吃水 (m)",
        "wall_thickness_m": "壳体壁厚 (m)",
        "leg_mean_diameter_m": "柱均径 (m)",
        "leg_mean_length_m": "柱均长 (m)",
        "leg_slenderness_L_over_D": "长细比 L/D",
        "leg_diameter_uniformity_pct": "柱径一致性 (%)",
        "leg_taper_ratio": "变径比",
        "column_spacing_m": "柱间距 (m)",
        "beso3_column_spacing_m": "BESO3 柱间距 (m)",
        "design_domain_span_m": "设计域尺度 (m)",
        "leg_layout_angle_deg_std": "120°布局偏差 (°)",
        "top_plate_diameter_m": "顶盘直径 (m)",
        "plate_to_leg_diameter_ratio": "顶盘/柱径比",
        "dt_ratio": "D/t 比",
        "hub_elevation_m": "Hub 高程 (m)",
        "freeboard_proxy_m": "干舷代理 (m)",
        "bbox_z_m": "竖向包络 (m)",
        "scale_factor": "缩放系数",
    }
    for key, label in metric_labels.items():
        v = score.metrics.get(key)
        if v is not None:
            lines.append(f"| {label} | {v:.3f} |" if isinstance(v, float) else f"| {label} | {v} |")
    lines.append("")

    lines.extend([
        "## 规则明细",
        "",
        "| 规则 | 状态 | 得分 | 实测 | 阈值 | 法规/来源 |",
        "|---|---|---:|---|---|---|",
    ])
    for r in score.rule_results:
        measured = f"{r.measured:.3f}" if r.measured is not None else "—"
        reg = (r.regulation_ref or r.source)[:48]
        lines.append(
            f"| {r.id} | {r.status} | {r.score_0_100:.0f} | {measured} | {r.threshold} | {reg} |"
        )
    lines.append("")

    lines.extend(["## 法规条款映射", "", "| 规则 | 条款 | 摘要 |", "|---|---|---|"])
    for r in score.rule_results:
        cref = r.clause_ref or ""
        c = clauses.get(cref, {})
        summary = c.get("summary_zh") or "—"
        doc = c.get("doc") or cref
        lines.append(f"| {r.id} | {doc} | {summary[:80]} |")
    lines.append("")

    if llm_rationales:
        lines.extend(["## LLM 合规解释（不参与打分）", ""])
        for rid, text in llm_rationales.items():
            lines.extend([f"### {rid}", "", text.strip(), ""])

    if score.calibration_notes:
        lines.extend(["## 综合分校准说明", ""])
        for note in score.calibration_notes:
            lines.append(f"- {note}")
        lines.append("")

    if score.assumptions:
        lines.extend(["## 假设与局限", ""])
        for a in score.assumptions:
            lines.append(f"- {a}")
        lines.append("")

    lines.append("---\n*本报告由 AI Engineer 验证模块自动生成；法规符合性需经持证验船师复核。*")
    return "\n".join(lines)


def score_to_json(score: ValidationScore, *, validation_id: str, artifacts: dict[str, Any]) -> dict[str, Any]:
    return {
        "validation_id": validation_id,
        "overall_score": score.overall_score,
        "grade": score.grade,
        "category_scores": score.category_scores,
        "metrics": score.metrics,
        "benchmark_context": score.benchmark_context,
        "assumptions": score.assumptions,
        "calibration_notes": score.calibration_notes,
        "scoring_config": score.scoring_config,
        "rules": [
            {
                "id": r.id,
                "category": r.category,
                "status": r.status,
                "score_0_100": r.score_0_100,
                "measured": r.measured,
                "threshold": r.threshold,
                "weight": r.weight,
                "weighted_contribution": r.weighted_contribution,
                "source": r.source,
                "clause_ref": r.clause_ref,
                "regulation_ref": r.regulation_ref,
                "unit": r.unit,
                "description_zh": r.description_zh,
            }
            for r in score.rule_results
        ],
        "artifacts": artifacts,
    }


def write_reports(
    score: ValidationScore,
    out_dir: Path,
    *,
    validation_id: str,
    geometry_title: str = "Design candidate",
    plot_artifacts: dict[str, list[str]] | None = None,
    llm_rationales: dict[str, str] | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = build_markdown_report(
        score,
        validation_id=validation_id,
        geometry_title=geometry_title,
        llm_rationales=llm_rationales,
    )
    md_path = out_dir / "validation_report.md"
    md_path.write_text(md, encoding="utf-8")

    art: dict[str, Any] = {"report_md": f"/api/validation/{validation_id}/files/validation_report.md"}
    if plot_artifacts:
        web_figs: dict[str, list[str]] = {}
        api_urls = build_artifact_urls(validation_id, out_dir)
        web_figs.update(api_urls.get("figures") or {})  # type: ignore[arg-type]
        art["figures"] = web_figs

    payload = score_to_json(score, validation_id=validation_id, artifacts=art)
    json_path = out_dir / "validation_score.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"report_md": str(md_path), "score_json": str(json_path)}
