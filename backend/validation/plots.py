"""Nature-style validation figures."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from backend.validation.benchmark_loader import load_benchmark_records
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


def configure_nature_style() -> None:
    import matplotlib.font_manager as fm

    preferred = ["Microsoft YaHei", "SimHei", "Arial", "Helvetica", "DejaVu Sans"]
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


def plot_benchmark_position(score: ValidationScore, out_dir: Path, label: str = "Candidate") -> list[str]:
    configure_nature_style()
    records = [r for r in load_benchmark_records() if r.steel_intensity is not None]
    records.sort(key=lambda r: (r.sort_year, r.short_name))
    x = np.arange(len(records))
    y = np.array([r.steel_intensity for r in records])
    cand_y = score.metrics.get("steel_intensity_t_per_MW")

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    _style_axis(ax)
    for region in ("international", "domestic"):
        idx = [i for i, r in enumerate(records) if r.region == region]
        if idx:
            ax.plot(
                x[idx], y[idx], "o-", color=NATURE_COLORS[region], markersize=4,
                markerfacecolor="white", markeredgewidth=0.9, linewidth=1.0,
                label="International" if region == "international" else "China",
            )
    ax.axhline(300, color="#999", linestyle=":", linewidth=0.8, label="300 t/MW target")
    ax.plot(x, y, color="#ccc", linestyle="--", linewidth=0.6, zorder=0)
    ax.scatter([len(records)], [cand_y], s=80, c=NATURE_COLORS["candidate"], marker="*",
               edgecolors="black", linewidths=0.5, zorder=5, label=label)
    ax.annotate(f"{label}\n{cand_y:.0f} t/MW", (len(records), cand_y),
                textcoords="offset points", xytext=(6, 6), fontsize=7, color=NATURE_COLORS["candidate"])
    ax.set_xticks(x)
    ax.set_xticklabels([r.year_label for r in records], rotation=0)
    ax.set_xlabel("Commissioning / planning year (fleet order)")
    ax.set_ylabel("Steel intensity (t MW$^{-1}$)")
    ax.set_title("Benchmark position — steel intensity", loc="left", fontweight="bold")
    ax.legend(loc="upper right")
    return _save(fig, out_dir, "fig_benchmark_position")


def plot_score_radar(score: ValidationScore, out_dir: Path) -> list[str]:
    configure_nature_style()
    cats = list(score.category_scores.keys())
    if not cats:
        return []
    labels = [CATEGORY_LABELS.get(c, c) for c in cats]
    vals = [score.category_scores[c] for c in cats]
    angles = np.linspace(0, 2 * np.pi, len(cats), endpoint=False).tolist()
    vals_c = vals + [vals[0]]
    angles_c = angles + [angles[0]]

    fig, ax = plt.subplots(figsize=(4.5, 4.5), subplot_kw={"projection": "polar"})
    ax.plot(angles_c, vals_c, "o-", color=NATURE_COLORS["candidate"], linewidth=1.2)
    ax.fill(angles_c, vals_c, alpha=0.15, color=NATURE_COLORS["candidate"])
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylim(0, 100)
    ax.set_title(f"Score radar (overall {score.overall_score:.0f}, grade {score.grade})", fontsize=9, pad=16)
    return _save(fig, out_dir, "fig_score_radar")


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


def generate_all_plots(score: ValidationScore, out_dir: Path, candidate_label: str = "Candidate") -> dict[str, list[str]]:
    artifacts: dict[str, list[str]] = {}
    for fn in (
        lambda: plot_benchmark_position(score, out_dir, candidate_label),
        lambda: plot_score_radar(score, out_dir),
        lambda: plot_rule_heatmap(score, out_dir),
        lambda: plot_capacity_intensity(score, out_dir, candidate_label),
    ):
        paths = fn()
        if paths:
            stem = Path(paths[0]).stem
            artifacts[stem] = paths
    return artifacts
