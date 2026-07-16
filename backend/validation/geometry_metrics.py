"""Extract measurable metrics from optimized geometry JSON."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GeometryMetrics:
    target_power_MW: float
    draft_m: float | None
    wall_thickness_m: float
    steel_density_kgpm3: float
    assembly_volume_m3: float | None
    bbox_z_m: float | None
    bbox_xy_span_m: float | None
    leg_mean_diameter_m: float | None
    leg_min_diameter_m: float | None
    leg_max_diameter_m: float | None
    leg_mean_length_m: float | None
    leg_slenderness_L_over_D: float | None
    leg_diameter_uniformity_pct: float | None
    leg_taper_ratio: float | None
    leg_mean_spacing_m: float | None
    leg_hub_spacing_mean_m: float | None
    beso3_column_spacing_m: float | None
    design_domain_span_m: float | None
    leg_layout_angle_deg_std: float | None
    top_plate_diameter_m: float | None
    top_plate_thickness_m: float | None
    plate_to_leg_diameter_ratio: float | None
    dt_ratio: float | None
    hub_elevation_m: float | None
    freeboard_proxy_m: float | None
    scale_factor: float | None
    steel_mass_t_est: float
    steel_mass_t_source: str
    steel_intensity_t_per_MW: float
    total_steel_t: float
    unit_cost_cny_per_MW: float | None
    unit_cost_source: str
    construction_years: float | None
    construction_years_source: str
    fatigue_life_years: float | None
    fatigue_life_source: str
    assumptions: list[str] = field(default_factory=list)


def _dig(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _horizontal_dist_m(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) / 1000.0


def _mean_pairwise_spacing_xy(points_mm: list[tuple[float, float]]) -> float | None:
    if len(points_mm) < 2:
        return None
    dists = [
        _horizontal_dist_m(points_mm[i], points_mm[j])
        for i in range(len(points_mm))
        for j in range(i + 1, len(points_mm))
    ]
    return sum(dists) / len(dists) if dists else None


def _triangle_mean_edge_m(corners_xy_mm: list[list[float]]) -> float | None:
    if len(corners_xy_mm) < 3:
        return None
    pts = [(float(c[0]), float(c[1])) for c in corners_xy_mm[:3]]
    edges = [_horizontal_dist_m(pts[i], pts[(i + 1) % 3]) for i in range(3)]
    return sum(edges) / 3.0


def _leg_surface_area_m2(leg: dict[str, Any]) -> float:
    length_mm = float(leg.get("length_mm") or 0.0)
    if length_mm <= 0:
        return 0.0
    fracs = leg.get("station_fracs") or [0.0, 1.0]
    radii_mm = leg.get("station_radii_mm") or []
    if len(fracs) < 2 or len(radii_mm) < 2:
        r_mm = float(leg.get("radius_mm") or 0.0)
        return 2.0 * math.pi * (r_mm / 1000.0) * (length_mm / 1000.0)
    area = 0.0
    for i in range(len(fracs) - 1):
        f0, f1 = float(fracs[i]), float(fracs[i + 1])
        r0 = float(radii_mm[min(i, len(radii_mm) - 1)]) / 1000.0
        r1 = float(radii_mm[min(i + 1, len(radii_mm) - 1)]) / 1000.0
        seg_len = (f1 - f0) * length_mm / 1000.0
        area += math.pi * (r0 + r1) * seg_len
    return area


def _top_plate_side_area_m2(plate: dict[str, Any]) -> float:
    r_m = float(plate.get("radius_mm") or 0.0) / 1000.0
    t_m = float(plate.get("thickness_mm") or 0.0) / 1000.0
    if r_m <= 0 or t_m <= 0:
        return 0.0
    return 2.0 * math.pi * r_m * t_m


def _leg_spacing_and_angles(legs: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    centers = []
    for leg in legs:
        c = leg.get("center_xyz_mm")
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            centers.append((float(c[0]), float(c[1])))
    if len(centers) < 2:
        return None, None
    mean_spacing = _mean_pairwise_spacing_xy(centers)
    if len(centers) == 3:
        origin = (
            sum(p[0] for p in centers) / 3.0,
            sum(p[1] for p in centers) / 3.0,
        )
        angles = sorted(
            math.degrees(math.atan2(p[1] - origin[1], p[0] - origin[0])) for p in centers
        )
        gaps = [angles[1] - angles[0], angles[2] - angles[1], 360.0 - angles[2] + angles[0]]
        angle_std = (sum((g - 120.0) ** 2 for g in gaps) / 3.0) ** 0.5
        return mean_spacing, angle_std
    return mean_spacing, None


def _leg_hub_spacing(legs: list[dict[str, Any]]) -> float | None:
    tops = []
    for leg in legs:
        t = leg.get("top_xyz_mm")
        if isinstance(t, (list, tuple)) and len(t) >= 2:
            tops.append((float(t[0]), float(t[1])))
    return _mean_pairwise_spacing_xy(tops)


def _leg_taper_ratio(legs: list[dict[str, Any]]) -> float | None:
    ratios = []
    for leg in legs:
        radii = leg.get("station_radii_mm") or []
        nums = [float(r) for r in radii if r]
        if len(nums) >= 2:
            lo, hi = min(nums), max(nums)
            if lo > 0:
                ratios.append(hi / lo)
    return sum(ratios) / len(ratios) if ratios else None


def _beso3_column_spacing(data: dict[str, Any]) -> float | None:
    cols = _dig(data, "beso3_reference_from_fcstd", "edge_columns_nondesign") or []
    pts = []
    for col in cols:
        c = col.get("center_xy_mm")
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            pts.append((float(c[0]), float(c[1])))
    return _mean_pairwise_spacing_xy(pts)


def _estimate_steel_mass_t(
    data: dict[str, Any],
    *,
    wall_thickness_m: float,
    steel_density_kgpm3: float,
    shell_volume_factor: float = 0.08,
) -> tuple[float, str, list[str]]:
    assumptions: list[str] = []
    override = _dig(data, "validation_overrides", "steel_mass_t")
    if override is not None:
        return float(override), "validation_overrides.steel_mass_t", assumptions

    beso7 = data.get("beso7_method1_topology_reconstructed") or {}
    legs = beso7.get("legs") or []
    opt = data.get("optimization_info") or {}
    plate = beso7.get("hub_top_plate") or {}

    if legs:
        try:
            from backend.tools.mixed_platform_steel import (
                compute_steel_report,
                default_params_from_geometry,
            )

            params = default_params_from_geometry(data)
            target = float(opt.get("target_power_MW") or 20.0)
            if opt.get("scale_factor") is not None:
                report = compute_steel_report(
                    data,
                    params=params,
                    target_power_mw=target,
                    optimize=False,
                    scale_factor=1.0,
                )
            else:
                report = compute_steel_report(
                    data,
                    params=params,
                    target_power_mw=target,
                    optimize=True,
                )
            steel = report["steel_summary"]
            comp = report["computation"]
            assumptions.append(
                f"用钢量：restruction4 混合平台模型（静倾≤{comp['pitch_limit_deg']}°），"
                f"水平缩放 {comp['final_horizontal_scale_factor']:.2f}，"
                f"结构钢 {steel['struct_mass_t']:.0f} t，"
                f"钢耗 {steel['steel_intensity_t_per_MW']:.1f} t/MW"
            )
            return (
                float(steel["struct_mass_t"]),
                "mixed_platform_steel_restruction4",
                assumptions,
            )
        except Exception as exc:
            assumptions.append(f"restruction4 计算失败，回退壳体估算：{exc}")

    plate_wall = float(opt.get("top_plate_wall_m") or wall_thickness_m)

    if legs:
        surface_m2 = sum(_leg_surface_area_m2(leg) for leg in legs)
        if plate:
            surface_m2 += _top_plate_side_area_m2(plate)
        mass_kg = surface_m2 * wall_thickness_m * steel_density_kgpm3
        if plate and opt.get("top_plate_hollow"):
            top_area = math.pi * (float(plate.get("radius_mm") or 0) / 1000.0) ** 2
            mass_kg += top_area * plate_wall * steel_density_kgpm3 * 2.0
        assumptions.append(
            f"钢重估算：三柱变径侧面积 + 顶盘侧面积 × 壁厚 {wall_thickness_m:.3f} m × 密度 {steel_density_kgpm3:.0f} kg/m³"
        )
        return mass_kg / 1000.0, "shell_surface_model", assumptions

    vol = _dig(beso7, "assembly_from_fcstd", "volume_m3")
    if vol is None:
        vol = _dig(data, "beso3_reference_from_fcstd", "full_assembly_pad", "volume_m3")
    if vol is not None:
        assumptions.append(
            f"回退估算：装配体积 {float(vol):.1f} m³ × 壳体系数 {shell_volume_factor} × 密度"
        )
        mass_kg = float(vol) * shell_volume_factor * steel_density_kgpm3
        return mass_kg / 1000.0, "volume_proxy", assumptions

    return 0.0, "missing_geometry", ["无法从 JSON 估算钢重"]


def _estimate_ai_review_economics(
    data: dict[str, Any],
    *,
    target_power_mw: float,
    steel_intensity_t_per_MW: float,
    total_steel_t: float,
    dt_ratio: float | None,
    wall_thickness_m: float,
    leg_taper_ratio: float | None,
    surrogate_prediction: Any | None = None,
) -> tuple[
    float | None,
    str,
    float | None,
    str,
    float | None,
    str,
    list[str],
]:
    """单位造价、施工年限、疲劳寿命：优先 validation_overrides，否则工程代理估算。"""
    notes: list[str] = []
    vo = data.get("validation_overrides") or {}

    cost_override = vo.get("unit_cost_cny_per_MW")
    if cost_override is not None:
        unit_cost = float(cost_override)
        cost_src = "validation_overrides.unit_cost_cny_per_MW"
    else:
        ref_int = 255.5
        ref_cost = 2500.0
        unit_cost = steel_intensity_t_per_MW * (ref_cost / ref_int) if steel_intensity_t_per_MW > 0 else None
        cost_src = "proxy_steel_intensity_to_cost"
        notes.append(f"单位造价代理：钢耗强度 × ({ref_cost:.0f}/{ref_int:.1f}) 万元/MW")

    const_override = vo.get("construction_years")
    if const_override is not None:
        construction = float(const_override)
        const_src = "validation_overrides.construction_years"
    else:
        base = 2.0
        steel_term = min(2.2, total_steel_t / 6000.0) if total_steel_t > 0 else 0.4
        taper_term = 0.15 if leg_taper_ratio and leg_taper_ratio > 1.35 else 0.0
        construction = base + steel_term + taper_term
        const_src = "proxy_steel_mass_and_complexity"
        notes.append("施工年限代理：基础 2.0 年 + 钢量/复杂度修正")

    fatigue_override = vo.get("fatigue_life_years")
    if fatigue_override is not None:
        fatigue = float(fatigue_override)
        fatigue_src = "validation_overrides.fatigue_life_years"
    else:
        life = 25.0
        if dt_ratio is not None:
            if 80 <= dt_ratio <= 250:
                life += 1.5
            elif dt_ratio > 250:
                life -= 2.0
            else:
                life -= 1.0
        if wall_thickness_m >= 0.04:
            life += 0.5
        if leg_taper_ratio is not None and leg_taper_ratio <= 1.45:
            life += 0.5
        fatigue = max(18.0, min(30.0, life))
        fatigue_src = "proxy_dt_wall_taper"
        notes.append("疲劳寿命代理：设计寿命 25 年 ± D/t、壁厚与变径修正")

    if surrogate_prediction is not None and getattr(surrogate_prediction, "enabled", False):
        from backend.surrogate.blend import blend_economics, choose_alpha

        alpha = choose_alpha(float(getattr(surrogate_prediction, "physics_residual", 0.0)))
        if alpha > 0:
            s_cost = getattr(surrogate_prediction, "unit_cost_cny_per_MW", None)
            s_const = getattr(surrogate_prediction, "construction_years", None)
            s_fat = getattr(surrogate_prediction, "fatigue_life_years", None)
            blended = blend_economics(
                (unit_cost, construction, fatigue),
                (s_cost, s_const, s_fat),
                alpha=alpha,
                sources=(cost_src, const_src, fatigue_src),
            )
            unit_cost = blended.unit_cost_cny_per_MW
            construction = blended.construction_years
            fatigue = blended.fatigue_life_years
            cost_src = blended.unit_cost_source
            const_src = blended.construction_years_source
            fatigue_src = blended.fatigue_life_source
            notes.extend(blended.notes)

    return unit_cost, cost_src, construction, const_src, fatigue, fatigue_src, notes


def extract_geometry_metrics(
    data: dict[str, Any],
    *,
    surrogate_prediction: Any | None = None,
) -> GeometryMetrics:
    opt = data.get("optimization_info") or {}
    target_power = float(opt.get("target_power_MW") or 20.0)
    draft_m = opt.get("draft_m")
    draft_m = float(draft_m) if draft_m is not None else None
    wall_thickness_m = float(opt.get("wall_thickness_m") or 0.06)
    steel_density = float(opt.get("steel_density_kgpm3") or 7850.0)
    scale_factor = opt.get("scale_factor")
    scale_factor = float(scale_factor) if scale_factor is not None else None

    beso7 = data.get("beso7_method1_topology_reconstructed") or {}
    legs = beso7.get("legs") or []
    stats = beso7.get("legs_statistics") or {}
    plate = beso7.get("hub_top_plate") or {}
    asm = beso7.get("assembly_from_fcstd") or {}
    bbox = asm.get("bounding_box_mm") or {}

    leg_mean_d = _dig(stats, "diameter_mm", "mean")
    leg_min_d = _dig(stats, "diameter_mm", "min")
    leg_max_d = _dig(stats, "diameter_mm", "max")
    leg_mean_len = _dig(stats, "length_mm", "mean")
    spacing_m, angle_std = _leg_spacing_and_angles(legs)
    hub_spacing = _leg_hub_spacing(legs)
    taper = _leg_taper_ratio(legs)

    leg_mean_d_m = float(leg_mean_d) / 1000.0 if leg_mean_d else None
    leg_mean_len_m = float(leg_mean_len) / 1000.0 if leg_mean_len else None
    slenderness = (
        leg_mean_len_m / leg_mean_d_m
        if leg_mean_len_m and leg_mean_d_m and leg_mean_d_m > 0
        else None
    )
    diam_uniformity = None
    if leg_mean_d and leg_min_d and leg_max_d and float(leg_mean_d) > 0:
        diam_uniformity = (float(leg_max_d) - float(leg_min_d)) / float(leg_mean_d) * 100.0

    plate_d_m = float(plate.get("diameter_mm") or 0) / 1000.0 if plate.get("diameter_mm") else None
    plate_t_m = float(plate.get("thickness_mm") or 0) / 1000.0 if plate.get("thickness_mm") else None
    plate_leg_ratio = (
        plate_d_m / leg_mean_d_m if plate_d_m and leg_mean_d_m and leg_mean_d_m > 0 else None
    )
    dt_ratio = leg_mean_d_m / wall_thickness_m if leg_mean_d_m and wall_thickness_m > 0 else None

    z_len = bbox.get("z_length")
    x_len = bbox.get("x_length")
    y_len = bbox.get("y_length")
    bbox_z_m = float(z_len) / 1000.0 if z_len is not None else None
    bbox_xy = None
    if x_len is not None and y_len is not None:
        bbox_xy = max(float(x_len), float(y_len)) / 1000.0

    hub_z = float(plate.get("z_top_mm") or 0) / 1000.0 if plate.get("z_top_mm") is not None else None
    freeboard = (hub_z - draft_m) if hub_z is not None and draft_m is not None else None

    pad = _dig(data, "beso3_reference_from_fcstd", "design_domain_pad001") or {}
    pad_bbox = pad.get("bounding_box_mm") or {}
    pad_span = None
    if pad_bbox.get("x_length") and pad_bbox.get("y_length"):
        pad_span = max(float(pad_bbox["x_length"]), float(pad_bbox["y_length"])) / 1000.0
    tri_edge = _triangle_mean_edge_m(pad.get("top_triangle_corners_xy_mm") or [])
    design_span = tri_edge or pad_span

    beso3_spacing = _beso3_column_spacing(data)
    column_spacing = beso3_spacing or design_span or spacing_m

    steel_mass_t, mass_source, assumptions = _estimate_steel_mass_t(
        data,
        wall_thickness_m=wall_thickness_m,
        steel_density_kgpm3=steel_density,
    )
    intensity = steel_mass_t / target_power if target_power > 0 else 0.0
    vol = asm.get("volume_m3")

    unit_cost, cost_src, construction, const_src, fatigue, fatigue_src, econ_notes = _estimate_ai_review_economics(
        data,
        target_power_mw=target_power,
        steel_intensity_t_per_MW=intensity,
        total_steel_t=steel_mass_t,
        dt_ratio=dt_ratio,
        wall_thickness_m=wall_thickness_m,
        leg_taper_ratio=taper,
        surrogate_prediction=surrogate_prediction,
    )
    assumptions.extend(econ_notes)
    if surrogate_prediction is not None and getattr(surrogate_prediction, "assumptions", None):
        assumptions.extend(list(surrogate_prediction.assumptions))

    return GeometryMetrics(
        target_power_MW=target_power,
        draft_m=draft_m,
        wall_thickness_m=wall_thickness_m,
        steel_density_kgpm3=steel_density,
        assembly_volume_m3=float(vol) if vol is not None else None,
        bbox_z_m=bbox_z_m,
        bbox_xy_span_m=bbox_xy,
        leg_mean_diameter_m=leg_mean_d_m,
        leg_min_diameter_m=float(leg_min_d) / 1000.0 if leg_min_d else None,
        leg_max_diameter_m=float(leg_max_d) / 1000.0 if leg_max_d else None,
        leg_mean_length_m=leg_mean_len_m,
        leg_slenderness_L_over_D=slenderness,
        leg_diameter_uniformity_pct=diam_uniformity,
        leg_taper_ratio=taper,
        leg_mean_spacing_m=spacing_m,
        leg_hub_spacing_mean_m=hub_spacing,
        beso3_column_spacing_m=beso3_spacing,
        design_domain_span_m=design_span,
        leg_layout_angle_deg_std=angle_std,
        top_plate_diameter_m=plate_d_m,
        top_plate_thickness_m=plate_t_m,
        plate_to_leg_diameter_ratio=plate_leg_ratio,
        dt_ratio=dt_ratio,
        hub_elevation_m=hub_z,
        freeboard_proxy_m=freeboard,
        scale_factor=scale_factor,
        steel_mass_t_est=steel_mass_t,
        steel_mass_t_source=mass_source,
        steel_intensity_t_per_MW=intensity,
        total_steel_t=steel_mass_t,
        unit_cost_cny_per_MW=unit_cost,
        unit_cost_source=cost_src,
        construction_years=construction,
        construction_years_source=const_src,
        fatigue_life_years=fatigue,
        fatigue_life_source=fatigue_src,
        assumptions=assumptions,
    )


def metrics_as_dict(m: GeometryMetrics) -> dict[str, float | None]:
    spacing_for_rules = m.beso3_column_spacing_m or m.design_domain_span_m or m.leg_mean_spacing_m
    return {
        "target_power_MW": m.target_power_MW,
        "draft_m": m.draft_m,
        "wall_thickness_m": m.wall_thickness_m,
        "steel_density_kgpm3": m.steel_density_kgpm3,
        "assembly_volume_m3": m.assembly_volume_m3,
        "bbox_z_m": m.bbox_z_m,
        "bbox_xy_span_m": m.bbox_xy_span_m,
        "leg_mean_diameter_m": m.leg_mean_diameter_m,
        "leg_min_diameter_m": m.leg_min_diameter_m,
        "leg_max_diameter_m": m.leg_max_diameter_m,
        "leg_mean_length_m": m.leg_mean_length_m,
        "leg_slenderness_L_over_D": m.leg_slenderness_L_over_D,
        "leg_diameter_uniformity_pct": m.leg_diameter_uniformity_pct,
        "leg_taper_ratio": m.leg_taper_ratio,
        "leg_mean_spacing_m": m.leg_mean_spacing_m,
        "leg_hub_spacing_mean_m": m.leg_hub_spacing_mean_m,
        "beso3_column_spacing_m": m.beso3_column_spacing_m,
        "design_domain_span_m": m.design_domain_span_m,
        "column_spacing_m": spacing_for_rules,
        "leg_layout_angle_deg_std": m.leg_layout_angle_deg_std,
        "top_plate_diameter_m": m.top_plate_diameter_m,
        "top_plate_thickness_m": m.top_plate_thickness_m,
        "plate_to_leg_diameter_ratio": m.plate_to_leg_diameter_ratio,
        "dt_ratio": m.dt_ratio,
        "hub_elevation_m": m.hub_elevation_m,
        "freeboard_proxy_m": m.freeboard_proxy_m,
        "scale_factor": m.scale_factor,
        "steel_mass_t_est": m.steel_mass_t_est,
        "steel_intensity_t_per_MW": m.steel_intensity_t_per_MW,
        "total_steel_t": m.total_steel_t,
        "unit_cost_cny_per_MW": m.unit_cost_cny_per_MW,
        "construction_years": m.construction_years,
        "fatigue_life_years": m.fatigue_life_years,
    }
