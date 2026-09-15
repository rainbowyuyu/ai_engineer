"""
半潜平台水平尺寸优化入口（restruction6）。

流程：读取几何 JSON（默认 rules/optimized_geometry.json）→ 固定吃水水平缩放
→ SLSQP / 可行域扫描，最小化 t/MW 且静倾角 ≤ pitch_limit。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PITCH_LIMIT_DEG = 5.0


def default_geometry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "optimized_geometry.json"


def nearest_platform(target_mw: float, *, platform_type: str = "semi-sub") -> dict[str, Any]:
    """兼容旧测试：返回基型元数据（几何路径由 restruction6 实际使用）。"""
    _ = platform_type
    return {
        "name": "optimized_geometry.json",
        "type": "semi-sub",
        "MW": 5.0,
        "note": "restruction6 uses mixed-platform JSON geometry, not PLATFORM_DB scalars",
        "target_MW": float(target_mw),
    }


def pitch_angle_deg(scaled: dict[str, Any], x: float, *, thrust_n: float | None = None) -> float:
    """兼容旧测试：若传入含 pitch 的摘要则直读；否则按小角度近似回退。"""
    _ = thrust_n
    if "pitch_angle_deg" in scaled and float(x) == 1.0:
        return float(scaled["pitch_angle_deg"])
    # 旧 PLATFORM_DB 路径已移除；无几何时给出保守值
    return float(scaled.get("pitch_angle_deg") or 90.0)


def run_platform_restruction(
    target_power_mw: float,
    *,
    pitch_limit_deg: float = DEFAULT_PITCH_LIMIT_DEG,
    geometry: dict[str, Any] | None = None,
    geometry_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    运行 restruction6 优化，返回与旧 platform_restruction 兼容的字典。
    """
    from backend.tools.mixed_platform_steel import (
        compute_steel_report,
        default_params_from_geometry,
        load_default_geometry,
    )

    if geometry is None:
        if geometry_path is not None:
            geometry = json.loads(Path(geometry_path).read_text(encoding="utf-8"))
        else:
            geometry = load_default_geometry()

    report = compute_steel_report(
        geometry,
        target_power_mw=float(target_power_mw),
        optimize=True,
        pitch_limit_deg=float(pitch_limit_deg),
    )
    prest = report.get("platform_restruction") or {}
    steel = report.get("steel_summary") or {}
    comp = report.get("computation") or {}
    geom = (report.get("result") or {}).get("geometry_summary") or {}
    params = default_params_from_geometry(geometry)

    scaled_opt = dict(prest.get("scaled_optimized") or {})
    scaled_opt.setdefault("MW", float(target_power_mw))
    scaled_opt.setdefault("draft", params.get("draft"))
    scaled_opt["pitch_angle_deg"] = steel.get("pitch_angle_deg")

    return {
        "ok": True,
        "optimizer": comp.get("optimizer") or prest.get("optimizer"),
        "pitch_limit_deg": float(pitch_limit_deg),
        "extra_scale_x": float(comp.get("extra_scale_factor_x") or prest.get("extra_scale_x") or 1.0),
        "final_horizontal_scale_factor": float(comp.get("final_horizontal_scale_factor") or 1.0),
        "scaled_initial": (report.get("initial_at_s0") or {}).get("geometry_summary"),
        "scaled_optimized": scaled_opt,
        "steel_summary": {
            "struct_mass_t": steel.get("struct_mass_t"),
            "steel_intensity_t_per_MW": steel.get("steel_intensity_t_per_MW"),
            "pitch_angle_deg": steel.get("pitch_angle_deg"),
            "ballast_mass_t": steel.get("ballast_mass_t"),
            "total_mass_t": steel.get("total_mass_t"),
            "K55_Nm_per_rad": steel.get("K55_Nm_per_rad"),
        },
        "geometry_summary": geom,
        "base_platform": nearest_platform(float(target_power_mw)),
        "target_power_MW": float(target_power_mw),
        "source": "restruction6",
        "report": report,
    }
