#!/usr/bin/env python3
"""Nature-style grouped bar charts: AI vs Tuqiang (8 key metrics, English only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib import patches
from matplotlib.lines import Line2D
from matplotlib.transforms import blended_transform_factory

os.environ.setdefault("MPLBACKEND", "Agg")

ROOT = Path(__file__).resolve().parents[1]
DATA_YAML = ROOT / "rules" / "ai_vs_tuqiang_comparison.yaml"
OUT_DIR = Path(__file__).resolve().parent / "output"

NATURE = {
    "text": "#1A1A1A",
    "grid": "#E8E8E8",
    "panel_bg": "#FAFAFA",
    "improve": "#00A087",
    "worse": "#E64B35",
    "neutral": "#8491B4",
}

ICON_GLYPH = {
    "steel": "S",
    "intensity": "I",
    "cost": "C",
    "frequency": "f",
    "motion": "M",
    "strength": "U",
    "fatigue": "D",
    "mooring": "T",
}


def _pick_font() -> str:
    import matplotlib.font_manager as fm

    preferred = ["Arial", "Helvetica", "DejaVu Sans"]
    available = {f.name for f in fm.fontManager.ttflist}
    return next((f for f in preferred if f in available), "DejaVu Sans")


def _load_data(path: Path = DATA_YAML) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _configure_style() -> None:
    font_family = _pick_font()
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font_family, "Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8,
            "axes.titlesize": 9,
            "axes.labelsize": 8,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
            "axes.linewidth": 0.55,
        }
    )


def _fmt_value(val: float, unit: str) -> str:
    if unit == "Hz":
        return f"{val:.3f}"
    if unit == "t/MW":
        return f"{val:.1f}"
    if unit in ("UC", "D"):
        return f"{val:.2f}"
    if unit == "deg":
        return f"{val:.2f}"
    if val >= 1000:
        return f"{val:,.0f}"
    if val >= 100:
        return f"{val:.0f}"
    return f"{val:.1f}"


def _delta_pct(ai: float, tuq: float, *, lower_is_better: bool) -> tuple[float, str, str]:
    if tuq == 0:
        return 0.0, "n/a", "neutral"
    pct = (ai - tuq) / abs(tuq) * 100.0
    improved = pct < 0 if lower_is_better else pct > 0
    sign = "+" if pct > 0 else ""
    color_tag = "improve" if improved else "worse"
    return pct, f"{sign}{pct:.1f}%", color_tag


def _platform_label(platforms: dict[str, Any], key: str) -> str:
    row = platforms.get(key) or {}
    return str(row.get("label") or row.get("label_en") or key)


def _metric_label(metric: dict[str, Any]) -> str:
    return str(metric.get("label") or metric.get("label_en") or metric.get("id") or "")


def _panel_title(ax: plt.Axes, letter: str, metric: dict[str, Any]) -> None:
    icon = ICON_GLYPH.get(str(metric.get("icon") or ""), "")
    label = _metric_label(metric)
    head = f"{letter}   [{icon}]  {label}" if icon else f"{letter}   {label}"
    subtitle = metric.get("subtitle") or metric.get("subtitle_en")
    if subtitle:
        ax.set_title(f"{head}\n{subtitle}", loc="left", fontsize=9, fontweight="bold", pad=20, linespacing=1.1)
    else:
        ax.set_title(head, loc="left", fontsize=9, fontweight="bold", pad=10)


def _draw_delta_badge(
    ax: plt.Axes,
    ai_val: float,
    tuq_val: float,
    *,
    lower_is_better: bool,
    ymax: float,
    ymin: float,
) -> None:
    _, pct_text, tag = _delta_pct(ai_val, tuq_val, lower_is_better=lower_is_better)
    badge_color = NATURE[tag]
    y = ymax - (ymax - ymin) * 0.04
    ax.text(
        0.5,
        y,
        f"AI vs Tuqiang  {pct_text}",
        ha="center",
        va="top",
        fontsize=6.5,
        color=badge_color,
        fontweight="bold",
        bbox={
            "boxstyle": "round,pad=0.3",
            "facecolor": "white",
            "edgecolor": badge_color,
            "linewidth": 0.85,
            "alpha": 0.96,
        },
        zorder=6,
        clip_on=True,
    )


def _draw_status_badge(ax: plt.Axes, text: str, *, ok: bool, y: float = 0.92) -> None:
    badge_color = NATURE["improve"] if ok else NATURE["worse"]
    ax.text(
        0.5,
        y,
        text,
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=6.5,
        color=badge_color,
        fontweight="bold",
        bbox={
            "boxstyle": "round,pad=0.3",
            "facecolor": "white",
            "edgecolor": badge_color,
            "linewidth": 0.85,
            "alpha": 0.96,
        },
        zorder=6,
        clip_on=True,
    )


def _style_panel(ax: plt.Axes) -> None:
    ax.set_facecolor(NATURE["panel_bg"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CCCCCC")
    ax.spines["bottom"].set_color("#CCCCCC")
    ax.grid(True, axis="y", color=NATURE["grid"], linewidth=0.55, zorder=0)
    ax.set_axisbelow(True)


def _draw_hatched_band(
    ax: plt.Axes,
    x0: float,
    x1: float,
    *,
    color: str,
    y0: float = 0.0,
    y1: float = 1.0,
    alpha: float = 0.35,
) -> None:
    ax.add_patch(
        patches.Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            facecolor=color,
            edgecolor=color,
            linewidth=1.0,
            alpha=alpha,
            hatch="////",
            zorder=1,
        )
    )


def _mode_clear_of_bands(hz: float, bands: list[dict[str, Any]]) -> bool:
    for band in bands:
        lo = float(band["hz_min"])
        hi = float(band["hz_max"])
        if lo <= hz <= hi:
            return False
    return True


def _draw_frequency_avoidance_panel(
    ax: plt.Axes,
    metric: dict[str, Any],
    platforms: dict[str, Any],
    *,
    letter: str,
) -> None:
    """1P / 3P excitation bands vs structural mode lines (no overlap)."""
    x_max = float(metric.get("x_max") or 0.5)
    bands: list[dict[str, Any]] = list(metric.get("excitation_bands") or [])
    ai_color = platforms["ai"]["color"]
    tuq_color = platforms["tuqiang"]["color"]
    ai_label = _platform_label(platforms, "ai")
    tuq_label = _platform_label(platforms, "tuqiang")

    ax.set_facecolor("white")
    ax.set_xlim(0.0, x_max)
    ax.set_ylim(0.0, 1.05)
    for band in bands:
        _draw_hatched_band(
            ax,
            float(band["hz_min"]),
            float(band["hz_max"]),
            color=str(band.get("color") or "#8491B4"),
        )

    legend_handles: list[Any] = []
    for band in bands:
        legend_handles.append(
            patches.Patch(
                facecolor=str(band.get("color") or "#8491B4"),
                edgecolor=str(band.get("color") or "#8491B4"),
                hatch="////",
                alpha=0.45,
                label=str(band.get("label") or "Band"),
            )
        )

    def _plot_modes(modes: list[dict[str, Any]], color: str, prefix: str) -> None:
        mode_label_trans = blended_transform_factory(ax.transData, ax.transAxes)
        for mode in modes:
            hz = float(mode["hz"])
            ls = str(mode.get("ls") or "-")
            ax.axvline(hz, color=color, linestyle=ls, linewidth=1.8, zorder=4)
            ax.text(
                hz,
                0.93,
                f"{hz:.2f}",
                transform=mode_label_trans,
                ha="center",
                va="bottom",
                fontsize=6.5,
                color=color,
                fontweight="bold",
                clip_on=True,
            )
            legend_handles.append(
                Line2D([0], [0], color=color, lw=1.8, ls=ls, label=f"{prefix} {mode.get('label', 'mode')}")
            )

    _plot_modes(list(metric.get("ai_modes") or []), ai_color, ai_label)
    _plot_modes(list(metric.get("tuqiang_modes") or []), tuq_color, tuq_label)

    ax.set_xlabel("Frequency (Hz)", fontsize=7.5, color="#555555")
    ax.set_ylabel("Normalized spectrum", fontsize=7.5, color="#555555")
    ax.set_yticks([0.0, 0.5, 1.0])
    ax.tick_params(axis="both", labelsize=7)
    ax.spines["top"].set_visible(True)
    ax.spines["right"].set_visible(True)
    for spine in ax.spines.values():
        spine.set_color("#333333")
        spine.set_linewidth(0.6)

    _panel_title(ax, letter, metric)

    all_modes = list(metric.get("ai_modes") or []) + list(metric.get("tuqiang_modes") or [])
    all_clear = all(_mode_clear_of_bands(float(m["hz"]), bands) for m in all_modes)
    _draw_status_badge(
        ax,
        "No overlap with 1P / 3P" if all_clear else "Check band clearance",
        ok=all_clear,
        y=0.90,
    )

    ax.legend(
        handles=legend_handles,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        fontsize=5.8,
        frameon=False,
        handlelength=1.6,
    )


def _draw_metric_panel(
    ax: plt.Axes,
    metric: dict[str, Any],
    platforms: dict[str, Any],
    *,
    letter: str,
) -> None:
    ai_val = float(metric["ai"])
    tuq_val = float(metric["tuqiang"])
    unit = str(metric.get("unit") or "")
    lower = bool(metric.get("lower_is_better", True))
    ai_color = platforms["ai"]["color"]
    tuq_color = platforms["tuqiang"]["color"]
    ai_label = _platform_label(platforms, "ai")
    tuq_label = _platform_label(platforms, "tuqiang")

    x = np.array([0, 1])
    heights = np.array([ai_val, tuq_val])
    colors = [ai_color, tuq_color]
    bars = ax.bar(
        x,
        heights,
        width=0.62,
        color=colors,
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )

    ymax = max(heights) * 1.28 if max(heights) > 0 else 1.0
    ref_line = metric.get("reference_line")
    if ref_line is not None:
        ymax = max(ymax, float(ref_line) * 1.22)
    ymin = 0.0
    if min(heights) > 0 and min(heights) / max(heights) < 0.55:
        ymin = max(0.0, min(heights) * 0.82)
    ax.set_ylim(ymin, ymax)

    if ref_line is not None:
        ref_val = float(ref_line)
        ax.axhline(
            ref_val,
            color="#666666",
            linestyle=":",
            linewidth=1.0,
            zorder=2,
        )
        ref_trans = blended_transform_factory(ax.transAxes, ax.transData)
        ax.text(
            0.03,
            ref_val + (ymax - ymin) * 0.015,
            str(metric.get("reference_label") or f"{ref_val:g} target"),
            transform=ref_trans,
            ha="left",
            va="bottom",
            fontsize=6.5,
            color="#666666",
            clip_on=False,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([ai_label, tuq_label], fontsize=8, fontweight="bold")
    ax.set_ylabel(unit, fontsize=7.5, color="#555555")

    _panel_title(ax, letter, metric)

    for bar, val in zip(bars, heights):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + (ymax - ymin) * 0.025,
            _fmt_value(float(val), unit),
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color=NATURE["text"],
            zorder=4,
        )

    _draw_delta_badge(ax, ai_val, tuq_val, lower_is_better=lower, ymax=ymax, ymin=ymin)
    _style_panel(ax)


def plot_comparison(data: dict[str, Any] | None = None, out_dir: Path | None = None) -> list[Path]:
    _configure_style()
    data = data or _load_data()
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = data.get("meta") or {}
    platforms = data.get("platforms") or {}
    metrics: list[dict[str, Any]] = list(data.get("metrics") or [])
    n_metrics = len(metrics)
    if n_metrics < 1:
        raise ValueError("no metrics defined in ai_vs_tuqiang_comparison.yaml")

    ncols = 4
    nrows = int(np.ceil(n_metrics / ncols))
    fig = plt.figure(figsize=(13.8, 4.2 * nrows))
    gs = fig.add_gridspec(nrows, ncols, hspace=0.72, wspace=0.42)

    letters = "abcdefghijklmnopqrstuvwxyz"
    for i, metric in enumerate(metrics):
        row, col = divmod(i, ncols)
        ax = fig.add_subplot(gs[row, col])
        if metric.get("chart") == "avoidance":
            _draw_frequency_avoidance_panel(ax, metric, platforms, letter=letters[i])
        else:
            _draw_metric_panel(ax, metric, platforms, letter=letters[i])

    for j in range(n_metrics, nrows * ncols):
        row, col = divmod(j, ncols)
        fig.add_subplot(gs[row, col]).axis("off")

    title = meta.get("title") or meta.get("title_en") or "AI vs Tuqiang — key performance comparison"
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.995)

    footnote = str(meta.get("footnote") or meta.get("footnote_en") or "").strip()
    if footnote:
        fig.text(0.02, 0.01, footnote, fontsize=6.5, color="#666666", va="bottom", wrap=True)

    legend_handles = [
        patches.Patch(facecolor=platforms["ai"]["color"], edgecolor="white", label=_platform_label(platforms, "ai")),
        patches.Patch(
            facecolor=platforms["tuqiang"]["color"],
            edgecolor="white",
            label=_platform_label(platforms, "tuqiang"),
        ),
        Line2D(
            [0],
            [0],
            color=NATURE["improve"],
            lw=0,
            marker="s",
            markersize=0,
            label="Favorable change (green badge)",
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower right",
        bbox_to_anchor=(0.98, 0.02),
        fontsize=7,
        frameon=True,
        fancybox=False,
        edgecolor="#DDDDDD",
        facecolor="white",
    )

    fig.subplots_adjust(top=0.91, bottom=0.10, left=0.07, right=0.94)

    paths: list[Path] = []
    stem = "fig_ai_vs_tuqiang_bars"
    for ext in (".png", ".pdf"):
        p = out_dir / f"{stem}{ext}"
        fig.savefig(p, facecolor="white")
        paths.append(p)
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(14.2, 4.2))
    bar_metrics = [m for m in metrics if m.get("chart") != "avoidance" and m.get("ai") is not None]
    n = len(bar_metrics)
    group_x = np.arange(n)
    bar_w = 0.34
    norm_ai: list[float] = []
    norm_tuq: list[float] = []
    for m in bar_metrics:
        ai = float(m["ai"])
        tuq = float(m["tuqiang"])
        lo = min(ai, tuq)
        hi = max(ai, tuq)
        span = max(hi - lo, hi * 0.08, 1e-9)
        if bool(m.get("lower_is_better", True)):
            norm_ai.append(100.0 * (hi - ai) / span)
            norm_tuq.append(100.0 * (hi - tuq) / span)
        else:
            norm_ai.append(100.0 * (ai - lo) / span)
            norm_tuq.append(100.0 * (tuq - lo) / span)

    ax2.bar(
        group_x - bar_w / 2,
        norm_ai,
        bar_w,
        color=platforms["ai"]["color"],
        label=_platform_label(platforms, "ai"),
        edgecolor="white",
        linewidth=1.0,
    )
    ax2.bar(
        group_x + bar_w / 2,
        norm_tuq,
        bar_w,
        color=platforms["tuqiang"]["color"],
        label=_platform_label(platforms, "tuqiang"),
        edgecolor="white",
        linewidth=1.0,
    )
    labels = [
        f"[{ICON_GLYPH.get(str(m.get('icon') or ''), '')}] {_metric_label(m)}".strip()
        for m in bar_metrics
    ]
    ax2.set_xticks(group_x)
    ax2.set_xticklabels(labels, fontsize=8)
    ax2.set_ylabel("Normalized performance index (0–100)", fontsize=8)
    ax2.set_ylim(0, 115)
    ax2.set_title(
        "AI vs Tuqiang — normalized comparison (higher = better within each metric)",
        loc="left",
        fontweight="bold",
        fontsize=10,
    )
    _style_panel(ax2)
    ax2.legend(loc="upper right", fontsize=7, frameon=False)
    fig2.subplots_adjust(top=0.82, bottom=0.18)
    stem2 = "fig_ai_vs_tuqiang_normalized"
    for ext in (".png", ".pdf"):
        p = out_dir / f"{stem2}{ext}"
        fig2.savefig(p, facecolor="white")
        paths.append(p)
    plt.close(fig2)

    return paths


def main() -> None:
    paths = plot_comparison()
    print(f"Wrote {len(paths)} files to {OUT_DIR}:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
