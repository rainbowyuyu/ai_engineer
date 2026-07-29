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
from matplotlib.patches import Rectangle

from backend.validation.ai_review import DIMENSION_KEYS
from backend.validation.benchmark_loader import BenchmarkRecord, load_benchmark_records
from backend.validation.fleet_scoring import FleetReviewPoint, score_fleet_benchmarks
from backend.validation.scorer import ValidationScore

NATURE_COLORS = {
    "international": "#3C5488",
    "domestic": "#E64B35",
    "candidate": "#00A087",
    "trend": "#8491B4",
    "grid": "#E8ECF0",
    "text": "#1A1A1A",
    "muted": "#5A5A5A",
}

# Nature-style type scale (pt) — print / SI panel readable
NATURE_TYPE = {
    "base": 13.0,
    "title": 16.0,
    "subtitle": 13.5,
    "axis": 13.0,
    "tick": 12.0,
    "legend": 12.0,
    "legend_title": 12.5,
    "table": 12.0,
    "table_header": 11.5,
    "note": 11.0,
    "radar_spoke": 14.0,
    "radar_ring": 12.0,
    "center": 13.0,
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
    "三峡引领": "TG Yinling",
    "三峡领航": "TG Linghang",
    "海装扶瑶": "HZ Fuyao",
    "海油观澜": "HY Guanlan",
    "明阳天成": "Mingyang TC",
    "万宁一期": "Wanning Ph1",
    "GHN": "GHN Gongxiang",
    "gongxiang": "GHN Gongxiang",
    "龙源南日岛": "Longyuan Nanri",
    "福岛": "Fukushima",
    "Fukushima": "Fukushima",
    "WindFloat Atlantic": "WF Atlantic",
    "WindFloat": "WindFloat",
    "Kincardine": "Kincardine Ph2",
}

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
        "target_label": "2500 (10$^{4}$ CNY/MW, design target)",
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
        "target_label": "2.8 yr design target",
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
    "Mingyang": {"color": "#91D1C2", "marker": "h", "ls": "-"},
    "万宁一期": {"color": "#7E6148", "marker": "X", "ls": "--"},
    "Hywind Scotland": {"color": "#B09C85", "marker": "8", "ls": "-"},
    "WindFloat Atlantic": {"color": "#76B7B2", "marker": "o", "ls": "-"},
    "WindFloat": {"color": "#9D7660", "marker": "^", "ls": "-"},
    "Kincardine Ph2": {"color": "#E15759", "marker": "P", "ls": "-"},
    "GHN": {"color": "#59A14F", "marker": "d", "ls": "-"},
    "gongxiang": {"color": "#59A14F", "marker": "d", "ls": "-"},
    "Fukushima": {"color": "#B07AA1", "marker": "*", "ls": "--"},
}


def _scheme_style(short_name: str) -> dict[str, str]:
    # Match longer / more specific keys first (e.g. WindFloat Atlantic before WindFloat).
    for key in sorted(FLEET_SCHEME_STYLE, key=len, reverse=True):
        if key in short_name:
            return FLEET_SCHEME_STYLE[key]
    return {"color": "#8491B4", "marker": "o", "ls": "--"}


def _radar_fleet_order(fleet_points: list[FleetReviewPoint]) -> list[FleetReviewPoint]:
    return sorted(fleet_points, key=lambda p: (-p.overall, p.short_name))


def _style_nature_radar(ax: plt.Axes, angles: list[float], labels: list[str]) -> None:
    """Nature-style polar grid: gray rings, axis-end dots, outer metric labels."""
    T = NATURE_TYPE
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels([])
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=T["radar_spoke"], color=NATURE_COLORS["text"], fontweight="600")
    ax.tick_params(axis="x", pad=30)
    ax.grid(color="#C8C8C8", linewidth=0.6, alpha=0.85, linestyle="-")
    ax.spines["polar"].set_visible(False)
    for ang in angles:
        ax.plot([ang, ang], [0, 100], color="#C8C8C8", linewidth=0.5, alpha=0.75, zorder=0)
        ax.plot(ang, 100, "o", color="#1a1a1a", markersize=3.8, zorder=8, clip_on=False)
    ax.text(
        0.5,
        0.5,
        "5\nmetrics",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=T["center"],
        fontweight="bold",
        color=NATURE_COLORS["text"],
        zorder=9,
        linespacing=1.05,
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
    T = NATURE_TYPE
    handles = [
        Line2D([0], [0], color=c, lw=2.4, marker="s", markersize=0, label=label)
        for label, c in entries
    ]
    leg = ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(-0.18, 1.16),
        fontsize=T["legend"],
        frameon=False,
        handlelength=0,
        handletextpad=0,
        borderaxespad=0,
        labelspacing=0.72,
    )
    for text, (_, color) in zip(leg.get_texts(), entries):
        text.set_bbox(
            {
                "boxstyle": "square,pad=0.42",
                "edgecolor": color,
                "facecolor": "white",
                "linewidth": 1.5,
                "alpha": 0.97,
            }
        )
        text.set_fontsize(T["legend"])
        text.set_color(NATURE_COLORS["text"])


def _score_cell(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{float(val):.0f}"


def _radar_score_table(
    ax_tbl: plt.Axes,
    fleet_points: list[FleetReviewPoint],
    cats: list[str],
) -> None:
    """Bottom panel: full fleet five-dimension scores."""
    T = NATURE_TYPE
    ax_tbl.axis("off")
    dim_headers = ["Cap.", "Steel", "Cost", "Sched.", "Life"]
    header = ["", "Project", "Overall", *dim_headers]
    rows: list[list[str]] = []

    for pt in _radar_fleet_order(fleet_points):
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
        colWidths=[0.034, 0.26, 0.078, 0.078, 0.078, 0.078, 0.078, 0.078],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(T["table"])
    table.scale(1.0, 1.95)

    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#D8DEE6")
        cell.set_linewidth(0.45)
        if r == 0:
            cell.set_facecolor("#EEF2F7")
            cell.set_text_props(fontweight="bold", fontsize=T["table_header"], color=NATURE_COLORS["text"])
            continue
        if c == 0 and r > 0:
            color = rows[r - 1][0]
            if color:
                cell.set_facecolor(color)
            cell.get_text().set_text("")
        elif c == 1:
            cell.set_text_props(ha="left", fontsize=T["table"], color=NATURE_COLORS["text"])
            cell.PAD = 0.06
        else:
            cell.set_text_props(fontsize=T["table"], color=NATURE_COLORS["text"])


def configure_nature_style() -> None:
    import matplotlib.font_manager as fm

    preferred = ["Arial", "Helvetica", "DejaVu Sans", "Microsoft YaHei", "SimHei"]
    available = {f.name for f in fm.fontManager.ttflist}
    font_family = next((f for f in preferred if f in available), "DejaVu Sans")
    T = NATURE_TYPE
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font_family, "Arial", "DejaVu Sans"],
            "font.size": T["base"],
            "axes.labelsize": T["axis"],
            "axes.titlesize": T["subtitle"],
            "axes.linewidth": 0.7,
            "axes.labelcolor": NATURE_COLORS["text"],
            "axes.titlecolor": NATURE_COLORS["text"],
            "xtick.labelsize": T["tick"],
            "ytick.labelsize": T["tick"],
            "legend.fontsize": T["legend"],
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.18,
            "pdf.fonttype": 42,
            "axes.unicode_minus": False,
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
    for zh, en in sorted(PROJECT_NAME_EN.items(), key=lambda kv: len(kv[0]), reverse=True):
        if zh in name or name == zh:
            return en
    return name if len(name) <= 22 else f"{name[:20]}…"


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


def plot_benchmark_metric(
    score: ValidationScore,
    out_dir: Path,
    config: dict[str, Any],
    label: str = "Proposed",
) -> list[str]:
    """Fleet-order benchmark chart with quadratic trend curve vs. commissioning year."""
    _ = score
    _ = label
    configure_nature_style()
    attr = str(config["record_attr"])
    records = [r for r in load_benchmark_records() if _record_metric_value(r, attr) is not None]
    records.sort(key=lambda r: (r.sort_year, r.short_name))
    if len(records) < 2:
        return []

    x = np.arange(len(records))
    y = np.array([_record_metric_value(r, attr) for r in records], dtype=float)
    tick_labels = [_chart_year_label(r) for r in records]

    T = NATURE_TYPE
    fig, ax = plt.subplots(figsize=(10.4, 5.0))
    _style_axis(ax)

    for region in ("international", "domestic"):
        idx = [i for i, r in enumerate(records) if r.region == region]
        if idx:
            ax.plot(
                x[idx],
                y[idx],
                "o-",
                color=NATURE_COLORS[region],
                markersize=5.5,
                markerfacecolor="white",
                markeredgewidth=1.1,
                linewidth=1.25,
                label="International" if region == "international" else "China",
            )

    ax.plot(x, y, color="#ccc", linestyle="--", linewidth=0.7, zorder=0)

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
            linewidth=1.8,
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
            0.012,
            f"* Planned project. Nonlinear fit vs. year; {note}.",
            fontsize=T["note"],
            color=NATURE_COLORS["muted"],
        )

    target = config.get("target")
    if target is not None:
        ax.axhline(
            float(target),
            color="#999",
            linestyle=":",
            linewidth=0.9,
            label=str(config.get("target_label") or "target"),
        )

    ax.set_xticks(x)
    ax.set_xticklabels(tick_labels, rotation=28, ha="right", fontsize=T["tick"])

    ax.set_xlabel("Commissioning / planning year (fleet order)", fontsize=T["axis"])
    ax.set_ylabel(str(config["ylabel"]), fontsize=T["axis"])
    ax.set_title(str(config["title"]), loc="left", fontweight="bold", fontsize=T["subtitle"], pad=10)
    ax.legend(loc="upper right", fontsize=T["legend"], frameon=False)
    fig.subplots_adjust(bottom=0.22, left=0.10, right=0.98, top=0.90)
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
    T = NATURE_TYPE
    _ = score  # fleet-only chart; candidate scores shown in validity table instead
    _ = candidate_label
    cats = list(DIMENSION_KEYS)
    labels = [RADAR_SHORT_LABELS.get(c, c) for c in cats]
    fleet_points = fleet_points or score_fleet_benchmarks()
    if not fleet_points:
        return []
    angles = np.linspace(0, 2 * np.pi, len(cats), endpoint=False).tolist()
    angles_c = angles + [angles[0]]

    fig = plt.figure(figsize=(14.0, 13.4))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.15, 1.05], hspace=0.42)
    ax = fig.add_subplot(gs[0], projection="polar")
    ax_tbl = fig.add_subplot(gs[1])
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    compare_handles: list[Line2D] = []
    for pt in _radar_fleet_order(fleet_points):
        vals = [float(pt.scores.get(c, 0) or 0) for c in cats]
        vals_c = vals + [vals[0]]
        style = _scheme_style(pt.short_name)
        ls = "--" if pt.year_status == "planned" else style["ls"]
        color = style["color"]
        ax.fill(angles_c, vals_c, color=color, alpha=0.08, zorder=2)
        ax.plot(
            angles_c,
            vals_c,
            ls=ls,
            linewidth=1.7,
            color=color,
            marker=style["marker"],
            markersize=5.0,
            alpha=0.92,
            zorder=3,
        )
        compare_handles.append(
            Line2D(
                [0],
                [0],
                color=color,
                lw=1.7,
                ls=ls,
                marker=style["marker"],
                markersize=4.5,
                label=_chart_project_name(pt.short_name),
            )
        )

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=T["radar_spoke"], fontweight="600", color=NATURE_COLORS["text"])
    ax.tick_params(axis="x", pad=36)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80])
    ax.set_yticklabels(["20", "40", "60", "80"], fontsize=T["radar_ring"], color=NATURE_COLORS["muted"])
    ax.grid(color="#D0D6DE", linewidth=0.65, alpha=0.9)
    ax.spines["polar"].set_color("#C5CCD6")
    ax.set_title(
        "AI Review — fleet five-metric comparison",
        fontsize=T["title"],
        fontweight="bold",
        pad=28,
        color=NATURE_COLORS["text"],
    )
    ax.legend(
        handles=compare_handles,
        loc="upper left",
        bbox_to_anchor=(1.04, 1.08),
        fontsize=T["legend"],
        frameon=True,
        fancybox=False,
        edgecolor="#D8DEE6",
        facecolor="white",
        ncol=2,
        title="Fleet (n={})".format(len(fleet_points)),
        title_fontsize=T["legend_title"],
        columnspacing=1.0,
        handletextpad=0.5,
        labelspacing=0.55,
        borderpad=0.6,
    )

    _radar_score_table(ax_tbl, fleet_points, cats)
    fig.text(
        0.5,
        0.012,
        "Full fleet overlay on five AI Review metrics (0–100). Dashed = planned projects.",
        ha="center",
        fontsize=T["note"],
        color=NATURE_COLORS["muted"],
    )
    fig.subplots_adjust(top=0.93, bottom=0.055, left=0.04, right=0.76)
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
    T = NATURE_TYPE
    fig, axes = plt.subplots(2, 3, figsize=(12.4, 8.0))
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

        ax.scatter(xs, ai_ys, s=42, c=NATURE_COLORS["international"], edgecolors="white", linewidths=0.5, zorder=3, label="AI Review")
        ax.scatter(xs, reg_ys, s=42, c=NATURE_COLORS["domestic"], marker="s", edgecolors="white", linewidths=0.5, zorder=3, label="Regulatory")

        if len(xs) >= 3:
            x_grid = np.linspace(min(xs), max(xs), 40)
            ai_trend = _trend_line(np.array(xs), np.array(ai_ys), x_grid)
            reg_trend = _trend_line(np.array(xs), np.array(reg_ys), x_grid)
            if ai_trend is not None:
                ax.plot(x_grid, ai_trend, "--", color=NATURE_COLORS["international"], linewidth=1.4, alpha=0.85, zorder=2)
            if reg_trend is not None:
                ax.plot(x_grid, reg_trend, "--", color=NATURE_COLORS["domestic"], linewidth=1.4, alpha=0.85, zorder=2)

        if cand and cand.get("ai_metrics", {}).get(dim) is not None:
            cr = cand["ai_metrics"][dim]
            c_ai = (cand.get("ai_scores") or {}).get(dim)
            c_reg = (cand.get("regulatory_scores") or {}).get(dim)
            if c_ai is not None and c_reg is not None:
                cx = _performance_index(dim, float(cr), sample)
                ax.scatter([cx], [float(c_ai)], s=110, c=NATURE_COLORS["candidate"], marker="*", edgecolors="black", linewidths=0.55, zorder=5)
                ax.scatter([cx], [float(c_reg)], s=70, c=NATURE_COLORS["candidate"], marker="D", edgecolors="black", linewidths=0.45, zorder=5)

        ax.set_xlim(-5, 105)
        ax.set_ylim(0, 105)
        ax.set_xlabel("Performance index (0–100)", fontsize=T["tick"])
        ax.set_ylabel("Score", fontsize=T["tick"])
        ax.tick_params(axis="both", labelsize=T["tick"])
        ax.set_title(RADAR_SHORT_LABELS.get(dim, dim), fontsize=T["subtitle"], fontweight="bold", loc="left", pad=8)
        ax.grid(True, color=NATURE_COLORS["grid"], linewidth=0.45, alpha=0.85)
        if i == 0:
            ax.legend(loc="lower right", fontsize=T["legend"], frameon=False, labelspacing=0.4)

    axes_list[5].axis("off")
    vs = validity_table.get("validity_summary") or {}
    note = (
        f"Fleet n={vs.get('n', len(cohort))}; overall Spearman={vs.get('overall_spearman', '—')}; "
        f"mean |AI−reg|={vs.get('overall_mean_abs_diff', '—')} pts; "
        f"high agreement={vs.get('high_agreement_pct', '—')}%. "
        "Dashed curves: nonlinear trend of scores vs. raw performance index."
    )
    fig.suptitle("AI Review validity — raw metrics vs. scores", fontsize=T["title"], fontweight="bold", y=0.985)
    fig.text(0.5, 0.018, note, ha="center", fontsize=T["note"], color=NATURE_COLORS["muted"], wrap=True)
    fig.subplots_adjust(top=0.91, bottom=0.10, left=0.07, right=0.98, hspace=0.48, wspace=0.36)
    return _save(fig, out_dir, "fig_fleet_metrics_bars")


def plot_rule_heatmap(score: ValidationScore, out_dir: Path) -> list[str]:
    configure_nature_style()
    T = NATURE_TYPE
    rules = score.rule_results
    if not rules:
        return []
    names = [r.id[:28] for r in rules]
    scores = [r.score_0_100 for r in rules]
    colors = [NATURE_COLORS["candidate"] if r.status == "pass" else "#E64B35" if r.status == "fail" else "#F39B7F" for r in rules]

    fig, ax = plt.subplots(figsize=(8.6, max(3.6, 0.36 * len(rules))))
    y = np.arange(len(rules))
    ax.barh(y, scores, color=colors, height=0.72, edgecolor="white", linewidth=0.35)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=T["tick"])
    ax.set_xlim(0, 105)
    ax.set_xlabel("Rule score (0–100)", fontsize=T["axis"])
    ax.set_title("Rule score breakdown", loc="left", fontweight="bold", fontsize=T["subtitle"], pad=10)
    ax.tick_params(axis="x", labelsize=T["tick"])
    _style_axis(ax)
    ax.invert_yaxis()
    fig.subplots_adjust(left=0.28, right=0.96, top=0.90, bottom=0.12)
    return _save(fig, out_dir, "fig_rule_heatmap")


def plot_capacity_intensity(score: ValidationScore, out_dir: Path, label: str = "Candidate") -> list[str]:
    configure_nature_style()
    T = NATURE_TYPE
    _ = score
    _ = label
    records = [r for r in load_benchmark_records() if r.steel_intensity and r.capacity_mw]

    fig, ax = plt.subplots(figsize=(5.8, 4.8))
    _style_axis(ax)
    ax.grid(True, color=NATURE_COLORS["grid"], linewidth=0.5)
    for r in records:
        ax.scatter(r.capacity_mw, r.steel_intensity, c=NATURE_COLORS[r.region], s=40,
                   edgecolors="white", linewidths=0.55, alpha=0.88)
    ax.axhline(300, color="#999", linestyle=":", linewidth=0.9)
    ax.set_xlabel("Unit capacity (MW)", fontsize=T["axis"])
    ax.set_ylabel("Steel intensity (t MW$^{-1}$)", fontsize=T["axis"])
    ax.set_title("Capacity vs. steel intensity", loc="left", fontweight="bold", fontsize=T["subtitle"], pad=10)
    ax.tick_params(axis="both", labelsize=T["tick"])
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NATURE_COLORS["international"], markersize=7, label="Intl."),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NATURE_COLORS["domestic"], markersize=7, label="China"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=T["legend"], frameon=False)
    fig.subplots_adjust(left=0.14, right=0.96, top=0.90, bottom=0.14)
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

    raw_headers = ["MW", "t/MW", "kCNY/MW", "Constr.", "Life"]
    # Compact headers so enlarged type stays legible without collision
    short_ai = {
        "capacity_mw": "Cap.",
        "steel_per_mw": "Steel",
        "unit_cost": "Cost",
        "construction_years": "Sched.",
        "fatigue_life": "Life",
    }
    header = ["Project", *raw_headers]
    header.extend([short_ai.get(c["key"], c.get("label", c["key"])[:6]) for c in ai_cols])
    header.extend([f"{short_ai.get(c['key'], 'M')}.R" for c in reg_cols])

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
    T = NATURE_TYPE
    name_w = 0.16
    other_w = (0.84 / max(ncols - 1, 1))
    col_widths = [name_w] + [other_w] * (ncols - 1)
    fig_w = max(15.5, 0.98 * ncols)
    fig_h = max(5.8, 0.62 * len(body) + 2.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")

    title = (
        validity.get("title_en")
        or "Table 1 | AI Review vs. regulatory scores (same five metrics)"
    )
    sub = (
        "Raw (MW…Life) · AI Review (Cap.…Life) · Regulatory (.R). "
        "Scores shown only when raw data exists."
    )
    fig.text(0.02, 0.97, title, fontsize=T["title"], fontweight="bold", color=NATURE_COLORS["text"], va="top")
    fig.text(0.02, 0.935, sub, fontsize=T["note"], color=NATURE_COLORS["muted"], va="top")

    table = ax.table(
        cellText=body,
        colLabels=header,
        loc="upper center",
        cellLoc="center",
        colWidths=col_widths,
        bbox=[0.01, 0.11, 0.98, 0.76],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(T["table"])
    table.scale(1.0, 2.15)

    n_ai = len(ai_cols)
    n_raw = len(raw_headers)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#D8DEE6")
        cell.set_linewidth(0.4)
        if r == 0:
            if c == 0:
                cell.set_facecolor("#F3F4F6")
            elif 0 < c <= n_raw:
                cell.set_facecolor("#F0F4F0")
            elif c <= n_raw + n_ai:
                cell.set_facecolor("#E8EEF7")
            else:
                cell.set_facecolor("#F7ECE8")
            cell.set_text_props(weight="bold", fontsize=T["table_header"], color=NATURE_COLORS["text"])
            continue
        if (r - 1) in section_row_indices:
            cell.set_facecolor("#EEF2FF")
            if c == 0:
                cell.set_text_props(weight="bold", ha="left", fontsize=T["table"])
            continue
        if c == 0:
            cell.set_text_props(ha="left", fontsize=T["table"], color=NATURE_COLORS["text"])
            cell.PAD = 0.06
        elif 0 < c <= n_raw:
            cell.set_facecolor("#FAFFFA")
            cell.set_text_props(fontsize=T["table"])
        elif n_raw < c <= n_raw + n_ai:
            cell.set_facecolor("#FAFCFF")
            cell.set_text_props(fontsize=T["table"])
        elif c > n_raw + n_ai:
            cell.set_facecolor("#FFFAF8")
            cell.set_text_props(fontsize=T["table"])

    note = validity.get("note_en") or validity.get("note") or ""
    note_show = note[:420] + ("…" if len(note) > 420 else "")
    fig.text(0.02, 0.035, note_show, fontsize=T["note"], color=NATURE_COLORS["muted"], va="bottom")
    fig.subplots_adjust(top=1.0, bottom=0.0, left=0.0, right=1.0)
    return _save(fig, out_dir, "fig_ai_review_validity")


STATIC_TARGET_LABELS = {
    "steel_mass_t": "Steel mass (t)",
    "max_uc_static": "Max UC (static)",
    "pitch_proxy_deg": "Pitch (deg)",
    "compliance_static": "Compliance proxy",
}

PHYSICS_PENALTY_LABELS = {
    "mass": "Mass anchor",
    "pitch": "Pitch limit",
    "mono": "Monotonicity",
    "bound": "Bounds",
}

ECON_LABELS = {
    "unit_cost_cny_per_MW": "Unit cost (kCNY/MW)",
    "construction_years": "Construction (yr)",
    "fatigue_life_years": "Fatigue life (yr)",
}


def _plot_pinn_workflow_schematic(ax, *, active: bool) -> None:
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    boxes = [
        (0.4, 3.8, "Geometry\nJSON"),
        (2.6, 3.8, "Feature\nextract"),
        (4.8, 3.8, "MLP\nsurrogate"),
        (7.0, 3.8, "Physics\nloss check"),
        (8.8, 3.8, "Blend\nα·PINN+(1−α)·H"),
    ]
    color = NATURE_COLORS["candidate"] if active else NATURE_COLORS["trend"]
    for i, (x, y, txt) in enumerate(boxes):
        ax.add_patch(Rectangle((x, y), 1.5, 1.2, fc="#f8fafc", ec=color, lw=1.4, zorder=2))
        ax.text(x + 0.75, y + 0.6, txt, ha="center", va="center", fontsize=NATURE_TYPE["tick"], color=NATURE_COLORS["text"])
        if i < len(boxes) - 1:
            ax.annotate(
                "",
                xy=(boxes[i + 1][0] - 0.08, y + 0.6),
                xytext=(x + 1.58, y + 0.6),
                arrowprops=dict(arrowstyle="->", color="#94a3b8", lw=1.1),
            )
    ax.text(
        5.0,
        2.2,
        "Phase 1: static PINN proxy (CalculiX / analytical labels)\nDoes not replace Zwind time-domain or CCS review",
        ha="center",
        va="top",
        fontsize=NATURE_TYPE["note"],
        color="#64748b",
    )
    title = "Physics-informed neural surrogate — active" if active else "Physics-informed neural surrogate — not engaged"
    ax.set_title(title, fontsize=NATURE_TYPE["subtitle"], fontweight="600", color=NATURE_COLORS["text"], pad=10)


def plot_surrogate_pinn(score: ValidationScore, out_dir: Path) -> list[str]:
    """Visualize PINN static predictions, physics residuals, and economics blend."""
    ctx = score.surrogate_context or {}
    enabled = bool(ctx.get("enabled"))
    static = ctx.get("static_predictions") or {}
    penalties = ctx.get("physics_penalties") or {}
    alpha = float(ctx.get("blend_alpha") or 0.0)
    phys_res = float(ctx.get("physics_residual") or 0.0)
    requested = bool(ctx.get("requested"))

    fig = plt.figure(figsize=(12.5, 8.5))
    gs = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.32)

    ax_flow = fig.add_subplot(gs[0, 0])
    _plot_pinn_workflow_schematic(ax_flow, active=enabled)

    ax_static = fig.add_subplot(gs[0, 1])
    if static:
        keys = [k for k in STATIC_TARGET_LABELS if k in static]
        if not keys:
            keys = list(static.keys())
        labels = [STATIC_TARGET_LABELS.get(k, k) for k in keys]
        vals = [float(static[k]) for k in keys]
        ypos = np.arange(len(keys))
        bars = ax_static.barh(ypos, vals, color=NATURE_COLORS["candidate"], height=0.55, alpha=0.88)
        ax_static.set_yticks(ypos)
        ax_static.set_yticklabels(labels, fontsize=9)
        ax_static.set_xlabel("Predicted value")
        ax_static.set_title("Static channel outputs", fontsize=11, fontweight="600")
        if "max_uc_static" in static:
            ax_static.axvline(1.0, color="#ef4444", ls="--", lw=1, alpha=0.75)
        if "pitch_proxy_deg" in static:
            ax_static.axvline(5.0, color="#f59e0b", ls=":", lw=1, alpha=0.75)
        for bar, v in zip(bars, vals):
            ax_static.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" {v:.2g}", va="center", fontsize=8)
    else:
        ax_static.text(
            0.5,
            0.55,
            "Enable surrogate in AI Review\nto populate static predictions",
            ha="center",
            va="center",
            transform=ax_static.transAxes,
            fontsize=10,
            color="#64748b",
        )
        ax_static.set_axis_off()

    ax_phys = fig.add_subplot(gs[1, 0])
    if penalties:
        pkeys = [k for k in PHYSICS_PENALTY_LABELS if k in penalties]
        plabels = [PHYSICS_PENALTY_LABELS[k] for k in pkeys]
        pvals = [float(penalties[k]) for k in pkeys]
        xpos = np.arange(len(pkeys))
        ax_phys.bar(xpos, pvals, color=NATURE_COLORS["international"], width=0.62, alpha=0.9)
        ax_phys.set_xticks(xpos)
        ax_phys.set_xticklabels(plabels, rotation=18, ha="right", fontsize=8)
        ax_phys.set_ylabel("Penalty term")
        ax_phys.set_title(f"Physics residual terms (Σ={phys_res:.3f})", fontsize=11, fontweight="600")
        ax_phys.axhline(0.35, color="#ef4444", ls="--", lw=1, label="fallback threshold")
        ax_phys.legend(fontsize=7, frameon=False, loc="upper right")
    else:
        ax_phys.text(
            0.5,
            0.5,
            "Physics penalties appear\nwhen surrogate is active",
            ha="center",
            va="center",
            transform=ax_phys.transAxes,
            fontsize=10,
            color="#64748b",
        )
        ax_phys.set_axis_off()

    ax_blend = fig.add_subplot(gs[1, 1])
    h_der = ctx.get("heuristic_derived") or {}
    s_der = ctx.get("derived") or {}
    b_der = ctx.get("blended_derived") or {}
    econ_keys = list(ECON_LABELS.keys())
    if enabled and h_der and s_der:
        xpos = np.arange(len(econ_keys))
        width = 0.26
        hvals = [float(h_der.get(k) or 0) for k in econ_keys]
        svals = [float(s_der.get(k) or 0) for k in econ_keys]
        bvals = [float(b_der.get(k) or 0) for k in econ_keys]
        ax_blend.bar(xpos - width, hvals, width, label="Heuristic", color=NATURE_COLORS["trend"], alpha=0.85)
        ax_blend.bar(xpos, svals, width, label="PINN", color=NATURE_COLORS["candidate"], alpha=0.9)
        ax_blend.bar(xpos + width, bvals, width, label=f"Blended (α={alpha:.2f})", color=NATURE_COLORS["international"], alpha=0.9)
        ax_blend.set_xticks(xpos)
        ax_blend.set_xticklabels([ECON_LABELS[k].split(" (")[0] for k in econ_keys], fontsize=8)
        ax_blend.set_title("Economics: heuristic vs PINN vs blend", fontsize=11, fontweight="600")
        ax_blend.legend(fontsize=7, frameon=False, loc="upper right")
    elif enabled:
        ax_blend.text(
            0.5,
            0.62,
            f"Blend weight α = {alpha:.2f}\nsource = {ctx.get('source', '—')}",
            ha="center",
            va="center",
            transform=ax_blend.transAxes,
            fontsize=10,
            color=NATURE_COLORS["text"],
        )
        ax_blend.set_axis_off()
    else:
        msg = "Surrogate not requested" if not requested else "Surrogate requested but inactive (see assumptions)"
        ax_blend.text(
            0.5,
            0.5,
            msg,
            ha="center",
            va="center",
            transform=ax_blend.transAxes,
            fontsize=10,
            color="#64748b",
        )
        ax_blend.set_axis_off()

    fig.suptitle(
        "Physics-informed neural surrogate (PINN) · AI Review assist",
        fontsize=13,
        fontweight="700",
        color=NATURE_COLORS["text"],
        y=0.98,
    )
    fig.subplots_adjust(top=0.91, bottom=0.08, left=0.08, right=0.97)
    return _save(fig, out_dir, "fig_surrogate_pinn")


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
    plotters.append(lambda: plot_surrogate_pinn(score, out_dir))
    for fn in plotters:
        paths = fn()
        if paths:
            stem = Path(paths[0]).stem
            artifacts[stem] = paths
    return artifacts
