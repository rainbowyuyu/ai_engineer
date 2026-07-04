"""Nature-style validation figures."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Headless backend — required when validation runs under uvicorn / worker threads
# (FreeCAD-bundled Python may default to TkAgg and fail outside the main thread).
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib as mpl

if mpl.get_backend().lower() != "agg":
    mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from backend.validation.ai_review import DIMENSION_KEYS
from backend.validation.benchmark_loader import BenchmarkRecord, load_benchmark_records
from backend.validation.fleet_scoring import FleetReviewPoint, score_fleet_benchmarks
from backend.validation.scorer import ValidationScore

NATURE_COLORS = {
    "international": "#3C5488",
    "domestic": "#E64B35",
    "candidate": "#00A087",
    "trend": "#8491B4",
    "grid": "#E6E6E6",
    "text": "#222222",
}

CATEGORY_LABELS = {
    "benchmark": "基准对标",
    "stability_watertight": "稳性/水密",
    "structural_layout": "结构布局",
    "detailing_fatigue_proxy": "疲劳/细节",
}

RADAR_SHORT_LABELS = {
    "capacity_mw": "Capacity",
    "steel_per_mw": "Steel/MW",
    "unit_cost": "Unit cost",
    "construction_years": "Construction",
    "fatigue_life": "Fatigue life",
}

DIMENSION_LABELS_EN = {
    "capacity_mw": "Capacity",
    "steel_per_mw": "Steel/MW",
    "unit_cost": "Unit cost",
    "construction_years": "Construction",
    "fatigue_life": "Fatigue life",
}

CHART_LABEL_MAP = {
    "本方案": "Proposed",
    "Candidate": "Proposed",
}

PROJECT_NAME_EN = {
    "图强": "Tuqiang",
    "三峡引领": "Three Gorges Yinling",
    "三峡领航": "Three Gorges Linghang",
    "海装扶瑶": "Haizhuang Fuyao",
    "海油观澜": "Haiyou Guanlan",
    "明阳天成": "Mingyang Tiancheng",
    "万宁一期": "Wanning Phase 1",
    "GHN 共享": "GHN Shared",
    "龙源南日岛": "Longyuan Nanri",
    "福岛示范": "Fukushima demo",
}

RADAR_HIGHLIGHT = (
    "图强",
    "三峡引领",
    "海装扶瑶",
    "海油观澜",
    "三峡领航",
    "明阳天成",
    "万宁一期",
    "Kincardine Ph2",
    "Hywind Scotland",
)

# Radar overlay: proposed design is drawn separately — do not include its alias "AI"
RADAR_ON_CHART = ("图强", "海油观澜", "明阳天成", "Kincardine Ph2")

# Industry benchmark charts: five metrics + quadratic trend vs. commissioning year
BENCHMARK_METRIC_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "stem": "fig_benchmark_position",
        "record_attr": "steel_intensity",
        "candidate_attrs": ("steel_intensity_t_per_MW",),
        "ylabel": "Steel intensity (t MW$^{-1}$)",
        "title": "Benchmark position — steel intensity",
        "title_zh": "钢耗强度 · 行业基准位置",
        "target": 300.0,
        "target_label": "300 t/MW target",
        "unit": "t/MW",
        "fmt": ".0f",
        "lower_is_better": True,
    },
    {
        "stem": "fig_benchmark_capacity",
        "record_attr": "capacity_mw",
        "candidate_attrs": ("target_power_MW",),
        "ylabel": "Unit capacity (MW)",
        "title": "Benchmark position — unit capacity",
        "title_zh": "单机容量 · 行业基准位置",
        "target": 20.0,
        "target_label": "20 MW target",
        "unit": "MW",
        "fmt": ".1f",
        "lower_is_better": False,
    },
    {
        "stem": "fig_benchmark_unit_cost",
        "record_attr": "unit_cost_cny_per_MW",
        "candidate_attrs": ("unit_cost_cny_per_MW",),
        "ylabel": "Unit cost (10$^{4}$ CNY MW$^{-1}$)",
        "title": "Benchmark position — unit cost",
        "title_zh": "单位造价 · 行业基准位置",
        "target": 2500.0,
        "target_label": "2500 (10$^{4}$ CNY/MW, proposed ref.)",
        "unit": "10$^{4}$ CNY/MW",
        "fmt": ".0f",
        "lower_is_better": True,
    },
    {
        "stem": "fig_benchmark_construction",
        "record_attr": "construction_years",
        "candidate_attrs": ("construction_years",),
        "ylabel": "Construction period (years)",
        "title": "Benchmark position — construction period",
        "title_zh": "施工年限 · 行业基准位置",
        "target": 2.8,
        "target_label": "2.8 yr target (proposed ref.)",
        "unit": "yr",
        "fmt": ".1f",
        "lower_is_better": True,
    },
    {
        "stem": "fig_benchmark_fatigue",
        "record_attr": "fatigue_life_years",
        "candidate_attrs": ("fatigue_life_years",),
        "ylabel": "Design fatigue life (years)",
        "title": "Benchmark position — fatigue life",
        "title_zh": "疲劳寿命 · 行业基准位置",
        "target": 25.0,
        "target_label": "25 yr design life",
        "unit": "yr",
        "fmt": ".1f",
        "lower_is_better": False,
    },
)

# 各方案独立配色与标记
FLEET_SCHEME_STYLE: dict[str, dict[str, str]] = {
    "图强": {"color": "#E64B35", "marker": "D", "ls": "-"},
    "三峡引领": {"color": "#F39B7F", "marker": "o", "ls": "-"},
    "海装扶瑶": {"color": "#8491B4", "marker": "s", "ls": "-"},
    "海油观澜": {"color": "#4DBBD5", "marker": "v", "ls": "--"},
    "三峡领航": {"color": "#DC0000", "marker": "p", "ls": "--"},
    "明阳天成": {"color": "#91D1C2", "marker": "h", "ls": "-"},
    "万宁一期": {"color": "#7E6148", "marker": "X", "ls": "--"},
    "Hywind Scotland": {"color": "#B09C85", "marker": "8", "ls": "-"},
    "Kincardine Ph2": {"color": "#E15759", "marker": "P", "ls": "-"},
    "WindFloat Atlantic": {"color": "#76B7B2", "marker": "o", "ls": "-"},
    "GHN 共享": {"color": "#59A14F", "marker": "d", "ls": "-"},
}


def _scheme_style(short_name: str) -> dict[str, str]:
    for key, style in FLEET_SCHEME_STYLE.items():
        if key in short_name:
            return style
    return {"color": "#8491B4", "marker": "o", "ls": "--"}


def _is_highlight(pt: FleetReviewPoint) -> bool:
    return any(h in pt.short_name for h in RADAR_HIGHLIGHT)


def _on_chart(pt: FleetReviewPoint) -> bool:
    return any(k in pt.short_name for k in RADAR_ON_CHART)


def _style_nature_radar(ax: plt.Axes, angles: list[float], labels: list[str]) -> None:
    """Nature-style polar grid: gray rings, axis-end dots, outer metric labels."""
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels([])
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=9, color=NATURE_COLORS["text"])
    ax.tick_params(axis="x", pad=22)
    ax.grid(color="#BFBFBF", linewidth=0.55, alpha=0.85, linestyle="-")
    ax.spines["polar"].set_visible(False)
    for ang in angles:
        ax.plot([ang, ang], [0, 100], color="#BFBFBF", linewidth=0.45, alpha=0.7, zorder=0)
        ax.plot(ang, 100, "o", color="#1a1a1a", markersize=3.2, zorder=8, clip_on=False)
    ax.text(
        0.5,
        0.5,
        "5\nmetrics",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        color=NATURE_COLORS["text"],
        zorder=9,
        linespacing=0.9,
    )


def _draw_radar_polygon(
    ax: plt.Axes,
    angles_c: list[float],
    values_c: list[float],
    *,
    color: str,
    alpha_fill: float = 0.28,
    linewidth: float = 1.3,
    zorder: int = 2,
) -> None:
    ax.fill(angles_c, values_c, color=color, alpha=alpha_fill, zorder=zorder, linewidth=0)
    ax.plot(
        angles_c,
        values_c,
        color=color,
        linewidth=linewidth,
        solid_capstyle="round",
        solid_joinstyle="round",
        zorder=zorder + 1,
    )


def _nature_radar_legend(ax: plt.Axes, entries: list[tuple[str, str]]) -> None:
    """Upper-left legend with colored border boxes (Nature figure style)."""
    handles = [
        Line2D([0], [0], color=c, lw=2.2, marker="s", markersize=0, label=label)
        for label, c in entries
    ]
    leg = ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(-0.22, 1.14),
        fontsize=7,
        frameon=False,
        handlelength=0,
        handletextpad=0,
        borderaxespad=0,
        labelspacing=0.55,
    )
    for text, (_, color) in zip(leg.get_texts(), entries):
        text.set_bbox(
            {
                "boxstyle": "square,pad=0.35",
                "edgecolor": color,
                "facecolor": "white",
                "linewidth": 1.4,
                "alpha": 0.95,
            }
        )
        text.set_fontsize(6.8)
        text.set_color(NATURE_COLORS["text"])


def _score_cell(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{float(val):.0f}"


def _radar_score_table(
    ax_tbl: plt.Axes,
    candidate_label: str,
    candidate_scores: dict[str, float],
    candidate_overall: float,
    fleet_points: list[FleetReviewPoint],
    cats: list[str],
) -> None:
    """Bottom panel: color swatch + five-dimension scores (no overlapping chart labels)."""
    ax_tbl.axis("off")
    dim_headers = ["Cap.", "Steel", "Cost", "Sched.", "Life"]
    header = ["", "Project", "Overall", *dim_headers]
    rows: list[list[str]] = []

    rows.append(
        [NATURE_COLORS["candidate"], candidate_label, _score_cell(candidate_overall)]
        + [_score_cell(candidate_scores.get(c)) for c in cats]
    )

    highlights = [p for p in fleet_points if _is_highlight(p)]
    highlights.sort(key=lambda p: p.overall, reverse=True)
    for pt in highlights:
        style = _scheme_style(pt.short_name)
        rows.append(
            [style["color"], _chart_project_name(pt.short_name), _score_cell(pt.overall)]
            + [_score_cell(pt.scores.get(c)) for c in cats]
        )

    table = ax_tbl.table(
        cellText=rows,
        colLabels=header,
        loc="center",
        cellLoc="center",
        colWidths=[0.04, 0.16, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.5)
    table.scale(1.0, 1.45)

    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_facecolor("#EEF2F7")
            cell.set_text_props(fontweight="bold", fontsize=7)
            continue
        if c == 0 and r > 0:
            color = rows[r - 1][0]
            if color:
                cell.set_facecolor(color)
            cell.get_text().set_text("")
        if r == 1:
            cell.set_facecolor("#E8F5F2")
            if c == 1:
                cell.set_text_props(fontweight="bold", ha="left")
        elif c == 1:
            cell.set_text_props(ha="left", fontsize=7.5)


def configure_nature_style() -> None:
    import matplotlib.font_manager as fm

    preferred = ["Arial", "Helvetica", "DejaVu Sans", "Microsoft YaHei", "SimHei"]
    available = {f.name for f in fm.fontManager.ttflist}
    font_family = next((f for f in preferred if f in available), "DejaVu Sans")
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font_family, "Arial", "DejaVu Sans"],
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 9,
            "axes.linewidth": 0.6,
            "legend.fontsize": 7,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
        }
    )


def _style_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, axis="y", color=NATURE_COLORS["grid"], linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)


def _save(fig: plt.Figure, out_dir: Path, stem: str) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in (".png", ".pdf"):
        p = out_dir / f"{stem}{ext}"
        fig.savefig(p)
        paths.append(str(p))
    plt.close(fig)
    return paths


def _chart_label(label: str) -> str:
    return CHART_LABEL_MAP.get(label, label)


def _chart_project_name(name: str) -> str:
    for zh, en in PROJECT_NAME_EN.items():
        if zh in name:
            return en
    return name


def _chart_year_label(record: BenchmarkRecord) -> str:
    if record.year is None:
        return "n/a"
    if record.year_status == "planned":
        return f"{record.year}*"
    return str(record.year)


def _record_metric_value(record: BenchmarkRecord, attr: str) -> float | None:
    val = getattr(record, attr, None)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _candidate_metric_value(score: ValidationScore, attrs: tuple[str, ...]) -> float | None:
    for key in attrs:
        if key in (score.ai_review_metrics or {}):
            val = score.ai_review_metrics.get(key)
            if val is not None:
                return float(val)
        if key in score.metrics:
            val = score.metrics.get(key)
            if val is not None:
                return float(val)
    return None


def _year_polynomial_trend(
    records: list[BenchmarkRecord],
    *,
    attr: str,
    degree: int = 2,
) -> tuple[np.poly1d, float] | None:
    """Quadratic (or lower) fit: metric ~ commissioning year. Returns (poly, r2)."""
    pts = [
        (float(r.year), v)
        for r in records
        if r.year is not None and (v := _record_metric_value(r, attr)) is not None
    ]
    if len(pts) < 3:
        return None
    years = np.array([p[0] for p in pts], dtype=float)
    vals = np.array([p[1] for p in pts], dtype=float)
    deg = min(degree, len(pts) - 1)
    if deg < 1:
        return None
    coeffs = np.polyfit(years, vals, deg)
    poly = np.poly1d(coeffs)
    pred = poly(years)
    ss_res = float(np.sum((vals - pred) ** 2))
    ss_tot = float(np.sum((vals - np.mean(vals)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    return poly, max(0.0, min(1.0, r2))


def _year_to_fleet_x(records: list[BenchmarkRecord], year_grid: np.ndarray) -> np.ndarray:
    """Map commissioning years onto fleet-order x positions (handles duplicate years)."""
    buckets: dict[float, list[float]] = {}
    for i, rec in enumerate(records):
        if rec.year is not None:
            buckets.setdefault(float(rec.year), []).append(float(i))
    if not buckets:
        return year_grid
    years_u = np.array(sorted(buckets), dtype=float)
    idx_u = np.array([float(np.mean(buckets[y])) for y in years_u], dtype=float)
    return np.interp(year_grid, years_u, idx_u)


def _trend_direction_note(
    poly: np.poly1d,
    years: list[float],
    *,
    lower_is_better: bool,
) -> str:
    if len(years) < 2:
        return "Industry trend"
    y0 = float(poly(min(years)))
    y1 = float(poly(max(years)))
    improving = y1 < y0 if lower_is_better else y1 > y0
    return "Tightening / improving" if improving else "Loosening / under pressure"


def _format_metric_annotation(val: float, unit: str, fmt: str) -> str:
    return f"{val:{fmt}} {unit}"


def plot_benchmark_metric(
    score: ValidationScore,
    out_dir: Path,
    config: dict[str, Any],
    label: str = "Proposed",
) -> list[str]:
    """Fleet-order benchmark chart with quadratic trend curve vs. commissioning year."""
    configure_nature_style()
    label = _chart_label(label)
    attr = str(config["record_attr"])
    records = [r for r in load_benchmark_records() if _record_metric_value(r, attr) is not None]
    records.sort(key=lambda r: (r.sort_year, r.short_name))
    if len(records) < 2:
        return []

    x = np.arange(len(records))
    y = np.array([_record_metric_value(r, attr) for r in records], dtype=float)
    cand_y = _candidate_metric_value(score, tuple(config["candidate_attrs"]))
    tick_labels = [_chart_year_label(r) for r in records]

    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    _style_axis(ax)

    for region in ("international", "domestic"):
        idx = [i for i, r in enumerate(records) if r.region == region]
        if idx:
            ax.plot(
                x[idx],
                y[idx],
                "o-",
                color=NATURE_COLORS[region],
                markersize=4,
                markerfacecolor="white",
                markeredgewidth=0.9,
                linewidth=1.0,
                label="International" if region == "international" else "China",
            )

    ax.plot(x, y, color="#ccc", linestyle="--", linewidth=0.6, zorder=0)

    trend_years = [float(r.year) for r in records if r.year is not None]
    trend = _year_polynomial_trend(records, attr=attr, degree=2)
    if trend and len(trend_years) >= 3:
        poly, r2 = trend
        year_min, year_max = min(trend_years), max(trend_years)
        year_grid = np.linspace(year_min, year_max, 120)
        val_grid = poly(year_grid)
        x_grid = _year_to_fleet_x(records, year_grid)
        deg_label = "quadratic" if poly.order >= 2 else "linear"
        ax.plot(
            x_grid,
            val_grid,
            color=NATURE_COLORS["trend"],
            linestyle="--",
            linewidth=1.5,
            zorder=2,
            label=f"Trend ({deg_label}, $R^2$={r2:.2f})",
        )
        note = _trend_direction_note(
            poly,
            trend_years,
            lower_is_better=bool(config.get("lower_is_better")),
        )
        fig.text(
            0.02,
            0.01,
            f"* Planned project. Nonlinear fit vs. year; {note}.",
            fontsize=6.5,
            color="#666666",
        )

    target = config.get("target")
    if target is not None:
        ax.axhline(
            float(target),
            color="#999",
            linestyle=":",
            linewidth=0.8,
            label=str(config.get("target_label") or "target"),
        )

    if cand_y is not None:
        fmt = str(config.get("fmt") or ".1f")
        unit = str(config.get("unit") or "")
        ax.scatter(
            [len(records)],
            [cand_y],
            s=80,
            c=NATURE_COLORS["candidate"],
            marker="*",
            edgecolors="black",
            linewidths=0.5,
            zorder=5,
            label=label,
        )
        ax.annotate(
            f"{label}\n{_format_metric_annotation(cand_y, unit, fmt)}",
            (len(records), cand_y),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=7,
            color=NATURE_COLORS["candidate"],
        )
        ax.set_xticks(list(x) + [len(records)])
        ax.set_xticklabels(tick_labels + [label], rotation=0, fontsize=7)
    else:
        ax.set_xticks(x)
        ax.set_xticklabels(tick_labels, rotation=0, fontsize=7)

    ax.set_xlabel("Commissioning / planning year (fleet order)")
    ax.set_ylabel(str(config["ylabel"]))
    ax.set_title(str(config["title"]), loc="left", fontweight="bold")
    ax.legend(loc="upper right", fontsize=6.5)
    fig.subplots_adjust(bottom=0.14)
    return _save(fig, out_dir, str(config["stem"]))


def plot_benchmark_position(score: ValidationScore, out_dir: Path, label: str = "Candidate") -> list[str]:
    """Steel intensity benchmark (backward-compatible entry point)."""
    return plot_benchmark_metric(score, out_dir, BENCHMARK_METRIC_CONFIGS[0], label)


def plot_all_benchmark_positions(
    score: ValidationScore,
    out_dir: Path,
    label: str = "Candidate",
) -> dict[str, list[str]]:
    """Generate benchmark position charts for all five AI Review metrics."""
    artifacts: dict[str, list[str]] = {}
    for cfg in BENCHMARK_METRIC_CONFIGS:
        paths = plot_benchmark_metric(score, out_dir, cfg, label)
        if paths:
            artifacts[str(cfg["stem"])] = paths
    return artifacts


def plot_score_radar(
    score: ValidationScore,
    out_dir: Path,
    *,
    fleet_points: list[FleetReviewPoint] | None = None,
    candidate_label: str = "Proposed",
) -> list[str]:
    configure_nature_style()
    candidate_label = _chart_label(candidate_label)
    if not score.ai_review_scores:
        return []
    cats = list(DIMENSION_KEYS)
    labels = [RADAR_SHORT_LABELS.get(c, c) for c in cats]
    fleet_points = fleet_points or score_fleet_benchmarks()
    angles = np.linspace(0, 2 * np.pi, len(cats), endpoint=False).tolist()
    angles_c = angles + [angles[0]]

    fig = plt.figure(figsize=(10.2, 9.4))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.12, 0.88], hspace=0.42)
    ax = fig.add_subplot(gs[0], projection="polar")
    ax_tbl = fig.add_subplot(gs[1])
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    for pt in fleet_points:
        if _on_chart(pt) or _is_highlight(pt):
            continue
        vals = [pt.scores.get(c, 0) for c in cats]
        vals_c = vals + [vals[0]]
        ax.plot(angles_c, vals_c, color="#C8CED8", linewidth=0.45, alpha=0.18, zorder=1)

    compare_handles: list[Line2D] = []
    for pt in fleet_points:
        if not _on_chart(pt):
            continue
        vals = [float(pt.scores.get(c, 0)) for c in cats]
        vals_c = vals + [vals[0]]
        style = _scheme_style(pt.short_name)
        ls = style["ls"] if pt.year_status != "planned" else "--"
        color = style["color"]
        ax.fill(angles_c, vals_c, color=color, alpha=0.12, zorder=2)
        ax.plot(
            angles_c,
            vals_c,
            ls=ls,
            linewidth=1.8,
            color=color,
            marker=style["marker"],
            markersize=4.5,
            alpha=0.92,
            zorder=3,
        )
        compare_handles.append(
            Line2D(
                [0],
                [0],
                color=color,
                lw=1.8,
                ls=ls,
                marker=style["marker"],
                markersize=4,
                label=_chart_project_name(pt.short_name),
            )
        )

    cand_vals = [float(score.ai_review_scores.get(c, 0)) for c in cats]
    cand_c = cand_vals + [cand_vals[0]]
    prop_color = NATURE_COLORS["candidate"]
    ax.fill(angles_c, cand_c, alpha=0.20, color=prop_color, zorder=5)
    ax.plot(
        angles_c,
        cand_c,
        "o-",
        color=prop_color,
        linewidth=3.0,
        markersize=8,
        markerfacecolor=prop_color,
        markeredgecolor="#1a1a1a",
        markeredgewidth=0.55,
        zorder=6,
        label=candidate_label,
    )

    for ang, val in zip(angles, cand_vals):
        r_text = min(float(val) + 7.0, 97.0)
        ax.text(
            ang,
            r_text,
            f"{val:.0f}",
            ha="center",
            va="center",
            fontsize=8,
            fontweight="bold",
            color="#004D40",
            zorder=7,
        )

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.tick_params(axis="x", pad=18)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80])
    ax.set_yticklabels(["20", "40", "60", "80"], fontsize=7, color="#888888")
    ax.grid(color="#DDDDDD", linewidth=0.55, alpha=0.9)
    ax.spines["polar"].set_color("#CCCCCC")
    ax.set_title(
        f"AI Review — {candidate_label} (overall {score.overall_score:.0f})",
        fontsize=10.5,
        fontweight="bold",
        pad=24,
    )
    ax.legend(
        handles=compare_handles,
        loc="upper right",
        bbox_to_anchor=(1.28, 1.12),
        fontsize=7,
        frameon=True,
        fancybox=False,
        edgecolor="#DDDDDD",
        title="Benchmarks",
        title_fontsize=7,
    )

    _radar_score_table(
        ax_tbl,
        candidate_label,
        score.ai_review_scores,
        score.overall_score,
        fleet_points,
        cats,
    )
    fig.text(
        0.5,
        0.02,
        f"Proposed (filled) vs. four benchmarks; scores 0–100. {candidate_label} overall {score.overall_score:.0f}.",
        ha="center",
        fontsize=7,
        color="#666666",
    )
    fig.subplots_adjust(top=0.92, bottom=0.08, right=0.82)
    return _save(fig, out_dir, "fig_score_radar")


def _metric_bar_label(key: str, metrics: dict[str, float | None]) -> str:
    val = metrics.get(key)
    if val is None:
        return "—"
    if key == "capacity_mw":
        return f"{val:.1f} MW"
    if key == "steel_per_mw":
        return f"{val:.0f} t/MW"
    if key == "unit_cost":
        return f"{val:.0f} kCNY/MW"
    if key in ("construction_years", "fatigue_life"):
        return f"{val:.1f} yr"
    return f"{val:.1f}"


def plot_fleet_metrics_bars(
    score: ValidationScore,
    out_dir: Path,
    *,
    validity_table: dict[str, Any] | None = None,
    candidate_label: str = "Proposed",
) -> list[str]:
    """Five-panel validity chart: raw performance index vs AI / regulatory scores."""
    configure_nature_style()
    if not validity_table:
        return []
    cohort: list[dict[str, Any]] = []
    for key in ("commissioned_cohort", "planned_cohort"):
        cohort.extend(validity_table.get(key) or [])
    cand = validity_table.get("candidate")
    if cand:
        cohort.append(cand)
    if len(cohort) < 3:
        return []

    cats = list(DIMENSION_KEYS)
    fig, axes = plt.subplots(2, 3, figsize=(10.5, 6.8))
    axes_list = list(axes.flat)

    for i, dim in enumerate(cats):
        ax = axes_list[i]
        raw_vals = [row.get("ai_metrics", {}).get(dim) for row in cohort]
        sample = [v for v in raw_vals if v is not None]
        xs: list[float] = []
        ai_ys: list[float] = []
        reg_ys: list[float] = []
        names: list[str] = []
        for row in cohort:
            raw = row.get("ai_metrics", {}).get(dim)
            ai_s = (row.get("ai_scores") or {}).get(dim)
            reg_s = (row.get("regulatory_scores") or {}).get(dim)
            if raw is None or ai_s is None or reg_s is None:
                continue
            xs.append(_performance_index(dim, float(raw), sample))
            ai_ys.append(float(ai_s))
            reg_ys.append(float(reg_s))
            names.append(_chart_project_name(str(row.get("name", ""))))

        ax.scatter(xs, ai_ys, s=28, c=NATURE_COLORS["international"], edgecolors="white", linewidths=0.4, zorder=3, label="AI Review")
        ax.scatter(xs, reg_ys, s=28, c=NATURE_COLORS["domestic"], marker="s", edgecolors="white", linewidths=0.4, zorder=3, label="Regulatory")

        if len(xs) >= 3:
            x_grid = np.linspace(min(xs), max(xs), 40)
            ai_trend = _trend_line(np.array(xs), np.array(ai_ys), x_grid)
            reg_trend = _trend_line(np.array(xs), np.array(reg_ys), x_grid)
            if ai_trend is not None:
                ax.plot(x_grid, ai_trend, "--", color=NATURE_COLORS["international"], linewidth=1.2, alpha=0.85, zorder=2)
            if reg_trend is not None:
                ax.plot(x_grid, reg_trend, "--", color=NATURE_COLORS["domestic"], linewidth=1.2, alpha=0.85, zorder=2)

        if cand and cand.get("ai_metrics", {}).get(dim) is not None:
            cr = cand["ai_metrics"][dim]
            c_ai = (cand.get("ai_scores") or {}).get(dim)
            c_reg = (cand.get("regulatory_scores") or {}).get(dim)
            if c_ai is not None and c_reg is not None:
                cx = _performance_index(dim, float(cr), sample)
                ax.scatter([cx], [float(c_ai)], s=90, c=NATURE_COLORS["candidate"], marker="*", edgecolors="black", linewidths=0.5, zorder=5)
                ax.scatter([cx], [float(c_reg)], s=55, c=NATURE_COLORS["candidate"], marker="D", edgecolors="black", linewidths=0.4, zorder=5)

        ax.set_xlim(-5, 105)
        ax.set_ylim(0, 105)
        ax.set_xlabel("Performance index (0–100)", fontsize=6.5)
        ax.set_ylabel("Score", fontsize=6.5)
        ax.set_title(RADAR_SHORT_LABELS.get(dim, dim), fontsize=8, fontweight="bold", loc="left")
        ax.grid(True, color=NATURE_COLORS["grid"], linewidth=0.4, alpha=0.8)
        if i == 0:
            ax.legend(loc="lower right", fontsize=6, frameon=False)

    axes_list[5].axis("off")
    vs = validity_table.get("validity_summary") or {}
    note = (
        f"Fleet n={vs.get('n', len(cohort))}; overall Spearman={vs.get('overall_spearman', '—')}; "
        f"mean |AI−reg|={vs.get('overall_mean_abs_diff', '—')} pts. "
        "Dashed curves: nonlinear trend of scores vs. raw performance index."
    )
    fig.suptitle("AI Review validity — raw metrics vs. scores", fontsize=10, fontweight="bold", y=0.98)
    fig.text(0.5, 0.02, note, ha="center", fontsize=7, color="#555555")
    fig.subplots_adjust(top=0.90, bottom=0.08, hspace=0.42, wspace=0.32)
    return _save(fig, out_dir, "fig_fleet_metrics_bars")


def plot_rule_heatmap(score: ValidationScore, out_dir: Path) -> list[str]:
    configure_nature_style()
    rules = score.rule_results
    if not rules:
        return []
    names = [r.id[:22] for r in rules]
    scores = [r.score_0_100 for r in rules]
    colors = [NATURE_COLORS["candidate"] if r.status == "pass" else "#E64B35" if r.status == "fail" else "#F39B7F" for r in rules]

    fig, ax = plt.subplots(figsize=(7.2, max(3.0, 0.28 * len(rules))))
    y = np.arange(len(rules))
    ax.barh(y, scores, color=colors, height=0.7, edgecolor="white", linewidth=0.3)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=6)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Rule score (0–100)")
    ax.set_title("Rule score breakdown", loc="left", fontweight="bold")
    _style_axis(ax)
    ax.invert_yaxis()
    return _save(fig, out_dir, "fig_rule_heatmap")


def plot_capacity_intensity(score: ValidationScore, out_dir: Path, label: str = "Candidate") -> list[str]:
    configure_nature_style()
    records = [r for r in load_benchmark_records() if r.steel_intensity and r.capacity_mw]
    cand_x = score.metrics.get("target_power_MW")
    cand_y = score.metrics.get("steel_intensity_t_per_MW")

    fig, ax = plt.subplots(figsize=(4.8, 4.0))
    _style_axis(ax)
    ax.grid(True, color=NATURE_COLORS["grid"], linewidth=0.5)
    for r in records:
        ax.scatter(r.capacity_mw, r.steel_intensity, c=NATURE_COLORS[r.region], s=28,
                   edgecolors="white", linewidths=0.5, alpha=0.85)
    ax.scatter([cand_x], [cand_y], s=120, c=NATURE_COLORS["candidate"], marker="*",
               edgecolors="black", linewidths=0.5, zorder=5, label=label)
    ax.axhline(300, color="#999", linestyle=":", linewidth=0.8)
    ax.set_xlabel("Unit capacity (MW)")
    ax.set_ylabel("Steel intensity (t MW$^{-1}$)")
    ax.set_title("Capacity vs. steel intensity", loc="left", fontweight="bold")
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NATURE_COLORS["international"], markersize=5, label="Intl."),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NATURE_COLORS["domestic"], markersize=5, label="China"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=NATURE_COLORS["candidate"], markersize=10, label=label),
    ]
    ax.legend(handles=handles, loc="upper right")
    return _save(fig, out_dir, "fig_capacity_intensity")


def _cell_score(val: Any) -> str:
    if val is None or val == "":
        return "-"
    try:
        return f"{float(val):.1f}"
    except (TypeError, ValueError):
        return str(val)


def _cell_raw(val: Any) -> str:
    if val is None or val == "":
        return "-"
    return str(val)


def _performance_index(key: str, value: float, sample: list[float]) -> float:
    """Map raw metric to 0–100 performance index (higher = better)."""
    nums = [float(v) for v in sample if v is not None]
    if not nums:
        return 50.0
    lo, hi = min(nums), max(nums)
    span = max(hi - lo, 1e-9)
    if key in ("steel_per_mw", "unit_cost", "construction_years"):
        return 100.0 * (hi - float(value)) / span
    return 100.0 * (float(value) - lo) / span


def _trend_line(xs: np.ndarray, ys: np.ndarray, x_grid: np.ndarray) -> np.ndarray | None:
    if len(xs) < 3:
        return None
    deg = 2 if len(xs) >= 4 else 1
    try:
        coef = np.polyfit(xs, ys, deg)
        return np.poly1d(coef)(x_grid)
    except (np.linalg.LinAlgError, ValueError):
        return None


def plot_validity_table(validity: dict[str, Any], out_dir: Path) -> list[str]:
    configure_nature_style()
    ai_cols = validity.get("ai_columns") or []
    reg_cols = validity.get("regulatory_columns") or []
    if not ai_cols or not reg_cols:
        return []

    raw_headers = ["MW", "t/MW", "kCNY/MW", "yr", "yr"]
    header = ["Project / turbine", *raw_headers]
    header.extend([DIMENSION_LABELS_EN.get(c["key"], c.get("label", c["key"])) for c in ai_cols])
    header.extend(
        [f"{DIMENSION_LABELS_EN.get(c['key'], c.get('label', c['key']))} (reg.)" for c in reg_cols]
    )

    def build_rows(cohort: list[dict[str, Any]]) -> list[list[str]]:
        rows: list[list[str]] = []
        for item in cohort:
            ai = item.get("ai_scores") or {}
            reg = item.get("regulatory_scores") or {}
            raw = item.get("raw_metrics") or {}
            row = [_chart_project_name(str(item.get("name", "")))]
            row.extend(_cell_raw(raw.get(c["key"])) for c in ai_cols)
            row.extend(_cell_score(ai.get(c["key"])) for c in ai_cols)
            row.extend(_cell_score(reg.get(c["key"])) for c in reg_cols)
            rows.append(row)
        return rows

    sections = [
        ("Commissioned fleet", validity.get("commissioned_cohort") or []),
        ("Planned projects", validity.get("planned_cohort") or []),
    ]
    body: list[list[str]] = []
    section_row_indices: set[int] = set()
    for title, cohort in sections:
        if not cohort:
            continue
        section_row_indices.add(len(body))
        body.append([title] + [""] * (len(header) - 1))
        body.extend(build_rows(cohort))

    cand = validity.get("candidate")
    if cand:
        section_row_indices.add(len(body))
        body.append(["Proposed (candidate)"] + [""] * (len(header) - 1))
        body.extend(build_rows([cand]))

    if not body:
        return []

    ncols = len(header)
    col_widths = [0.14] + [0.078] * (ncols - 1)
    fig_w = max(13.5, 0.95 * ncols)
    fig_h = max(4.2, 0.38 * len(body) + 1.8)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")

    sub = (
        "Raw metrics (left, '-' if missing); AI Review scores; regulatory scores (same five metrics). "
        "Scores shown only when raw data exists."
    )
    ax.set_title(
        validity.get("title_en")
        or "Table 1 | AI Review vs. regulatory scores (same five metrics)",
        loc="left",
        fontsize=10,
        fontweight="bold",
        pad=14,
    )
    fig.text(0.02, 0.94, sub, fontsize=7, color="#444444")

    table = ax.table(
        cellText=body,
        colLabels=header,
        loc="center",
        cellLoc="center",
        colWidths=col_widths,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(6.8)
    table.scale(1.0, 1.55)

    n_ai = len(ai_cols)
    n_raw = len(raw_headers)
    for (r, c), cell in table.get_celld().items():
        if r == 0:
            if c == 0:
                cell.set_facecolor("#F3F4F6")
            elif 0 < c <= n_raw:
                cell.set_facecolor("#F0F4F0")
            elif c <= n_raw + n_ai:
                cell.set_facecolor("#E8EEF7")
            else:
                cell.set_facecolor("#F7ECE8")
            cell.set_text_props(weight="bold", fontsize=6.5)
            continue
        if (r - 1) in section_row_indices:
            cell.set_facecolor("#EEF2FF")
            if c == 0:
                cell.set_text_props(weight="bold", ha="left")
            continue
        if c == 0:
            cell.set_text_props(ha="left", fontsize=6.8)
        elif 0 < c <= n_raw:
            cell.set_facecolor("#FAFFFA")
        elif n_raw < c <= n_raw + n_ai:
            cell.set_facecolor("#FAFCFF")
        elif c > n_raw + n_ai:
            cell.set_facecolor("#FFFAF8")

    note = validity.get("note_en") or validity.get("note") or ""
    fig.text(0.02, 0.02, note[:280] + ("…" if len(note) > 280 else ""), fontsize=6.5, color="#555555")
    fig.subplots_adjust(top=0.88, bottom=0.08)
    return _save(fig, out_dir, "fig_ai_review_validity")


def generate_all_plots(
    score: ValidationScore,
    out_dir: Path,
    candidate_label: str = "Proposed",
    *,
    fleet_points: list[FleetReviewPoint] | None = None,
    validity_table: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    fleet_points = fleet_points or score_fleet_benchmarks()
    artifacts: dict[str, list[str]] = {}
    chart_label = _chart_label(candidate_label)

    bench_artifacts = plot_all_benchmark_positions(score, out_dir, chart_label)
    artifacts.update(bench_artifacts)

    plotters = [
        lambda: plot_score_radar(
            score,
            out_dir,
            fleet_points=fleet_points,
            candidate_label=chart_label,
        ),
        lambda: plot_fleet_metrics_bars(
            score,
            out_dir,
            validity_table=validity_table,
            candidate_label=chart_label,
        ),
        lambda: plot_rule_heatmap(score, out_dir),
        lambda: plot_capacity_intensity(score, out_dir, chart_label),
    ]
    if validity_table:
        plotters.append(lambda: plot_validity_table(validity_table, out_dir))
    for fn in plotters:
        paths = fn()
        if paths:
            stem = Path(paths[0]).stem
            artifacts[stem] = paths
    return artifacts
