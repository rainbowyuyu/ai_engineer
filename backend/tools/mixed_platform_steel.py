"""
固定吃水、水平缩放下的混合半潜平台用钢量与稳性计算。

核心物理模型来自 restruction6.py（经 ``_restruction6_src`` 接入）：
功率驱动几何缩放 + 静倾角约束下最小化 t/MW。
本模块保留既有 pipeline / API / 验证侧的报告接口。
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

from backend.tools import _restruction6_src as r6

# 兼容旧调用方常量名（项目几何默认以 NREL 5 MW / OC4 为基型）
DEFAULT_STEEL_DENSITY = r6.DEFAULT_STEEL_DENSITY
DEFAULT_WATER_DENSITY = r6.DEFAULT_WATER_DENSITY
DEFAULT_G = r6.DEFAULT_G
DEFAULT_WALL_THICKNESS = r6.DEFAULT_WALL_THICKNESS
DEFAULT_AIR_DENSITY = r6.DEFAULT_AIR_DENSITY
DEFAULT_RATED_WIND_SPEED = r6.DEFAULT_RATED_WIND_SPEED
DEFAULT_THRUST_COEFF = r6.DEFAULT_THRUST_COEFF
DEFAULT_RATED_POWER_MW = 5.0
DEFAULT_ROTOR_DIA_M = 126.0
DEFAULT_HUB_HEIGHT_M = 90.0
DEFAULT_RNA_MASS_KG = 542_900.0
DEFAULT_TOWER_MASS_KG = 347_460.0  # NREL 5 MW 量级
DEFAULT_TOWER_COG_M = 45.0
DEFAULT_BALLAST_COG_Z_M = r6.DEFAULT_BALLAST_COG_Z_M
DEFAULT_DRAFT_M = 20.0
DEFAULT_TARGET_POWER_MW = 20.0
CALCULATION_METHOD = "mixed_platform_steel_restruction6"

mm_to_m = r6.mm_to_m
cylindrical_volume = r6.cylindrical_volume
point_on_line = r6.point_on_line
intersect_z = r6.intersect_z
distance_3d = r6.distance_3d
scale_geometry_horizontal = r6.scale_geometry_horizontal
MixedPlatform = r6.MixedPlatform


def default_geometry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "optimized_geometry.json"


def load_default_geometry() -> dict[str, Any]:
    path = default_geometry_path()
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def default_params_from_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    opt = geometry.get("optimization_info") or {}
    vo = geometry.get("validation_overrides") or {}
    hollow = opt.get("top_plate_hollow", True)
    wall = float(opt.get("wall_thickness_m") or vo.get("wall_thickness_m") or DEFAULT_WALL_THICKNESS)
    top_wall = opt.get("top_plate_wall_m")
    return {
        "steel_density": float(opt.get("steel_density_kgpm3") or DEFAULT_STEEL_DENSITY),
        "water_density": float(opt.get("water_density_kgpm3") or DEFAULT_WATER_DENSITY),
        "wall_thickness": wall,
        "draft": float(opt.get("draft_m") or vo.get("draft_m") or DEFAULT_DRAFT_M),
        "top_plate_hollow": bool(hollow),
        "top_plate_wall_thickness": float(top_wall if top_wall is not None else wall),
        "rated_power_MW": float(opt.get("base_rated_power_MW") or DEFAULT_RATED_POWER_MW),
        "rotor_dia_m": float(opt.get("rotor_dia_m") or DEFAULT_ROTOR_DIA_M),
        "hub_height_m": float(opt.get("hub_height_m") or DEFAULT_HUB_HEIGHT_M),
        "rna_mass_kg": float(opt.get("rna_mass_kg") or DEFAULT_RNA_MASS_KG),
        "tower_mass_kg": float(opt.get("tower_mass_kg") or DEFAULT_TOWER_MASS_KG),
        "tower_cog_m": float(opt.get("tower_cog_m") or DEFAULT_TOWER_COG_M),
        "ballast_cog_z_m": float(opt.get("ballast_cog_z_m") or DEFAULT_BALLAST_COG_Z_M),
    }


def compute_for_scale(
    json_data: dict[str, Any],
    scale: float,
    params: dict[str, Any],
    target_mw: float,
    mesh_geoms: list | None = None,
) -> dict[str, float]:
    """委托 restruction6；缺省参数键自动补齐。"""
    full = {
        "tower_mass_kg": DEFAULT_TOWER_MASS_KG,
        "tower_cog_m": DEFAULT_TOWER_COG_M,
        "ballast_cog_z_m": DEFAULT_BALLAST_COG_Z_M,
        **params,
    }
    return _normalize_props(
        r6.compute_for_scale(json_data, float(scale), full, float(target_mw), mesh_geoms)
    )


def optimize_scale(
    json_data: dict[str, Any],
    params: dict[str, Any],
    target_mw: float,
    *,
    x_min: float = 0.5,
    x_max: float = 2.5,
    steps: int = 201,
    pitch_limit_deg: float = 5.0,
) -> tuple[float, float, dict[str, float], str]:
    """返回 (final_scale, x_opt, props, optimizer_note)。"""
    full = {
        "tower_mass_kg": DEFAULT_TOWER_MASS_KG,
        "tower_cog_m": DEFAULT_TOWER_COG_M,
        "ballast_cog_z_m": DEFAULT_BALLAST_COG_Z_M,
        **params,
    }
    scan_step = max(0.001, (float(x_max) - float(x_min)) / max(1, int(steps) - 1))
    final_scale, x_opt, props, _mesh = r6.optimize_scale(
        json_data,
        full,
        float(target_mw),
        quiet=True,
        pitch_limit_deg=float(pitch_limit_deg),
        x_min=float(x_min),
        x_max=float(x_max),
        scan_step=scan_step,
    )
    note = str(props.pop("_optimizer_note", "SLSQP"))
    return float(final_scale), float(x_opt), _normalize_props(props), note


def summarize_geometry(json_data: dict[str, Any], scale: float, params: dict[str, Any]) -> dict[str, Any]:
    scaled = scale_geometry_horizontal(json_data, scale)
    topology_key = (
        "beso9_method1_topology_reconstructed"
        if "beso9_method1_topology_reconstructed" in scaled
        else "beso7_method1_topology_reconstructed"
    )
    beso = scaled.get(topology_key, {}) or {}
    edge_cols = (scaled.get("beso3_reference_from_fcstd") or {}).get("edge_columns_nondesign", [])
    if not edge_cols:
        edge_cols = scaled.get("edge_columns_nondesign", []) or []

    out: dict[str, Any] = {"draft_m": float(params.get("draft", DEFAULT_DRAFT_M)), "topology_key": topology_key}

    diam_list: list[float] = []
    centers: list[tuple[float, float]] = []
    for col in edge_cols:
        rad = col.get("true_orthogonal_radius_mm", col.get("radius_mm", 0))
        if rad:
            diam_list.append(2 * mm_to_m(rad))
        if "center_xy_mm" in col:
            centers.append((mm_to_m(col["center_xy_mm"][0]), mm_to_m(col["center_xy_mm"][1])))
    if diam_list:
        out["edge_column_mean_diameter_m"] = sum(diam_list) / len(diam_list)
        out["offset_col_dia"] = out["edge_column_mean_diameter_m"]
    if len(centers) >= 3:
        d12 = math.hypot(centers[0][0] - centers[1][0], centers[0][1] - centers[1][1])
        d23 = math.hypot(centers[1][0] - centers[2][0], centers[1][1] - centers[2][1])
        d31 = math.hypot(centers[2][0] - centers[0][0], centers[2][1] - centers[0][1])
        out["column_mean_spacing_m"] = (d12 + d23 + d31) / 3
        out["spacing"] = out["column_mean_spacing_m"]

    leg_dias = [
        mm_to_m(leg.get("diameter_mm", leg.get("radius_mm", 0) * 2))
        for leg in beso.get("legs", [])
    ]
    if leg_dias:
        out["beso_leg_mean_diameter_m"] = sum(leg_dias) / len(leg_dias)
        out["beso7_leg_mean_diameter_m"] = out["beso_leg_mean_diameter_m"]
        out["main_col_dia"] = out["beso_leg_mean_diameter_m"]

    plate = beso.get("hub_top_plate", {}) or {}
    if plate:
        rad = mm_to_m(plate.get("radius_mm", plate.get("diameter_mm", 0) / 2))
        out["top_plate_radius_m"] = rad
        out["heave_plate_dia"] = 2.0 * rad
    return out


def _normalize_props(props: dict[str, Any]) -> dict[str, Any]:
    """将 restruction6 原始字段补齐为报告/验证侧常用别名。"""
    out = dict(props)
    if "struct_mass_t" not in out and "struct_mass_kg" in out:
        out["struct_mass_t"] = float(out["struct_mass_kg"]) / 1000.0
    if "ballast_mass_t" not in out and "ballast_mass_kg" in out:
        out["ballast_mass_t"] = float(out["ballast_mass_kg"]) / 1000.0
    if "total_mass_t" not in out and "total_mass_kg" in out:
        out["total_mass_t"] = float(out["total_mass_kg"]) / 1000.0
    if "steel_intensity_t_per_MW" not in out and "steel_per_MW_t" in out:
        out["steel_intensity_t_per_MW"] = float(out["steel_per_MW_t"])
    if "steel_per_MW_t" not in out and "steel_intensity_t_per_MW" in out:
        out["steel_per_MW_t"] = float(out["steel_intensity_t_per_MW"])
    return out


def _round_props(props: dict[str, Any]) -> dict[str, Any]:
    props = _normalize_props(props)
    return {
        k: round(float(v), 4) if isinstance(v, (int, float)) else v
        for k, v in props.items()
        if not str(k).startswith("_")
    }


def compute_steel_report(
    geometry: dict[str, Any],
    *,
    target_power_mw: float | None = None,
    params: dict[str, Any] | None = None,
    optimize: bool = True,
    scale_factor: float | None = None,
    pitch_limit_deg: float = 5.0,
) -> dict[str, Any]:
    """
    对几何 JSON 计算用钢量报告（restruction6）。

    - optimize=True：在静倾角≤pitch_limit 下最小化 t/MW（默认）
    - scale_factor 给定：跳过优化，直接使用该水平缩放因子
    """
    params = params or default_params_from_geometry(geometry)
    target_mw = float(
        target_power_mw
        or (geometry.get("optimization_info") or {}).get("target_power_MW")
        or DEFAULT_TARGET_POWER_MW
    )
    s0 = math.sqrt(target_mw / params["rated_power_MW"])
    initial_props = _round_props(compute_for_scale(geometry, s0, params, target_mw))
    initial_geom = summarize_geometry(geometry, s0, params)

    if scale_factor is not None:
        final_scale = float(scale_factor)
        x_opt = final_scale / s0 if s0 > 0 else 1.0
        final_props = _round_props(compute_for_scale(geometry, final_scale, params, target_mw))
        opt_note = "fixed_scale"
    elif optimize:
        final_scale, x_opt, final_props_raw, opt_note = optimize_scale(
            geometry, params, target_mw, pitch_limit_deg=float(pitch_limit_deg)
        )
        final_props = _round_props(final_props_raw)
    else:
        final_scale = s0
        x_opt = 1.0
        final_props = initial_props
        opt_note = "initial_scale_only"

    final_geom = summarize_geometry(geometry, final_scale, params)

    report: dict[str, Any] = {
        "title": geometry.get("title"),
        "units_note": "lengths in source JSON are mm; report values in SI unless noted",
        "model": "restruction6",
        "computation": {
            "target_power_MW": target_mw,
            "base_rated_power_MW": params["rated_power_MW"],
            "initial_scale_factor_s0": round(s0, 4),
            "extra_scale_factor_x": round(x_opt, 4),
            "final_horizontal_scale_factor": round(final_scale, 4),
            "optimized": optimize and scale_factor is None,
            "optimizer": opt_note,
            "pitch_limit_deg": float(pitch_limit_deg),
        },
        "parameters": params,
        "initial_at_s0": {
            "performance": initial_props,
            "geometry_summary": initial_geom,
        },
        "result": {
            "performance": final_props,
            "geometry_summary": final_geom,
        },
        "steel_summary": {
            "struct_mass_t": final_props["struct_mass_t"],
            "steel_intensity_t_per_MW": final_props["steel_intensity_t_per_MW"],
            "ballast_mass_t": final_props["ballast_mass_t"],
            "total_mass_t": final_props["total_mass_t"],
            "pitch_angle_deg": final_props["pitch_angle_deg"],
            "displaced_vol_m3": final_props["displaced_vol_m3"],
            "cog_z_struct_m": final_props["cog_z_struct_m"],
            "cob_z_m": final_props["cob_z_m"],
            "K55_Nm_per_rad": final_props["K55_Nm_per_rad"],
        },
    }
    # 自引用摘要（同模型）；保留键名供旧前端读取
    report["platform_restruction"] = {
        "ok": True,
        "source": "restruction6",
        "extra_scale_x": round(x_opt, 4),
        "optimizer": opt_note,
        "steel_summary": report["steel_summary"],
        "scaled_optimized": {
            "MW": target_mw,
            "draft": params["draft"],
            "hub_height": params["hub_height_m"] * math.sqrt(target_mw / params["rated_power_MW"]),
            "rotor_dia": params["rotor_dia_m"] * math.sqrt(target_mw / params["rated_power_MW"]),
            **{k: final_geom[k] for k in ("main_col_dia", "offset_col_dia", "heave_plate_dia", "spacing") if k in final_geom},
            "extra_scale_x": round(x_opt, 4),
        },
        "geometry_summary": final_geom,
    }
    return report


def attach_steel_to_geometry(
    geometry: dict[str, Any],
    report: dict[str, Any],
    *,
    write_optimization_info: bool = True,
) -> dict[str, Any]:
    """将 steel_summary 写入 geometry 副本，供验证模块读取。"""
    out = copy.deepcopy(geometry)
    steel = report["steel_summary"]
    comp = report["computation"]
    params = report["parameters"]
    if write_optimization_info:
        out["optimization_info"] = {
            **(out.get("optimization_info") or {}),
            "target_power_MW": comp["target_power_MW"],
            "scale_factor": comp["final_horizontal_scale_factor"],
            "extra_scale_x": comp["extra_scale_factor_x"],
            "wall_thickness_m": params["wall_thickness"],
            "steel_density_kgpm3": params["steel_density"],
            "draft_m": params["draft"],
            "top_plate_hollow": params["top_plate_hollow"],
            "top_plate_wall_m": params["top_plate_wall_thickness"],
            "base_rated_power_MW": params["rated_power_MW"],
            "tower_mass_kg": params.get("tower_mass_kg"),
            "tower_cog_m": params.get("tower_cog_m"),
            "ballast_cog_z_m": params.get("ballast_cog_z_m"),
        }
    out["validation_overrides"] = {
        **(out.get("validation_overrides") or {}),
        "steel_mass_t": steel["struct_mass_t"],
        "steel_intensity_t_per_MW": steel["steel_intensity_t_per_MW"],
        "calculation_method": CALCULATION_METHOD,
    }
    out["steel_calculation_report"] = report
    return out
