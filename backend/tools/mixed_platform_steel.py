"""
固定吃水、水平缩放下的混合半潜平台用钢量与稳性计算。

源自 restruction4.py：功率驱动几何缩放 + 静倾角约束下最小化 t/MW。
"""
from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np

DEFAULT_STEEL_DENSITY = 7850.0
DEFAULT_WATER_DENSITY = 1025.0
DEFAULT_G = 9.81
DEFAULT_WALL_THICKNESS = 0.06
DEFAULT_AIR_DENSITY = 1.225
DEFAULT_RATED_WIND_SPEED = 11.4
DEFAULT_THRUST_COEFF = 0.8
DEFAULT_RATED_POWER_MW = 5.0
DEFAULT_ROTOR_DIA_M = 126.0
DEFAULT_HUB_HEIGHT_M = 90.0
DEFAULT_RNA_MASS_KG = 542_900.0
DEFAULT_DRAFT_M = 20.0
DEFAULT_TARGET_POWER_MW = 20.0


def mm_to_m(v: float) -> float:
    return float(v) / 1000.0


def cylindrical_volume(outer_diam: float, inner_diam: float, height: float) -> float:
    a_outer = math.pi * (outer_diam / 2) ** 2
    a_inner = math.pi * (inner_diam / 2) ** 2
    return (a_outer - a_inner) * height


def point_on_line(p1: list[float], p2: list[float], t: float) -> list[float]:
    return [float(p1[i] + t * (p2[i] - p1[i])) for i in range(3)]


def intersect_z(p1: list[float], p2: list[float], z_target: float) -> float | None:
    if abs(p2[2] - p1[2]) < 1e-9:
        return None
    t = (z_target - p1[2]) / (p2[2] - p1[2])
    return float(t) if 0.0 <= t <= 1.0 else None


def distance_3d(p1: list[float], p2: list[float]) -> float:
    return float(np.linalg.norm(np.array(p1, dtype=float) - np.array(p2, dtype=float)))


def scale_geometry_horizontal(json_data: dict[str, Any], scale_factor: float) -> dict[str, Any]:
    """固定吃水缩放：水平尺寸乘以 scale_factor，垂直尺寸不变（柱长同比例以保持倾角）。"""
    new_data = copy.deepcopy(json_data)
    sf = float(scale_factor)
    for leg in new_data.get("beso7_method1_topology_reconstructed", {}).get("legs", []):
        leg["diameter_mm"] = float(leg.get("diameter_mm", 0)) * sf
        leg["radius_mm"] = float(leg.get("radius_mm", 0)) * sf
        leg["length_mm"] = float(leg.get("length_mm", 0)) * sf
        for i in range(2):
            leg["base_xyz_mm"][i] = float(leg["base_xyz_mm"][i]) * sf
            leg["top_xyz_mm"][i] = float(leg["top_xyz_mm"][i]) * sf
        for i, r in enumerate(leg.get("station_radii_mm") or []):
            leg["station_radii_mm"][i] = float(r) * sf
    plate = new_data.get("beso7_method1_topology_reconstructed", {}).get("hub_top_plate", {})
    if plate:
        plate["radius_mm"] = float(plate.get("radius_mm", 0)) * sf
        plate["diameter_mm"] = float(plate.get("diameter_mm", 0)) * sf
        plate["center_xy_mm"][0] = float(plate["center_xy_mm"][0]) * sf
        plate["center_xy_mm"][1] = float(plate["center_xy_mm"][1]) * sf
    for col in new_data.get("beso3_reference_from_fcstd", {}).get("edge_columns_nondesign", []):
        if "radius_mm" in col:
            col["radius_mm"] = float(col["radius_mm"]) * sf
        if "diameter_mm" in col:
            col["diameter_mm"] = float(col["diameter_mm"]) * sf
        if "center_xy_mm" in col:
            col["center_xy_mm"][0] = float(col["center_xy_mm"][0]) * sf
            col["center_xy_mm"][1] = float(col["center_xy_mm"][1]) * sf
        foot = col.get("footing")
        if foot and "equivalent_radius_mm" in foot:
            foot["equivalent_radius_mm"] = float(foot["equivalent_radius_mm"]) * sf
    return new_data


class MixedPlatform:
    def __init__(
        self,
        json_data: dict[str, Any],
        *,
        wall_thickness: float,
        steel_density: float,
        water_density: float,
        draft: float,
        current_power_mw: float,
        rotor_dia_m: float,
        hub_height_m: float,
        rna_mass_kg: float,
        top_plate_hollow: bool = True,
        top_plate_wall: float | None = None,
    ) -> None:
        self.wall_thickness = wall_thickness
        self.steel_density = steel_density
        self.water_density = water_density
        self.draft = draft
        self.current_power_mw = current_power_mw
        self.rotor_dia_m = rotor_dia_m
        self.hub_height_m = hub_height_m
        self.rna_mass_kg = rna_mass_kg
        self.top_plate_hollow = top_plate_hollow
        self.top_plate_wall = top_plate_wall if top_plate_wall is not None else wall_thickness
        self.beso7 = json_data.get("beso7_method1_topology_reconstructed", {})
        self.beso3 = json_data.get("beso3_reference_from_fcstd", {})

    def _add_leg(self, leg, comp_masses, submerged_vols, waterplane_items) -> None:
        d = mm_to_m(leg["diameter_mm"])
        length = mm_to_m(leg["length_mm"])
        base = [mm_to_m(v) for v in leg["base_xyz_mm"]]
        top = [mm_to_m(v) for v in leg["top_xyz_mm"]]
        inner = max(0.0, d - 2 * self.wall_thickness)
        mass = cylindrical_volume(d, inner, length) * self.steel_density
        cog_z = (base[2] + top[2]) / 2
        comp_masses.append((mass, cog_z))

        t0 = intersect_z(base, top, 0)
        if t0 is None:
            sub_len = length if base[2] <= 0 and top[2] <= 0 else 0
            inter = None
        else:
            inter = point_on_line(base, top, t0)
            bottom = base if base[2] < top[2] else top
            sub_len = distance_3d(bottom, inter)
        area = math.pi * (d / 2) ** 2
        sub_vol = area * sub_len
        if sub_vol > 0:
            if inter is not None:
                bottom = base if base[2] < top[2] else top
                mid_z = (bottom[2] + inter[2]) / 2.0
            else:
                mid_z = (base[2] + top[2]) / 2.0
            submerged_vols.append((sub_vol, mid_z))

        t_swl = intersect_z(base, top, 0)
        if t_swl is not None:
            center = point_on_line(base, top, t_swl)
            waterplane_items.append((center[0], center[1], area))

    def _add_vertical_column(self, col, comp_masses, submerged_vols, waterplane_items) -> None:
        radius = mm_to_m(col.get("radius_mm", 0))
        if radius == 0 and "diameter_mm" in col:
            radius = mm_to_m(col["diameter_mm"]) / 2
        if radius == 0:
            return
        z_bot = mm_to_m(col.get("z_bottom_mm", 0))
        z_top = mm_to_m(col.get("z_top_mm", 0))
        height = z_top - z_bot
        cx = mm_to_m(col.get("center_xy_mm", [0, 0])[0])
        cy = mm_to_m(col.get("center_xy_mm", [0, 0])[1])
        d = 2 * radius
        inner = max(0.0, d - 2 * self.wall_thickness)
        mass = cylindrical_volume(d, inner, height) * self.steel_density
        cog_z = (z_bot + z_top) / 2
        comp_masses.append((mass, cog_z))

        sub_bot = max(z_bot, -self.draft)
        sub_top = min(z_top, 0)
        if sub_top > sub_bot:
            sub_len = sub_top - sub_bot
            area = math.pi * radius**2
            submerged_vols.append((area * sub_len, (sub_bot + sub_top) / 2))
        if z_bot <= 0 <= z_top:
            waterplane_items.append((cx, cy, math.pi * radius**2))

    def _add_footing(self, foot, comp_masses, submerged_vols, waterplane_items) -> None:
        radius = mm_to_m(foot.get("equivalent_radius_mm", 0))
        if radius == 0:
            return
        z_bot = mm_to_m(foot.get("z_bottom_mm", 0))
        z_top = mm_to_m(foot.get("z_top_mm", 0))
        height = z_top - z_bot
        d = 2 * radius
        inner = max(0.0, d - 2 * self.wall_thickness)
        mass = cylindrical_volume(d, inner, height) * self.steel_density
        comp_masses.append((mass, (z_bot + z_top) / 2))

        sub_bot = max(z_bot, -self.draft)
        sub_top = min(z_top, 0)
        if sub_top > sub_bot:
            sub_len = sub_top - sub_bot
            area = math.pi * radius**2
            submerged_vols.append((area * sub_len, (sub_bot + sub_top) / 2))

    def _add_top_plate(self, plate, comp_masses, submerged_vols, waterplane_items) -> None:
        r = mm_to_m(plate["radius_mm"])
        h = mm_to_m(plate["thickness_mm"])
        z_bot = mm_to_m(plate["z_bottom_mm"])
        z_top = mm_to_m(plate["z_top_mm"])
        if self.top_plate_hollow:
            inner_r = max(0.0, r - self.top_plate_wall)
            vol = math.pi * (r**2 - inner_r**2) * h
        else:
            vol = math.pi * r**2 * h
        mass = vol * self.steel_density
        comp_masses.append((mass, (z_bot + z_top) / 2))

    def compute(self) -> dict[str, float]:
        comp_masses: list[tuple[float, float]] = []
        submerged_vols: list[tuple[float, float]] = []
        waterplane_items: list[tuple[float, float, float]] = []

        for leg in self.beso7.get("legs", []):
            self._add_leg(leg, comp_masses, submerged_vols, waterplane_items)
        for col in self.beso3.get("edge_columns_nondesign", []):
            self._add_vertical_column(col, comp_masses, submerged_vols, waterplane_items)
            if "footing" in col:
                self._add_footing(col["footing"], comp_masses, submerged_vols, waterplane_items)
        plate = self.beso7.get("hub_top_plate", {})
        if plate:
            self._add_top_plate(plate, comp_masses, submerged_vols, waterplane_items)

        total_mass_struct = sum(m for m, _ in comp_masses)
        cog_z_struct = sum(m * z for m, z in comp_masses) / total_mass_struct if total_mass_struct > 0 else 0.0

        total_sub_vol = sum(v for v, _ in submerged_vols)
        cob_z = sum(v * z for v, z in submerged_vols) / total_sub_vol if total_sub_vol > 0 else 0.0

        i_y = 0.0
        for x, _y, area in waterplane_items:
            d = 2 * math.sqrt(area / math.pi)
            i_y += math.pi * d**4 / 64 + area * x**2
        if i_y == 0:
            i_y = 1e-6

        disp_mass = self.water_density * total_sub_vol
        ballast = max(0.0, disp_mass - total_mass_struct - self.rna_mass_kg)
        total_mass = total_mass_struct + ballast + self.rna_mass_kg
        ballast_cog = cob_z if total_sub_vol > 0 else -self.draft / 2
        if total_mass > 0:
            cog_z_total = (
                total_mass_struct * cog_z_struct + ballast * ballast_cog + self.rna_mass_kg * self.hub_height_m
            ) / total_mass
        else:
            cog_z_total = 0.0

        f_b = self.water_density * DEFAULT_G * total_sub_vol
        k55 = self.water_density * DEFAULT_G * i_y + f_b * (cob_z - cog_z_total)

        rotor_area = math.pi * (self.rotor_dia_m / 2) ** 2
        thrust = 0.5 * DEFAULT_AIR_DENSITY * rotor_area * DEFAULT_RATED_WIND_SPEED**2 * DEFAULT_THRUST_COEFF
        tilt_moment = thrust * self.hub_height_m
        pitch_deg = math.degrees(tilt_moment / k55) if k55 > 0 else 90.0

        steel_per_mw = total_mass_struct / 1000.0 / self.current_power_mw if self.current_power_mw > 0 else 0.0

        return {
            "struct_mass_kg": total_mass_struct,
            "struct_mass_t": total_mass_struct / 1000.0,
            "ballast_mass_kg": ballast,
            "ballast_mass_t": ballast / 1000.0,
            "total_mass_kg": total_mass,
            "total_mass_t": total_mass / 1000.0,
            "cog_z_struct_m": cog_z_struct,
            "cob_z_m": cob_z,
            "cog_z_total_m": cog_z_total,
            "displaced_vol_m3": total_sub_vol,
            "I_y_m4": i_y,
            "K55_Nm_per_rad": k55,
            "rated_thrust_N": thrust,
            "pitch_angle_deg": pitch_deg,
            "steel_intensity_t_per_MW": steel_per_mw,
            "steel_per_MW_t": steel_per_mw,
        }


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
    }


def compute_for_scale(
    json_data: dict[str, Any],
    scale: float,
    params: dict[str, Any],
    target_mw: float,
) -> dict[str, float]:
    scaled = scale_geometry_horizontal(json_data, scale)
    s_power = math.sqrt(target_mw / params["rated_power_MW"])
    plat = MixedPlatform(
        scaled,
        wall_thickness=params["wall_thickness"],
        steel_density=params["steel_density"],
        water_density=params["water_density"],
        draft=params["draft"],
        current_power_mw=target_mw,
        rotor_dia_m=params["rotor_dia_m"] * s_power,
        hub_height_m=params["hub_height_m"] * s_power,
        rna_mass_kg=params["rna_mass_kg"] * (s_power**0.88),
        top_plate_hollow=params["top_plate_hollow"],
        top_plate_wall=params["top_plate_wall_thickness"],
    )
    return plat.compute()


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
    s0 = math.sqrt(target_mw / params["rated_power_MW"])

    def eval_x(x: float) -> dict[str, float]:
        return compute_for_scale(json_data, s0 * x, params, target_mw)

    best_x = 1.0
    best_steel = float("inf")
    best_props: dict[str, float] | None = None
    note = "brute_force_scan"

    try:
        from scipy.optimize import minimize

        def obj(x_arr):
            return eval_x(float(x_arr[0]))["steel_per_MW_t"]

        def con(x_arr):
            return pitch_limit_deg - eval_x(float(x_arr[0]))["pitch_angle_deg"]

        res = minimize(
            obj,
            x0=[1.0],
            method="SLSQP",
            bounds=[(x_min, x_max)],
            constraints={"type": "ineq", "fun": con},
        )
        if res.success:
            best_x = float(res.x[0])
            best_props = eval_x(best_x)
            best_steel = best_props["steel_per_MW_t"]
            note = "SLSQP"
    except Exception:
        pass

    if best_props is None or best_steel == float("inf"):
        for x in np.linspace(x_min, x_max, steps):
            props = eval_x(float(x))
            if props["pitch_angle_deg"] <= pitch_limit_deg and props["steel_per_MW_t"] < best_steel:
                best_x = float(x)
                best_steel = props["steel_per_MW_t"]
                best_props = props
        note = "brute_force_scan"

    if best_props is None:
        best_x = 1.0
        best_props = eval_x(best_x)
        note = "fallback_x=1"

    return s0 * best_x, best_x, best_props, note


def summarize_geometry(json_data: dict[str, Any], scale: float, params: dict[str, Any]) -> dict[str, float]:
    scaled = scale_geometry_horizontal(json_data, scale)
    beso7 = scaled.get("beso7_method1_topology_reconstructed", {})
    beso3 = scaled.get("beso3_reference_from_fcstd", {})
    out: dict[str, float] = {"draft_m": params["draft"]}

    dias = []
    for col in beso3.get("edge_columns_nondesign", []):
        if "radius_mm" in col:
            dias.append(2 * mm_to_m(col["radius_mm"]))
    if dias:
        out["edge_column_mean_diameter_m"] = sum(dias) / len(dias)

    centers = []
    for col in beso3.get("edge_columns_nondesign", []):
        if "center_xy_mm" in col:
            centers.append((mm_to_m(col["center_xy_mm"][0]), mm_to_m(col["center_xy_mm"][1])))
    if len(centers) == 3:
        d12 = math.hypot(centers[0][0] - centers[1][0], centers[0][1] - centers[1][1])
        d23 = math.hypot(centers[1][0] - centers[2][0], centers[1][1] - centers[2][1])
        d31 = math.hypot(centers[2][0] - centers[0][0], centers[2][1] - centers[0][1])
        out["column_mean_spacing_m"] = (d12 + d23 + d31) / 3

    beso7_dias = [mm_to_m(leg["diameter_mm"]) for leg in beso7.get("legs", [])]
    if beso7_dias:
        out["beso7_leg_mean_diameter_m"] = sum(beso7_dias) / len(beso7_dias)

    plate = beso7.get("hub_top_plate", {})
    if plate:
        out["top_plate_radius_m"] = mm_to_m(plate["radius_mm"])
    return out


def _round_props(props: dict[str, float]) -> dict[str, float]:
    return {k: round(float(v), 4) if isinstance(v, (int, float)) else v for k, v in props.items()}


def compute_steel_report(
    geometry: dict[str, Any],
    *,
    target_power_mw: float | None = None,
    params: dict[str, Any] | None = None,
    optimize: bool = True,
    scale_factor: float | None = None,
) -> dict[str, Any]:
    """
    对几何 JSON 计算用钢量报告。

    - optimize=True：在静倾角≤5°下最小化 t/MW（默认）
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
        final_scale, x_opt, final_props_raw, opt_note = optimize_scale(geometry, params, target_mw)
        final_props = _round_props(final_props_raw)
    else:
        final_scale = s0
        x_opt = 1.0
        final_props = initial_props
        opt_note = "initial_scale_only"

    final_geom = summarize_geometry(geometry, final_scale, params)

    return {
        "title": geometry.get("title"),
        "units_note": "lengths in source JSON are mm; report values in SI unless noted",
        "computation": {
            "target_power_MW": target_mw,
            "base_rated_power_MW": params["rated_power_MW"],
            "initial_scale_factor_s0": round(s0, 4),
            "extra_scale_factor_x": round(x_opt, 4),
            "final_horizontal_scale_factor": round(final_scale, 4),
            "optimized": optimize and scale_factor is None,
            "optimizer": opt_note,
            "pitch_limit_deg": 5.0,
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
            "wall_thickness_m": params["wall_thickness"],
            "steel_density_kgpm3": params["steel_density"],
            "draft_m": params["draft"],
            "top_plate_hollow": params["top_plate_hollow"],
            "top_plate_wall_m": params["top_plate_wall_thickness"],
            "base_rated_power_MW": params["rated_power_MW"],
        }
    out["validation_overrides"] = {
        **(out.get("validation_overrides") or {}),
        "steel_mass_t": steel["struct_mass_t"],
        "steel_intensity_t_per_MW": steel["steel_intensity_t_per_MW"],
        "calculation_method": "mixed_platform_steel_restruction4",
    }
    out["steel_calculation_report"] = report
    return out
