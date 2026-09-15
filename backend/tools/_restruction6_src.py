# -*- coding: utf-8 -*-
"""
本程序基于“固定吃水”设计原则，对混合半潜式平台进行功率驱动的几何缩放，并优化水平尺寸以满足静倾角 ≤5° 的同时最小化单位兆瓦用钢量 (t/MW)
缩放策略
    - 固定吃水：水线到平台最低点的距离保持不变（符合码头水深及运输限制）。
    - 水平尺寸缩放：所有水平方向尺寸（立柱直径、间距、顶盘半径、XY坐标）统一乘以缩放因子 s；垂直方向尺寸（高度、厚度、Z坐标）保持不变。
    - 初始缩放因子 s0 = sqrt(P_target / P_base)，源于叶轮直径与功率的平方根关系。
    - 额外优化因子 x（范围 0.5~2.5），最终水平缩放因子 s = s0 * x。
物理计算模型
    - 结构质量：基于空心圆柱体积公式，钢材密度默认 7850 kg/m³，壁厚可调。
    - 桩靴/垂荡板质量：计入侧壁、底板及顶板封板质量，更接近真实物理实体。
    - 倾斜立柱体积：采用真实 3D 斜长而非垂直投影高度，修正体积计算误差。
    - 排水体积：仅计入水线 (z=0) 以下构件的外包络体积（按外径计算）。
    - 重心与浮心：各构件质量加权平均；压载重心固定在水面下18 m (z=-18 m)。
    - 顶部荷载处理：RNA（机头）与塔筒质量独立建模，分别置于轮毂高度和塔筒重心高度，解决等效重心导致的稳性计算偏差。
    - 水线面惯性矩 I_y：收集所有与水线面相交的截面，考虑倾斜立柱的椭圆截面面积补偿，应用平行轴定理：I_y = Σ(I_self + A * x²)
    - 静水回复刚度 K55：K55 = ρ_w g I_y + ρ_w g V_disp (z_B - z_G)
    - 额定推力：F_t = 0.5 ρ_air A_rotor V_rated² C_T
    - 静倾角：θ = arctan(F_t * H_hub / K55)，要求 θ ≤ 5°。
    - 单位用钢量：steel_per_MW = M_struct / (1000 * P_target)
优化模型
    - 目标函数：最小化单位用钢量 (t/MW)
    - 约束条件：静倾角 ≤ 5°
    - 优化变量：额外缩放因子 x
    - 算法：优先使用 SLSQP（带自定义梯度），失败时自动切换为暴力扫描（0.5~2.5，步长 0.005）
数据结构兼容
    - 自动识别 JSON 中的拓扑键名（优先 beso9_method1_topology_reconstructed，回退 beso7_method1_topology_reconstructed）。
    - 兼容 edge_columns_nondesign 在顶层或嵌套于 beso3_reference_from_fcstd 下的两种结构。
注意事项
    - 所有长度单位在 JSON 中必须为毫米 (mm)，程序内部自动转换为米。
    - 固定吃水要求几何最低点与水线距离等于用户输入的吃水值；若实际几何最低点更深，计算结果中浮心位置可能不准确，建议根据平台实际吃水输入。
    - 若压载质量为负，表示平台结构过重或排水体积不足，程序自动将此设计判定为不可行（静倾角强制设为 90°）以淘汰。
    - 优化失败时会自动执行手动扫描，确保输出可行解。
    - 本程序仅基于静水稳性，未计及波浪载荷、系泊及动态效应，适用于初步设计筛选。
    - 塔筒重心高度随功率因子 s_power 同比例缩放，以保持几何相似性。
"""

import json
import math
import copy
import numpy as np
from scipy.optimize import minimize

# matplotlib 仅用于 CLI 可视化；服务端库路径不强制依赖 GUI backend

# ===================== 全局常数 (默认 20MW 级别参数) =====================
DEFAULT_STEEL_DENSITY = 7850.0
DEFAULT_WATER_DENSITY = 1025.0
DEFAULT_G = 9.81
DEFAULT_WALL_THICKNESS = 0.06            # m
DEFAULT_AIR_DENSITY = 1.225
DEFAULT_RATED_WIND_SPEED = 11.5          # 匹配表格 11.5 m/s
DEFAULT_THRUST_COEFF = 0.8
DEFAULT_RATED_POWER_MW = 20.0
DEFAULT_ROTOR_DIA_M = 262.0              # 叶片 131m * 2
DEFAULT_HUB_HEIGHT_M = 158.7             # 轮毂高度 (推力作用点)
DEFAULT_RNA_MASS_KG = 832000.0           # 机头质量 832 t
DEFAULT_TOWER_MASS_KG = 1665000.0        # 塔筒质量 1665 t
DEFAULT_TOWER_COG_M = 75.0               # 塔筒重心高度估算 (m)
DEFAULT_BALLAST_COG_Z_M = -18.0          # 压载重心固定在水面下18 m

def mm_to_m(v):
    return float(v) / 1000.0

def cylindrical_volume(outer_diam, inner_diam, height):
    a_outer = math.pi * (outer_diam/2)**2
    a_inner = math.pi * (inner_diam/2)**2
    return (a_outer - a_inner) * height

def point_on_line(p1, p2, t):
    return [float(p1[i] + t*(p2[i]-p1[i])) for i in range(3)]

def intersect_z(p1, p2, z_target):
    if abs(p2[2]-p1[2]) < 1e-9:
        return None
    t = (z_target - p1[2]) / (p2[2]-p1[2])
    return float(t) if 0.0 <= t <= 1.0 else None

def distance_3d(p1, p2):
    return float(np.linalg.norm(np.array(p1, dtype=float) - np.array(p2, dtype=float)))

# ===================== 几何缩放 (兼容版) =====================
def scale_geometry_horizontal(json_data, scale_factor):
    new_data = copy.deepcopy(json_data)
    topology_key = 'beso9_method1_topology_reconstructed' if 'beso9_method1_topology_reconstructed' in new_data else 'beso7_method1_topology_reconstructed'
    
    for leg in new_data.get(topology_key, {}).get('legs', []):
        if 'radius_mm' in leg:
            leg['radius_mm'] *= scale_factor
            leg['diameter_mm'] = leg['radius_mm'] * 2.0
        elif 'diameter_mm' in leg:
            leg['diameter_mm'] *= scale_factor
            leg['radius_mm'] = leg['diameter_mm'] / 2.0
            
        for i in range(2):
            leg['base_xyz_mm'][i] *= scale_factor
            leg['top_xyz_mm'][i] *= scale_factor
            
        dx = leg['top_xyz_mm'][0] - leg['base_xyz_mm'][0]
        dy = leg['top_xyz_mm'][1] - leg['base_xyz_mm'][1]
        dz = leg['top_xyz_mm'][2] - leg['base_xyz_mm'][2]
        true_len = math.sqrt(dx**2 + dy**2 + dz**2)
        leg['length_mm'] = true_len

    plate = new_data.get(topology_key, {}).get('hub_top_plate', {})
    if plate:
        if 'radius_mm' in plate:
            plate['radius_mm'] *= scale_factor
            plate['diameter_mm'] = plate['radius_mm'] * 2.0
        elif 'diameter_mm' in plate:
            plate['diameter_mm'] *= scale_factor
            plate['radius_mm'] = plate['diameter_mm'] / 2.0
            
        plate['center_xy_mm'][0] *= scale_factor
        plate['center_xy_mm'][1] *= scale_factor
        
    edge_cols = new_data.get('beso3_reference_from_fcstd', {}).get('edge_columns_nondesign', [])
    if not edge_cols:
        edge_cols = new_data.get('edge_columns_nondesign', [])
        
    for col in edge_cols:
        if 'true_orthogonal_radius_mm' in col:
            col['true_orthogonal_radius_mm'] *= scale_factor
            col['radius_mm'] = col['true_orthogonal_radius_mm']
        elif 'radius_mm' in col:
            col['radius_mm'] *= scale_factor
            
        if 'diameter_mm' in col:
            col['diameter_mm'] *= scale_factor
            
        if 'center_xy_mm' in col:
            col['center_xy_mm'][0] *= scale_factor
            col['center_xy_mm'][1] *= scale_factor
        if 'top_center_xy_mm' in col:
            col['top_center_xy_mm'][0] *= scale_factor
            col['top_center_xy_mm'][1] *= scale_factor
            
        if 'footing' in col:
            foot = col['footing']
            if 'equivalent_radius_mm' in foot:
                foot['equivalent_radius_mm'] *= scale_factor
            if 'center_xy_mm' in foot:
                foot['center_xy_mm'][0] *= scale_factor
                foot['center_xy_mm'][1] *= scale_factor
                
    return new_data

# ===================== 平台计算类 =====================
class MixedPlatform:
    def __init__(self, json_data, wall_thickness, steel_density, water_density, draft,
                 current_power_MW, rotor_dia_m, hub_height_m, rna_mass_kg, tower_mass_kg, tower_cog_m,
                 top_plate_hollow=True, top_plate_wall=None, ballast_cog_z_m=DEFAULT_BALLAST_COG_Z_M):
        self.wall_thickness = wall_thickness
        self.steel_density = steel_density
        self.water_density = water_density
        self.draft = draft
        self.current_power_MW = current_power_MW
        self.rotor_dia_m = rotor_dia_m
        self.hub_height_m = hub_height_m
        self.rna_mass_kg = rna_mass_kg
        self.tower_mass_kg = tower_mass_kg
        self.tower_cog_m = tower_cog_m
        self.top_plate_hollow = top_plate_hollow
        self.top_plate_wall = top_plate_wall if top_plate_wall is not None else wall_thickness
        self.ballast_cog_z_m = ballast_cog_z_m
        
        self.beso = json_data.get('beso9_method1_topology_reconstructed') or json_data.get('beso7_method1_topology_reconstructed', {})
        self.edge_cols = json_data.get('beso3_reference_from_fcstd', {}).get('edge_columns_nondesign', [])
        if not self.edge_cols:
            self.edge_cols = json_data.get('edge_columns_nondesign', [])

    def _add_leg(self, leg, comp_masses, submerged_vols, waterplane_items, mesh_geoms):
        D = mm_to_m(leg.get('diameter_mm', leg.get('radius_mm', 0) * 2))
        L = mm_to_m(leg['length_mm']) 
        base = [mm_to_m(v) for v in leg['base_xyz_mm']]
        top = [mm_to_m(v) for v in leg['top_xyz_mm']]
        inner = max(0.0, D - 2*self.wall_thickness)
        mass = cylindrical_volume(D, inner, L) * self.steel_density
        cog_z = (base[2]+top[2])/2
        comp_masses.append((mass, cog_z))
        
        mesh_geoms.append(('cylinder', np.array(base), np.array(top), D/2, '#1f77b4'))

        # 排水体积严格限制在固定吃水范围 [-draft, 0] 内。
        # 先求该圆柱中心线与两个吃水边界 z=-draft、z=0 的交点，
        # 再计算两交点之间的真实3D长度；这样即使整根构件位于水面以下，
        # 也不会把 -draft 以下的部分错误计入排水量。
        z_low = min(base[2], top[2])
        z_high = max(base[2], top[2])
        sub_bot = max(z_low, -self.draft)
        sub_top = min(z_high, 0.0)
        sub_vol = 0.0
        if sub_top > sub_bot and L > 1e-12:
            t_low = (sub_bot - base[2]) / (top[2] - base[2])
            t_high = (sub_top - base[2]) / (top[2] - base[2])
            p_low = point_on_line(base, top, t_low)
            p_high = point_on_line(base, top, t_high)
            sub_len = distance_3d(p_low, p_high)
            area = math.pi * (D/2)**2
            sub_vol = area * sub_len
            if sub_vol > 0:
                mid_z = 0.5 * (p_low[2] + p_high[2])
                submerged_vols.append((sub_vol, mid_z))

        # 水线面仅在中心线穿过 z=0 时存在。
        t_swl = intersect_z(base, top, 0)
        if t_swl is not None:
            center = point_on_line(base, top, t_swl)
            axis_vec = np.array(top, dtype=float) - np.array(base, dtype=float)
            axis_len = np.linalg.norm(axis_vec)
            uz = abs(axis_vec[2]) / axis_len if axis_len > 1e-12 else 1.0
            uz = max(uz, 1e-12)
            area = math.pi * (D/2)**2 / uz
            a = (D/2) / uz
            b = D/2

            # 椭圆长轴方向应垂直于圆柱轴线的水平投影；
            # 短轴方向平行于该水平投影。
            ux = axis_vec[0] / axis_len
            uy = axis_vec[1] / axis_len
            h_norm = math.hypot(ux, uy)
            if h_norm > 1e-12:
                e_minor_x = ux / h_norm
                e_minor_y = uy / h_norm
                e_major_x = -e_minor_y
                e_major_y = e_minor_x
            else:
                e_major_x, e_major_y = 1.0, 0.0
                e_minor_x, e_minor_y = 0.0, 1.0

            I_y_self = area / 4.0 * (
                a**2 * e_major_x**2 + b**2 * e_minor_x**2
            )
            waterplane_items.append({
                'x': center[0], 'y': center[1], 'area': area,
                'I_y_self': I_y_self
            })


    def _add_vertical_column(self, col, comp_masses, submerged_vols, waterplane_items, mesh_geoms):
        radius = mm_to_m(col.get('true_orthogonal_radius_mm', col.get('radius_mm', 0)))
        if radius==0 and 'diameter_mm' in col:
            radius = mm_to_m(col['diameter_mm'])/2
        if radius==0: return
        
        z_bot = mm_to_m(col.get('z_bottom_mm',0))
        z_top = mm_to_m(col.get('z_top_mm',0))
        
        # 提取真实的3D中心坐标计算斜长。
        # 默认顶部坐标直接复用原始mm坐标，避免重复进行 mm -> m 转换。
        center_xy_mm = col.get('center_xy_mm', [0, 0])
        top_center_xy_mm = col.get('top_center_xy_mm', center_xy_mm)
        cx = mm_to_m(center_xy_mm[0])
        cy = mm_to_m(center_xy_mm[1])
        top_cx = mm_to_m(top_center_xy_mm[0])
        top_cy = mm_to_m(top_center_xy_mm[1])
        
        true_len = math.sqrt((top_cx - cx)**2 + (top_cy - cy)**2 + (z_top - z_bot)**2)
            
        D = 2*radius
        inner = max(0.0, D - 2*self.wall_thickness)
        mass = cylindrical_volume(D, inner, true_len) * self.steel_density
        cog_z = (z_bot+z_top)/2
        comp_masses.append((mass, cog_z))
        
        mesh_geoms.append(('cylinder', np.array([cx, cy, z_bot]), np.array([top_cx, top_cy, z_top]), radius, '#d62728'))

        # 排水体积：只计入 [-draft, 0] 范围内的圆柱段。
        z_low = min(z_bot, z_top)
        z_high = max(z_bot, z_top)
        sub_bot = max(z_low, -self.draft)
        sub_top = min(z_high, 0.0)

        if sub_top > sub_bot and abs(z_top - z_bot) > 1e-12:
            t_low = (sub_bot - z_bot) / (z_top - z_bot)
            t_high = (sub_top - z_bot) / (z_top - z_bot)
            p_low = point_on_line(
                [cx, cy, z_bot], [top_cx, top_cy, z_top], t_low
            )
            p_high = point_on_line(
                [cx, cy, z_bot], [top_cx, top_cy, z_top], t_high
            )
            sub_len = distance_3d(p_low, p_high)
            area = math.pi * radius**2
            sub_vol = area * sub_len
            sub_cog = 0.5 * (p_low[2] + p_high[2])
            submerged_vols.append((sub_vol, sub_cog))

        # 水线面：倾斜圆柱与水平水面相交形成真实椭圆。
        # 水线中心取中心线与 z=0 的交点。
        t_swl = intersect_z(
            [cx, cy, z_bot], [top_cx, top_cy, z_top], 0.0
        )
        if t_swl is not None:
            center = point_on_line(
                [cx, cy, z_bot], [top_cx, top_cy, z_top], t_swl
            )

            axis_vec = np.array(
                [top_cx - cx, top_cy - cy, z_top - z_bot], dtype=float
            )
            axis_len = np.linalg.norm(axis_vec)
            uz = abs(axis_vec[2]) / axis_len if axis_len > 1e-12 else 1.0
            uz = max(uz, 1e-12)

            # 椭圆半短轴 b=R，半长轴 a=R/|cos(theta)|。
            area = math.pi * radius**2 / uz
            a = radius / uz
            b = radius

            # 椭圆长轴方向 = 圆柱轴线在水平面上的投影方向。
            ux = axis_vec[0] / axis_len
            uy = axis_vec[1] / axis_len
            h_norm = math.hypot(ux, uy)

            if h_norm > 1e-12:
                e_major_x = ux / h_norm
                e_major_y = uy / h_norm
                e_minor_x = -e_major_y
            else:
                e_major_x = 1.0
                e_minor_x = 0.0

            # 关于平台 y 轴的截面自身面积二阶矩。
            # I_y,self = A/4 * (a²*e_major_x² + b²*e_minor_x²)
            I_y_self = area / 4.0 * (
                a**2 * e_major_x**2 + b**2 * e_minor_x**2
            )

            waterplane_items.append({
                'x': center[0],
                'y': center[1],
                'area': area,
                'I_y_self': I_y_self
            })

    def _add_footing(self, foot, parent_col_radius, comp_masses, submerged_vols, waterplane_items, mesh_geoms):
        radius = mm_to_m(foot.get('equivalent_radius_mm',0))
        if radius==0: return
        z_bot = mm_to_m(foot.get('z_bottom_mm',0))
        z_top = mm_to_m(foot.get('z_top_mm',0))
        height = z_top - z_bot
        
        fx = mm_to_m(foot.get('center_xy_mm', [0,0])[0])
        fy = mm_to_m(foot.get('center_xy_mm', [0,0])[1])
            
        D = 2*radius
        inner = max(0.0, D - 2*self.wall_thickness)
        
        # 修复 2：计算真实垂荡板质量 (包含侧壁、底板、顶板)
        side_wall_mass = cylindrical_volume(D, inner, height) * self.steel_density
        bottom_plate_vol = math.pi * radius**2 * self.wall_thickness
        top_plate_area = math.pi * (radius**2 - parent_col_radius**2)
        if top_plate_area < 0: top_plate_area = 0
        top_plate_vol = top_plate_area * self.wall_thickness
        
        total_plate_mass = (bottom_plate_vol + top_plate_vol) * self.steel_density
        mass = side_wall_mass + total_plate_mass
        
        cog_z = (z_bot+z_top)/2
        comp_masses.append((mass, cog_z))
        mesh_geoms.append(('cylinder', np.array([fx, fy, z_bot]), np.array([fx, fy, z_top]), radius, '#2ca02c'))

        sub_bot = max(z_bot, -self.draft)
        sub_top = min(z_top, 0)
        if sub_top > sub_bot:
            sub_len = sub_top - sub_bot
            area = math.pi*radius**2
            sub_vol = area * sub_len
            sub_cog = (sub_bot+sub_top)/2
            submerged_vols.append((sub_vol, sub_cog))

    def _add_top_plate(self, plate, comp_masses, submerged_vols, waterplane_items, mesh_geoms):
        R = mm_to_m(plate.get('radius_mm', plate.get('diameter_mm', 0)/2))
        H = mm_to_m(plate['thickness_mm'])
        z_bot = mm_to_m(plate['z_bottom_mm'])
        z_top = mm_to_m(plate['z_top_mm'])
        cx = mm_to_m(plate['center_xy_mm'][0])
        cy = mm_to_m(plate['center_xy_mm'][1])
        
        if self.top_plate_hollow:
            r_in = max(0.0, R - self.top_plate_wall)
            h_in = max(0.0, H - 2 * self.top_plate_wall)
            vol = (math.pi * R**2 * H) - (math.pi * r_in**2 * h_in)
        else:
            vol = math.pi * R**2 * H
            
        mass = vol * self.steel_density
        cog_z = (z_bot+z_top)/2
        comp_masses.append((mass, cog_z))
        mesh_geoms.append(('cylinder', np.array([cx, cy, z_bot]), np.array([cx, cy, z_top]), R, '#17becf'))

    def compute(self, mesh_geoms=None):
        comp_masses = []
        submerged_vols = []
        waterplane_items = []
        if mesh_geoms is not None:
            mesh_geoms.clear()
        else:
            mesh_geoms = []

        for leg in self.beso.get('legs', []):
            self._add_leg(leg, comp_masses, submerged_vols, waterplane_items, mesh_geoms)
            
        for col in self.edge_cols:
            self._add_vertical_column(col, comp_masses, submerged_vols, waterplane_items, mesh_geoms)
            if 'footing' in col:
                parent_rad = mm_to_m(col.get('true_orthogonal_radius_mm', col.get('radius_mm', 0)))
                self._add_footing(col['footing'], parent_rad, comp_masses, submerged_vols, waterplane_items, mesh_geoms)
                
        plate = self.beso.get('hub_top_plate', {})
        if plate:
            self._add_top_plate(plate, comp_masses, submerged_vols, waterplane_items, mesh_geoms)

        total_mass_struct = sum(m for m,_ in comp_masses)
        cog_z_struct = sum(m*z for m,z in comp_masses)/total_mass_struct if total_mass_struct>0 else 0
        total_sub_vol = sum(v for v,_ in submerged_vols)
        cob_z = sum(v*z for v,z in submerged_vols)/total_sub_vol if total_sub_vol>0 else 0

        # 水线面关于平台 y 轴的惯性矩。
        # 每个截面使用真实椭圆自身惯性矩，再应用平行轴定理 A*x²。
        I_y = 0.0
        for item in waterplane_items:
            if isinstance(item, dict):
                x = item['x']
                area = item['area']
                I_self = item['I_y_self']
            else:
                x, y, area = item
                D_equiv = 2 * math.sqrt(area / math.pi)
                I_self = math.pi * D_equiv**4 / 64.0
            I_y += I_self + area * x**2
        if I_y == 0:
            I_y = 1e-6

        disp_mass = self.water_density * total_sub_vol
        # 修正 3：加入独立的塔筒质量进行压载配平
        ballast = disp_mass - total_mass_struct - self.rna_mass_kg - self.tower_mass_kg
        
        # 若浮力不足，则此设计不可行，强制倾角为 90° 以淘汰
        if ballast < 0:
            ballast = 0
            # 不计算后续稳性，直接返回无效结果
            pitch_deg = 90.0
            K55 = 0.0
            total_mass = total_mass_struct + self.rna_mass_kg + self.tower_mass_kg
            cog_z_total = 0.0  # 无效
            thrust = 0.0
            steel_per_MW = total_mass_struct / 1000.0 / self.current_power_MW
            return {
                'struct_mass_kg': total_mass_struct,
                'ballast_mass_kg': ballast,
                'total_mass_kg': total_mass,
                'cog_z_struct_m': cog_z_struct,
                'cob_z_m': cob_z,
                'cog_z_total_m': cog_z_total,
                'displaced_vol_m3': total_sub_vol,
                'I_y_m4': I_y,
                'K55_Nm_per_rad': K55,
                'rated_thrust_N': 0.0,
                'pitch_angle_deg': pitch_deg,
                'steel_per_MW_t': steel_per_MW,
            }
        
        total_mass = total_mass_struct + ballast + self.rna_mass_kg + self.tower_mass_kg
        ballast_cog = self.ballast_cog_z_m
        
        # 修正 4：分别将 RNA(机头)和 Tower(塔筒) 的重量回归真实位置
        if total_mass>0:
            cog_z_total = (total_mass_struct*cog_z_struct + ballast*ballast_cog + 
                           self.rna_mass_kg*self.hub_height_m + 
                           self.tower_mass_kg*self.tower_cog_m) / total_mass
        else:
            cog_z_total = 0

        F_b = self.water_density * DEFAULT_G * total_sub_vol
        K55 = self.water_density * DEFAULT_G * I_y + F_b * (cob_z - cog_z_total)

        rotor_area = math.pi*(self.rotor_dia_m/2)**2
        thrust = 0.5*DEFAULT_AIR_DENSITY*rotor_area*DEFAULT_RATED_WIND_SPEED**2*DEFAULT_THRUST_COEFF
        tilt_moment = thrust * self.hub_height_m
        pitch_deg = math.degrees(tilt_moment/K55) if K55>0 else 90

        steel_per_MW = total_mass_struct / 1000.0 / self.current_power_MW
        return {
            'struct_mass_kg': total_mass_struct,
            'ballast_mass_kg': ballast,
            'total_mass_kg': total_mass,
            'cog_z_struct_m': cog_z_struct,
            'cob_z_m': cob_z,
            'cog_z_total_m': cog_z_total,
            'displaced_vol_m3': total_sub_vol,
            'I_y_m4': I_y,
            'K55_Nm_per_rad': K55,
            'rated_thrust_N': thrust,
            'pitch_angle_deg': pitch_deg,
            'steel_per_MW_t': steel_per_MW,
        }

# ===================== 交互与优化 =====================
def interactive_input():
    print("\n=== 请设置风机与计算参数（直接回车使用 20MW 默认值）===")
    rated = float(input(f"基准功率 (MW) 默认 {DEFAULT_RATED_POWER_MW}: ") or DEFAULT_RATED_POWER_MW)
    rotor = float(input(f"叶轮直径 (m) 默认 {DEFAULT_ROTOR_DIA_M}: ") or DEFAULT_ROTOR_DIA_M)
    hub = float(input(f"轮毂高度 (m) 默认 {DEFAULT_HUB_HEIGHT_M}: ") or DEFAULT_HUB_HEIGHT_M)
    rna = float(input(f"机头(RNA)质量 (kg) 默认 {DEFAULT_RNA_MASS_KG}: ") or DEFAULT_RNA_MASS_KG)
    tower_m = float(input(f"塔筒质量 (kg) 默认 {DEFAULT_TOWER_MASS_KG}: ") or DEFAULT_TOWER_MASS_KG)
    tower_cog = float(input(f"塔筒重心高度 (m) 默认 {DEFAULT_TOWER_COG_M}: ") or DEFAULT_TOWER_COG_M)
    return {
        'steel_density': DEFAULT_STEEL_DENSITY, 'water_density': DEFAULT_WATER_DENSITY, 'wall_thickness': DEFAULT_WALL_THICKNESS,
        'draft': 21.0, 'ballast_cog_z_m': DEFAULT_BALLAST_COG_Z_M,
        'top_plate_hollow': True, 'top_plate_wall_thickness': DEFAULT_WALL_THICKNESS,
        'rated_power_MW': rated, 'rotor_dia_m': rotor, 'hub_height_m': hub, 
        'rna_mass_kg': rna, 'tower_mass_kg': tower_m, 'tower_cog_m': tower_cog
    }

def compute_for_scale(json_data, scale, params, target_MW, mesh_geoms=None):
    scaled = scale_geometry_horizontal(json_data, scale)
    s_power = math.sqrt(target_MW / params['rated_power_MW'])
    # 塔筒重心高度随功率缩放（与轮毂高度同比例）
    tower_cog_scaled = params['tower_cog_m'] * s_power
    plat = MixedPlatform(
        scaled, params['wall_thickness'], params['steel_density'], params['water_density'], params['draft'],
        target_MW, params['rotor_dia_m'] * s_power, params['hub_height_m'] * s_power,
        params['rna_mass_kg'] * (s_power ** 0.88), params['tower_mass_kg'] * (s_power ** 0.88), tower_cog_scaled,
        params['top_plate_hollow'], params['top_plate_wall_thickness'], params['ballast_cog_z_m']
    )
    return plat.compute(mesh_geoms)

def optimize_scale(json_data, params, target_MW, quiet=True, pitch_limit_deg=5.0,
                   x_min=0.5, x_max=2.5, scan_step=0.005):
    s0 = math.sqrt(target_MW / params['rated_power_MW'])
    note = "SLSQP"
    
    def obj(x): return compute_for_scale(json_data, s0 * x[0], params, target_MW)['steel_per_MW_t']
    def con(x): return float(pitch_limit_deg) - compute_for_scale(json_data, s0 * x[0], params, target_MW)['pitch_angle_deg']

    def obj_jac(x):
        eps = 1e-3 
        return np.array([(compute_for_scale(json_data, s0 * (x[0] + eps), params, target_MW)['steel_per_MW_t'] - 
                          compute_for_scale(json_data, s0 * (x[0] - eps), params, target_MW)['steel_per_MW_t']) / (2 * eps)])
        
    def con_jac(x):
        eps = 1e-3
        return np.array([((float(pitch_limit_deg) - compute_for_scale(json_data, s0 * (x[0] + eps), params, target_MW)['pitch_angle_deg']) - 
                          (float(pitch_limit_deg) - compute_for_scale(json_data, s0 * (x[0] - eps), params, target_MW)['pitch_angle_deg'])) / (2 * eps)])

    if not quiet:
        print("\n--- 启动 SLSQP 优化器 ---")
    res = minimize(
        obj, x0=[1.0], method='SLSQP', jac=obj_jac, bounds=[(float(x_min), float(x_max))], 
        constraints={'type': 'ineq', 'fun': con, 'jac': con_jac},
        options={'ftol': 1e-6, 'disp': (not quiet)}
    )
    
    if res.success:
        x_candidate = float(res.x[0])
        check = compute_for_scale(json_data, s0 * x_candidate, params, target_MW)
        if check['pitch_angle_deg'] <= float(pitch_limit_deg) + 1e-8:
            x_opt = x_candidate
            if not quiet:
                print(f"SLSQP 优化成功: x={x_opt:.4f}")
        else:
            if not quiet:
                print("SLSQP 返回成功，但最终约束未满足，改用可行域扫描。")
            res.success = False
    if not res.success:
        note = "feasible_domain_scan"
        best_x = None
        best_steel = float('inf')
        for x in np.arange(float(x_min), float(x_max) + 1e-12, float(scan_step)):
            props = compute_for_scale(json_data, s0 * x, params, target_MW)
            if props['pitch_angle_deg'] <= float(pitch_limit_deg) and props['steel_per_MW_t'] < best_steel:
                best_x, best_steel = float(x), props['steel_per_MW_t']
        if best_x is None:
            raise RuntimeError(
                f"在 x={x_min}~{x_max} 范围内不存在满足静倾角≤{pitch_limit_deg}°的可行设计。"
            )
        x_opt = best_x
        if not quiet:
            print(f"可行域扫描得到: x={x_opt:.4f}")

    final_scale = s0 * x_opt
    mesh_geoms = []
    final_props = compute_for_scale(json_data, final_scale, params, target_MW, mesh_geoms)
    final_props = dict(final_props)
    final_props['_optimizer_note'] = note
    return final_scale, x_opt, final_props, mesh_geoms

def print_props(title, p):
    print(f"\n{title}:")
    print(f"  结构质量: {p['struct_mass_kg']/1000:.1f} t")
    print(f"  压载质量: {p['ballast_mass_kg']/1000:.1f} t")
    print(f"  总质量: {p['total_mass_kg']/1000:.1f} t")
    print(f"  结构重心 Z: {p['cog_z_struct_m']:.2f} m")
    print(f"  浮心 Z: {p['cob_z_m']:.2f} m")
    print(f"  总重心 Z: {p['cog_z_total_m']:.2f} m")
    print(f"  排水体积: {p['displaced_vol_m3']:.1f} m³")
    print(f"  水线面惯性矩 I_y: {p['I_y_m4']:.3e} m⁴")
    print(f"  静水刚度 K55: {p['K55_Nm_per_rad']:.3e} N·m/rad")
    print(f"  额定推力: {p['rated_thrust_N']/1000:.1f} kN")
    print(f"  静倾角: {p['pitch_angle_deg']:.2f}°")
    print(f"  单位用钢量: {p['steel_per_MW_t']:.1f} t/MW")

def print_geom(json_data, scale, params):
    """打印缩放后的关键几何尺寸（兼容 beso7 / beso9）"""
    scaled = scale_geometry_horizontal(json_data, scale)
    topology_key = 'beso9_method1_topology_reconstructed' if 'beso9_method1_topology_reconstructed' in json_data else 'beso7_method1_topology_reconstructed'
    beso_top = scaled.get(topology_key, {})
    
    # 1. 边立柱（BESO3 或顶层）
    edge_cols = scaled.get('beso3_reference_from_fcstd', {}).get('edge_columns_nondesign', [])
    if not edge_cols:
        edge_cols = scaled.get('edge_columns_nondesign', [])
        
    diam_list = []
    centers = []
    for col in edge_cols:
        rad = col.get('true_orthogonal_radius_mm', col.get('radius_mm', 0))
        if rad:
            diam_list.append(2 * mm_to_m(rad))
        if 'center_xy_mm' in col:
            centers.append((mm_to_m(col['center_xy_mm'][0]), mm_to_m(col['center_xy_mm'][1])))
    
    if diam_list:
        print(f"  边立柱平均直径: {sum(diam_list)/len(diam_list):.3f} m")
    else:
        print(f"  边立柱平均直径: N/A")
        
    if len(centers) == 3:
        d12 = math.hypot(centers[0][0] - centers[1][0], centers[0][1] - centers[1][1])
        d23 = math.hypot(centers[1][0] - centers[2][0], centers[1][1] - centers[2][1])
        d31 = math.hypot(centers[2][0] - centers[0][0], centers[2][1] - centers[0][1])
        print(f"  立柱间距: {(d12 + d23 + d31)/3:.3f} m")
    else:
        print(f"  立柱间距: N/A")
        
    # 2. BESO主立柱（倾斜立柱）
    legs = beso_top.get('legs', [])
    if legs:
        beso_dias = [mm_to_m(leg.get('diameter_mm', leg.get('radius_mm', 0) * 2)) for leg in legs]
        print(f"  BESO主立柱平均直径: {sum(beso_dias)/len(beso_dias):.3f} m")
    else:
        print(f"  BESO主立柱平均直径: N/A")
        
    # 3. 顶盘
    plate = beso_top.get('hub_top_plate', {})
    if plate:
        rad = mm_to_m(plate.get('radius_mm', plate.get('diameter_mm', 0) / 2))
        print(f"  顶盘半径: {rad:.3f} m")
    else:
        print(f"  顶盘半径: N/A")
        
    print(f"  吃水: {params['draft']:.3f} m")

def _m_to_mm(v):
    return float(v) * 1000.0


def _update_optimized_descriptions(data, final_props, params, target_power):
    """根据最终缩放后的真实几何与最终计算结果，刷新 JSON 中的描述和汇总数据。"""
    topology_key = (
        'beso9_method1_topology_reconstructed'
        if 'beso9_method1_topology_reconstructed' in data
        else 'beso7_method1_topology_reconstructed'
    )
    topo = data.get(topology_key, {})
    legs = topo.get('legs', [])
    plate = topo.get('hub_top_plate', {})

    # ---- 读取最终几何尺寸 ----
    leg_diams_m = []
    leg_lengths_m = []
    for leg in legs:
        d_mm = leg.get('diameter_mm', leg.get('radius_mm', 0.0) * 2.0)
        leg_diams_m.append(mm_to_m(d_mm))
        if 'length_mm' in leg:
            leg_lengths_m.append(mm_to_m(leg['length_mm']))

    plate_d_mm = plate.get('diameter_mm', plate.get('radius_mm', 0.0) * 2.0)
    plate_d_m = mm_to_m(plate_d_mm) if plate_d_mm else 0.0

    # 外侧非设计柱
    edge_cols = data.get('beso3_reference_from_fcstd', {}).get('edge_columns_nondesign', [])
    if not edge_cols:
        edge_cols = data.get('edge_columns_nondesign', [])
    edge_diams_m = []
    edge_centers = []
    for col in edge_cols:
        r_mm = col.get('true_orthogonal_radius_mm', col.get('radius_mm', 0.0))
        if r_mm:
            edge_diams_m.append(2.0 * mm_to_m(r_mm))
        c = col.get('center_xy_mm')
        if c and len(c) >= 2:
            edge_centers.append((mm_to_m(c[0]), mm_to_m(c[1])))

    edge_spacing_m = None
    if len(edge_centers) >= 3:
        ds = []
        for i in range(len(edge_centers)):
            for j in range(i + 1, len(edge_centers)):
                ds.append(math.hypot(edge_centers[i][0] - edge_centers[j][0],
                                     edge_centers[i][1] - edge_centers[j][1]))
        if ds:
            edge_spacing_m = sum(ds) / len(ds)

    # ---- 动态描述：不再沿用原始 JSON 中可能过期的“12m/9.6m”等文字 ----
    leg_desc = (
        f"{len(legs)}根内部优化倾斜立柱"
        + (f"，平均直径{sum(leg_diams_m)/len(leg_diams_m):.3f}m" if leg_diams_m else '')
    )
    plate_desc = (
        f"顶部连接圆盘（最终优化直径{plate_d_m:.3f}m）"
        if plate_d_m > 0 else "顶部连接圆盘"
    )
    topo['description'] = (
        f"最终优化后几何：{leg_desc}；{plate_desc}。"
        f"目标功率{target_power:.3f}MW，最终水平缩放因子{data['optimization_info']['scale_factor']:.6f}。"
    )
    if plate:
        plate['name'] = plate_desc
    for i, leg in enumerate(legs, start=1):
        leg['name'] = f"内部优化柱 {i}（最终优化几何）"

    # ---- 用程序最终计算结果覆盖旧的质量估算 ----
    struct_t = final_props['struct_mass_kg'] / 1000.0
    ballast_t = final_props['ballast_mass_kg'] / 1000.0
    total_t = final_props['total_mass_kg'] / 1000.0
    rna_t = params['rna_mass_kg'] * math.sqrt(target_power / params['rated_power_MW'])**0.88 / 1000.0
    tower_t = params['tower_mass_kg'] * math.sqrt(target_power / params['rated_power_MW'])**0.88 / 1000.0

    # 保留旧字段兼容性，但明确标注这些是程序计算值，不是从原 JSON 复制的估算。
    data['mass_estimation_tonnes'] = {
        'platform_total_steel_t': struct_t,
        'rna_mass_t': rna_t,
        'tower_mass_t': tower_t,
        'ballast_mass_t': ballast_t,
        'total_displacement_mass_t': final_props['displaced_vol_m3'] * params['water_density'] / 1000.0,
        'total_mass_t': total_t,
        'steel_per_MW_t': final_props['steel_per_MW_t'],
        'source': 'recalculated_by_optimization_code_from_final_geometry'
    }

    # ---- 增加完整的最终优化性能结果，便于后续 CAD / 报告直接引用 ----
    data['optimization_result'] = {
        'target_power_MW': target_power,
        'final_scale_factor': data['optimization_info']['scale_factor'],
        'final_extra_scale_x': data['optimization_info'].get('extra_scale_x'),
        'feasible_pitch_angle_deg': final_props['pitch_angle_deg'],
        'structure_mass_t': struct_t,
        'ballast_mass_t': ballast_t,
        'rna_mass_t': rna_t,
        'tower_mass_t': tower_t,
        'total_mass_t': total_t,
        'displaced_volume_m3': final_props['displaced_vol_m3'],
        'displaced_mass_t': final_props['displaced_vol_m3'] * params['water_density'] / 1000.0,
        'structure_cog_z_m': final_props['cog_z_struct_m'],
        'total_cog_z_m': final_props['cog_z_total_m'],
        'center_of_buoyancy_z_m': final_props['cob_z_m'],
        'waterplane_Iy_m4': final_props['I_y_m4'],
        'K55_Nm_per_rad': final_props['K55_Nm_per_rad'],
        'rated_thrust_N': final_props['rated_thrust_N'],
        'steel_per_MW_t': final_props['steel_per_MW_t'],
        'fixed_draft_m': params['draft'],
        'ballast_cog_z_m': params['ballast_cog_z_m'],
    }

    data['final_geometry_summary'] = {
        'units': 'm',
        'inner_optimized_legs_count': len(legs),
        'inner_optimized_leg_average_diameter_m': sum(leg_diams_m) / len(leg_diams_m) if leg_diams_m else None,
        'inner_optimized_leg_average_length_m': sum(leg_lengths_m) / len(leg_lengths_m) if leg_lengths_m else None,
        'top_hub_plate_diameter_m': plate_d_m if plate_d_m else None,
        'outer_edge_columns_count': len(edge_cols),
        'outer_edge_column_average_diameter_m': sum(edge_diams_m) / len(edge_diams_m) if edge_diams_m else None,
        'outer_edge_column_average_spacing_m': edge_spacing_m,
        'draft_m': params['draft'],
        'note': 'All values in this section are recalculated from the final horizontally scaled geometry.'
    }


def export_optimized_geometry(orig_json, final_scale, params, output_json, target_power,
                              final_props=None, x_opt=None):
    """导出最终优化几何，并同步刷新描述、质量和静稳性结果。"""
    scaled_json = scale_geometry_horizontal(orig_json, final_scale)
    scaled_json['optimization_info'] = {
        'target_power_MW': target_power,
        'scale_factor': final_scale,
        'extra_scale_x': x_opt,
        'base_scale_s0': math.sqrt(target_power / params['rated_power_MW']),
        'wall_thickness_m': params['wall_thickness'],
        'steel_density_kgpm3': params['steel_density'],
        'water_density_kgpm3': params['water_density'],
        'draft_m': params['draft'],
        'ballast_cog_z_m': params['ballast_cog_z_m'],
        'top_plate_hollow': params['top_plate_hollow'],
        'top_plate_wall_m': params['top_plate_wall_thickness'],
    }

    if final_props is None:
        raise ValueError("export_optimized_geometry 必须传入最终优化计算结果 final_props，避免导出旧的/过期性能数据。")

    _update_optimized_descriptions(scaled_json, final_props, params, target_power)

    # 顶层标题也由最终几何自动生成，彻底避免沿用原始文件中的尺寸描述。
    g = scaled_json.get('final_geometry_summary', {})
    d_inner = g.get('inner_optimized_leg_average_diameter_m')
    d_plate = g.get('top_hub_plate_diameter_m')
    scaled_json['title'] = (
        f"AI-Engineer BESO9 最终优化结构参数汇总 "
        f"— {target_power:.3f}MW；内部柱平均直径"
        f"{d_inner:.3f}m；顶盘直径{d_plate:.3f}m"
        if d_inner is not None and d_plate is not None
        else f"AI-Engineer BESO9 最终优化结构参数汇总 — {target_power:.3f}MW"
    )
    scaled_json['description'] = (
        "本文件由优化程序在最终最优水平缩放因子下自动生成。"
        "几何尺寸、结构质量、压载质量、排水量、水线面惯性矩、K55、静倾角及单位用钢量"
        "均来自最终优化计算，不沿用原始 JSON 中的历史估算或描述文字。"
    )

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(scaled_json, f, indent=2, ensure_ascii=False)
    print(f"优化后的几何与性能参数已同步保存至: {output_json}")

# ===================== 3D 可视化函数（从 V5 移植） =====================
def plot_3d_solid(mesh_geoms):
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    print("\n🎨 正在渲染优化后的 3D 实体模型...")
    for geom_type, p0, p1, R, color in mesh_geoms:
        if geom_type == 'cylinder':
            v = p1 - p0
            mag = np.linalg.norm(v)
            if mag < 1e-6:
                continue
            v = v / mag
            
            not_v = np.array([1, 0, 0])
            if (np.abs(v) == not_v).all():
                not_v = np.array([0, 1, 0])
            n1 = np.cross(v, not_v)
            n1 /= np.linalg.norm(n1)
            n2 = np.cross(v, n1)
            
            t = np.linspace(0, 2 * np.pi, 25)
            z = np.linspace(0, mag, 2)
            T, Z = np.meshgrid(t, z)
            
            X = p0[0] + R * np.cos(T) * n1[0] + R * np.sin(T) * n2[0] + Z * v[0]
            Y = p0[1] + R * np.cos(T) * n1[1] + R * np.sin(T) * n2[1] + Z * v[1]
            Z_coord = p0[2] + R * np.cos(T) * n1[2] + R * np.sin(T) * n2[2] + Z * v[2]
            
            ax.plot_surface(X, Y, Z_coord, color=color, alpha=0.7)

    # 绘制水线面（z=0 平面）
    xx, yy = np.meshgrid(np.linspace(-80, 80, 2), np.linspace(-80, 80, 2))
    zz = np.zeros_like(xx)
    ax.plot_surface(xx, yy, zz, color='cyan', alpha=0.15)

    ax.set_box_aspect([1, 1, 0.5])
    max_range = 80
    ax.set_xlim([-max_range, max_range])
    ax.set_ylim([-max_range, max_range])
    ax.set_zlim([-25, 20])
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_zlabel('Z (m)')
    ax.set_title("Optimized Platform 3D Solid Model\n(Blue: Inner Legs, Red: Tilted Outer Legs, Green: Footings, Cyan: Top Hub)")
    plt.show()

if __name__ == "__main__":
    print("=== 混合模型平台物理修正版（真3D长+封闭桩靴+分离塔重） ===")
    path = input("请输入 JSON 文件路径: ").strip()
    with open(path, 'r', encoding='utf-8') as f:
        orig_json = json.load(f)
        
    params = interactive_input()
    target = float(input("\n请输入目标功率 (MW): "))
    s0 = math.sqrt(target / params['rated_power_MW'])
    
    print("\n初始几何尺寸:")
    print_geom(orig_json, s0, params)
    
    init = compute_for_scale(orig_json, s0, params, target, [])
    print_props("初始缩放后性能", init)
    
    final_scale, x_opt, opt, mesh_geoms_final = optimize_scale(orig_json, params, target)
    print(f"\n优化结果: 额外缩放因子 x = {x_opt:.4f}")
    print_props("优化后性能", opt)
    
    print("\n优化后几何尺寸:")
    print_geom(orig_json, final_scale, params)
    
    # 导出优化后的几何文件
    export_optimized_geometry(orig_json, final_scale, params, "optimized_geometry.json", target, final_props=opt, x_opt=x_opt)
    
    # 弹出 3D 实体模型窗口（如需关闭，注释掉下一行）
    plot_3d_solid(mesh_geoms_final)