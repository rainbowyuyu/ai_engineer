"""Static and dynamic surrogate target schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Phase 1 static labels (CalculiX / analytical anchor)
STATIC_TARGET_KEYS = (
    "max_uc_static",
    "compliance_static",
    "steel_mass_t",
    "pitch_proxy_deg",
)

# Phase 2 dynamic (Zwind envelope) — see zwind_adapter.py
DYNAMIC_TARGET_KEYS = (
    "system_frequency_hz",
    "platform_pitch_deg",
    "structural_uc_max",
    "fatigue_damage",
    "mooring_tension_kn",
)


@dataclass
class StaticLabels:
    max_uc_static: float
    compliance_static: float
    steel_mass_t: float
    pitch_proxy_deg: float
    source: str = "analytical"
    inp_path: str | None = None

    def as_dict(self) -> dict[str, float]:
        return {
            "max_uc_static": self.max_uc_static,
            "compliance_static": self.compliance_static,
            "steel_mass_t": self.steel_mass_t,
            "pitch_proxy_deg": self.pitch_proxy_deg,
        }


@dataclass
class DatasetRow:
    sample_id: str
    features: dict[str, float | None]
    labels: dict[str, float]
    geometry_path: str | None = None
    inp_path: str | None = None
    source: str = "synthetic"

    def to_manifest_entry(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "features": self.features,
            "labels": self.labels,
            "geometry_path": self.geometry_path,
            "inp_path": self.inp_path,
            "source": self.source,
        }
