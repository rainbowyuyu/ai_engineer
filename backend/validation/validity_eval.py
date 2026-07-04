"""Fleet dimension comparison table: AI Review 五维 vs 法规五维（同一套指标）."""
from __future__ import annotations

from typing import Any

from backend.validation.ai_review import DIMENSION_KEYS, load_ai_review_config
from backend.validation.fleet_scoring import FleetReviewPoint, score_fleet_benchmarks
from backend.validation.regulatory_review import load_regulatory_review_config
from backend.validation.scorer import ValidationScore

# 法规侧与 AI 使用相同的五维键；综合分键用于排序/有效性统计
REGULATORY_OVERALL_KEY = "regulatory_overall"


def _fmt_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) + 1e-9, 1)


def _scores_for_row(metrics: dict[str, float | None], scores: dict[str, float]) -> dict[str, float | None]:
    """Hide score cells when the underlying metric is missing (show '-' in tables)."""
    return {
        k: _fmt_score(scores.get(k)) if metrics.get(k) is not None else None
        for k in DIMENSION_KEYS
    }


def _format_raw_metric(key: str, value: float | None) -> str | None:
    if value is None:
        return None
    v = float(value)
    if key == "capacity_mw":
        return f"{v:.1f}"
    if key == "steel_per_mw":
        return f"{v:.0f}"
    if key == "unit_cost":
        return f"{v:.0f}"
    if key in ("construction_years", "fatigue_life"):
        return f"{v:.1f}"
    return f"{v:.2f}"


def _rank(values: list[float]) -> list[float]:
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    rx = _rank(xs)
    ry = _rank(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den_x = sum((a - mx) ** 2 for a in rx) ** 0.5
    den_y = sum((b - my) ** 2 for b in ry) ** 0.5
    if den_x < 1e-12 or den_y < 1e-12:
        return None
    return round(num / (den_x * den_y), 3)


def _validity_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure AI vs regulatory agreement on the same five dimensions."""
    if len(rows) < 3:
        return {"n": len(rows), "note": "样本不足，未计算相关性"}

    ai_overall = [float(r["ai_overall"]) for r in rows if r.get("ai_overall") is not None]
    reg_overall = [float(r["regulatory_overall"]) for r in rows if r.get("regulatory_overall") is not None]
    n = min(len(ai_overall), len(reg_overall))
    ai_overall = ai_overall[:n]
    reg_overall = reg_overall[:n]

    dim_mae: dict[str, float] = {}
    for key in DIMENSION_KEYS:
        diffs = []
        for r in rows:
            ai = (r.get("ai_scores") or {}).get(key)
            reg = (r.get("regulatory_scores") or {}).get(key)
            if ai is not None and reg is not None:
                diffs.append(abs(float(ai) - float(reg)))
        if diffs:
            dim_mae[key] = round(sum(diffs) / len(diffs), 1)

    agree = 0
    for a, b in zip(ai_overall, reg_overall):
        if abs(a - b) <= 15.0 and a >= 60.0 and b >= 60.0:
            agree += 1

    return {
        "n": n,
        "overall_spearman": _spearman(ai_overall, reg_overall),
        "overall_mean_abs_diff": round(sum(abs(a - b) for a, b in zip(ai_overall, reg_overall)) / n, 1)
        if n
        else None,
        "dimension_mean_abs_diff": dim_mae,
        "high_agreement_pct": round(100.0 * agree / n, 1) if n else None,
        "interpretation": (
            "综合分 Spearman 越接近 1，说明 AI 与法规在机队排序上越一致；"
            "各维平均绝对差 |AI−法规| 越小，说明同指标下两套口径越接近。"
        ),
    }


def _row_from_fleet(point: FleetReviewPoint, *, regulatory: dict[str, float] | None = None) -> dict[str, Any]:
    reg_src = regulatory if regulatory is not None else point.regulatory_scores
    metrics = point.metrics or {}
    raw = {k: _format_raw_metric(k, metrics.get(k)) for k in DIMENSION_KEYS}
    ai = _scores_for_row(metrics, point.scores)
    reg = _scores_for_row(metrics, reg_src)
    return {
        "name": point.short_name,
        "region": point.region,
        "year_status": point.year_status,
        "ai_overall": _fmt_score(point.overall),
        "regulatory_overall": _fmt_score(point.regulatory_overall),
        "raw_metrics": raw,
        "ai_scores": ai,
        "ai_metrics": {k: metrics.get(k) for k in DIMENSION_KEYS},
        "regulatory_scores": reg,
    }


def _row_from_candidate(score: ValidationScore, *, label: str) -> dict[str, Any]:
    metrics = score.ai_review_metrics or {}
    raw = {k: _format_raw_metric(k, metrics.get(k)) for k in DIMENSION_KEYS}
    reg_scores = score.regulatory_review_scores or {}
    reg = _scores_for_row(metrics, reg_scores)
    ai = _scores_for_row(metrics, score.ai_review_scores or {})
    return {
        "name": label,
        "region": "candidate",
        "year_status": "candidate",
        "ai_overall": _fmt_score(score.overall_score),
        "regulatory_overall": _fmt_score(score.regulatory_overall),
        "raw_metrics": raw,
        "ai_scores": ai,
        "ai_metrics": {k: metrics.get(k) for k in DIMENSION_KEYS},
        "regulatory_scores": reg,
        "is_candidate": True,
    }


def compute_dimension_comparison_table(
    score: ValidationScore,
    fleet_points: list[FleetReviewPoint] | None = None,
    *,
    candidate_label: str = "本方案",
) -> dict[str, Any]:
    """Build Table 1: per-project AI 5-dim vs Regulatory 5-dim on the SAME metrics."""
    fleet_points = fleet_points or score_fleet_benchmarks()
    ai_cfg = load_ai_review_config()
    reg_cfg = load_regulatory_review_config()
    ai_labels = {k: (ai_cfg.get("dimension_labels_zh") or {}).get(k, k) for k in DIMENSION_KEYS}
    reg_labels = {k: (reg_cfg.get("dimension_labels_zh") or {}).get(k, k) for k in DIMENSION_KEYS}
    reg_sources = reg_cfg.get("sources_zh") or {}

    commissioned: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []

    for pt in fleet_points:
        row = _row_from_fleet(pt)
        if pt.year_status == "planned" or (pt.year and pt.year >= 2025):
            planned.append(row)
        else:
            commissioned.append(row)

    candidate_row = _row_from_candidate(score, label=candidate_label)
    validity_summary = _validity_summary(commissioned)

    spearman = validity_summary.get("overall_spearman")
    mae = validity_summary.get("overall_mean_abs_diff")
    agree = validity_summary.get("high_agreement_pct")
    validity_line = ""
    validity_line_en = ""
    if spearman is not None:
        n = validity_summary.get("n")
        validity_line = (
            f"已建成机队 (n={n})："
            f"综合分 Spearman={spearman}，平均 |AI−法规|={mae} 分，"
            f"双通道均≥60 且差≤15 分占比 {agree}%。"
        )
        validity_line_en = (
            f"Commissioned fleet (n={n}): overall Spearman={spearman}, "
            f"mean |AI-reg|={mae} pts, agreement (both >=60, diff<=15)={agree}%."
        )

    return {
        "title": "表1 | 同一五维指标：AI Review vs 法规标准打分对照",
        "title_en": "Table 1 | AI Review vs. regulatory scores (same five metrics)",
        "note": (
            "左右五列指标名称相同（容量、钢耗、造价、工期、寿命）；"
            "左为 AI Review（机队分位/AI 参考线/经济性代理），"
            "右为法规口径（DNV 规则合成分、300 t/MW 目标、25 年设计寿命、示范 EPC/工期上限）。"
            "原始物理量见 ai_metrics，两套打分共用同一实测值。"
            f" {validity_line}"
        ),
        "note_en": (
            "Same five metrics left (AI Review) and right (regulatory / DNV thresholds). "
            "Raw values shared per row. "
            f"{validity_line_en}"
        ),
        "ai_columns": [{"key": k, "label": ai_labels.get(k, k)} for k in DIMENSION_KEYS],
        "regulatory_columns": [
            {"key": k, "label": reg_labels.get(k, k), "source": reg_sources.get(k, "")}
            for k in DIMENSION_KEYS
        ],
        "validity_summary": validity_summary,
        "candidate": candidate_row,
        "commissioned_cohort": commissioned,
        "planned_cohort": planned,
    }


# Backward-compatible alias used by pipeline
def compute_validity_table(
    fleet_points: list[FleetReviewPoint] | None = None,
    score: ValidationScore | None = None,
    *,
    candidate_label: str = "本方案",
) -> dict[str, Any]:
    if score is None:
        from backend.validation.geometry_metrics import extract_geometry_metrics
        from backend.validation.scorer import score_design
        import json
        from pathlib import Path

        sample = Path(__file__).resolve().parents[2] / "rules" / "optimized_geometry.json"
        geom = json.loads(sample.read_text(encoding="utf-8"))
        score = score_design(extract_geometry_metrics(geom))
    return compute_dimension_comparison_table(
        score,
        fleet_points,
        candidate_label=candidate_label,
    )
