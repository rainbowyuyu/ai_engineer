"""
半潜平台库缩放 + 静倾约束下的水平尺寸优化（源自 restruction.py）。

流程：按目标 MW 选取最近参考平台 → 转子/几何初缩放 → SLSQP 最小化 x³
且纵摇角 ≤ pitch_limit → 输出优化后柱径/间距，并估算用钢量。
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

DEFAULT_AIR_DENSITY = 1.225
DEFAULT_RATED_WIND = 11.4
DEFAULT_THRUST_COEFF = 0.8
DEFAULT_WATER_DENSITY = 1025.0
DEFAULT_G = 9.81
DEFAULT_PITCH_LIMIT_DEG = 5.0
DEFAULT_STEEL_DENSITY = 7850.0
DEFAULT_WALL_THICKNESS = 0.06

PLATFORM_DB: list[dict[str, Any]] = [
    {
        "name": "OC4 DeepCwind",
        "type": "semi-sub",
        "MW": 5.0,
        "rotor_dia": 126.0,
        "hub_height": 90.0,
        "draft": 20.0,
        "main_col_dia": 6.5,
        "offset_col_dia": 12.0,
        "heave_plate_dia": 24.0,
        "spacing": 50.0,
    },
    {
        "name": "DTU Upscaled",
        "type": "semi-sub",
        "MW": 10.0,
        "rotor_dia": 178.3,
        "hub_height": 119.0,
        "draft": 28.3,
        "main_col_dia": 8.3,
        "offset_col_dia": 16.97,
        "heave_plate_dia": 33.94,
        "spacing": 70.7,
    },
    {
        "name": "VolturnUS-S",
        "type": "semi-sub",
        "MW": 15.0,
        "rotor_dia": 240.0,
        "hub_height": 150.0,
        "draft": 20.0,
        "main_col_dia": 10.0,
        "offset_col_dia": 20.0,
        "heave_plate_dia": 40.0,
        "spacing": 86.0,
    },
]


def nearest_platform(target_mw: float, *, platform_type: str = "semi-sub") -> dict[str, Any]:
    pool = [p for p in PLATFORM_DB if p.get("type") == platform_type] or list(PLATFORM_DB)
    mw = np.array([float(p["MW"]) for p in pool], dtype=float)
    idx = int(np.argmin(np.abs(mw - float(target_mw))))
    return dict(pool[idx])


def initial_scale(base: dict[str, Any], target_mw: float) -> dict[str, Any]:
    """转子按 √(P) 缩放；平台水平几何按 rotor_ratio^0.75（与 restruction.py 一致）。"""
    new_mw = float(target_mw)
    base_mw = float(base["MW"])
    rotor_ratio = math.sqrt(new_mw / base_mw) if base_mw > 0 else 1.0
    scale_factor = rotor_ratio**0.75
    return {
        "MW": new_mw,
        "base_name": str(base.get("name") or ""),
        "base_MW": base_mw,
        "rotor_ratio": float(rotor_ratio),
        "geometry_scale": float(scale_factor),
        "rotor_dia": float(base["rotor_dia"]) * rotor_ratio,
        "hub_height": float(base["hub_height"]) * rotor_ratio,
        "draft": float(base["draft"]) * scale_factor,
        "main_col_dia": float(base["main_col_dia"]) * scale_factor,
        "offset_col_dia": float(base["offset_col_dia"]) * scale_factor,
        "heave_plate_dia": float(base["heave_plate_dia"]) * scale_factor,
        "spacing": float(base["spacing"]) * scale_factor,
    }


def calc_iwp(scaled: dict[str, Any], x: float) -> float:
    offset_dia = float(scaled["offset_col_dia"]) * float(x)
    spacing = float(scaled["spacing"]) * float(x)
    d = spacing / 2.0
    a_offset = math.pi * (offset_dia / 2.0) ** 2
    return float(3.0 * a_offset * d**2)


def estimate_thrust_n(rotor_dia_m: float) -> float:
    area = math.pi * (float(rotor_dia_m) / 2.0) ** 2
    return float(0.5 * DEFAULT_AIR_DENSITY * area * DEFAULT_RATED_WIND**2 * DEFAULT_THRUST_COEFF)


def pitch_angle_deg(scaled: dict[str, Any], x: float, *, thrust_n: float | None = None) -> float:
    thrust = float(thrust_n) if thrust_n is not None else estimate_thrust_n(scaled["rotor_dia"])
    i_wp = calc_iwp(scaled, x)
    if i_wp <= 1e-12:
        return 90.0
    theta = (thrust * float(scaled["hub_height"])) / (DEFAULT_WATER_DENSITY * DEFAULT_G * i_wp)
    return float(theta * (180.0 / math.pi))


def estimate_struct_mass_t(scaled: dict[str, Any], x: float, *, wall_m: float = DEFAULT_WALL_THICKNESS) -> float:
    """三立柱 + 中央柱近似壳体用钢量（t）。"""
    sf = float(x)
    draft = float(scaled["draft"])
    dens = DEFAULT_STEEL_DENSITY

    def shell_mass(od: float, length: float) -> float:
        r_o = od / 2.0
        r_i = max(0.0, r_o - wall_m)
        return math.pi * (r_o**2 - r_i**2) * length * dens / 1000.0

    m_offset = 3.0 * shell_mass(float(scaled["offset_col_dia"]) * sf, draft)
    m_main = shell_mass(float(scaled["main_col_dia"]) * sf, draft)
    # 垂荡板：环形平板近似
    hp = float(scaled["heave_plate_dia"]) * sf
    oc = float(scaled["offset_col_dia"]) * sf
    a_ring = max(0.0, math.pi * ((hp / 2.0) ** 2 - (oc / 2.0) ** 2))
    m_plates = 3.0 * a_ring * wall_m * dens / 1000.0
    return float(m_offset + m_main + m_plates)


def optimize_horizontal_scale(
    scaled: dict[str, Any],
    *,
    pitch_limit_deg: float = DEFAULT_PITCH_LIMIT_DEG,
    x_min: float = 0.5,
    x_max: float = 3.0,
) -> dict[str, Any]:
    """SLSQP：min x³ s.t. pitch(x) ≤ pitch_limit（与 restruction.py 一致）。"""
    thrust = estimate_thrust_n(scaled["rotor_dia"])

    def objective(x_arr: np.ndarray) -> float:
        return float(x_arr[0] ** 3)

    def constraint(x_arr: np.ndarray) -> float:
        return float(pitch_limit_deg - pitch_angle_deg(scaled, float(x_arr[0]), thrust_n=thrust))

    x_opt = 1.0
    note = "fallback_x=1"
    try:
        from scipy.optimize import minimize

        res = minimize(
            objective,
            x0=np.array([1.0]),
            method="SLSQP",
            bounds=[(x_min, x_max)],
            constraints={"type": "ineq", "fun": constraint},
            options={"disp": False, "maxiter": 80},
        )
        if res.success:
            x_opt = float(res.x[0])
            note = "SLSQP_x3_pitch"
        else:
            note = f"SLSQP_failed:{res.message}"
    except Exception as exc:  # noqa: BLE001
        note = f"SLSQP_unavailable:{exc}"

    # 扫描兜底：满足纵摇的最小 x³
    if note.startswith("SLSQP_failed") or note.startswith("SLSQP_unavailable"):
        best = None
        for x in np.linspace(x_min, x_max, 121):
            if pitch_angle_deg(scaled, float(x), thrust_n=thrust) <= pitch_limit_deg:
                cost = float(x) ** 3
                if best is None or cost < best[0]:
                    best = (cost, float(x))
        if best is not None:
            x_opt = best[1]
            note = "grid_scan_x3_pitch"

    optimized = dict(scaled)
    for key in ("main_col_dia", "offset_col_dia", "heave_plate_dia", "spacing"):
        optimized[key] = float(scaled[key]) * x_opt
    optimized["extra_scale_x"] = float(x_opt)
    mass_t = estimate_struct_mass_t(optimized, 1.0)
    mw = float(optimized["MW"])
    pitch = pitch_angle_deg(optimized, 1.0, thrust_n=thrust)
    return {
        "ok": True,
        "optimizer": note,
        "pitch_limit_deg": float(pitch_limit_deg),
        "thrust_n": float(thrust),
        "extra_scale_x": float(x_opt),
        "scaled_initial": scaled,
        "scaled_optimized": optimized,
        "steel_summary": {
            "struct_mass_t": round(mass_t, 3),
            "steel_intensity_t_per_MW": round(mass_t / mw, 3) if mw > 0 else None,
            "pitch_angle_deg": round(pitch, 4),
        },
        "source": "platform_restruction",
    }


def run_platform_restruction(
    target_power_mw: float,
    *,
    pitch_limit_deg: float = DEFAULT_PITCH_LIMIT_DEG,
) -> dict[str, Any]:
    base = nearest_platform(target_power_mw)
    scaled = initial_scale(base, target_power_mw)
    out = optimize_horizontal_scale(scaled, pitch_limit_deg=pitch_limit_deg)
    out["base_platform"] = {
        "name": base.get("name"),
        "MW": base.get("MW"),
        "type": base.get("type"),
    }
    out["target_power_MW"] = float(target_power_mw)
    return out
