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

FONT = {
    "title": 13.0,
    "subtitle": 10.5,
    "axis": 11.0,
    "tick": 11.0,
    "value": 11.5,
    "badge": 10.0,
    "roman": 13.0,
    "legend": 9.5,
}

NATURE = {
    "text": "#1A1A1A",
    "grid": "#E8E8E8",
    "panel_bg": "white",
    "improve": "#00A087",
    "worse": "#E64B35",
    "neutral": "#8491B4",
}

_ROMAN = (
    "I",
    "II",
    "III",
    "IV",
    "V",
    "VI",
    "VII",
    "VIII",
    "IX",
    "X",
)


def _roman(index: int) -> str:
    if 0 <= index < len(_ROMAN):
        return _ROMAN[index]
    return str(index + 1)


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
            "font.size": FONT["tick"],
            "axes.titlesize": FONT["title"],
            "axes.labelsize": FONT["axis"],
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


def _panel_title(ax: plt.Axes, roman: str, metric: dict[str, Any]) -> None:
    label = _metric_label(metric)
    head = f"{roman}   {label}"
    subtitle = metric.get("subtitle") or metric.get("subtitle_en")
    ax.text(
        0.0,
        1.14,
        head,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=FONT["title"],
        fontweight="bold",
        clip_on=False,
    )
    if subtitle:
        ax.text(
            0.0,
            1.02,
            subtitle,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=FONT["subtitle"],
            color="#555555",
            clip_on=False,
        )


def _draw_delta_badge(
    ax: plt.Axes,
    ai_val: float,
    tuq_val: float,
    *,
    lower_is_better: bool,
    show_vs_label: bool,
    ref_line: float | None = None,
) -> None:
    _, pct_text, tag = _delta_pct(ai_val, tuq_val, lower_is_better=lower_is_better)
    badge_color = NATURE[tag]
    label = f"AI vs Tuqiang  {pct_text}" if show_vs_label else pct_text
    ax.text(
        0.5,
        0.90,
        label,
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=FONT["badge"],
        color=badge_color,
        fontweight="bold",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "white",
            "edgecolor": badge_color,
            "linewidth": 0.9,
            "alpha": 0.96,
        },
        zorder=8,
        clip_on=True,
    )


def _draw_status_badge(ax: plt.Axes, text: str, *, ok: bool) -> None:
    badge_color = NATURE["improve"] if ok else NATURE["worse"]
    ax.text(
        0.5,
        0.90,
        text,
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=FONT["badge"],
        color=badge_color,
        fontweight="bold",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "white",
            "edgecolor": badge_color,
            "linewidth": 0.9,
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
    ax.tick_params(axis="both", labelsize=FONT["tick"])


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
    roman: str,
    show_vs_label: bool,
) -> None:
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

    mode_entries: list[tuple[float, str, str]] = []
    for mode in list(metric.get("ai_modes") or []):
        mode_entries.append((float(mode["hz"]), ai_color, str(mode.get("ls") or "-")))
    for mode in list(metric.get("tuqiang_modes") or []):
        mode_entries.append((float(mode["hz"]), tuq_color, str(mode.get("ls") or "-")))
    mode_entries.sort(key=lambda item: item[0])

    for hz, color, ls in mode_entries:
        ax.axvline(hz, color=color, linestyle=ls, linewidth=2.0, zorder=4)

    ax.set_xlabel("Frequency (Hz)", fontsize=FONT["axis"], color="#444444", labelpad=10)
    ax.set_ylabel("Normalized spectrum", fontsize=FONT["axis"], color="#444444")
    ax.set_yticks([0.0, 0.5, 1.0])
    ax.spines["top"].set_visible(True)
    ax.spines["right"].set_visible(True)
    for spine in ax.spines.values():
        spine.set_color("#333333")
        spine.set_linewidth(0.6)

    _panel_title(ax, roman, metric)

    all_modes = list(metric.get("ai_modes") or []) + list(metric.get("tuqiang_modes") or [])
    all_clear = all(_mode_clear_of_bands(float(m["hz"]), bands) for m in all_modes)
    if show_vs_label:
        _draw_status_badge(
            ax,
            "No overlap with 1P / 3P" if all_clear else "Check band clearance",
            ok=all_clear,
        )

    band_patches = [
        patches.Patch(
            facecolor=str(b.get("color") or "#8491B4"),
            edgecolor=str(b.get("color") or "#8491B4"),
            hatch="////",
            alpha=0.45,
            label=str(b.get("label") or "Band"),
        )
        for b in bands
    ]
    mode_handles = [
        Line2D([0], [0], color=ai_color, lw=2, ls=":", label=f"{ai_label} 1st SS"),
        Line2D([0], [0], color=ai_color, lw=2, ls="-", label=f"{ai_label} 1st FA"),
        Line2D([0], [0], color=tuq_color, lw=2, ls=":", label=f"{tuq_label} 1st SS"),
        Line2D([0], [0], color=tuq_color, lw=2, ls="-", label=f"{tuq_label} 1st FA"),
    ]
    ax.legend(
        handles=band_patches + mode_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.21),
        ncol=2,
        fontsize=FONT["legend"],
        frameon=False,
        handlelength=1.4,
        borderaxespad=0.0,
    )


def _draw_metric_panel(
    ax: plt.Axes,
    metric: dict[str, Any],
    platforms: dict[str, Any],
    *,
    roman: str,
    show_vs_label: bool,
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
    bars = ax.bar(
        x,
        heights,
        width=0.62,
        color=[ai_color, tuq_color],
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )

    ymax = max(heights) * 1.38 if max(heights) > 0 else 1.0
    ref_line = metric.get("reference_line")
    if ref_line is not None:
        ref_val = float(ref_line)
        ymax = max(ymax, ref_val * 1.20, max(heights) * 1.48)
    ymin = 0.0
    ax.set_ylim(ymin, ymax)

    if ref_line is not None:
        ref_val = float(ref_line)
        ax.axhline(ref_val, color="#666666", linestyle=":", linewidth=1.1, zorder=2)
        ref_trans = blended_transform_factory(ax.transAxes, ax.transData)
        span = ymax - ymin
        ax.text(
            0.02,
            ref_val + span * 0.012,
            str(metric.get("reference_label") or f"{ref_val:g} target"),
            transform=ref_trans,
            ha="left",
            va="bottom",
            fontsize=FONT["tick"],
            color="#555555",
            clip_on=True,
            zorder=7,
        )

    ax.set_xticks(x)
    ax.set_xticklabels([ai_label, tuq_label], fontsize=FONT["tick"], fontweight="bold")
    ax.set_ylabel(unit, fontsize=FONT["axis"], color="#444444")

    _panel_title(ax, roman, metric)

    span = ymax - ymin
    label_pad = span * 0.018
    text_height = span * 0.040
    ref_val_opt = float(ref_line) if ref_line is not None else None
    ref_gap = span * 0.022
    for bar, val in zip(bars, heights):
        bar_top = float(val)
        label_y = bar_top + label_pad
        if ref_val_opt is not None:
            ceiling = ref_val_opt - ref_gap - text_height
            label_y = min(label_y, ceiling)
            label_y = max(label_y, bar_top + span * 0.010)
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            label_y,
            _fmt_value(bar_top, unit),
            ha="center",
            va="bottom",
            fontsize=FONT["value"],
            fontweight="bold",
            color=NATURE["text"],
            zorder=6,
            clip_on=True,
        )

    ref_for_badge = float(ref_line) if ref_line is not None else None
    if show_vs_label:
        _draw_delta_badge(
            ax, ai_val, tuq_val, lower_is_better=lower, show_vs_label=True, ref_line=ref_for_badge
        )
    else:
        _draw_delta_badge(
            ax, ai_val, tuq_val, lower_is_better=lower, show_vs_label=False, ref_line=ref_for_badge
        )

    _style_panel(ax)


def plot_comparison(
    data: dict[str, Any] | None = None,
    out_dir: Path | None = None,
    *,
    stem: str = "fig_ai_vs_tuqiang_bars",
    show_vs_label: bool = True,
    include_normalized: bool = True,
) -> list[Path]:
    _configure_style()
    data = data or _load_data()
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    platforms = data.get("platforms") or {}
    metrics: list[dict[str, Any]] = list(data.get("metrics") or [])
    if not metrics:
        raise ValueError("no metrics defined in ai_vs_tuqiang_comparison.yaml")

    ncols = 4
    nrows = int(np.ceil(len(metrics) / ncols))
    fig = plt.figure(figsize=(14.2, 4.5 * nrows), facecolor="white")
    gs = fig.add_gridspec(nrows, ncols, hspace=0.88, wspace=0.48)

    for i, metric in enumerate(metrics):
        row, col = divmod(i, ncols)
        ax = fig.add_subplot(gs[row, col])
        roman = _roman(i)
        if metric.get("chart") == "avoidance":
            _draw_frequency_avoidance_panel(ax, metric, platforms, roman=roman, show_vs_label=show_vs_label)
        else:
            _draw_metric_panel(ax, metric, platforms, roman=roman, show_vs_label=show_vs_label)

    for j in range(len(metrics), nrows * ncols):
        row, col = divmod(j, ncols)
        fig.add_subplot(gs[row, col]).axis("off")

    fig.subplots_adjust(top=0.86, bottom=0.16, left=0.08, right=0.97)

    paths: list[Path] = []
    for ext in (".png", ".pdf"):
        p = out_dir / f"{stem}{ext}"
        fig.savefig(p, facecolor="white")
        paths.append(p)
    plt.close(fig)

    if not include_normalized:
        return paths

    fig2, ax2 = plt.subplots(figsize=(14.2, 4.2), facecolor="white")
    bar_metrics = [m for m in metrics if m.get("chart") != "avoidance" and m.get("ai") is not None]
    group_x = np.arange(len(bar_metrics))
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
    labels = [_metric_label(m) for m in bar_metrics]
    ax2.set_xticks(group_x)
    ax2.set_xticklabels(labels, fontsize=FONT["tick"])
    ax2.set_ylabel("Normalized performance index (0–100)", fontsize=FONT["axis"])
    ax2.set_ylim(0, 115)
    _style_panel(ax2)
    ax2.legend(loc="upper right", fontsize=FONT["legend"], frameon=False)
    fig2.subplots_adjust(top=0.90, bottom=0.22)
    norm_stem = stem.replace("_bars", "_normalized")
    if norm_stem == stem:
        norm_stem = f"{stem}_normalized"
    for ext in (".png", ".pdf"):
        p = out_dir / f"{norm_stem}{ext}"
        fig2.savefig(p, facecolor="white")
        paths.append(p)
    plt.close(fig2)

    return paths


def main() -> None:
    paths: list[Path] = []
    paths.extend(plot_comparison(stem="fig_ai_vs_tuqiang_bars", show_vs_label=True))
    paths.extend(
        plot_comparison(
            stem="fig_ai_vs_tuqiang_bars_noprefix",
            show_vs_label=False,
            include_normalized=False,
        )
    )
    print(f"Wrote {len(paths)} files to {OUT_DIR}:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
