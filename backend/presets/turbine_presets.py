"""Turbine / platform MW presets (5 / 10 / 15 / 20) for closed-loop demos."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

# NREL 5 MW baseline (matches mixed_platform_steel defaults)
BASE_RATED_POWER_MW = 5.0
BASE_ROTOR_DIA_M = 126.0
BASE_HUB_HEIGHT_M = 90.0
BASE_RNA_MASS_KG = 542_900.0
BASE_CLOAD_MAG = -5.0e6  # vertical concentrated load magnitude (checklist default scale)
BASE_HORIZONTAL_THRUST_N = 2.81e5  # OC4 methodology trial thrust at ~5 MW


@dataclass(frozen=True)
class ColumnPickThresholds:
    """OC4-style vertical column heuristics (mm), scalable with platform scale."""

    center_r_min: float = 1200.0
    center_r_max: float = 2200.0
    center_len_min: float = 20000.0
    vertical_r_min: float = 1200.0
    vertical_len_min: float = 5000.0
    outer_len_min: float = 18000.0

    def scaled(self, scale: float) -> "ColumnPickThresholds":
        s = max(0.5, float(scale))
        return ColumnPickThresholds(
            center_r_min=self.center_r_min * s,
            center_r_max=self.center_r_max * s,
            center_len_min=self.center_len_min,  # vertical extent often fixed with draft
            vertical_r_min=self.vertical_r_min * s,
            vertical_len_min=self.vertical_len_min,
            outer_len_min=self.outer_len_min,
        )

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ColumnPickThresholds":
        if not data:
            return cls()
        base = cls()
        return cls(
            center_r_min=float(data.get("center_r_min", base.center_r_min)),
            center_r_max=float(data.get("center_r_max", base.center_r_max)),
            center_len_min=float(data.get("center_len_min", base.center_len_min)),
            vertical_r_min=float(data.get("vertical_r_min", base.vertical_r_min)),
            vertical_len_min=float(data.get("vertical_len_min", base.vertical_len_min)),
            outer_len_min=float(data.get("outer_len_min", base.outer_len_min)),
        )


@dataclass(frozen=True)
class TurbinePreset:
    id: str
    label: str
    target_power_mw: float
    base_rated_power_mw: float = BASE_RATED_POWER_MW
    rotor_dia_m: float = BASE_ROTOR_DIA_M
    hub_height_m: float = BASE_HUB_HEIGHT_M
    rna_mass_kg: float = BASE_RNA_MASS_KG
    draft_m: float = 20.0
    wall_thickness_m: float = 0.06
    cload_mag: float = BASE_CLOAD_MAG
    horizontal_thrust_n: float = BASE_HORIZONTAL_THRUST_N
    band_scale: float = 1.22
    z_fix_band: float = 800.0
    steel_intensity_t_per_mw: float = 300.0
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def horizontal_scale(self) -> float:
        return math.sqrt(max(1e-6, self.target_power_mw) / max(1e-6, self.base_rated_power_mw))

    @property
    def column_thresholds(self) -> ColumnPickThresholds:
        return ColumnPickThresholds().scaled(self.horizontal_scale)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["notes"] = list(self.notes)
        d["horizontal_scale"] = self.horizontal_scale
        d["column_thresholds"] = self.column_thresholds.to_dict()
        return d


def _scale_from_base(target_mw: float) -> float:
    return math.sqrt(max(1e-6, float(target_mw)) / BASE_RATED_POWER_MW)


def _build_preset(target_mw: float, *, label: str | None = None) -> TurbinePreset:
    s = _scale_from_base(target_mw)
    # RNA ~ (scale)^0.88 — same exponent as mixed_platform_steel
    rna = BASE_RNA_MASS_KG * (s**0.88)
    rotor = BASE_ROTOR_DIA_M * s
    hub = BASE_HUB_HEIGHT_M * s
    # Loads: area ∝ s² for thrust; vertical cload scaled by power ratio
    thrust = BASE_HORIZONTAL_THRUST_N * (s**2)
    cload = BASE_CLOAD_MAG * (target_mw / BASE_RATED_POWER_MW)
    pid = str(int(target_mw)) if float(target_mw).is_integer() else f"{target_mw:g}"
    return TurbinePreset(
        id=pid,
        label=label or f"{pid} MW FOWT (OC4 family, scaled from {BASE_RATED_POWER_MW:g} MW)",
        target_power_mw=float(target_mw),
        rotor_dia_m=rotor,
        hub_height_m=hub,
        rna_mass_kg=rna,
        cload_mag=cload,
        horizontal_thrust_n=thrust,
        notes=(
            f"Horizontal scale √(P/{BASE_RATED_POWER_MW:g}) = {s:.4f}",
            "Geometry remains OC4/BESO semisub family unless user replaces CAD.",
        ),
    )


_PRESETS: dict[str, TurbinePreset] = {
    "5": _build_preset(5.0, label="5 MW (NREL baseline scale)"),
    "10": _build_preset(10.0, label="10 MW FOWT demo"),
    "15": _build_preset(15.0, label="15 MW FOWT demo"),
    "20": _build_preset(20.0, label="20 MW FOWT demo (legacy manuscript target)"),
}


def list_presets() -> list[TurbinePreset]:
    return [_PRESETS[k] for k in ("5", "10", "15", "20")]


def get_preset(preset_id: str | float | int) -> TurbinePreset:
    key = str(preset_id).strip().lower().replace("mw", "").strip()
    if key in _PRESETS:
        return _PRESETS[key]
    try:
        mw = float(key)
    except ValueError as e:
        raise KeyError(f"unknown turbine preset: {preset_id!r}; choose 5/10/15/20") from e
    # nearest known or synthesize
    if key in _PRESETS:
        return _PRESETS[key]
    for p in list_presets():
        if abs(p.target_power_mw - mw) < 0.05:
            return p
    return _build_preset(mw)


def nearest_preset_id(capacity_mw: float) -> str:
    caps = [5.0, 10.0, 15.0, 20.0]
    best = min(caps, key=lambda c: abs(c - float(capacity_mw)))
    return str(int(best))


def apply_preset_to_checklist(checklist: Any, preset: TurbinePreset) -> Any:
    """Mutate / return DesignChecklist with preset fields."""
    checklist.project.target_capacity_mw = float(preset.target_power_mw)
    checklist.structural_assumptions.draft_m = float(preset.draft_m)
    checklist.structural_assumptions.wall_thickness_m = float(preset.wall_thickness_m)
    checklist.structural_assumptions.scale_factor = float(preset.horizontal_scale)
    checklist.performance_targets.steel_intensity_t_per_MW = float(preset.steel_intensity_t_per_mw)
    checklist.job_descriptor.theta.oc4_loads.cload_mag = float(preset.cload_mag)
    checklist.job_descriptor.theta.oc4_loads.band_scale = float(preset.band_scale)
    checklist.job_descriptor.theta.oc4_loads.z_fix_band = float(preset.z_fix_band)
    note = f"turbine_preset={preset.id}MW scale={preset.horizontal_scale:.4f}"
    if note not in checklist.assumptions:
        checklist.assumptions = [note, *list(checklist.assumptions or [])][:20]
    # drop capacity gap if resolved
    checklist.gaps = [g for g in (checklist.gaps or []) if "capacity" not in str(g).lower()]
    return checklist


def preset_session_meta_patch(preset: TurbinePreset) -> dict[str, Any]:
    return {
        "turbine_preset_id": preset.id,
        "target_power_mw": preset.target_power_mw,
        "base_rated_power_mw": preset.base_rated_power_mw,
        "horizontal_scale": preset.horizontal_scale,
        "rotor_dia_m": preset.rotor_dia_m,
        "hub_height_m": preset.hub_height_m,
        "rna_mass_kg": preset.rna_mass_kg,
        "cload_mag": preset.cload_mag,
        "horizontal_thrust_n": preset.horizontal_thrust_n,
        "column_pick_thresholds": preset.column_thresholds.to_dict(),
        "validation_target_mw": preset.target_power_mw,
        "domain_envelope": "triangle_prism",
    }
