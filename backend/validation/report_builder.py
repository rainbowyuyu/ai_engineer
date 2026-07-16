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


def _validity_markdown(validity: dict[str, Any] | None) -> list[str]:
    if not validity:
        return []
    ai_cols = validity.get("ai_columns") or []
    reg_cols = validity.get("regulatory_columns") or []
    if not ai_cols:
        return []
    raw_hdr = "MW | t/MW | kCNY/MW | yr | yr"
    ai_hdr = " | ".join(c.get("label", "") for c in ai_cols)
    reg_hdr = " | ".join(c.get("label", "") for c in reg_cols)
    lines = [
        "## 表1 · 同一五维指标：AI Review vs 法规标准",
        "",
        f"*{validity.get('note', '')}*",
        "",
    ]

    def append_cohort(title: str, cohort: list[dict[str, Any]]) -> None:
        if not cohort:
            return
        lines.extend([f"### {title}", ""])
        lines.append(f"| 项目 | {raw_hdr} | {ai_hdr} | {reg_hdr} |")
        lines.append(
            "|---|"
            + "|".join("---:" for _ in range(5))
            + "|"
            + "|".join("---:" for _ in ai_cols)
            + "|"
            + "|".join("---:" for _ in reg_cols)
            + "|"
        )
        for row in cohort:
            ai = row.get("ai_scores") or {}
            reg = row.get("regulatory_scores") or {}
            raw = row.get("raw_metrics") or {}
            raw_cells = " | ".join(
                str(raw.get(c["key"])) if raw.get(c["key"]) is not None else "-"
                for c in ai_cols
            )
            ai_cells = " | ".join(
                f"{ai.get(c['key']):.1f}" if ai.get(c["key"]) is not None else "-"
                for c in ai_cols
            )
            reg_cells = " | ".join(
                f"{reg.get(c['key']):.1f}" if reg.get(c["key"]) is not None else "-"
                for c in reg_cols
            )
            lines.append(f"| {row.get('name', '')} | {raw_cells} | {ai_cells} | {reg_cells} |")
        lines.append("")

    append_cohort("已建成机队", validity.get("commissioned_cohort") or [])
    append_cohort("规划/前瞻项目", validity.get("planned_cohort") or [])
    cand = validity.get("candidate")
    if cand:
        append_cohort("本方案（候选）", [cand])
    return lines


def build_markdown_report(
    score: ValidationScore,
    *,
    validation_id: str,
    geometry_title: str = "Design candidate",
    llm_rationales: dict[str, str] | None = None,
    validity_table: dict[str, Any] | None = None,
    plot_artifacts: dict[str, list[str]] | None = None,
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
            "",
        ])

    lines.extend(["## AI Review 五维得分", "", "| 指标 | 实测 | 得分 |", "|---|---:|---:|"])
    for key, val in (score.ai_review_scores or {}).items():
        label = (score.ai_review_labels or {}).get(key, key)
        measured = (score.ai_review_metrics or {}).get(key)
        mtxt = f"{measured:.2f}" if isinstance(measured, (int, float)) else "—"
        lines.append(f"| {label} | {mtxt} | {val:.1f} |")
    lines.append("")
    lines.append(
        f"*综合分 {score.overall_score:.1f} 为 AI Review 五维加权；"
        f"法规五维综合 {score.regulatory_overall:.1f} 为同一指标下的 DNV/行业阈值口径，供有效性对照。*"
    )
    lines.append("")

    lines.extend(["## 法规五维得分（同一指标 · DNV/行业阈值）", "", "| 指标 | 实测 | 法规分 |", "|---|---:|---:|"])
    reg_scores = score.regulatory_review_scores or {}
    for key in score.ai_review_scores or {}:
        label = (score.ai_review_labels or {}).get(key, key)
        measured = (score.ai_review_metrics or {}).get(key)
        mtxt = f"{measured:.2f}" if isinstance(measured, (int, float)) else "—"
        rval = reg_scores.get(key)
        rtxt = f"{rval:.1f}" if rval is not None else "—"
        lines.append(f"| {label} | {mtxt} | {rtxt} |")
    lines.append("")

    lines.extend(["## 合规维度得分（DNV 规则分类 · 补充审计）", "", "| 维度 | 得分 |", "|---|---:|"])
    for cat, val in score.category_scores.items():
        lines.append(f"| {CATEGORY_LABELS.get(cat, cat)} | {val:.1f} |")
    lines.append("")

    lines.extend(["## 指标实测", "", "| 指标 | 数值 |", "|---|---:|"])
    metric_labels = {
        "target_power_MW": "目标容量 (MW)",
        "steel_intensity_t_per_MW": "钢耗强度 (t/MW)",
        "steel_mass_t_est": "估算钢量 (t)",
        "unit_cost_cny_per_MW": "单位造价 (万元/MW)",
        "construction_years": "施工年限 (年)",
        "fatigue_life_years": "疲劳寿命 (年)",
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

    lines.extend(_validity_markdown(validity_table))

    if plot_artifacts:
        lines.extend(["## 图表产物（PNG / PDF）", ""])
        for stem in sorted(plot_artifacts):
            lines.append(f"- `{stem}.png`, `{stem}.pdf`")
        lines.append("")

    if score.assumptions:
        lines.extend(["## 假设与局限", ""])
        for a in score.assumptions:
            lines.append(f"- {a}")
        lines.append("")

    lines.append("---\n*本报告由 AI Engineer 验证模块自动生成；法规符合性需经持证验船师复核。*")
    return "\n".join(lines)


def score_to_json(
    score: ValidationScore,
    *,
    validation_id: str,
    artifacts: dict[str, Any],
    validity_table: dict[str, Any] | None = None,
    fleet_radar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "validation_id": validation_id,
        "overall_score": score.overall_score,
        "grade": score.grade,
        "regulatory_overall": score.regulatory_overall,
        "regulatory_review_scores": score.regulatory_review_scores,
        "ai_review_primary": True,
        "ai_review_scores": score.ai_review_scores,
        "ai_review_metrics": score.ai_review_metrics,
        "ai_review_weights": score.ai_review_weights,
        "ai_review_labels": score.ai_review_labels,
        "category_scores": score.category_scores,
        "metrics": score.metrics,
        "benchmark_context": score.benchmark_context,
        "assumptions": score.assumptions,
        "calibration_notes": score.calibration_notes,
        "scoring_config": score.scoring_config,
        "surrogate_context": score.surrogate_context,
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
    if validity_table:
        payload["validity_table"] = validity_table
    if fleet_radar:
        payload["fleet_radar"] = fleet_radar
    return payload


def write_reports(
    score: ValidationScore,
    out_dir: Path,
    *,
    validation_id: str,
    geometry_title: str = "Design candidate",
    plot_artifacts: dict[str, list[str]] | None = None,
    llm_rationales: dict[str, str] | None = None,
    validity_table: dict[str, Any] | None = None,
    fleet_radar: dict[str, Any] | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = build_markdown_report(
        score,
        validation_id=validation_id,
        geometry_title=geometry_title,
        llm_rationales=llm_rationales,
        validity_table=validity_table,
        plot_artifacts=plot_artifacts,
    )
    md_path = out_dir / "validation_report.md"
    md_path.write_text(md, encoding="utf-8")

    art: dict[str, Any] = {"report_md": f"/api/validation/{validation_id}/files/validation_report.md"}
    if plot_artifacts:
        web_figs: dict[str, list[str]] = {}
        api_urls = build_artifact_urls(validation_id, out_dir)
        web_figs.update(api_urls.get("figures") or {})  # type: ignore[arg-type]
        art["figures"] = web_figs

    payload = score_to_json(
        score,
        validation_id=validation_id,
        artifacts=art,
        validity_table=validity_table,
        fleet_radar=fleet_radar,
    )
    json_path = out_dir / "validation_score.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    docx_path: str | None = None
    docx_detailed_path: str | None = None
    word_export_error: str | None = None
    word_detailed_export_error: str | None = None
    try:
        from backend.validation.word_export import build_validation_docx

        docx_file = build_validation_docx(
            out_dir,
            score=score,
            validation_id=validation_id,
            geometry_title=geometry_title,
            llm_rationales=llm_rationales,
        )
        docx_path = str(docx_file)
        art["report_docx"] = f"/api/validation/{validation_id}/files/validation_report.docx"
        payload["artifacts"] = art
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except ImportError:
        word_export_error = "python-docx 未安装（pip install -r backend/requirements-validation.txt）"
    except Exception as e:
        word_export_error = str(e)

    try:
        from backend.validation.word_export_detailed import build_validation_docx_detailed

        docx_detailed_file = build_validation_docx_detailed(
            out_dir,
            score=score,
            validation_id=validation_id,
            geometry_title=geometry_title,
            llm_rationales=llm_rationales,
        )
        docx_detailed_path = str(docx_detailed_file)
        art["report_docx_detailed"] = (
            f"/api/validation/{validation_id}/files/validation_report_detailed.docx"
        )
        art["export_word_detailed"] = f"/api/validation/{validation_id}/export/word/detailed"
        payload["artifacts"] = art
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except ImportError:
        word_detailed_export_error = (
            "python-docx 未安装（pip install -r backend/requirements-validation.txt）"
        )
    except Exception as e:
        word_detailed_export_error = str(e)

    result = {"report_md": str(md_path), "score_json": str(json_path)}
    if docx_path:
        result["report_docx"] = docx_path
    if docx_detailed_path:
        result["report_docx_detailed"] = docx_detailed_path
    if word_export_error:
        result["word_export_error"] = word_export_error
    if word_detailed_export_error:
        result["word_detailed_export_error"] = word_detailed_export_error
    return result
