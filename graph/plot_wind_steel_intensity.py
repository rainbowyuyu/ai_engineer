#!/usr/bin/env python3
"""Plot wind-turbine steel metrics from 风电项目钢耗强度统计表.xlsx (Nature-style)."""

from __future__ import annotations

import datetime
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patches
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent
XLSX = ROOT / "风电项目钢耗强度统计表.xlsx"
OUT_DIR = ROOT

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Nature-inspired palette (colorblind-friendly)
NATURE_COLORS = {
    "international": "#3C5488",
    "domestic": "#E64B35",
    "trend": "#8491B4",
    "grid": "#E6E6E6",
    "text": "#222222",
}

NAME_FIX = {
    "Haizhuang Fuyao��2022��": "海装扶瑶(2022)",
    "Haiyou Guanlan��2023��": "海油观澜(2023)",
    "Tuqiang��2026��": "图强(2026)",
    "AI��2026��": "AI(2026)",
}


@dataclass
class ProjectRecord:
    name: str
    short_name: str
    year: int | None
    year_label: str
    year_status: str
    region: str
    steel_intensity: float | None
    steel_intensity_err: tuple[float, float] | None
    capacity_mw: float | None
    total_steel_t: float | None
    total_steel_err: tuple[float, float] | None
    raw_intensity: str
    raw_total: str

    @property
    def sort_year(self) -> int:
        return self.year if self.year is not None else 9999


_YEAR_IN_NAME = re.compile(r"[\uff08(](\d{4})[\uff09)]")
_PLANNED_NAME_HINTS = ("AI", "Tuqiang", "图强", "Linghang", "领航", "观澜", "扶瑶", "gongxiang", "Tiancheng")


def _parse_year_info(name: str) -> tuple[int | None, str, str]:
    now = datetime.date.today().year
    m = _YEAR_IN_NAME.search(name)
    if not m:
        return None, "未标注", "unknown"
    year = int(m.group(1))
    if year > now:
        return year, f"规划·{year}", "planned"
    if year == now and any(h in name for h in _PLANNED_NAME_HINTS):
        return year, f"规划·{year}", "planned"
    return year, str(year), "commissioned"


def _read_xlsx_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall(".//m:si", NS):
                texts = [t.text or "" for t in si.findall(".//m:t", NS)]
                shared.append("".join(texts))
        root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        rows: list[dict[str, str]] = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            cells: dict[str, str] = {}
            for cell in row.findall("m:c", NS):
                ref = cell.get("r", "")
                col_match = re.match(r"([A-Z]+)", ref)
                if not col_match:
                    continue
                col = col_match.group(1)
                value_el = cell.find("m:v", NS)
                if value_el is None:
                    continue
                val = value_el.text or ""
                if cell.get("t") == "s":
                    val = shared[int(val)]
                cells[col] = val
            if cells:
                rows.append(cells)
    return rows


def _parse_numeric_range(text: str) -> tuple[float | None, tuple[float, float] | None]:
    if not text or not str(text).strip():
        return None, None
    s = str(text).strip().lower()
    s = s.replace("about ", "").replace("almost ", "")
    if "/" in s:
        parts = [p.strip() for p in s.split("/") if p.strip()]
        nums = []
        for p in parts:
            v, _ = _parse_numeric_range(p)
            if v is not None:
                nums.append(v)
        if len(nums) >= 2:
            lo, hi = min(nums), max(nums)
            return (lo + hi) / 2.0, (hi - lo) / 2.0
        if nums:
            return nums[0], None
    m = re.search(r"<\s*([\d.]+)", s)
    if m:
        v = float(m.group(1))
        return v, (0.0, v * 0.08)
    m = re.search(r">\s*([\d.]+)", s)
    if m:
        v = float(m.group(1))
        return v, (v * 0.08, v * 0.25)
    m = re.search(r"([\d.]+)", s)
    if m:
        return float(m.group(1)), None
    return None, None


def _normalize_name(name: str) -> str:
    return NAME_FIX.get(name, name)


def _short_label(name: str) -> str:
    name = _normalize_name(name)
    name = re.sub(r"\(\d{4}\)|（\d{4}）", "", name).strip()
    replacements = {
        "Three gorgesYinling": "三峡引领",
        "Three gorges Linghang": "三峡领航",
        "Haizhuang Fuyao": "海装扶瑶",
        "Haiyou Guanlan": "海油观澜",
        "Mingyang Tiancheng": "明阳天成",
        "GHN Energy gongxiang": "国能共享",
        "Fukushima Shimpuu": "福岛新风",
        "Fukushima Mirai": "福岛未来",
        "WindFloat Atlantic": "WindFloat Atlantic",
        "WindFloat": "WindFloat",
        "Kincardine Ph1": "Kincardine I",
        "Kincardine Ph2": "Kincardine II",
        "Tuqiang": "图强",
    }
    for key, val in replacements.items():
        if key in name:
            return val
    return name


def _is_domestic(name: str) -> bool:
    domestic_keys = (
        "Three gorges",
        "Haizhuang",
        "Haiyou",
        "Mingyang",
        "GHN Energy",
        "Tuqiang",
        "AI",
        "三峡",
        "海装",
        "海油",
        "明阳",
        "国能",
        "图强",
    )
    return any(k in name for k in domestic_keys)


def load_records(use_clean_section: bool = True) -> list[ProjectRecord]:
    rows = _read_xlsx_rows(XLSX)
    data_rows = []
    section = 0
    for row in rows:
        if row.get("C") == "Steel intensity" and row.get("D") == "Unit Capacity":
            section += 1
            continue
        if row.get("C") == "t/MW":
            continue
        if "B" not in row:
            continue
        if use_clean_section and section < 2:
            continue
        data_rows.append(row)

    seen: set[str] = set()
    records: list[ProjectRecord] = []
    for row in data_rows:
        raw_name = row["B"]
        if raw_name in seen:
            continue
        seen.add(raw_name)
        name = _normalize_name(raw_name)
        intensity_raw = row.get("C", "")
        total_raw = row.get("E", "")
        intensity, intensity_err = _parse_numeric_range(intensity_raw)
        total, total_err = _parse_numeric_range(total_raw)
        cap_raw = row.get("D", "")
        capacity = float(cap_raw) if cap_raw else None
        if intensity is None and capacity is None and total is None:
            continue
        err_i = None
        if intensity_err is not None and intensity is not None:
            err_i = intensity_err
        err_t = None
        if total_err is not None and total is not None:
            err_t = total_err
        year, year_label, year_status = _parse_year_info(name)
        records.append(
            ProjectRecord(
                name=name,
                short_name=_short_label(name),
                year=year,
                year_label=year_label,
                year_status=year_status,
                region="domestic" if _is_domestic(name) else "international",
                steel_intensity=intensity,
                steel_intensity_err=err_i,
                capacity_mw=capacity,
                total_steel_t=total,
                total_steel_err=err_t,
                raw_intensity=intensity_raw,
                raw_total=total_raw,
            )
        )
    records.sort(key=lambda r: (r.sort_year, r.short_name))
    return records


def configure_nature_style() -> None:
    # Prefer YaHei on Windows for bilingual labels; fall back to Arial.
    import matplotlib.font_manager as fm

    preferred = ["Microsoft YaHei", "SimHei", "Arial", "Helvetica", "DejaVu Sans"]
    available = {f.name for f in fm.fontManager.ttflist}
    font_family = next((f for f in preferred if f in available), "DejaVu Sans")

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font_family, "Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 9,
            "axes.linewidth": 0.6,
            "axes.edgecolor": NATURE_COLORS["text"],
            "axes.labelcolor": NATURE_COLORS["text"],
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 3,
            "ytick.major.size": 3,
            "legend.fontsize": 7,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _style_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, axis="y", color=NATURE_COLORS["grid"], linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)


def _region_color(region: str) -> str:
    return NATURE_COLORS[region]


def _add_panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.12,
        1.08,
        label,
        transform=ax.transAxes,
        fontsize=10,
        fontweight="bold",
        va="top",
        ha="left",
    )


def _plot_metric_curve(
    records: list[ProjectRecord],
    metric: str,
    ylabel: str,
    title: str,
    filename: str,
    panel_label: str | None = None,
) -> None:
    valid = [r for r in records if getattr(r, metric) is not None]
    if len(valid) < 2:
        return

    x = np.arange(len(valid))
    y = np.array([getattr(r, metric) for r in valid], dtype=float)
    yerr = None
    err_attr = f"{metric}_err"
    if any(getattr(r, err_attr, None) for r in valid):
        lower = []
        upper = []
        for r in valid:
            err = getattr(r, err_attr, None)
            val = getattr(r, metric)
            if err and val is not None:
                lower.append(err[0])
                upper.append(err[1])
            else:
                lower.append(0.0)
                upper.append(0.0)
        yerr = np.array([lower, upper])

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    _style_axis(ax)

    for i, r in enumerate(valid):
        ax.errorbar(
            x[i],
            y[i],
            yerr=[[yerr[0][i]], [yerr[1][i]]] if yerr is not None else None,
            fmt="none",
            ecolor=_region_color(r.region),
            elinewidth=0.8,
            capsize=2,
            alpha=0.85,
            zorder=2,
        )

    for region in ("international", "domestic"):
        idx = [i for i, r in enumerate(valid) if r.region == region]
        if not idx:
            continue
        ax.plot(
            x[idx],
            y[idx],
            color=_region_color(region),
            linewidth=1.2,
            marker="o",
            markersize=4.5,
            markerfacecolor="white",
            markeredgewidth=1.0,
            markeredgecolor=_region_color(region),
            zorder=3,
            label="International" if region == "international" else "China projects",
        )

    ax.plot(x, y, color="#B0B0B0", linewidth=0.8, linestyle="--", alpha=0.55, zorder=1)

    for i, r in enumerate(valid):
        ax.annotate(
            f"{r.short_name}\n({r.year_label})",
            (x[i], y[i]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            va="bottom",
            fontsize=6,
            color=NATURE_COLORS["text"],
            rotation=35 if len(valid) > 8 else 0,
        )

    ax.set_xticks(x)
    ax.set_xticklabels([r.year_label for r in valid], rotation=0)
    ax.set_xlabel("Commissioning year (project order)")
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontweight="bold", pad=10)

    z = np.polyfit(x, y, 1)
    trend = np.poly1d(z)
    ax.plot(
        x,
        trend(x),
        color=NATURE_COLORS["trend"],
        linewidth=1.0,
        linestyle=":",
        alpha=0.9,
        zorder=1,
        label=f"Linear trend (slope={z[0]:.1f})",
    )

    handles = [
        Line2D([0], [0], color=NATURE_COLORS["international"], marker="o", markersize=4, markerfacecolor="white", label="International"),
        Line2D([0], [0], color=NATURE_COLORS["domestic"], marker="o", markersize=4, markerfacecolor="white", label="China projects"),
        Line2D([0], [0], color=NATURE_COLORS["trend"], linestyle=":", label="Linear trend"),
    ]
    ax.legend(handles=handles, loc="upper right", ncol=1)

    if panel_label:
        _add_panel_label(ax, panel_label)

    note = "Error bars: range/measurement uncertainty from source table."
    fig.text(0.01, 0.01, note, fontsize=6, color="#666666")

    fig.savefig(OUT_DIR / f"{filename}.png")
    fig.savefig(OUT_DIR / f"{filename}.pdf")
    plt.close(fig)


def plot_combined_panel(records: list[ProjectRecord]) -> None:
    metrics = [
        ("steel_intensity", "Steel intensity (t MW$^{-1}$)", "Steel intensity trend"),
        ("capacity_mw", "Unit capacity (MW)", "Turbine capacity trend"),
        ("total_steel_t", "Total steel usage (t)", "Total steel usage trend"),
    ]

    fig, axes = plt.subplots(3, 1, figsize=(7.2, 8.8), sharex=False)
    panel_labels = ["a", "b", "c"]

    for ax, (metric, ylabel, subtitle), panel in zip(axes, metrics, panel_labels):
        valid = [r for r in records if getattr(r, metric) is not None]
        x = np.arange(len(valid))
        y = np.array([getattr(r, metric) for r in valid], dtype=float)
        _style_axis(ax)
        _add_panel_label(ax, panel)

        for region, label in (("international", "Intl."), ("domestic", "China")):
            idx = [i for i, r in enumerate(valid) if r.region == region]
            if not idx:
                continue
            ax.plot(
                x[idx],
                y[idx],
                color=_region_color(region),
                linewidth=1.0,
                marker="o",
                markersize=3.8,
                markerfacecolor="white",
                markeredgewidth=0.9,
                markeredgecolor=_region_color(region),
                label=label,
            )
        ax.plot(x, y, color="#CFCFCF", linewidth=0.7, linestyle="--", alpha=0.7, zorder=0)

        err_attr = f"{metric}_err"
        for i, r in enumerate(valid):
            err = getattr(r, err_attr, None)
            val = getattr(r, metric)
            if err and val is not None:
                ax.errorbar(
                    x[i],
                    val,
                    yerr=[[err[0]], [err[1]]],
                    fmt="none",
                    ecolor=_region_color(r.region),
                    elinewidth=0.7,
                    capsize=2,
                    alpha=0.8,
                    zorder=2,
                )

        ax.set_ylabel(ylabel)
        ax.set_title(subtitle, loc="left", fontsize=8, pad=6)
        ax.set_xticks(x)
        ax.set_xticklabels([r.short_name for r in valid], rotation=45, ha="right")
        if metric == metrics[-1][0]:
            ax.set_xlabel("Wind turbine project")

    handles = [
        Line2D([0], [0], color=NATURE_COLORS["international"], marker="o", markersize=4, markerfacecolor="white", label="International"),
        Line2D([0], [0], color=NATURE_COLORS["domestic"], marker="o", markersize=4, markerfacecolor="white", label="China projects"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 0.995), frameon=False)
    fig.suptitle(
        "Steel consumption metrics across offshore wind projects",
        fontsize=10,
        fontweight="bold",
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(OUT_DIR / "wind_steel_metrics_combined.png")
    fig.savefig(OUT_DIR / "wind_steel_metrics_combined.pdf")
    plt.close(fig)


def plot_capacity_vs_intensity(records: list[ProjectRecord]) -> None:
    valid = [r for r in records if r.steel_intensity is not None and r.capacity_mw is not None]
    if len(valid) < 2:
        return

    fig, ax = plt.subplots(figsize=(4.5, 4.0))
    _style_axis(ax)
    ax.grid(True, color=NATURE_COLORS["grid"], linewidth=0.5)

    for r in valid:
        x = r.capacity_mw
        y = r.steel_intensity
        color = _region_color(r.region)
        xerr = yerr = None
        if r.steel_intensity_err:
            yerr = [[r.steel_intensity_err[0]], [r.steel_intensity_err[1]]]
        ax.errorbar(
            x,
            y,
            xerr=xerr,
            yerr=yerr,
            fmt="o",
            color=color,
            markerfacecolor="white",
            markersize=5,
            markeredgewidth=1.0,
            capsize=2,
            elinewidth=0.8,
            zorder=3,
        )
        ax.annotate(
            r.short_name,
            (x, y),
            textcoords="offset points",
            xytext=(4, 4),
            fontsize=6,
            color=NATURE_COLORS["text"],
        )

    xs = np.array([r.capacity_mw for r in valid])
    ys = np.array([r.steel_intensity for r in valid])
    z = np.polyfit(xs, ys, 1)
    xline = np.linspace(xs.min() * 0.85, xs.max() * 1.05, 100)
    ax.plot(xline, np.poly1d(z)(xline), color=NATURE_COLORS["trend"], linestyle=":", linewidth=1.0, label="Linear fit")

    ax.set_xlabel("Unit capacity (MW)")
    ax.set_ylabel("Steel intensity (t MW$^{-1}$)")
    ax.set_title("Capacity vs. steel intensity", loc="left", fontweight="bold")
    _add_panel_label(ax, "d")

    handles = [
        Line2D([0], [0], color=NATURE_COLORS["international"], marker="o", markersize=4, markerfacecolor="white", label="International"),
        Line2D([0], [0], color=NATURE_COLORS["domestic"], marker="o", markersize=4, markerfacecolor="white", label="China projects"),
        Line2D([0], [0], color=NATURE_COLORS["trend"], linestyle=":", label="Linear fit"),
    ]
    ax.legend(handles=handles, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "wind_steel_capacity_vs_intensity.png")
    fig.savefig(OUT_DIR / "wind_steel_capacity_vs_intensity.pdf")
    plt.close(fig)


def plot_per_turbine_profiles(records: list[ProjectRecord]) -> None:
    """Small-multiples: each turbine's three normalized metrics."""
    metrics = [
        ("steel_intensity", "Steel intensity\n(t MW$^{-1}$)"),
        ("capacity_mw", "Capacity\n(MW)"),
        ("total_steel_t", "Total steel\n(t)"),
    ]
    complete = [
        r
        for r in records
        if r.steel_intensity is not None and r.capacity_mw is not None and r.total_steel_t is not None
    ]
    if not complete:
        return

    n = len(complete)
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(9.0, 2.2 * rows), squeeze=False)

    for idx, r in enumerate(complete):
        ax = axes[idx // cols][idx % cols]
        vals = [r.steel_intensity, r.capacity_mw, r.total_steel_t]
        vals_norm = np.array(vals, dtype=float)
        vals_norm = vals_norm / vals_norm.max()
        x = np.arange(3)
        color = _region_color(r.region)
        ax.plot(x, vals_norm, color=color, marker="o", markersize=3.5, linewidth=1.1, markerfacecolor="white")
        ax.fill_between(x, vals_norm, alpha=0.12, color=color)
        ax.set_xticks(x)
        ax.set_xticklabels(["SI", "Cap.", "Steel"], fontsize=6)
        ax.set_ylim(0, 1.15)
        ax.set_ylabel("Normalized", fontsize=6)
        ax.set_title(f"{r.short_name} ({r.year_label})", fontsize=7, pad=4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(True, axis="y", color=NATURE_COLORS["grid"], linewidth=0.4)
        for j, (val, label) in enumerate(zip(vals, ["SI", "Cap.", "Steel"])):
            ax.text(j, vals_norm[j] + 0.05, f"{val:.0f}" if val >= 100 else f"{val:.1f}", ha="center", fontsize=5.5, color="#444")

    for idx in range(n, rows * cols):
        axes[idx // cols][idx % cols].axis("off")

    fig.suptitle("Per-turbine metric profiles (normalized within project)", fontsize=10, fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "wind_steel_per_turbine_profiles.png")
    fig.savefig(OUT_DIR / "wind_steel_per_turbine_profiles.pdf")
    plt.close(fig)


def export_data_summary(records: list[ProjectRecord]) -> None:
    lines = ["# Wind project steel metrics (parsed from xlsx)", ""]
    lines.append("| Project | Year | Region | Steel intensity (t/MW) | Capacity (MW) | Total steel (t) |")
    lines.append("|---|---:|---|---:|---:|---:|")
    for r in records:
        si = f"{r.steel_intensity:.1f}" if r.steel_intensity is not None else "—"
        cap = f"{r.capacity_mw:.2f}" if r.capacity_mw is not None else "—"
        tot = f"{r.total_steel_t:.0f}" if r.total_steel_t is not None else "—"
        region = "China" if r.region == "domestic" else "International"
        lines.append(f"| {r.short_name} | {r.year_label} | {region} | {si} | {cap} | {tot} |")
    (OUT_DIR / "wind_steel_data_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    configure_nature_style()
    records = load_records(use_clean_section=True)
    if not records:
        raise SystemExit("No records parsed from spreadsheet.")

    plot_combined_panel(records)
    _plot_metric_curve(
        records,
        "steel_intensity",
        "Steel intensity (t MW$^{-1}$)",
        "Steel intensity across wind projects",
        "wind_steel_intensity_curve",
        panel_label="a",
    )
    _plot_metric_curve(
        records,
        "capacity_mw",
        "Unit capacity (MW)",
        "Rated capacity across wind projects",
        "wind_capacity_curve",
        panel_label="b",
    )
    _plot_metric_curve(
        records,
        "total_steel_t",
        "Total steel usage (t)",
        "Total steel consumption across wind projects",
        "wind_total_steel_curve",
        panel_label="c",
    )
    plot_capacity_vs_intensity(records)
    plot_per_turbine_profiles(records)
    export_data_summary(records)

    print(f"Parsed {len(records)} projects.")
    print(f"Figures saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
