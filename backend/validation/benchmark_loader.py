"""Load fleet benchmark data from 风电项目钢耗强度统计表.xlsx."""
from __future__ import annotations

import datetime
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_XLSX = _REPO_ROOT / "rules" / "风电项目钢耗强度统计表.xlsx"

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

NAME_FIX = {
    "Haizhuang Fuyao\uFF082022\uFF09": "海装扶瑶(2022)",
    "Haiyou Guanlan\uFF082023\uFF09": "海油观澜(2023)",
    "Tuqiang\uFF082026\uFF09": "图强(2026)",
    "AI\uFF082026\uFF09": "AI(2026)",
}


@dataclass
class BenchmarkRecord:
    name: str
    short_name: str
    year: int | None
    year_label: str
    year_status: str
    region: str
    steel_intensity: float | None
    capacity_mw: float | None
    total_steel_t: float | None

    @property
    def sort_year(self) -> int:
        return self.year if self.year is not None else 9999


_YEAR_IN_NAME = re.compile(r"[\uff08(](\d{4})[\uff09)]")
_PLANNED_NAME_HINTS = ("AI", "Tuqiang", "图强", "Linghang", "领航", "观澜", "扶瑶", "gongxiang", "Tiancheng")


def parse_year_info(name: str, *, current_year: int | None = None) -> tuple[int | None, str, str]:
    """Return (year, display_label, status) where status is commissioned | planned | unknown."""
    now = current_year or datetime.date.today().year
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
                m = re.match(r"([A-Z]+)", ref)
                if not m:
                    continue
                col = m.group(1)
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


def _parse_numeric(text: str) -> float | None:
    if not text or not str(text).strip():
        return None
    s = str(text).strip().lower().replace("about ", "").replace("almost ", "")
    if "/" in s:
        parts = [_parse_numeric(p.strip()) for p in s.split("/") if p.strip()]
        nums = [p for p in parts if p is not None]
        if len(nums) >= 2:
            return (min(nums) + max(nums)) / 2.0
        if nums:
            return nums[0]
    m = re.search(r"<\s*([\d.]+)", s)
    if m:
        return float(m.group(1))
    m = re.search(r">\s*([\d.]+)", s)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)", s)
    return float(m.group(1)) if m else None


def _short_label(name: str) -> str:
    name = NAME_FIX.get(name, name)
    name = re.sub(r"[\uff08(]\d{4}[\uff09)]", "", name).strip()
    for key, val in {
        "Three gorgesYinling": "三峡引领",
        "Three gorges Linghang": "三峡领航",
        "Tuqiang": "图强",
    }.items():
        if key in name:
            return val
    return name[:24]


def _is_domestic(name: str) -> bool:
    keys = ("Three gorges", "Haizhuang", "Haiyou", "Mingyang", "GHN", "Tuqiang", "AI", "三峡", "图强")
    return any(k in name for k in keys)


def load_benchmark_records(xlsx_path: Path | None = None) -> list[BenchmarkRecord]:
    path = (xlsx_path or DEFAULT_XLSX).resolve()
    rows = _read_xlsx_rows(path)
    section = 0
    data_rows: list[dict[str, str]] = []
    for row in rows:
        if row.get("C") == "Steel intensity" and row.get("D") == "Unit Capacity":
            section += 1
            continue
        if row.get("C") == "t/MW" or "B" not in row:
            continue
        if section < 2:
            continue
        data_rows.append(row)

    seen: set[str] = set()
    out: list[BenchmarkRecord] = []
    for row in data_rows:
        raw = row["B"]
        if raw in seen:
            continue
        seen.add(raw)
        cap = float(row["D"]) if row.get("D") else None
        si = _parse_numeric(row.get("C", ""))
        tot = _parse_numeric(row.get("E", ""))
        if si is None and cap is None and tot is None:
            continue
        year, year_label, year_status = parse_year_info(raw)
        out.append(
            BenchmarkRecord(
                name=raw,
                short_name=_short_label(raw),
                year=year,
                year_label=year_label,
                year_status=year_status,
                region="domestic" if _is_domestic(raw) else "international",
                steel_intensity=si,
                capacity_mw=cap,
                total_steel_t=tot,
            )
        )
    out.sort(key=lambda r: (r.sort_year, r.short_name))
    return out


def filter_peers(
    records: list[BenchmarkRecord],
    *,
    capacity_MW: float | None = None,
    peer_set: str | None = None,
    tolerance_mw: float = 4.0,
) -> list[BenchmarkRecord]:
    pool = records
    if peer_set == "domestic_2024_plus":
        pool = [
            r
            for r in records
            if r.region == "domestic" and r.year is not None and r.year >= 2024
        ]
    elif peer_set == "same_capacity_20mw":
        pool = [
            r
            for r in records
            if r.capacity_mw is not None and abs(r.capacity_mw - 20.0) < 0.5
        ]
    if capacity_MW is not None:
        pool = [
            r
            for r in pool
            if r.capacity_mw is None or abs(r.capacity_mw - capacity_MW) <= tolerance_mw
        ]
    return pool or records


def percentile_rank(value: float, sample: list[float], *, lower_is_better: bool = True) -> float:
    if not sample:
        return 50.0
    if lower_is_better:
        better = sum(1 for v in sample if value <= v)
    else:
        better = sum(1 for v in sample if value >= v)
    return 100.0 * better / len(sample)


def find_reference(records: list[BenchmarkRecord], *name_parts: str) -> BenchmarkRecord | None:
    for r in records:
        if any(p.lower() in r.name.lower() or p in r.short_name for p in name_parts):
            if r.steel_intensity is not None:
                return r
    return None


def fleet_median(values: list[float]) -> float | None:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    ordered = sorted(nums)
    return ordered[len(ordered) // 2]


def enrich_benchmark_metrics(
    metrics_dict: dict[str, float | None],
    *,
    target_power_MW: float,
    steel_mass_t_source: str,
    records: list[BenchmarkRecord] | None = None,
) -> dict[str, float | None]:
    """Derive fleet-relative ratios and estimation confidence for plausibility rules."""
    bench = records or load_benchmark_records()
    peers_20 = filter_peers(bench, capacity_MW=target_power_MW, peer_set="same_capacity_20mw")
    sample_si = [float(r.steel_intensity) for r in peers_20 if r.steel_intensity is not None]
    sample_mass = [float(r.total_steel_t) for r in peers_20 if r.total_steel_t is not None]

    tuqiang = find_reference(bench, "Tuqiang", "图强")
    tuq_si = float(tuqiang.steel_intensity) if tuqiang and tuqiang.steel_intensity else 278.0

    intensity = metrics_dict.get("steel_intensity_t_per_MW")
    total_steel = metrics_dict.get("total_steel_t")

    out = dict(metrics_dict)
    if isinstance(intensity, (int, float)) and tuq_si > 0:
        out["intensity_ratio_vs_tuqiang"] = float(intensity) / tuq_si

    median_mass = fleet_median(sample_mass)
    if isinstance(total_steel, (int, float)) and median_mass and median_mass > 0:
        out["total_steel_ratio_vs_fleet_median"] = float(total_steel) / median_mass

    confidence = {
        "validation_overrides.steel_mass_t": 1.0,
        "shell_surface_model": 0.62,
        "volume_proxy": 0.72,
        "missing_geometry": 0.0,
    }.get(steel_mass_t_source, 0.5)
    out["estimation_confidence_score"] = confidence
    return out
