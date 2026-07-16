"""Shared scoring primitives for AI Review and Regulatory Review."""
from __future__ import annotations

DIMENSION_KEYS = (
    "capacity_mw",
    "steel_per_mw",
    "unit_cost",
    "construction_years",
    "fatigue_life",
)

DEFAULT_LABELS_ZH = {
    "capacity_mw": "单机兆瓦数",
    "steel_per_mw": "单位兆瓦用钢量",
    "unit_cost": "单位造价",
    "construction_years": "施工年限",
    "fatigue_life": "疲劳寿命",
}

DEFAULT_UNITS = {
    "capacity_mw": "MW",
    "steel_per_mw": "t/MW",
    "unit_cost": "万元/MW",
    "construction_years": "年",
    "fatigue_life": "年",
}


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def score_capacity_mw(value: float, target: float) -> float:
    delta = abs(value - target)
    if delta <= 0.5:
        return 98.0
    if delta <= 2.0:
        return clamp(95.0 - (delta - 0.5) * 12.0, 72.0, 98.0)
    return clamp(72.0 - (delta - 2.0) * 8.0, 45.0, 72.0)


def score_lower_better(
    value: float,
    ref: float,
    *,
    excellent_ratio: float = 1.0,
    pass_ratio: float = 1.18,
) -> float:
    if ref <= 0:
        return 60.0
    ratio = value / ref
    if ratio <= excellent_ratio:
        return 98.0
    if ratio <= 1.0:
        return clamp(98.0 - (ratio - excellent_ratio) / max(1.0 - excellent_ratio, 1e-9) * 8.0, 90.0, 98.0)
    if ratio <= pass_ratio:
        return clamp(90.0 - (ratio - 1.0) / max(pass_ratio - 1.0, 1e-9) * 30.0, 60.0, 90.0)
    return clamp(60.0 - (ratio - pass_ratio) * 80.0, 25.0, 60.0)


def score_higher_better(value: float, ref: float, *, pass_ratio: float = 0.88) -> float:
    if ref <= 0:
        return 60.0
    ratio = value / ref
    if ratio >= 1.0:
        return 98.0
    if ratio >= pass_ratio:
        return clamp(60.0 + (ratio - pass_ratio) / max(1.0 - pass_ratio, 1e-9) * 38.0, 60.0, 98.0)
    return clamp(40.0 + (ratio / pass_ratio) * 20.0, 25.0, 60.0)


def innovation_bonus_lower(value: float, proposed: float, *, max_bonus: float) -> float:
    if proposed <= 0 or value > proposed:
        return 0.0
    margin = (proposed - value) / proposed
    return min(max_bonus, margin * max_bonus * 2.5)


def innovation_bonus_higher(value: float, proposed: float, *, max_bonus: float) -> float:
    if proposed <= 0 or value < proposed:
        return 0.0
    margin = (value - proposed) / proposed
    return min(max_bonus, margin * max_bonus * 2.5)


def with_innovation_bonus(base: float, bonus: float) -> float:
    return round(min(98.0, base + bonus), 2)
