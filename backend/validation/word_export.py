"""Export validation report as Word (.docx) with embedded figures."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.validation.paths import FIGURE_STEMS
from backend.validation.report_builder import CATEGORY_LABELS, score_to_json
from backend.validation.scorer import ValidationScore

_REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUSE_INDEX = _REPO_ROOT / "rules" / "dnv_clause_index.yaml"

FIGURE_CAPTIONS: dict[str, str] = {
    "fig_benchmark_position": "图1 钢耗强度 · 行业基准位置（含行业趋势线）",
    "fig_benchmark_capacity": "图2 单机容量 · 行业基准位置（含行业趋势线）",
    "fig_benchmark_unit_cost": "图3 单位造价 · 行业基准位置（含行业趋势线）",
    "fig_benchmark_construction": "图4 施工年限 · 行业基准位置（含行业趋势线）",
    "fig_benchmark_fatigue": "图5 疲劳寿命 · 行业基准位置（含行业趋势线）",
    "fig_score_radar": "图6 AI Review 五维对比雷达（机队对比）",
    "fig_fleet_metrics_bars": "图7 AI Review 有效性（原始指标 vs AI/法规得分）",
    "fig_rule_heatmap": "图8 规则得分分解",
    "fig_capacity_intensity": "图9 容量–钢耗强度散点",
    "fig_ai_review_validity": "表1 同一五维指标：AI Review vs 法规标准打分对照",
}

METRIC_LABELS: dict[str, str] = {
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
    "steel_mass_t_source": "钢量估算方法",
}


def _load_clause_map() -> dict[str, dict[str, Any]]:
    if not CLAUSE_INDEX.is_file():
        return {}
    raw = yaml.safe_load(CLAUSE_INDEX.read_text(encoding="utf-8"))
    return {c["id"]: c for c in (raw.get("clauses") or [])}


def _geometry_title_from_dir(out_dir: Path, fallback: str = "Design candidate") -> str:
    snap = out_dir / "input_geometry_snapshot.json"
    if snap.is_file():
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
            title = str(data.get("title") or "").strip()
            if title:
                return title
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return fallback


def _payload_from_score(score: ValidationScore, *, validation_id: str) -> dict[str, Any]:
    return score_to_json(score, validation_id=validation_id, artifacts={})


def _payload_from_dir(out_dir: Path) -> tuple[dict[str, Any], str]:
    score_path = out_dir / "validation_score.json"
    if not score_path.is_file():
        raise FileNotFoundError(f"Missing {score_path}")
    payload = json.loads(score_path.read_text(encoding="utf-8"))
    title = _geometry_title_from_dir(out_dir)
    return payload, title


def _set_run_cn(run, *, size_pt: float | None = 11, bold: bool = False) -> None:
    from docx.oxml.ns import qn
    from docx.shared import Pt

    run.font.name = "宋体"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    run.bold = bold


def _add_heading(doc, text: str, level: int = 1) -> None:
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        _set_run_cn(run, size_pt=16 if level == 1 else 14, bold=True)


def _add_paragraph(doc, text: str, *, bold: bool = False) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    _set_run_cn(run, bold=bold)


def _add_bullet(doc, text: str) -> None:
    p = doc.add_paragraph(text, style="List Bullet")
    for run in p.runs:
        _set_run_cn(run)


def _add_table(doc, headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        return
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        for p in hdr_cells[i].paragraphs:
            for run in p.runs:
                _set_run_cn(run, bold=True)
    for ri, row in enumerate(rows):
        cells = table.rows[ri + 1].cells
        for ci, val in enumerate(row):
            cells[ci].text = str(val)
            for p in cells[ci].paragraphs:
                for run in p.runs:
                    _set_run_cn(run)
    doc.add_paragraph()


def _format_metric(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _build_docx_body(
    doc,
    payload: dict[str, Any],
    *,
    validation_id: str,
    geometry_title: str,
    out_dir: Path,
    llm_rationales: dict[str, str] | None = None,
) -> None:
    from docx.shared import Inches

    clauses = _load_clause_map()
    metrics = payload.get("metrics") or {}
    bc = payload.get("benchmark_context") or {}

    _add_heading(doc, f"验证报告 — {geometry_title}", level=1)
    _add_paragraph(doc, f"验证 ID：{validation_id}")
    _add_paragraph(
        doc,
        f"生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    )
    doc.add_paragraph()

    _add_heading(doc, "执行摘要", level=2)
    _add_bullet(doc, f"综合得分：{payload.get('overall_score', 0):.1f} / 100")
    _add_bullet(doc, f"等级：{payload.get('grade', '—')}")
    _add_bullet(doc, f"钢耗强度：{metrics.get('steel_intensity_t_per_MW', 0):.1f} t/MW")
    _add_bullet(doc, f"估算总钢量：{metrics.get('steel_mass_t_est', 0):.0f} t")
    _add_bullet(doc, f"估算方法：{metrics.get('steel_mass_t_source', 'n/a')}")

    if bc:
        doc.add_paragraph()
        _add_heading(doc, "基准对比", level=3)
        _add_bullet(doc, f"20 MW 机队分位：{bc.get('percentile_vs_fleet_20mw', '—')}%")
        _add_bullet(doc, f"机队中位钢耗：{bc.get('fleet_median_intensity_20mw', '—')} t/MW")
        _add_bullet(doc, f"相对图强：{bc.get('delta_vs_tuqiang_pct', '—')}%")

    doc.add_paragraph()
    _add_heading(doc, "AI Review 五维得分", level=2)
    ai_scores = payload.get("ai_review_scores") or {}
    ai_labels = payload.get("ai_review_labels") or {}
    ai_metrics = payload.get("ai_review_metrics") or {}
    ai_rows: list[list[str]] = []
    for key, val in ai_scores.items():
        label = ai_labels.get(key, key)
        measured = ai_metrics.get(key)
        mtxt = f"{measured:.2f}" if isinstance(measured, (int, float)) else "—"
        ai_rows.append([label, mtxt, f"{float(val):.1f}"])
    _add_table(doc, ["指标", "实测", "得分"], ai_rows)

    _add_heading(doc, "合规维度得分（DNV 规则明细）", level=2)
    cat_rows = [
        [CATEGORY_LABELS.get(cat, cat), f"{float(val):.1f}"]
        for cat, val in (payload.get("category_scores") or {}).items()
    ]
    _add_table(doc, ["维度", "得分"], cat_rows)

    _add_heading(doc, "验证图表", level=2)
    fig_idx = 0
    for stem in FIGURE_STEMS:
        png = out_dir / f"{stem}.png"
        if not png.is_file():
            continue
        fig_idx += 1
        caption = FIGURE_CAPTIONS.get(stem, stem)
        try:
            doc.add_picture(str(png), width=Inches(6.2))
        except Exception:
            _add_paragraph(doc, f"[无法嵌入图片：{png.name}]")
        cap = doc.add_paragraph()
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(caption)
        _set_run_cn(run, size_pt=10)
        doc.add_paragraph()

    _add_heading(doc, "指标实测", level=2)
    metric_rows: list[list[str]] = []
    for key, label in METRIC_LABELS.items():
        v = metrics.get(key)
        if v is not None:
            metric_rows.append([label, _format_metric(v)])
    _add_table(doc, ["指标", "数值"], metric_rows)

    _add_heading(doc, "规则明细", level=2)
    rule_rows: list[list[str]] = []
    for r in payload.get("rules") or []:
        measured = f"{r['measured']:.3f}" if r.get("measured") is not None else "—"
        reg = str(r.get("regulation_ref") or r.get("source") or "")[:48]
        rule_rows.append([
            r.get("id", ""),
            r.get("status", ""),
            f"{float(r.get('score_0_100', 0)):.0f}",
            measured,
            str(r.get("threshold", "")),
            reg,
        ])
    _add_table(doc, ["规则", "状态", "得分", "实测", "阈值", "法规/来源"], rule_rows)

    _add_heading(doc, "法规条款映射", level=2)
    clause_rows: list[list[str]] = []
    for r in payload.get("rules") or []:
        cref = r.get("clause_ref") or ""
        c = clauses.get(cref, {})
        summary = str(c.get("summary_zh") or "—")[:80]
        doc_name = c.get("doc") or cref
        clause_rows.append([r.get("id", ""), str(doc_name), summary])
    _add_table(doc, ["规则", "条款", "摘要"], clause_rows)

    if llm_rationales:
        _add_heading(doc, "LLM 合规解释（不参与打分）", level=2)
        for rid, text in llm_rationales.items():
            _add_heading(doc, rid, level=3)
            _add_paragraph(doc, text.strip())

    notes = payload.get("calibration_notes") or []
    if notes:
        _add_heading(doc, "综合分校准说明", level=2)
        for note in notes:
            _add_bullet(doc, str(note))

    assumptions = payload.get("assumptions") or []
    if assumptions:
        _add_heading(doc, "假设与局限", level=2)
        for a in assumptions:
            _add_bullet(doc, str(a))

    doc.add_paragraph()
    _add_paragraph(
        doc,
        "本报告由 AI Engineer 验证模块自动生成；法规符合性需经持证验船师复核。",
    )


def build_validation_docx(
    out_dir: Path,
    *,
    score: ValidationScore | None = None,
    validation_id: str | None = None,
    geometry_title: str | None = None,
    llm_rationales: dict[str, str] | None = None,
) -> Path:
    """Build validation_report.docx under out_dir. Requires python-docx."""
    try:
        from docx import Document
    except ImportError as e:
        raise ImportError(
            "python-docx is required for Word export; "
            "install with: pip install -r backend/requirements-validation.txt"
        ) from e

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    vid = validation_id or out_dir.name

    if score is not None:
        payload = _payload_from_score(score, validation_id=vid)
        title = geometry_title or "Design candidate"
    else:
        payload, title = _payload_from_dir(out_dir)
        if geometry_title:
            title = geometry_title

    docx_path = out_dir / "validation_report.docx"
    doc = Document()
    _build_docx_body(
        doc,
        payload,
        validation_id=vid,
        geometry_title=title,
        out_dir=out_dir,
        llm_rationales=llm_rationales,
    )
    doc.save(str(docx_path))
    return docx_path
