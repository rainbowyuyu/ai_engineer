#!/usr/bin/env python3
"""Generate Nature-style Fig. 2b–e panels from paper_fig2_metrics.json.

Aligned with the preprint caption:
  b — tower frequencies vs 1P/3P + platform 6-DOF periods
  c — operating DLC1.1 surge / pitch / tower-top acceleration
  d — extreme DLC 6.1 motions
  e — mooring tension + tower-base My
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
DEFAULT_METRICS = HERE / "paper_fig2_metrics.json"


def _style() -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    plt.rcParams["axes.linewidth"] = 1.2
    plt.rcParams["mathtext.default"] = "regular"


def _bar(ax, title, data, color_ai, color_tq, ylabel="", limit=None, limit_label=""):
    ai_val = float(data["ai"])
    tq_val = float(data["tuqiang"])
    bars = ax.bar(["AI", "Tuqiang"], [ai_val, tq_val], color=[color_ai, color_tq], width=0.55)
    for bar in bars:
        yval = bar.get_height()
        label = f"{yval:,.0f}" if yval >= 1000 else f"{yval:.2f}"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            yval + (max(ai_val, tq_val) * 0.03),
            label,
            ha="center",
            va="bottom",
            fontsize=14,
            fontweight="bold",
        )
    max_y = max(ai_val, tq_val)
    if limit is not None:
        ax.axhline(y=limit, color="#7f8c8d", linestyle="--", linewidth=1.5, zorder=0)
        ax.text(
            0.5,
            limit + max_y * 0.05,
            f"Limit: {limit_label}",
            color="#7f8c8d",
            va="center",
            ha="center",
            fontsize=11,
            fontweight="bold",
        )
        max_y = max(max_y, float(limit))
    pct_diff = (ai_val - tq_val) / tq_val * 100
    box_color = color_ai if pct_diff < 0 else color_tq
    sign = "+" if pct_diff > 0 else ""
    bbox_props = dict(boxstyle="round,pad=0.3", fc="white", ec=box_color, lw=1.2)
    ax.text(
        0.5,
        max_y * 1.25,
        f"{sign}{pct_diff:.1f}%",
        ha="center",
        va="center",
        color=box_color,
        fontweight="bold",
        bbox=bbox_props,
        fontsize=12,
    )
    ax.set_ylim(0, max_y * 1.45)
    ax.set_title(title, fontweight="bold", pad=20, fontsize=16)
    if ylabel:
        ax.set_ylabel(ylabel, fontweight="bold", fontsize=14)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", labelsize=15)
    ax.tick_params(axis="y", labelsize=13)
    ax.grid(axis="y", linestyle="--", alpha=0.4)


def _label(fig, letter: str) -> None:
    fig.text(0.01, 0.98, letter, fontsize=26, fontweight="bold", va="top", ha="left")


def plot_all(metrics: dict, out_dir: Path, dpi: int = 300) -> list[Path]:
    _style()
    out_dir.mkdir(parents=True, exist_ok=True)
    color_ai = metrics["colors"]["ai"]
    color_tq = metrics["colors"]["tuqiang"]
    fig_w, fig_h = 15.0, 5.0
    written: list[Path] = []

    # ---- b ----
    b = metrics["fig2b"]
    fig_b, (ax_b1, ax_b2) = plt.subplots(
        1, 2, figsize=(fig_w, fig_h), gridspec_kw={"width_ratios": [1, 1.3]}
    )
    bands = b["tower_frequencies_hz"]["excitation_bands"]
    ax_b1.axvspan(bands["1P"]["hz_min"], bands["1P"]["hz_max"], color="#92a8d1", alpha=0.6, label="1P Excitation")
    ax_b1.axvspan(bands["3P"]["hz_min"], bands["3P"]["hz_max"], color="#f6b0a0", alpha=0.6, label="3P Excitation")
    ai_f = b["tower_frequencies_hz"]["ai"]
    tq_f = b["tower_frequencies_hz"]["tuqiang"]
    ax_b1.axvline(ai_f["1st_fa"], color=color_ai, linestyle="-", linewidth=3, label=f"AI 1st FA ({ai_f['1st_fa']:.3f} Hz)")
    ax_b1.axvline(ai_f["1st_ss"], color=color_ai, linestyle="--", linewidth=3, label=f"AI 1st SS ({ai_f['1st_ss']:.3f} Hz)")
    ax_b1.axvline(tq_f["1st_fa"], color=color_tq, linestyle="-", linewidth=2.5, label=f"Tuqiang 1st FA ({tq_f['1st_fa']:.3f} Hz)")
    ax_b1.axvline(tq_f["1st_ss"], color=color_tq, linestyle="--", linewidth=2.5, label=f"Tuqiang 1st SS ({tq_f['1st_ss']:.3f} Hz)")
    ax_b1.set_ylim(0, 1)
    ax_b1.set_xlim(0.0, 0.55)
    ax_b1.set_title("I. Tower Natural Frequencies vs 1P/3P", fontweight="bold", pad=20, fontsize=16)
    ax_b1.set_xlabel("Frequency (Hz)", fontweight="bold", fontsize=14)
    ax_b1.set_ylabel("Normalized spectrum", fontweight="bold", fontsize=14)
    ax_b1.spines["top"].set_visible(False)
    ax_b1.spines["right"].set_visible(False)
    ax_b1.set_yticks([])
    ax_b1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False, fontsize=12)

    periods = b["platform_natural_periods_s"]
    dofs = periods["dofs"]
    x = np.arange(len(dofs))
    width = 0.35
    ax_b2.bar(x - width / 2, periods["ai"], width, label="AI", color=color_ai)
    ax_b2.bar(x + width / 2, periods["tuqiang"], width, label="Tuqiang", color=color_tq)
    w0, w1 = periods["wave_energy_range_s"]
    ax_b2.axhspan(w0, w1, color="#E0E0E0", alpha=0.5, label="Wave Energy Range (Danger)")
    ax_b2.set_ylabel("Natural Period (s)", fontweight="bold", fontsize=14)
    ax_b2.set_title("II. Platform 6-DOF Natural Periods", fontweight="bold", pad=20, fontsize=16)
    ax_b2.set_xticks(x)
    ax_b2.set_xticklabels(dofs, fontweight="bold", fontsize=13)
    ax_b2.spines["top"].set_visible(False)
    ax_b2.spines["right"].set_visible(False)
    ax_b2.set_ylim(0, 85)
    ax_b2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False, fontsize=12)
    plt.tight_layout()
    plt.subplots_adjust(top=0.76, wspace=0.2)
    fig_b.suptitle(b["title"], fontweight="bold", fontsize=20, y=0.96, x=0.5, ha="center")
    _label(fig_b, "b")
    p = out_dir / "fig2b_dynamics.png"
    fig_b.savefig(p, dpi=dpi, bbox_inches="tight")
    plt.close(fig_b)
    written.append(p)

    # ---- c / d / e ----
    for letter, key, layout, items in [
        (
            "c",
            "fig2c",
            3,
            [
                ("I. Surge", "surge_m", "m"),
                ("II. Pitch", "pitch_deg", "deg"),
                ("III. Tower Top Acc", "tower_top_acc_mps2", "m/s²"),
            ],
        ),
        (
            "d",
            "fig2d",
            3,
            [
                ("I. Surge", "surge_m", "m"),
                ("II. Pitch", "pitch_deg", "deg"),
                ("III. Tower Top Acc", "tower_top_acc_mps2", "m/s²"),
            ],
        ),
        (
            "e",
            "fig2e",
            2,
            [
                ("I. Max Mooring Tension", "max_mooring_tension_kn", "kN"),
                ("II. Tower Base My", "tower_base_my_mnm", r"MN$\cdot$m"),
            ],
        ),
    ]:
        block = metrics[key]
        fig, axes = plt.subplots(1, layout, figsize=(fig_w, fig_h))
        if layout == 1:
            axes = [axes]
        for ax, (title, field, ylabel) in zip(axes, items):
            data = block[field]
            _bar(
                ax,
                title,
                data,
                color_ai,
                color_tq,
                ylabel,
                data.get("limit"),
                data.get("limit_label") or "",
            )
        plt.tight_layout()
        plt.subplots_adjust(top=0.76, wspace=0.45 if layout == 2 else 0.3)
        fig.suptitle(block["title"], fontweight="bold", fontsize=20, y=0.96, x=0.5, ha="center")
        _label(fig, letter)
        p = out_dir / f"fig2{letter}_{'operating' if letter == 'c' else 'extreme' if letter == 'd' else 'loads'}.png"
        if letter == "c":
            p = out_dir / "fig2c_operating.png"
        elif letter == "d":
            p = out_dir / "fig2d_extreme.png"
        else:
            p = out_dir / "fig2e_loads.png"
        fig.savefig(p, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        written.append(p)

    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    ap.add_argument(
        "--out",
        type=Path,
        default=HERE / "figures" / "generated",
        help="Output directory for Fig. 2b–e PNG panels",
    )
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    paths = plot_all(metrics, args.out, dpi=args.dpi)
    for p in paths:
        print(f"Wrote {p}")


if __name__ == "__main__":
    main()
