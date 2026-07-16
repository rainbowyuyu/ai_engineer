"""Blend surrogate predictions with heuristic proxies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.surrogate.config import load_surrogate_config


@dataclass
class BlendedEconomics:
    unit_cost_cny_per_MW: float | None
    construction_years: float | None
    fatigue_life_years: float | None
    unit_cost_source: str
    construction_years_source: str
    fatigue_life_source: str
    alpha_used: float
    notes: list[str]


def derive_economics_from_static(
    *,
    steel_mass_t: float,
    steel_intensity_t_per_MW: float,
    max_uc_static: float,
    pitch_proxy_deg: float,
) -> tuple[float | None, float | None, float | None]:
    """Map static surrogate outputs to AI Review economic proxies."""
    ref_int = 255.5
    ref_cost = 2500.0
    unit_cost = steel_intensity_t_per_MW * (ref_cost / ref_int) if steel_intensity_t_per_MW > 0 else None

    base = 2.0
    steel_term = min(2.2, steel_mass_t / 6000.0) if steel_mass_t > 0 else 0.4
    pitch_term = 0.1 if pitch_proxy_deg > 4.0 else 0.0
    construction = base + steel_term + pitch_term

    life = 25.0
    if max_uc_static > 0.85:
        life -= 2.0
    elif max_uc_static > 0.75:
        life -= 1.0
    else:
        life += 0.5
    if pitch_proxy_deg > 4.5:
        life -= 1.0
    fatigue = max(18.0, min(30.0, life))

    return unit_cost, construction, fatigue


def blend_economics(
    heuristic: tuple[float | None, float | None, float | None],
    surrogate: tuple[float | None, float | None, float | None],
    *,
    alpha: float,
    sources: tuple[str, str, str],
) -> BlendedEconomics:
    """final = alpha * surrogate + (1-alpha) * heuristic for each field."""
    notes: list[str] = []
    h_cost, h_const, h_fat = heuristic
    s_cost, s_const, s_fat = surrogate

    def mix(h: float | None, s: float | None) -> float | None:
        if h is None and s is None:
            return None
        if h is None:
            return s
        if s is None:
            return h
        return alpha * s + (1.0 - alpha) * h

    cost = mix(h_cost, s_cost)
    const = mix(h_const, s_const)
    fat = mix(h_fat, s_fat)
    if alpha > 0:
        notes.append(f"经济性指标：物理代理混合 α={alpha:.2f}")

    src_suffix = "_surrogate_blend" if alpha > 0 else ""
    return BlendedEconomics(
        unit_cost_cny_per_MW=cost,
        construction_years=const,
        fatigue_life_years=fat,
        unit_cost_source=sources[0] + src_suffix,
        construction_years_source=sources[1] + src_suffix,
        fatigue_life_source=sources[2] + src_suffix,
        alpha_used=alpha,
        notes=notes,
    )


def choose_alpha(physics_residual: float, cfg: dict[str, Any] | None = None) -> float:
    cfg = cfg or load_surrogate_config()
    blend = cfg.get("blend") or {}
    alpha_default = float(blend.get("alpha_default") or 0.7)
    threshold = float(blend.get("physics_residual_threshold") or 0.35)
    if physics_residual > threshold:
        return 0.0
    return alpha_default
