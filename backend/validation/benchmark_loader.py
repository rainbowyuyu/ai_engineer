"""Load fleet benchmark data from 风电项目钢耗强度统计表.xlsx."""
from __future__ import annotations

import datetime
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_XLSX = _REPO_ROOT / "rules" / "风电项目钢耗强度统计表.xlsx"
DEFAULT_FLEET_METRICS = _REPO_ROOT / "rules" / "fleet_ai_review_metrics.yaml"
DEFAULT_FLEET_REFERENCE = _REPO_ROOT / "rules" / "fleet_ai_review_reference.yaml"
DEFAULT_FLEET_ROSTER = _REPO_ROOT / "rules" / "fleet_table_roster.yaml"

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
    unit_cost_cny_per_MW: float | None = None
    construction_years: float | None = None
    fatigue_life_years: float | None = None
    metrics_source: str = ""
    metrics_notes: list[str] = field(default_factory=list)

    @property
    def sort_year(self) -> int:
        return self.year if self.year is not None else 9999


_YEAR_IN_NAME = re.compile(r"[\uff08(](\d{4})[\uff09)]")
_PLANNED_NAME_HINTS = ("AI", "Tuqiang", "图强", "Linghang", "领航", "观澜", "扶瑶", "gongxiang", "Tiancheng")


def is_proposed_alias_entry(record: BenchmarkRecord) -> bool:
    """Exclude duplicate 'AI' fleet row — same design as the proposed candidate."""
    sn = (record.short_name or "").strip()
    if sn == "AI":
        return True
    name = record.name or ""
    if name.startswith("AI") and "2026" in name:
        return True
    return False


def _load_excluded_xlsx_match(path: Path | None = None) -> tuple[str, ...]:
    p = (path or DEFAULT_FLEET_ROSTER).resolve()
    if not p.is_file():
        return ("Kincardine Ph1", "AI")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    items = raw.get("excluded_xlsx_match") or ["Kincardine Ph1", "AI"]
    return tuple(str(i) for i in items if i)


def is_excluded_fleet_entry(record: BenchmarkRecord, excluded: tuple[str, ...] | None = None) -> bool:
    """Drop xlsx rows that must not appear in the fleet comparison table."""
    if is_proposed_alias_entry(record):
        return True
    keys = excluded if excluded is not None else _load_excluded_xlsx_match()
    name = record.name or ""
    short = record.short_name or ""
    for key in keys:
        if key in name or key in short:
            return True
    return False


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


def _load_fleet_metrics_supplement(path: Path | None = None) -> list[dict[str, Any]]:
    p = (path or DEFAULT_FLEET_METRICS).resolve()
    if not p.is_file():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(raw.get("projects") or [])


def _match_fleet_supplement(name: str, short_name: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_len = -1
    for row in rows:
        keys = row.get("match") or []
        for k in keys:
            if not k:
                continue
            if k in name or k in short_name:
                if len(k) > best_len:
                    best = row
                    best_len = len(k)
    return best


def _load_fleet_table_roster(path: Path | None = None) -> frozenset[str]:
    p = (path or DEFAULT_FLEET_ROSTER).resolve()
    if not p.is_file():
        return frozenset()
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    ids: list[str] = []
    ids.extend(raw.get("commissioned_ids") or [])
    ids.extend(raw.get("planned_ids") or [])
    return frozenset(str(i) for i in ids if i)


def _reference_by_id(reference: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r.get("id")): r for r in reference if r.get("id")}


def _record_on_roster(record: BenchmarkRecord, roster_ids: frozenset[str], ref_by_id: dict[str, dict[str, Any]]) -> bool:
    if not roster_ids:
        return True
    best_id: str | None = None
    best_len = -1
    for ref_id in roster_ids:
        ref = ref_by_id.get(ref_id)
        if not ref:
            continue
        score = _reference_match_score(record, ref)
        if score > best_len:
            best_id = ref_id
            best_len = score
    return best_len >= 0


def _record_from_reference(ref: dict[str, Any], supplement: list[dict[str, Any]]) -> BenchmarkRecord | None:
    if ref.get("status") in ("candidate",):
        return None
    m = ref.get("metrics") or {}
    cap = m.get("capacity_mw")
    si = m.get("steel_t_per_MW")
    if cap is None:
        return None
    year = ref.get("year")
    year_status = ref.get("status") or "unknown"
    if year_status == "commissioned" and year:
        year_label = str(year)
    elif year_status == "planned" and year:
        year_label = f"规划·{year}"
    else:
        year_label = str(year) if year else "未标注"
    name_en = ref.get("name_en") or ref.get("short_name") or ref.get("id")
    rec = BenchmarkRecord(
        name=str(name_en),
        short_name=str(ref.get("short_name") or name_en),
        year=int(year) if year is not None else None,
        year_label=year_label,
        year_status=year_status if year_status in ("commissioned", "planned") else "unknown",
        region=str(ref.get("region") or "international"),
        steel_intensity=float(si) if si is not None else None,
        capacity_mw=float(cap),
        total_steel_t=float(m["steel_total_t"])
        if m.get("steel_total_t")
        else (float(si) * float(cap) if si is not None else None),
        unit_cost_cny_per_MW=float(m["unit_cost_cny_per_MW"]) if m.get("unit_cost_cny_per_MW") is not None else None,
        construction_years=float(m["construction_years"]) if m.get("construction_years") is not None else None,
        fatigue_life_years=float(m["fatigue_life_years"]) if m.get("fatigue_life_years") is not None else None,
        metrics_source="fleet_ai_review_reference.yaml",
        metrics_notes=[str(ref.get("sources", {}).get("steel_t_per_MW") or "reference yaml")],
    )
    return enrich_record_metrics(rec, supplement)


def _apply_reference_override(record: BenchmarkRecord, ref: dict[str, Any]) -> BenchmarkRecord:
    """Prefer verified reference metrics over simplified xlsx rows."""
    m = ref.get("metrics") or {}
    conf = ref.get("confidence") or {}
    si = m.get("steel_t_per_MW")
    cap = m.get("capacity_mw")
    tot = m.get("steel_total_t")
    notes = list(record.metrics_notes)
    if ref.get("notes"):
        notes.append(str(ref["notes"]))
    updated = replace(
        record,
        steel_intensity=float(si) if si is not None else record.steel_intensity,
        capacity_mw=float(cap) if cap is not None else record.capacity_mw,
        total_steel_t=float(tot) if tot is not None else record.total_steel_t,
        unit_cost_cny_per_MW=float(m["unit_cost_cny_per_MW"])
        if m.get("unit_cost_cny_per_MW") is not None
        else record.unit_cost_cny_per_MW,
        construction_years=float(m["construction_years"])
        if m.get("construction_years") is not None
        else record.construction_years,
        fatigue_life_years=float(m["fatigue_life_years"])
        if m.get("fatigue_life_years") is not None
        else record.fatigue_life_years,
        metrics_source="fleet_ai_review_reference.yaml",
        metrics_notes=notes,
    )
    if conf.get("steel_t_per_MW") in ("verified", "reported") and si is not None:
        updated = replace(updated, steel_intensity=float(si))
    if conf.get("capacity_mw") in ("verified", "reported") and cap is not None:
        updated = replace(updated, capacity_mw=float(cap))
    return updated


def _compact_match_text(text: str) -> str:
    """Ignore spaces for xlsx vs reference name matching (e.g. 'Name(2020)' vs 'Name (2020)')."""
    return re.sub(r"\s+", "", (text or "").strip()).lower()


def _reference_match_keys(ref: dict[str, Any]) -> list[str]:
    keys = [str(ref.get("short_name") or ""), str(ref.get("name_en") or ""), str(ref.get("id") or "")]
    keys.extend(str(k) for k in (ref.get("match") or []) if k)
    return [k for k in keys if k]


def _reference_match_score(record: BenchmarkRecord, ref: dict[str, Any]) -> int:
    best = -1
    name_c = _compact_match_text(record.name)
    short_c = _compact_match_text(record.short_name)
    for k in _reference_match_keys(ref):
        kc = _compact_match_text(k)
        if not kc:
            continue
        if kc in name_c or kc in short_c or k in record.name or k in record.short_name:
            best = max(best, len(k))
    return best


def _find_reference_for_record(record: BenchmarkRecord, reference: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_len = -1
    for ref in reference:
        score = _reference_match_score(record, ref)
        if score > best_len:
            best = ref
            best_len = score
    return best if best_len >= 0 else None


def enrich_record_metrics(
    record: BenchmarkRecord,
    supplement: list[dict[str, Any]] | None = None,
) -> BenchmarkRecord:
    """Attach public unit cost / schedule / fatigue data when available."""
    supplement = supplement if supplement is not None else _load_fleet_metrics_supplement()
    row = _match_fleet_supplement(record.name, record.short_name, supplement)
    if not row:
        return record
    notes = list(record.metrics_notes)
    if row.get("source"):
        notes.append(str(row["source"]))
    return BenchmarkRecord(
        name=record.name,
        short_name=record.short_name,
        year=record.year,
        year_label=record.year_label,
        year_status=record.year_status,
        region=record.region,
        steel_intensity=record.steel_intensity,
        capacity_mw=record.capacity_mw,
        total_steel_t=record.total_steel_t,
        unit_cost_cny_per_MW=row.get("unit_cost_cny_per_MW"),
        construction_years=row.get("construction_years"),
        fatigue_life_years=row.get("fatigue_life_years"),
        metrics_source="fleet_ai_review_metrics.yaml",
        metrics_notes=notes,
    )


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
    supplement = _load_fleet_metrics_supplement()
    reference = _load_fleet_reference_projects()
    roster_ids = _load_fleet_table_roster()
    ref_by_id = _reference_by_id(reference)

    out = [enrich_record_metrics(r, supplement) for r in out]
    merged: list[BenchmarkRecord] = []
    for rec in out:
        ref = _find_reference_for_record(rec, reference)
        if ref is not None:
            rec = _apply_reference_override(rec, ref)
        merged.append(rec)

    merged = [r for r in merged if not is_excluded_fleet_entry(r)]
    if roster_ids:
        merged = [r for r in merged if _record_on_roster(r, roster_ids, ref_by_id)]
    merged.sort(key=lambda r: (r.sort_year, r.short_name))
    return merged


def _load_fleet_reference_projects(path: Path | None = None) -> list[dict[str, Any]]:
    p = (path or DEFAULT_FLEET_REFERENCE).resolve()
    if not p.is_file():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(raw.get("projects") or [])


def _record_matches_reference(record: BenchmarkRecord, ref: dict[str, Any]) -> bool:
    return _reference_match_score(record, ref) >= 0


def merge_reference_only_records(
    records: list[BenchmarkRecord],
    reference: list[dict[str, Any]] | None = None,
) -> list[BenchmarkRecord]:
    """Deprecated — roster merge runs inside load_benchmark_records()."""
    return list(records)


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
        "mixed_platform_steel_restruction4": 0.95,
        "shell_surface_model": 0.62,
        "volume_proxy": 0.72,
        "missing_geometry": 0.0,
    }.get(steel_mass_t_source, 0.5)
    out["estimation_confidence_score"] = confidence
    return out
