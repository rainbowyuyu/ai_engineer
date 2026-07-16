"""Feature extraction from geometry JSON (aligned with validation metrics)."""
from __future__ import annotations

from typing import Any

import numpy as np

from backend.surrogate.config import feature_keys, load_surrogate_config
from backend.validation.geometry_metrics import extract_geometry_metrics, metrics_as_dict


def extract_feature_dict(geometry: dict[str, Any]) -> dict[str, float | None]:
    m = extract_geometry_metrics(geometry)
    md = metrics_as_dict(m)
    keys = feature_keys()
    return {k: _as_float(md.get(k)) for k in keys}


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def feature_vector(geometry: dict[str, Any], *, keys: list[str] | None = None) -> np.ndarray:
    keys = keys or feature_keys()
    fd = extract_feature_dict(geometry)
    cfg = load_surrogate_config()
    defaults = _feature_defaults(cfg)
    out: list[float] = []
    for k in keys:
        v = fd.get(k)
        if v is None:
            v = defaults.get(k, 0.0)
        out.append(float(v))
    return np.array(out, dtype=np.float64)


def _feature_defaults(cfg: dict[str, Any]) -> dict[str, float]:
    return {
        "target_power_MW": 20.0,
        "wall_thickness_m": 0.06,
        "scale_factor": 1.0,
        "leg_taper_ratio": 1.2,
    }


def normalize_features(
    x: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
) -> np.ndarray:
    std_safe = np.where(std < 1e-8, 1.0, std)
    return (x - mean) / std_safe
