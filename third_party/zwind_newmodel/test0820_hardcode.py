# endregion
# -*- coding: utf-8 -*-
# 基于 Compare20MW.py 生成的新脚本：
# - region3：浮体几何与截面数据来自 optimized_geometry.json（动态生成）
# - 节点/杆件：6 根立柱（3 倾斜 + 3 垂直）通过 JSON 解析
# - 质量：m = Length*Area*Density，两端各 1/2；节点 1 叠加 SubDyn 集中质量与转动惯量
# - 附加质量：通过坐标映射继承原硬编码模型的 added_mass_dict
# - 系泊挂载点：自动使用 JSON 中的外部边立柱顶端节点
# - 其余区域（系泊、上部结构、载荷与求解）保持原有逻辑与接口一致
#
# 单位: SI (kg, m, N, Pa, s)
# =============================================================================
# region 0. 环境与路径
# =============================================================================

# opsvis.set_plot_props(point_size=6, line_width=3, cmap="jet", notebook=False)  # set notebook=False for practical use
# fig = opsvis.plot_model(show_nodal_loads=True, show_ele_loads=True, show_node_numbering=True)
# fig.show()  # fig.show() for practical use

import numpy as np
import math as m
import time
import matplotlib        # 新增
matplotlib.use('Agg')    # 强制使用非交互式后端
import matplotlib.pyplot as plt
import math
import sys
import os
from tqdm import tqdm
import json  # 新增
import math

current_dir = os.path.dirname(os.path.abspath(__file__))
servo_data_dir = os.path.join(current_dir, "servoData")
os.chdir(current_dir)

python_dll_dir = os.path.join(sys.base_prefix, "DLLs")
os.environ["PATH"] = (
    current_dir + ";"
    + servo_data_dir + ";"
    + python_dll_dir + ";"
    + os.environ.get("PATH", "")
)

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(current_dir)
    if os.path.isdir(servo_data_dir):
        os.add_dll_directory(servo_data_dir)
    os.add_dll_directory(python_dll_dir)

import openseespy.opensees as ops
import opstool as opst
import opstool.vis.pyvista as opsvis

OUTPUT_LABEL = "test0820_hardcode"
MAX_STAT_START_TIME_S = 100.0  # 最大值统计剔除启动阶段；原始时程仍完整保留。
OUT_DIR = os.path.join(current_dir, "OPSout", OUTPUT_LABEL)
os.makedirs(OUT_DIR, exist_ok=True)


def out_path(name: str) -> str:
    return os.path.join(OUT_DIR, name)

os.system("cls")
# endregion


# 辅助函数（保持兼容）
def find_closest_node(target_coords, node_dict):
    min_dist = float('inf')
    closest_id = None
    for nid, coords in node_dict.items():
        dist = np.linalg.norm(np.array(coords) - np.array(target_coords))
        if dist < min_dist:
            min_dist = dist
            closest_id = nid
    return closest_id
# ---------- 可视化函数（供 region 3 调用） ----------
def plot_platform(foundation_data, save_path="OPSout/platform_geometry.png"):
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    nodes = foundation_data["nodes"]
    xs = [coord[0] for coord in nodes.values()]
    ys = [coord[1] for coord in nodes.values()]
    zs = [coord[2] for coord in nodes.values()]
    ax.scatter(xs, ys, zs, c='red', s=50, label='Nodes')
    for ele in foundation_data["elements"]:
        n1, n2 = ele["n1"], ele["n2"]
        p1 = np.array(nodes[n1])
        p2 = np.array(nodes[n2])
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], 'b-', linewidth=2)
    
    # 标记系泊挂载点（导缆孔节点）
    moor_nodes = foundation_data["mooring_nodes"]  # [9901, 9902, 9903]
    for nid in moor_nodes:
        p = nodes[nid]
        ax.scatter([p[0]], [p[1]], [p[2]], c='green', s=100, marker='s', label='Mooring' if nid==moor_nodes[0] else "")
    
    # 绘制系泊方向线：取每条线最后5个节点（靠近挂载点）
    for j in range(1, 13):
        # 最后节点编号为 1000*j + 39
        end_node = 1000 * j + 39
        # 取最后5个节点（若不足5个则取全部）
        num_nodes_to_plot = min(5, 39)  # 实际可以动态判断，但系泊线有39个节点
        node_ids = [end_node - k for k in range(num_nodes_to_plot-1, -1, -1)]  # 从远到近排序
        coords = []
        for nid in node_ids:
            try:
                coord = ops.nodeCoord(nid)
                if coord is not None:
                    coords.append(coord)
            except:
                pass
        if len(coords) >= 2:
            xs_line = [c[0] for c in coords]
            ys_line = [c[1] for c in coords]
            zs_line = [c[2] for c in coords]
            ax.plot(xs_line, ys_line, zs_line, 'g--', linewidth=1.5, alpha=0.7,
                    label='Mooring line' if j==1 else "")
        # 也可额外标记最后一个节点（导缆孔端）和远端端点
        if coords:
            # 远端端点（离平台最远）用点标记
            ax.scatter([coords[0][0]], [coords[0][1]], [coords[0][2]], c='cyan', s=30, marker='o')
            # 最近端点（导缆孔端）已在前面标记过，不重复
    ax.set_xlabel('X (m)'); ax.set_ylabel('Y (m)'); ax.set_zlabel('Z (m)')
    ax.set_title('Platform Geometry (fairlead nodes at average positions)')
    ax.legend()
    # 等比例显示
    all_x = xs + [coord[0] for line in range(1,13) for coord in coords]  # 可能需要处理coords未定义
    # 更稳健：收集所有显示的点
    # ... (省略，原代码已有自动等比例)
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"[INFO] 几何可视化保存至 {save_path}")


# =============================================================================
# region 1. 参数设置 时域、控制
# =============================================================================
DT = 0.01  # s
TMAX = 120.0  # s
NSTEPS = int(TMAX / DT)

PI = math.pi
G_ACC = 9.8  # 与 _Zwind_v2.2.9_12.py 一致

# driver接口开关（ServoLoad 节点编号与 ServoLoadPattern.cpp 一致）
Aero  = True
Servo = True
Hydro = True
Moor  = True
LOCK_PLATFORM_6DOF = False
ENABLE_START_ASSIST = True
ENABLE_DECAY_TEST = False

DECAY_MONITOR_NODE = 1
DECAY_MONITOR_DOF = 5
DECAY_AMP = -4.3e8
DECAY_FREQ_HZ = 0.05
DECAY_EXCITE_DURATION = 20.0
DECAY_UNLOAD_RATIO = 0.05
DECAY_PATTERN_TAG = 3001
DECAY_TS_TAG = 3001
DECAY_OMEGA = 2.0 * PI * DECAY_FREQ_HZ
DOF_LABELS = {1: "Surge", 2: "Sway", 3: "Heave", 4: "Roll", 5: "Pitch", 6: "Yaw"}

if ENABLE_DECAY_TEST:
    Servo = False
    Aero = False

# 传动系统 / 控制器参数（与 ServoDyn / ElastoDyn 一致）
GBRatio = 74.627 #齿轮比
GenIner = 13000.0
GenIner_LSS = GenIner * (GBRatio ** 2)
DTTorSpr = 1.21e10  #传动系统刚度
DTTorDmp = 1.255e7  #传动系统阻尼
HubMass = 130000.0
HubIner = 934261.0
Rated_Power = 20.0e6
Rated_Speed_LSS = 7.56 * (2.0 * PI / 60.0)
Rated_Speed_HSS = Rated_Speed_LSS * GBRatio
Rated_Torque_LSS = Rated_Power / Rated_Speed_LSS / 0.85172 

# 编号分区（避免与系泊/浮体冲突）：shx
#   1–15        浮体 
#   80–144      塔架
#   901–903     桨距代理（ServoLoad）
#   1001–12039  系泊链节点（含 9010/9020/9030 等，勿占用）
#   29010+      桨距代理弹簧锚固端 / 材料 / 单元（本脚本专用）
#   10000*线号  系泊单元；section 901/902 为系泊截面 tag（非节点）

PROXY_NODES = [901, 902, 903] # ServoLoadPattern.cpp 硬编码桨距代理节点，不可改
GEN_NODE_TAG = 194  # 发电机序号 - 与servo耦合

# 主轴辅助力矩软启动：主轴 DOF4 始终自由，不再使用 sp(193,4) 强制转角
# 思路：对 LSS 节点 193 的 DOF4 施加临时辅助力矩，达到目标转速并稳定后平滑卸载
START_TARGET_RATIO = 0.9        # 达到 START_TARGET_RATIO * ratedSpeed 后开始计稳定时间
START_STABLE_TIME = 5.0          # 连续稳定START_STABLE_TIME后进入卸载阶段，s
START_UNLOAD_TIME = 10.0         # 辅助力矩卸载时间，s
START_RAMP_IN_TIME = 10.0        # 起动力矩从 0 平滑升至闭环计算值的时间，s
START_TORQUE_LIMIT_RATIO = 1.80  # 辅助力矩限幅：1.5*Rated_Torque_LSS
START_KP_RATIO = 1.80            # 速度误差为 rated speed 时，比例力矩约为 1.35*Rated_Torque_LSS
START_UPDATE_DT = 0.05           # 辅助力矩更新间隔，s；无需每 0.01 s 重建 load pattern

# 分区 Rayleigh 阻尼设置
# 浮体和塔筒保留结构阻尼；RNA/主轴/传动链/刚性梁仅保留极小质量比例阻尼，
# 传动链本身仍由 DTTorDmp 提供物理扭转阻尼。

ENABLE_REGIONAL_DAMPING = True

# 浮体 SubDyn 建模区：低频结构阻尼
DAMP_FLOAT_ZETA = 0.12
DAMP_FLOAT_W1 = 0.02
DAMP_FLOAT_W2 = 0.50

# 塔筒区：比浮体更低，避免过度耗散塔顶/RNA运动
DAMP_TOWER_ZETA = 0.11
DAMP_TOWER_W1 = 0.20
DAMP_TOWER_W2 = 3.00

# RNA / 主轴 / 传动链 / 刚性梁区：仅给极小阻尼，避免高刚度单元形成数值刹车
DAMP_RNA_ALPHA_M = 1.0e-4
DAMP_RNA_BETA_K = 1.0e-6

# shx 系泊线已有单元级阻尼；此处不改动原设置，检查是否合理

#shx 干什么的
def setup_pitch_proxy(proxy_tag, anchor_tag, mat_tag, elem_tag, x, y, z):
    """桨距通信通道：anchor(固定) --[K=1 弹簧]--> proxy(DOF4 开放)。

    proxy_tag: 代理节点，须为 901/902/903（与 ServoLoadPattern.cpp 一致）
    anchor_tag: 弹簧固定端节点（须避开系泊节点 1001–12039）
    mat_tag:  uniaxialMaterial Elastic 的 tag
    elem_tag: zeroLength 单元 tag（dir=4 扭转）
    """
    ops.node(proxy_tag, x, y, z)
    ops.fix(proxy_tag, 1, 1, 1, 0, 1, 1)
    ops.mass(proxy_tag, 0.0, 0.0, 0.0, 1.0e-13, 0.0, 0.0)
    ops.uniaxialMaterial("Elastic", mat_tag, 1.0)
    ops.node(anchor_tag, x, y, z)
    ops.fix(anchor_tag, 1, 1, 1, 1, 1, 1)
    ops.element("zeroLength", elem_tag, anchor_tag, proxy_tag, "-mat", mat_tag, "-dir", 4)


def clamp_val(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


# endregion


# =============================================================================
# region 2. 初始化 OpenSees 模型与精简 recorder
# =============================================================================
ops.wipe()
ops.model("BasicBuilder", "-ndm", 3, "-ndf", 6)

# 关键输出（<10）
#叶根 zgy
ops.recorder("Element", "-file",  out_path("b1_force.out"), "-time", "-ele", 191601, "force")
# 记录 1 号叶片尖端节点的位移坐标
ops.recorder("Node", "-file", "OPSout/191_disp.out", "-time", "-node", 191, "-dof", 1, 2, 3, 4, 5, 6,"disp")
# ops.recorder("Node", "-file", "OPSout/hubreaction.out", "-time", "-node", 191, "-dof", 1, 2, 3, 4, 5, 6,"reaction")
ops.recorder("Node", "-file", "OPSout/601_disp.out", "-time", "-node", 601, "-dof", 1, 2, 3, 4, 5, 6,"disp")
ops.recorder("Node", "-file", "OPSout/658_disp.out", "-time", "-node", 658, "-dof", 1, 2, 3, 4, 5, 6,"disp")
ops.recorder("Node", "-file", "OPSout/601vel.out", "-time", "-node", 601, "-dof", 1, 2, 3, 4, 5, 6,"vel")
ops.recorder("Node", "-file", "OPSout/801disp.out", "-time", "-node", 801, "-dof", 1, 2, 3, 4, 5, 6,"disp")
ops.recorder("Node", "-file", "OPSout/gen194_vel.out", "-time", "-node", 194, "-dof", 4, "vel")
ops.recorder("Node", "-file", "OPSout/191_vel.out", "-time", "-node", 191, "-dof", 4, "vel")
ops.recorder("Node", "-file", "OPSout/901_disp.out", "-time", "-node", 901, "-dof", 4, "disp")
ops.recorder("Node", "-file", out_path("platform_disp.out"), "-time", "-node", 1, "-dof", 1, 2, 3, 4, 5, 6, "disp")
ops.recorder("Node", "-file", out_path("platform_accel.out"), "-time", "-node", 1, "-dof", 1, 2, 3, 4, 5, 6, "accel")
# ---------------- 追加的数据记录器 ----------------

# 1. 记录塔顶节点 (144) 的加速度，用于评估机舱振动水平
ops.recorder("Node", "-file", out_path("tower_top_accel.out"), "-time", "-node", 144, "-dof", 1, 2, 3, 4, 5, 6, "accel")

# 2. 记录塔顶节点 (144) 的位移
ops.recorder("Node", "-file", out_path("tower_top_disp.out"), "-time", "-node", 144, "-dof", 1, 2, 3, 4, 5, 6, "disp")

# 3. 记录塔底单元 (2001) 的六自由度内力，用于提取极限弯矩
#    保留历史文件名，并额外使用与 v2.2.9 相同的标准原始文件名。
ops.recorder("Element", "-file", out_path("tower_base_force.out"), "-time", "-ele", 2001, "globalForce")
ops.recorder("Element", "-file", out_path("tower_base_global_force.out"), "-time", "-ele", 2001, "globalForce")

# 4. 记录系泊导缆孔(顶端)张力 (第38号单元)
top_moor_eles = [100000*j + 38 for j in range(1, 13)]
ops.recorder("Element", "-file", out_path("mooring_tension.out"), "-time", "-ele", *top_moor_eles, "globalForce")

# 5. 记录系泊锚点(底端)张力 (第1号单元)
bot_moor_eles = [100000*j + 1 for j in range(1, 13)]
ops.recorder("Element", "-file", out_path("mooring_anchor_tension.out"), "-time", "-ele", *bot_moor_eles, "globalForce")

# 与 v2.2.9 使用同一套逐根系泊端力文件，后处理据此输出导缆孔端张力。
for _line in range(1, 13):
    ops.recorder(
        "Element", "-file", out_path(f"mooring_line{_line:02d}_anchor_global_force.out"),
        "-time", "-ele", 100000 * _line + 1, "globalForce"
    )
    ops.recorder(
        "Element", "-file", out_path(f"mooring_line{_line:02d}_fairlead_global_force.out"),
        "-time", "-ele", 100000 * _line + 38, "globalForce"
    )


def _load_response_output(path, expected_columns, label):
    """读取 recorder 文件，并验证列数、数值和时间轴。"""
    if not os.path.isfile(path):
        raise RuntimeError(f"{label} 文件不存在: {path}")
    data = np.atleast_2d(np.loadtxt(path))
    if data.shape[1] != expected_columns:
        raise RuntimeError(f"{label} 列数错误: {data.shape[1]}，期望 {expected_columns}: {path}")
    if not np.isfinite(data).all() or data.shape[0] < 1:
        raise RuntimeError(f"{label} 含 NaN/Inf 或没有数据: {path}")
    if np.any(np.diff(data[:, 0]) <= 0.0):
        raise RuntimeError(f"{label} 时间列不是严格递增: {path}")
    return data


def build_standard_response_outputs(output_dir, num_lines=12):
    """输出两脚本通用的塔顶加速度、塔底荷载、导缆孔张力时程。"""
    top_accel = _load_response_output(
        os.path.join(output_dir, "tower_top_accel.out"), 7, "塔顶加速度"
    )
    np.savetxt(
        os.path.join(output_dir, "tower_top_acceleration.out"), top_accel,
        header="Time_s AccX_mps2 AccY_mps2 AccZ_mps2 AlphaX_radps2 AlphaY_radps2 AlphaZ_radps2",
        comments="# ",
    )

    base_force = _load_response_output(
        os.path.join(output_dir, "tower_base_global_force.out"), 13, "塔底 globalForce"
    )
    # 取 2001 单元 I 端（节点 80）的截面力；坐标变换与 v2.2.9 保持一致。
    tower_base_loads = np.column_stack([
        base_force[:, 0], base_force[:, 1] * 1.0e-3, -base_force[:, 2] * 1.0e-3,
        base_force[:, 3] * 1.0e-3, base_force[:, 4] * 1.0e-3,
        -base_force[:, 5] * 1.0e-3, base_force[:, 6] * 1.0e-3,
    ])
    for _name in ("tower_base_openfast_force.out", "tower_base_loads.out"):
        np.savetxt(
            os.path.join(output_dir, _name), tower_base_loads,
            header="Time_s TwrBsFxt_kN TwrBsFyt_kN TwrBsFzt_kN TwrBsMxt_kNm TwrBsMyt_kNm TwrBsMzt_kNm",
            comments="# ",
        )

    tension_columns = []
    time_values = None
    for line_no in range(1, num_lines + 1):
        fairlead = _load_response_output(
            os.path.join(output_dir, f"mooring_line{line_no:02d}_fairlead_global_force.out"),
            13, f"系泊线 {line_no:02d} 导缆孔端力"
        )
        if time_values is None:
            time_values = fairlead[:, 0]
        elif not np.allclose(time_values, fairlead[:, 0], rtol=0.0, atol=1.0e-9):
            raise RuntimeError(f"系泊线 {line_no:02d} 导缆孔端力时间轴不一致")
        # 单元 j 端（导缆孔端）的全局力向量模长，即该端缆线张力。
        tension_columns.append(np.linalg.norm(fairlead[:, 7:10], axis=1))
    mooring_tension = np.column_stack([time_values] + tension_columns)
    tension_header = "Time_s " + " ".join(
        f"Line{line_no:02d}_FairleadTension_N" for line_no in range(1, num_lines + 1)
    )
    np.savetxt(
        os.path.join(output_dir, "mooring_fairlead_tension.out"), mooring_tension,
        header=tension_header, comments="# ",
    )

    extrema = []
    for source_name, data, labels in (
        ("tower_top_acceleration", top_accel, ["AccX_mps2", "AccY_mps2", "AccZ_mps2", "AlphaX_radps2", "AlphaY_radps2", "AlphaZ_radps2"]),
        ("tower_base_loads", tower_base_loads, ["TwrBsFxt_kN", "TwrBsFyt_kN", "TwrBsFzt_kN", "TwrBsMxt_kNm", "TwrBsMyt_kNm", "TwrBsMzt_kNm"]),
        ("mooring_fairlead_tension", mooring_tension, [f"Line{line_no:02d}_FairleadTension_N" for line_no in range(1, num_lines + 1)]),
    ):
        stable_data = data[data[:, 0] >= MAX_STAT_START_TIME_S]
        if stable_data.shape[0] == 0:
            raise RuntimeError(
                f"{source_name} 没有 t >= {MAX_STAT_START_TIME_S:.1f}s 的数据，无法计算稳定阶段最大值"
            )
        for col, label in enumerate(labels, start=1):
            index = int(np.argmax(np.abs(stable_data[:, col])))
            extrema.append([source_name, label, stable_data[index, 0], stable_data[index, col], abs(stable_data[index, col])])
    with open(os.path.join(output_dir, "response_max_abs.out"), "w", encoding="utf-8") as extrema_file:
        extrema_file.write(f"# statistics_window: time_s >= {MAX_STAT_START_TIME_S:.1f}\n")
        extrema_file.write("# source channel time_s value_at_max_abs max_abs\n")
        for source_name, label, time_s, value, max_abs in extrema:
            extrema_file.write(f"{source_name} {label} {time_s:.6f} {value:.9e} {max_abs:.9e}\n")
    print(">>> 标准响应时程及最大绝对值已输出: tower_top_acceleration.out, "
          "tower_base_loads.out, mooring_fairlead_tension.out, response_max_abs.out")


# endregion
# =============================================================================
# region 3. Hydro 浮体结构（硬编码几何，侧立柱方位 60/180/300°，保留 30° 外倾）
# =============================================================================
# ---- 显式几何常量（单位 m，取自 optimized_geometry30.json 实测） ----
R_BOT = 44.46        # 外边立柱底部半径（center_xy 半径）
R_TOP = 59.47        # 外边立柱顶部(导缆孔)半径（top_center_xy 半径）→ 外倾30°
Z_BOT = -14.0        # 立柱底 z (m)
Z_TOP = 12.0         # 立柱顶/导缆孔 z (m) = Hub 顶
T_wall = 0.06        # 壁厚 (m)
ANGLES_DEG = [60.0, 180.0, 300.0]   # 三根侧立柱方位角（自 +x 轴逆时针）
D_OUTER = [18.397, 18.678, 18.678]  # 外边立柱直径 (m)
D_INNER = [9.4857, 9.6643, 9.6258]  # 内立柱直径 (m)，取自 BESO7 legs

FE = 2.06e11
FG = FE / (2 * (1 + 0.3))

ops.geomTransf("PDelta", 1, 0, 0, 1)
ops.geomTransf("PDelta", 2, 0, 1, 0)
ops.geomTransf("Linear", 3, 0, 0, 1)
ops.geomTransf("Linear", 99, 1.0, 1.0, 1.0)  # 防奇异变换

# 1. 建立节点（Hub=1；外边立柱顶=导缆孔 41/51/61，底 42/52/62）
nodes = {1: (0.0, 0.0, Z_TOP)}
for i, theta_deg in enumerate(ANGLES_DEG):
    leg_open = i + 4                       # 4,5,6
    theta = math.radians(theta_deg)
    cx, sy = math.cos(theta), math.sin(theta)
    top_nid = 10 * leg_open + 1            # 41,51,61
    bot_nid = 10 * leg_open + 2            # 42,52,62
    nodes[top_nid] = (R_TOP * cx, R_TOP * sy, Z_TOP)
    nodes[bot_nid] = (R_BOT * cx, R_BOT * sy, Z_BOT)

# 直接写节点（参考 _Zwind_v2.2.8_elastic.py region3 风格）
for nid, (x, y, z) in nodes.items():
    ops.node(nid, x, y, z)

# 2. 水动力参考点与塔筒/浮体连接点重合。
# HydroDyn 的 PtfmRefzt=12 m；不可再在 z=0 创建偏置 PRP，否则会引入 12 m 力矩臂。
PRP_NODE = 1

# 3. 建立单元（外边立柱 + 内立柱，硬壳截面属性）
elements = []
opt_ele_tags = []
ele_id = 101
# 外边立柱：顶(导缆孔) → 底
for i, theta_deg in enumerate(ANGLES_DEG):
    leg_open = i + 4
    top_nid = 10 * leg_open + 1
    bot_nid = 10 * leg_open + 2
    D_leg = D_OUTER[i]
    FA_leg = np.pi * T_wall * (D_leg - T_wall)
    FIy_leg = np.pi * (D_leg**4 - (D_leg - 2*T_wall)**4) / 64.0
    FIz_leg = FIy_leg
    FJ_leg = 2 * FIy_leg
    ops.element("elasticBeamColumn", ele_id, top_nid, bot_nid, FA_leg, FE, FG, FJ_leg, FIy_leg, FIz_leg, 2)
    elements.append({"id": ele_id, "n1": top_nid, "n2": bot_nid, "type": "optimized_leg", "D": D_leg})
    opt_ele_tags.append(ele_id)
    ele_id += 1

# =========================================================================
# 【全新重构】：完全符合物理实际的全弹性框架模型 (无 RigidLink，无 Pin，无假质量)
# =========================================================================
R_HUB = 12.0  # 承台半径 12m

# 建立承台等效辐射梁的截面属性 (模拟内部重型箱梁构架)
H_PLATE = 4.433 # 精确厚度/高度
T_WALL = 0.06   # 壁厚

# 将圆盘划分为 3 份等效辐射梁，计算每根箱形梁的截面属性
B_avg = (math.pi * R_HUB) / 3.0  # 平均宽度约 12.48m
B_in = B_avg - 2 * T_WALL
H_in = H_PLATE - 2 * T_WALL

A_hub = B_avg * H_PLATE - B_in * H_in                            # 等效截面积
Iy_hub = (B_avg * H_PLATE**3 - B_in * H_in**3) / 12.0            # 等效抗弯惯性矩
Iz_hub = (H_PLATE * B_avg**3 - H_in * B_in**3) / 12.0            # 等效面内惯性矩
J_hub = Iy_hub + Iz_hub                                          # 等效扭转极惯性矩

# 顶盘辐射梁专用坐标变换 (Z轴朝上)
ops.geomTransf("Linear", 888, 0, 0, 1)

for i, theta_deg in enumerate(ANGLES_DEG):
    hub_edge_nid = 811 + i  
    theta = math.radians(theta_deg)
    hx = R_HUB * math.cos(theta)
    hy = R_HUB * math.sin(theta)
    hz = Z_TOP
    ops.node(hub_edge_nid, hx, hy, hz)
    nodes[hub_edge_nid] = (hx, hy, hz)
    
    # 1. 建立真实的顶盘等效弹性梁 (连接中心节点1与边缘节点)
    # 这样既有真实的 12 米抗弯力臂，又允许符合物理规律的微小弹性协调变形！
    ops.element("elasticBeamColumn", 9000+i, 1, hub_edge_nid, A_hub, FE, FG, J_hub, Iy_hub, Iz_hub, 888)
    
    # 2. 建立内立柱 (全刚接，无任何释放，完美还原真实厚板全熔透焊接)
    bot_nid = 10 * (i + 4) + 2
    D_leg = D_INNER[i]
    FA_leg = np.pi * T_wall * (D_leg - T_wall)
    FIy_leg = np.pi * (D_leg**4 - (D_leg - 2*T_wall)**4) / 64.0
    FIz_leg = FIy_leg
    FJ_leg = 2 * FIy_leg
    
    # 内立柱直接连接在承台边缘节点上
    ops.element("elasticBeamColumn", ele_id, hub_edge_nid, bot_nid, FA_leg, FE, FG, FJ_leg, FIy_leg, FIz_leg, 2)
    elements.append({"id": ele_id, "n1": hub_edge_nid, "n2": bot_nid, "type": "optimized_leg", "D": D_leg})
    opt_ele_tags.append(ele_id)
    ele_id += 1

# 供下游（region4 系泊 / plot）使用的几何数据
foundation_data = {
    "nodes": nodes,
    "elements": elements,
    "mooring_nodes": [41, 51, 61],
    "interface_node": 1,
    "opt_ele_tags": opt_ele_tags,
    "wall_thickness": T_wall,
}

# 4. 质量分配（沿用原逻辑）
def hydro_mass_local(n1, n2, A, rho, J, L, node_mass_dict, node_I_dict):
    m_elem = L * A * rho
    node_mass_dict[n1] += 0.5 * m_elem
    node_mass_dict[n2] += 0.5 * m_elem
    m_half = 0.5 * m_elem
    I_t = m_half * (J / A) if A > 0.0 else 0.0
    I_b = m_elem * L * L / 24.0
    x1, x2 = np.array(ops.nodeCoord(n1), dtype=float), np.array(ops.nodeCoord(n2), dtype=float)
    vec = x2 - x1
    Ln = float(np.linalg.norm(vec))
    if Ln > 1e-6:
        e1 = vec / Ln
        e2 = np.cross(e1, np.array([0.0, 0.0, 1.0])) if abs(e1[2]) < 0.9 else np.cross(e1, np.array([0.0, 1.0, 0.0]))
        e2 = e2 / float(np.linalg.norm(e2))
        e3 = np.cross(e1, e2)
        R = np.column_stack((e1, e2, e3))
        I_loc = np.diag([I_t, I_b, I_b])
        I_glob = R @ I_loc @ R.T
        node_I_dict[n1] += I_glob
        node_I_dict[n2] += I_glob

HY_RHO_STEEL = 7850.0
hydro_node_mass = {nid: 0.0 for nid in nodes}
hydro_node_I = {nid: np.zeros((3, 3)) for nid in nodes}

for ele in elements:
    if ele["type"] == "optimized_leg":
        n1, n2 = ele["n1"], ele["n2"]
        L = np.linalg.norm(np.array(nodes[ele["n2"]]) - np.array(nodes[ele["n1"]]))
        D_leg = ele["D"]
        FA_leg = np.pi * T_wall * (D_leg - T_wall)
        FIy_leg = np.pi * (D_leg**4 - (D_leg - 2*T_wall)**4) / 64.0
        FJ_leg = 2 * FIy_leg
        hydro_mass_local(n1, n2, FA_leg, HY_RHO_STEEL, FJ_leg, L, hydro_node_mass, hydro_node_I)

# 【极其核心：自适应压载水配平，消除翻船风险】
DISP_VOL = 23718.8
RHO_WATER = 1025.0
TARGET_TOTAL_MASS = DISP_VOL * RHO_WATER

# 人工附加质量：读取当前 HydroDyn PotFile 的无限频率（omega=-1）对角项。
# WAMIT .1 的系数无量纲；按 HydroDyn RdtnDim 规则，平动为 rho*L^3、转动为 rho*L^5。
WAMIT_ULEN = 1.0
WAMIT_ADDED_MASS_FILE = os.path.join(
    current_dir, "hydrodynNbody", "hydrodata", "beso7_nemoh_case_001.1"
)

def read_wamit_infinite_frequency_diagonal(path):
    diagonal = np.full(6, np.nan)
    with open(path, "r", encoding="utf-8") as wamit_file:
        for raw_line in wamit_file:
            fields = raw_line.split()
            if len(fields) < 4:
                continue
            try:
                omega = float(fields[0])
                row = int(fields[1])
                col = int(fields[2])
                value = float(fields[3])
            except ValueError:
                continue
            if np.isclose(omega, -1.0) and row == col and 1 <= row <= 6:
                diagonal[row - 1] = abs(value)
    if np.isnan(diagonal).any():
        raise ValueError(f"未在 {path} 中找到完整的 omega=-1 added-mass 对角项: {diagonal}")
    return diagonal

WAMIT_ADDED_MASS_DIAG_ND = read_wamit_infinite_frequency_diagonal(WAMIT_ADDED_MASS_FILE)
WAMIT_ADDED_MASS_DIAG = np.abs(WAMIT_ADDED_MASS_DIAG_ND) * np.array([
    RHO_WATER * WAMIT_ULEN**3,
    RHO_WATER * WAMIT_ULEN**3,
    RHO_WATER * WAMIT_ULEN**3,
    RHO_WATER * WAMIT_ULEN**5,
    RHO_WATER * WAMIT_ULEN**5,
    RHO_WATER * WAMIT_ULEN**5,
])

target_platform_mass = TARGET_TOTAL_MASS - 3.1e6
current_steel_mass = sum(hydro_node_mass.values())
total_ballast = target_platform_mass - current_steel_mass

ballast_per_leg = total_ballast / 3.0
for leg_id in [4, 5, 6]:
    bot_nid = 10 * leg_id + 2
    hydro_node_mass[bot_nid] += ballast_per_leg

total_mass = 0
for nid in nodes:
    m_struct = hydro_node_mass.get(nid, 0.0)
    total_mass += m_struct
    In = hydro_node_I.get(nid, np.zeros((3, 3)))
    if nid == foundation_data["interface_node"]:
        m_add = WAMIT_ADDED_MASS_DIAG[:3]
        I_add = WAMIT_ADDED_MASS_DIAG[3:]
        # I_add = np.zeros(3) 
    else:
        m_add = np.zeros(3)
        I_add = np.zeros(3)

    ops.mass(
        nid,
        m_struct + m_add[0], m_struct + m_add[1], m_struct + m_add[2],
        In[0, 0] + I_add[0], In[1, 1] + I_add[1], In[2, 2] + I_add[2],
    )

print("[INFO] 节点 1 人工附加质量："
      f"source={WAMIT_ADDED_MASS_FILE}, ND={WAMIT_ADDED_MASS_DIAG_ND.tolist()}, "
      f"SI={WAMIT_ADDED_MASS_DIAG.tolist()}")

print(f"[INFO] 动态浮体建模完成！浮座总质量 = {total_mass/1e3:.1f} 吨")
total = total_mass

# 5. 记录立柱内力（全时段，用于 UC 计算）
opt_ele_tags = foundation_data["opt_ele_tags"]  # 需要提前定义
ops.recorder("Element", "-file", out_path("leg_forces.out"), "-time", "-ele", *opt_ele_tags, "force")

# endregion

# =============================================================================
# region 4. Moor 系泊结构
# =============================================================================
# ------------------------------
x_coords_1000 = [-596.0, -577.0, -558.0, -538.0, -519.0, -500.0, -481.0, -462.0, -442.0, -423.0, -404.0, -385.0, -366.0, -346.0, -327.0, -308.0, -289.0, -269.0, -250.0, -231.0, -212.0, -208.0, -204.0, -201.0, -197.0, -193.0, -189.0, -186.0, -182.0, -168.0, -155.0, -142.0, -129.0, -116.0, -105.0, -93.1, -82.1, -71.6, -61.5]
y_coords_1000 = [-53.3, -51.6, -49.9, -48.2, -46.5, -44.8, -43.1, -41.4, -39.7, -38.0, -36.3, -34.6, -32.9, -31.2, -29.5, -27.8, -26.1, -24.4, -22.7, -21.0, -19.3, -19.0, -18.6, -18.3, -18.0, -17.7, -17.3, -17.0, -16.7, -15.4, -14.3, -13.1, -12.0, -10.9, -9.8, -8.8, -7.8, -6.9, -6.0]
z_coords_1000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_2000 = [-597.9, -578.8, -559.8, -539.7, -520.6, -501.6, -482.5, -463.5, -443.4, -424.3, -405.3, -386.2, -367.2, -347.1, -328.0, -309.0, -289.9, -269.9, -250.8, -231.7, -212.7, -208.7, -204.7, -201.7, -197.6, -193.6, -189.6, -186.6, -182.6, -168.6, -155.5, -142.5, -129.4, -116.4, -105.4, -93.4, -82.4, -71.9, -61.7]
y_coords_2000 = [-24.2, -23.5, -22.7, -22.0, -21.2, -20.4, -19.6, -18.9, -18.1, -17.4, -16.6, -15.8, -15.0, -14.3, -13.5, -12.8, -12.0, -11.3, -10.5, -9.7, -9.0, -8.9, -8.6, -8.5, -8.4, -8.3, -8.1, -7.9, -7.8, -7.2, -6.7, -6.2, -5.7, -5.2, -4.7, -4.3, -3.8, -3.4, -3.0]
z_coords_2000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_3000 = [-597.4, -578.4, -559.3, -539.3, -520.2, -501.2, -482.2, -463.1, -443.1, -424.0, -405.0, -385.9, -366.9, -346.9, -327.8, -308.8, -289.7, -269.7, -250.6, -231.6, -212.6, -208.6, -204.5, -201.5, -197.5, -193.5, -189.5, -186.5, -182.5, -168.5, -155.4, -142.4, -129.4, -116.4, -105.3, -93.4, -82.4, -71.8, -61.7]
y_coords_3000 = [34.0, 32.9, 31.9, 30.6, 29.5, 28.5, 27.4, 26.3, 25.1, 24.0, 22.9, 21.8, 20.7, 19.5, 18.4, 17.3, 16.2, 15.0, 13.9, 12.8, 11.8, 11.5, 11.3, 11.2, 10.9, 10.6, 10.4, 10.3, 10.0, 9.2, 8.4, 7.7, 6.9, 6.1, 5.6, 4.8, 4.2, 3.6, 3.0]
z_coords_3000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_4000 = [-595.0, -576.1, -557.1, -537.2, -518.2, -499.2, -480.2, -461.3, -441.3, -422.4, -403.4, -384.4, -365.4, -345.5, -326.5, -307.6, -288.6, -268.6, -249.7, -230.7, -211.7, -207.7, -203.7, -200.7, -196.8, -192.8, -188.8, -185.8, -181.8, -167.8, -154.8, -141.9, -128.9, -115.9, -104.9, -93.0, -82.1, -71.6, -61.5]
y_coords_4000 = [63.1, 61.1, 59.0, 56.8, 54.8, 52.8, 50.8, 48.8, 46.6, 44.6, 42.6, 40.6, 38.6, 36.4, 34.3, 32.3, 30.3, 28.1, 26.1, 24.1, 22.1, 21.6, 21.2, 20.9, 20.5, 20.0, 19.6, 19.3, 18.8, 17.4, 16.0, 14.6, 13.2, 11.8, 10.7, 9.4, 8.2, 7.1, 6.0]
z_coords_4000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_5000 = [251.8, 243.8, 235.8, 227.3, 219.2, 211.2, 203.2, 195.1, 186.6, 178.6, 170.6, 162.5, 154.5, 146.0, 138.0, 129.9, 121.9, 113.4, 105.3, 97.3, 89.3, 87.5, 85.9, 84.7, 82.9, 81.2, 79.5, 78.3, 76.5, 70.7, 65.1, 59.7, 54.1, 48.6, 44.0, 38.9, 34.3, 29.8, 25.5]
y_coords_5000 = [542.8, 525.5, 508.2, 490.0, 472.7, 455.4, 438.1, 420.8, 402.6, 385.3, 368.0, 350.7, 333.4, 315.2, 297.9, 280.6, 263.3, 245.2, 227.9, 210.6, 193.2, 189.6, 186.0, 183.2, 179.6, 176.0, 172.3, 169.6, 166.0, 153.2, 141.4, 129.5, 117.7, 105.9, 95.8, 85.0, 75.0, 65.5, 56.3]
z_coords_5000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_6000 = [278.0, 269.1, 260.2, 250.8, 242.0, 233.1, 224.3, 215.4, 206.0, 197.1, 188.3, 179.4, 170.6, 161.2, 152.3, 143.4, 134.6, 125.2, 116.3, 107.4, 98.6, 96.7, 94.8, 93.5, 91.6, 89.6, 87.8, 86.4, 84.5, 78.0, 71.9, 65.9, 59.8, 53.7, 48.6, 43.0, 37.9, 33.0, 28.2]
y_coords_6000 = [529.9, 513.0, 496.1, 478.4, 461.5, 444.6, 427.7, 410.8, 393.1, 376.2, 359.3, 342.4, 325.5, 307.8, 290.9, 274.0, 257.1, 239.4, 222.5, 205.6, 188.7, 185.1, 181.6, 178.9, 175.4, 171.8, 168.3, 165.6, 162.0, 149.6, 138.0, 126.5, 114.9, 103.4, 93.6, 83.0, 73.3, 63.9, 55.0]
z_coords_6000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_7000 = [328.2, 317.7, 307.2, 296.2, 285.7, 275.2, 264.8, 254.3, 243.2, 232.8, 222.3, 211.9, 201.4, 190.3, 179.9, 169.4, 158.9, 147.8, 137.4, 126.9, 116.5, 114.2, 112.0, 110.4, 108.2, 105.9, 103.8, 102.1, 99.9, 92.2, 85.0, 77.9, 70.7, 63.5, 57.5, 50.9, 44.8, 39.0, 33.5]
y_coords_7000 = [500.4, 484.4, 468.5, 451.7, 435.8, 419.8, 403.9, 387.9, 371.2, 355.2, 339.3, 323.3, 307.4, 290.6, 274.7, 258.7, 242.8, 226.0, 210.1, 194.1, 178.2, 174.9, 171.5, 168.9, 165.6, 162.3, 158.9, 156.4, 153.1, 141.3, 130.4, 119.5, 108.6, 97.7, 88.4, 78.5, 69.2, 60.4, 52.0]
z_coords_7000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_8000 = [352.1, 340.9, 329.7, 317.8, 306.6, 295.4, 284.1, 272.9, 261.0, 249.8, 238.6, 227.3, 216.1, 204.2, 193.0, 181.8, 170.6, 158.7, 147.5, 136.2, 125.0, 122.6, 120.3, 118.5, 116.1, 113.7, 111.4, 109.6, 107.2, 99.0, 91.2, 83.6, 75.9, 68.1, 61.7, 54.6, 48.1, 41.9, 35.9]
y_coords_8000 = [483.8, 468.4, 452.9, 436.8, 421.3, 405.9, 390.5, 375.1, 358.9, 343.5, 328.1, 312.6, 297.2, 281.0, 265.6, 250.2, 234.8, 218.6, 203.2, 187.7, 172.3, 169.1, 165.8, 163.4, 160.2, 157.0, 153.7, 151.2, 148.0, 136.6, 126.1, 115.5, 105.0, 94.5, 85.5, 75.9, 67.0, 58.5, 50.3]
z_coords_8000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_9000 = [344.2, 333.2, 322.2, 310.7, 299.8, 288.8, 277.8, 266.9, 255.4, 244.4, 233.4, 222.5, 211.5, 200.0, 189.0, 178.1, 167.1, 155.6, 144.7, 133.7, 122.7, 120.5, 118.1, 116.3, 114.1, 111.8, 109.5, 107.7, 105.5, 97.3, 89.9, 82.3, 74.9, 67.4, 61.0, 54.2, 47.8, 41.8, 36.0]
y_coords_9000 = [-489.5, -473.9, -458.3, -441.8, -426.2, -410.6, -395.0, -379.4, -362.9, -347.3, -331.7, -316.1, -300.5, -284.0, -268.4, -252.8, -237.2, -220.8, -205.2, -189.6, -173.9, -170.6, -167.4, -164.9, -161.6, -158.3, -155.0, -152.6, -149.3, -137.8, -127.1, -116.4, -105.7, -95.0, -86.0, -76.2, -67.2, -58.6, -50.3]
z_coords_9000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_10000 = [319.9, 309.7, 299.5, 288.9, 278.7, 268.5, 258.3, 248.1, 237.4, 227.2, 217.0, 206.8, 196.6, 186.0, 175.8, 165.6, 155.4, 144.7, 134.5, 124.3, 114.1, 112.0, 109.8, 108.2, 106.1, 104.0, 101.8, 100.2, 98.1, 90.5, 83.6, 76.6, 69.7, 62.7, 56.7, 50.4, 44.5, 38.9, 33.5]
y_coords_10000 = [-505.7, -489.6, -473.4, -456.4, -440.3, -424.2, -408.1, -391.9, -374.9, -358.8, -342.7, -326.6, -310.5, -293.4, -277.3, -261.2, -245.1, -228.1, -212.0, -195.8, -179.7, -176.3, -172.9, -170.4, -167.0, -163.5, -160.2, -157.6, -154.2, -142.4, -131.3, -120.3, -109.2, -98.2, -88.9, -78.8, -69.4, -60.5, -51.9]
z_coords_10000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_11000 = [269.2, 260.7, 252.1, 243.1, 234.5, 226.0, 217.4, 208.8, 199.8, 191.2, 182.7, 174.1, 165.5, 156.5, 148.0, 139.4, 130.8, 121.8, 113.3, 104.7, 96.1, 94.3, 92.5, 91.1, 89.3, 87.6, 85.7, 84.4, 82.6, 76.2, 70.4, 64.5, 58.7, 52.9, 47.8, 42.5, 37.6, 32.8, 28.3]
y_coords_11000 = [-534.4, -517.3, -500.3, -482.3, -465.3, -448.3, -431.2, -414.2, -396.2, -379.2, -362.2, -345.1, -328.1, -310.1, -293.1, -276.1, -259.0, -241.1, -224.0, -207.0, -190.0, -186.3, -182.8, -180.1, -176.5, -172.9, -169.3, -166.6, -163.0, -150.5, -138.8, -127.2, -115.5, -103.8, -94.0, -83.3, -73.4, -64.0, -55.0]
z_coords_11000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]
x_coords_12000 = [242.9, 235.2, 227.4, 219.4, 211.6, 203.9, 196.1, 188.4, 180.3, 172.6, 164.8, 157.1, 149.3, 141.3, 133.5, 125.8, 118.0, 110.0, 102.2, 94.5, 86.7, 85.2, 83.5, 82.2, 80.7, 79.1, 77.4, 76.2, 74.6, 68.8, 63.6, 58.3, 53.0, 47.8, 43.2, 38.4, 33.9, 29.7, 25.6]
y_coords_12000 = [-546.9, -529.4, -512.0, -493.6, -476.2, -458.7, -441.3, -423.9, -405.5, -388.1, -370.6, -353.2, -335.8, -317.4, -300.0, -282.5, -265.1, -246.7, -229.3, -211.8, -194.4, -190.7, -187.1, -184.3, -180.6, -176.9, -173.3, -170.5, -166.9, -154.0, -142.1, -130.2, -118.2, -106.3, -96.2, -85.3, -75.2, -65.5, -56.3]
z_coords_12000 = [-51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -51.0, -50.9, -48.4, -44.8, -40.1, -34.4, -27.9, -20.6, -12.5, -3.9, 5.3, 15.0]

base_ids = [1000 * i for i in range(1, 13)]
for base_id in base_ids:
    x_coords = globals()[f"x_coords_{base_id}"]
    y_coords = globals()[f"y_coords_{base_id}"]
    z_coords = globals()[f"z_coords_{base_id}"]
    for i in range(39):
        nid = base_id + i + 1
        ops.node(nid, x_coords[i], y_coords[i], z_coords[i])

# 系泊节点质量 (kg)
series_starts = [1001, 2001, 3001, 4001, 5001, 6001, 7001, 8001, 9001, 10001, 11001, 12001]
load_value1 = 9394
load_value2 = 15000
load_value3 = 6832

for start_id in series_starts:
    for i in range(39):
        nid = start_id + i
        if i < 20:
            ops.mass(nid, load_value1, load_value1, load_value1, 0, 0, 0)
            total += load_value1
        elif 20 <= i < 28:
            ops.mass(nid, load_value2, load_value2, load_value2, 0, 0, 0)
            total += load_value2
        else :
            ops.mass(nid, load_value3, load_value3, load_value3, 0, 0, 0)
            total += load_value3

# 海底固定端与竖向弹簧（SI）
for base_id in base_ids:
    x_coords = globals()[f"x_coords_{base_id}"]
    y_coords = globals()[f"y_coords_{base_id}"]
    z_coords = globals()[f"z_coords_{base_id}"]
    for i in range(1, 40):
        node_id = 10 * base_id + i
        fixnode = node_id + 9000
        stiffnessnode = node_id + 900
        ops.node(fixnode, x_coords[i - 1], y_coords[i - 1], z_coords[i - 1])
        ops.fix(fixnode, 1, 1, 1, 1, 1, 1)  # 系泊底端锚固
        ops.uniaxialMaterial("ElasticPPGap", stiffnessnode, 3e6, 3e11, z_coords[i - 1] + 51, 0)
        ops.element("zeroLength", 10000 * base_id + i, base_id + i, fixnode, "-mat", stiffnessnode, "-dir", 3)

# 系泊梁截面（Aggregator，SI）
MA = 0.07
ME = 1.8e10
MG = 8e10
MJ = 8e-4
MIy = 4e-4
MIz = 4e-4
shear_factor = 1.2

P_stiffness = 1.8e9
Mz_stiffness = ME * MIz
My_stiffness = ME * MIy
T_stiffness = MG * MJ
Vy_stiffness = MA * shear_factor
Vz_stiffness = MA * shear_factor

BA = 0.9 * 152.0 / 20.0 * (1.8e9 * 465.0) ** 0.5
ops.uniaxialMaterial("ElasticPPGap", 2001, P_stiffness, 1e13, 0, 1e-3)
ops.uniaxialMaterial("Elastic", 2002, Mz_stiffness)
ops.uniaxialMaterial("Elastic", 2003, My_stiffness)
ops.uniaxialMaterial("Elastic", 2004, Vz_stiffness)
ops.uniaxialMaterial("Elastic", 2005, Vy_stiffness)
ops.uniaxialMaterial("Elastic", 2006, T_stiffness)
ops.uniaxialMaterial("Viscous", 2008, BA, 1)
ops.uniaxialMaterial("Series", 20000, 2001, 2008)

MOOR_SEC_A = 8901  # 系泊 Aggregator 截面 tag（勿与节点 901/902/903 混淆）
MOOR_SEC_B = 8902
ops.section("Aggregator", MOOR_SEC_A, 2001, "P", 2002, "Mz", 2003, "My", 2004, "Vz", 2005, "Vz", 2006, "T")
ops.section("Aggregator", MOOR_SEC_B, 2001, "P", 2002, "Mz", 2003, "My", 2004, "Vz", 2005, "Vz", 2006, "T")

w1 = [0.424 * 6.28, 6.28 / 28.0]
zeta1 = 1.0
a_ray = 2.0 * (w1[0] * w1[1]) / (w1[0] + w1[1])
b_ray = 2.0 / (w1[0] + w1[1])

mn = [51, 41, 61]  # 修正系泊挂载(原41/51接反): 线1-4→51, 线5-8→41, 线9-12→61
for j in range(1, 13):
    node_id = 1000 * j 
    element_id = 100000 * j 
    group_idx = (j - 1) // 4
    mooring_node = mn[group_idx % len(mn)]
    # 改为 equalDOF，移除 elasticBeamColumn
    ops.equalDOF(mooring_node, node_id + 39, 1, 2, 3)
    for i in range(1, 39):
        ops.element("elasticBeamColumn", element_id + i, node_id + i, node_id + i + 1, MOOR_SEC_B, 1)
        ops.region(1, "-ele", element_id + i, "-rayleigh", a_ray * zeta1, b_ray * zeta1, 0, 0)

# 约束：海底节点固定（沿用原脚本）
for end_id in [1001, 2001, 3001, 4001, 5001, 6001, 7001, 8001, 9001, 10001, 11001, 12001]:
    ops.fix(end_id, 1, 1, 1, 0, 0, 0)  # shx铰接

# endregion
def plot_full_model(save_path="OPSout/full_model.png"):
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    # 1. 绘制浮体节点和单元（保持原样）
    nodes = foundation_data["nodes"]
    xs_f = [coord[0] for coord in nodes.values()]
    ys_f = [coord[1] for coord in nodes.values()]
    zs_f = [coord[2] for coord in nodes.values()]
    ax.scatter(xs_f, ys_f, zs_f, c='red', s=30, label='Foundation Nodes')
    for ele in foundation_data["elements"]:
        n1, n2 = ele["n1"], ele["n2"]
        p1 = np.array(nodes[n1])
        p2 = np.array(nodes[n2])
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], 'b-', linewidth=1.5)
    
    # 2. 绘制系泊链最后10个节点（靠近挂载点）
    for line_id in range(1, 13):
        base = line_id * 1000
        coords = []
        for i in range(1, 40):
            nid = base + i
            try:
                coord = ops.nodeCoord(nid)
                coords.append(coord)
            except:
                break
        if len(coords) >= 10:
            coords_sub = coords[-10:]   # 取最后10个
        else:
            coords_sub = coords
        if len(coords_sub) > 1:
            xs_m = [c[0] for c in coords_sub]
            ys_m = [c[1] for c in coords_sub]
            zs_m = [c[2] for c in coords_sub]
            ax.plot(xs_m, ys_m, zs_m, 'g-', linewidth=1.5, alpha=0.8,
                    label='Mooring line' if line_id == 1 else "")
            # 标记导缆孔（末端节点）
            fairlead = coords[-1]
            ax.scatter([fairlead[0]], [fairlead[1]], [fairlead[2]],
                       c='magenta', s=50, marker='^',
                       label='Fairlead' if line_id == 1 else "")
    
    # 3. 突出显示浮体系泊挂载点
    for nid in foundation_data["mooring_nodes"]:
        p = nodes[nid]
        ax.scatter([p[0]], [p[1]], [p[2]], c='orange', s=100, marker='s',
                   label='Mooring Attachment' if nid == foundation_data["mooring_nodes"][0] else "")
    
    ax.set_xlabel('X (m)'); ax.set_ylabel('Y (m)'); ax.set_zlabel('Z (m)')
    ax.set_title('Platform Model (mooring lines: last 10 nodes near fairlead)')
    ax.legend(loc='upper right', fontsize=8)
    
    # 收集所有显示的点（浮体 + 系泊末端段）
    all_x = xs_f + [coord[0] for line in range(1,13) for coord in coords_sub]
    all_y = ys_f + [coord[1] for line in range(1,13) for coord in coords_sub]
    all_z = zs_f + [coord[2] for line in range(1,13) for coord in coords_sub]
    if all_x:
        # 计算显示范围
        x_range = max(all_x) - min(all_x)
        y_range = max(all_y) - min(all_y)
        z_range = max(all_z) - min(all_z)
        max_range = max(x_range, y_range, z_range) * 0.5
        mid_x = (max(all_x)+min(all_x))*0.5
        mid_y = (max(all_y)+min(all_y))*0.5
        mid_z = (max(all_z)+min(all_z))*0.5
        ax.set_xlim(mid_x - max_range, mid_x + max_range)
        ax.set_ylim(mid_y - max_range, mid_y + max_range)
        ax.set_zlim(mid_z - max_range, mid_z + max_range)
        # 强制等比例
        ax.set_box_aspect([1,1,1])
    
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"[INFO] 全模型可视化（聚焦挂载点附近，等比例）已保存至 {save_path}")
# 调用绘图（此时所有节点都已建立）
plot_full_model()

# ========== 建模后立即进行可视化（在分析前） ==========
plot_platform(foundation_data)   # 调用可视化函数，确保模型正确
# ===========================================================
# endregion

# =============================================================================
# region 5. 塔架 + RNA（浮体系泊已耦合）
# =============================================================================
interface_nid = foundation_data["interface_node"]  # 节点 1
z_offset = foundation_data["nodes"][interface_nid][2]  # 浮体接口节点 z 坐标

Numtower = 64
Height = 136.7  # 固定旧塔长；新接口 z=12 m 后，塔顶为 148.7 m

TowerHtFract_str = "0.00000 0.00201 0.02246 0.04294 0.06342 0.08391 0.10439 0.12487 0.14535 0.16591 0.16796 0.17001 0.18756 0.20512 0.22268 0.24023 0.25779 0.27535 0.29290 0.31083 0.32875 0.34704 0.36533 0.38361 0.40190 0.42012 0.42195 0.42377 0.44236 0.46094 0.47952 0.49817 0.51683 0.53566 0.55450 0.57352 0.59254 0.61156 0.63072 0.64989 0.66920 0.68859 0.69027 0.69195 0.71024 0.72853 0.74682 0.76511 0.78339 0.80168 0.81997 0.83826 0.85655 0.87484 0.89312 0.91214 0.93116 0.95018 0.96920 0.97074 0.97228 0.98888 0.99517 0.99663 1.00000"
TowerMass_str = "2.36733E+05 2.13075E+04 2.13075E+04 2.07157E+04 1.83482E+04 1.70171E+04 1.64252E+04 1.61293E+04 1.58333E+04 1.58333E+04 1.21862E+05 1.57496E+04 1.49995E+04 1.45507E+04 1.41081E+04 1.38128E+04 1.33811E+04 1.29557E+04 1.25349E+04 1.22533E+04 1.19744E+04 1.16965E+04 1.14218E+04 1.11510E+04 1.08828E+04 1.08134E+04 9.99814E+04 1.07418E+04 1.03527E+04 9.97016E+03 9.71324E+03 9.46015E+03 9.20942E+03 8.96156E+03 8.71659E+03 8.47359E+03 8.12514E+03 7.89067E+03 7.65962E+03 7.43066E+03 7.10224E+03 7.04268E+03 7.62340E+04 6.98652E+03 6.57534E+03 6.46832E+03 6.16814E+03 5.96961E+03 5.68118E+03 5.49039E+03 5.30322E+03 5.03102E+03 4.85161E+03 4.76080E+03 4.58457E+03 4.32833E+03 4.15914E+03 4.69765E+03 4.64697E+03 5.51041E+04 7.74494E+03 1.08429E+04 1.08429E+04 1.08429E+04 4.95647E+04"
TowerFA_str = "1.0065E+13 1.0065E+13 1.0065E+13 9.7855E+12 8.6671E+12 8.0390E+12 7.7594E+12 7.6196E+12 7.4798E+12 7.4798E+12 7.4798E+12 7.3617E+12 6.8627E+12 6.5155E+12 6.1812E+12 5.9201E+12 5.6088E+12 5.3097E+12 5.0202E+12 4.7931E+12 4.5731E+12 4.3583E+12 4.1512E+12 3.9522E+12 3.7598E+12 3.6883E+12 3.6883E+12 3.6155E+12 3.3926E+12 3.1799E+12 3.0134E+12 2.8540E+12 2.7001E+12 2.5521E+12 2.4099E+12 2.2725E+12 2.1133E+12 1.9890E+12 1.8702E+12 1.7559E+12 1.6234E+12 1.5829E+12 1.5829E+12 1.5453E+12 1.4080E+12 1.3404E+12 1.2361E+12 1.1564E+12 1.0631E+12 9.9184E+11 9.2438E+11 8.4558E+11 7.8563E+11 7.4234E+11 6.8724E+11 6.2279E+11 5.7404E+11 6.2126E+11 6.0137E+11 6.0137E+11 1.0023E+12 1.4033E+12 1.4033E+12 1.4033E+12 1.4033E+12"
TowerSS_str = TowerFA_str

def _parse(s: str):
    return [float(x) for x in s.split()]

TowerHtFract = _parse(TowerHtFract_str)
TowerMass = _parse(TowerMass_str)
TowerFA = _parse(TowerFA_str)
TowerSS = _parse(TowerSS_str)

E_tower = 2.1e11
G_tower = 8.08e10
rho_tower = 8500.0

ops.geomTransf("PDelta", 950, 0, 1, 0)
ops.geomTransf("Linear", 951, 0, 1, 0)

# 1. 生成塔架节点
for i in range(Numtower + 1):
    z = TowerHtFract[i] * Height + z_offset
    ops.node(80 + i, 0.0, 0.0, z)

# 2. 塔底(80) 与浮体接口节点 (interface_nid) 全自由度耦合
ops.equalDOF(interface_nid, 80, 1, 2, 3, 4, 5, 6)

# 3. 建立塔筒单元
for i in range(1, Numtower + 1):
    n1 = 80 + i - 1
    n2 = 80 + i
    FA1 = TowerFA[i - 1]
    FA2 = TowerFA[i]
    I_FA = (FA1 + FA2) / 2.0 / E_tower
    SS1 = TowerSS[i - 1]
    SS2 = TowerSS[i]
    I_SS = (SS1 + SS2) / 2.0 / E_tower
    J_tower = I_FA + I_SS
    M1 = TowerMass[i - 1]
    M2 = TowerMass[i]
    MassDenAvg = (M1 + M2) / 2.0
    A_tower = MassDenAvg / rho_tower
    ops.element("elasticBeamColumn", 2000 + i, n1, n2, A_tower, E_tower, G_tower, J_tower, I_FA, I_SS, 950)

# 4. 赋予塔筒质量与转动惯量（total 自 region 3-4 延续，勿清零）
for i in range(Numtower + 1):
    m_node = 0.0
    if i > 0:
        h_below = (TowerHtFract[i] - TowerHtFract[i - 1]) * Height
        M_elem_below = (TowerMass[i - 1] + TowerMass[i]) / 2.0 * h_below
        m_node += M_elem_below / 2.0
    if i < Numtower:
        h_above = (TowerHtFract[i + 1] - TowerHtFract[i]) * Height
        M_elem_above = (TowerMass[i] + TowerMass[i + 1]) / 2.0 * h_above
        m_node += M_elem_above / 2.0
    ops.mass(80 + i, m_node, m_node, m_node, m_node, m_node, m_node)
    total += m_node

# -----------------------------------------------------------
# 重构 RNA：AeroLoad(191) + ServoLoad(194) 双接口传动系统
# -----------------------------------------------------------
nacelle_z = Height + 1.75 + z_offset
hub_x = -1.9
hub_z = nacelle_z

ops.node(190, 0.0, 0.0, nacelle_z)                 # 机舱定子
ops.node(194, 0.0, 0.0, nacelle_z)                 # 发电机转子 (ServoLoad 接口)
ops.node(193, 0.0, 0.0, nacelle_z)                 # 主轴根部 / LSS
ops.node(191, hub_x, 0.0, hub_z)                   # 轮毂中心 (AeroLoad 扭矩接口)

Arigid = 100.0
Erigid = 1.0e11
Grigid = 1.0e11
Jrigid = 100.0
Irigid = 100.0

ops.geomTransf("Corotational", 952, 0, 1, 0)
ops.geomTransf("Corotational", 953, 1, 0, 0)#shx 改pitch时修改
ops.geomTransf("Corotational", 954, 1, 0, 0)
ops.geomTransf("Corotational", 955, 1, 0, 0)

ops.element("elasticBeamColumn", 144190, 144, 190, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 950)

# 机舱定子 ↔ 发电机转子：释放主轴旋转 DOF4
ops.equalDOF(190, 194, 1, 2, 3, 5, 6)
ops.uniaxialMaterial("Elastic", 999, 1.0)
ops.element("zeroLength", 999999, 190, 194, "-mat", 999, "-dir", 4)

# 发电机转子 ↔ 主轴根部：传动链扭转柔度
ops.uniaxialMaterial("Elastic", 101, DTTorSpr)
ops.uniaxialMaterial("Viscous", 102, DTTorDmp, 1.0)
ops.uniaxialMaterial("Parallel", 103, 101, 102)
ops.element("zeroLength", 190193, 194, 193, "-mat", 103, "-dir", 4)
ops.equalDOF(190, 193, 1, 2, 3, 5, 6)

# 主轴根部 ↔ 轮毂
ops.element("elasticBeamColumn", 193191, 193, 191, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 952)

NacMass1 = 447000.0
total += NacMass1 + HubMass
ops.mass(190, NacMass1, NacMass1, NacMass1, 1e6, 1e6, 5311000.0)
ops.mass(194, 0.0, 0.0, 0.0, GenIner_LSS, 0.0, 0.0)
ops.mass(193, 0.0, 0.0, 0.0, 7.33e7, 0.0, 0.0)
ops.mass(191, HubMass, HubMass, HubMass, HubIner, 1e7, 1e7)

# ServoLoad 桨距代理：节点 901–903 固定；锚固/材料/单元用 29000 段（避开系泊 9010 等）
_pitch_proxy_cfg = [
    # (proxy_node, anchor_node, mat_tag, zeroLength_elem_tag)
    (901, 911, 911, 901911),
    (902, 912, 912, 902912),
    (903, 913, 913, 903913),
]
for p_tag, a_tag, m_tag, e_tag in _pitch_proxy_cfg:
    setup_pitch_proxy(p_tag, a_tag, m_tag, e_tag, hub_x, 0.0, hub_z)

# -----------------------------------------------------------
# 叶片建模（已更新：601, 701, 801 设为叶根节点，退化为完整刚性叶片）
# -----------------------------------------------------------
ex0 = 5.0191
ez0 = 1.912

Bladelength_str = "0.0000 1.0001 2.0000 3.0000 5.5000 8.0000 10.5000 13.0000 15.5001 18.0001 20.5001 23.0001 25.4999 27.9999 30.4999 32.9999 35.5000 38.0000 40.5000 43.0000 45.5000 48.0000 50.5000 53.0000 55.5000 58.0000 60.5000 63.0000 65.5000 68.0000 70.5000 73.0000 75.5000 78.0000 80.5000 83.0000 85.5000 88.0000 90.5000 93.0000 95.5000 98.0001 100.5001 103.0001 105.5001 107.9999 110.4999 112.9999 115.4999 118.0000 120.5000 123.0000 125.5000 128.0000 129.5001 129.9999 130.5000 131.0000"
Massblade_str = "16374.300 2475.250 1828.100 1727.750 1602.260 1566.230 1460.020 1320.830 1282.450 1159.130 1097.710 995.935 940.165 813.497 731.649 705.943 670.861 639.000 612.053 636.394 569.391 551.632 529.802 508.792 472.946 459.446 443.397 429.040 400.814 470.238 410.179 356.310 345.972 328.519 317.112 300.344 282.536 273.383 258.046 229.007 216.913 203.712 190.423 179.279 166.594 152.780 140.369 129.284 118.423 122.765 136.276 84.676 73.599 60.434 36.007 29.417 19.543 7.123"

Bladelength = _parse(Bladelength_str)
Massblade = _parse(Massblade_str)
max_L = Bladelength[-1]       # 131.0 米 (叶片满长)
root_L = Bladelength[0]       # 0.0 米 (叶片展向起点相对叶根基准)

# 计算单根叶片的总质量
m_blade_total = 0.0
for i in range(1, len(Bladelength)):
    m_blade_total += (Bladelength[i] - Bladelength[i - 1]) * (Massblade[i - 1] + Massblade[i]) / 2.0

gen3 = math.sqrt(3.0)

# 1. 建立 3 个【叶根节点】（保持物理叶根初始距离坐标：max_L = 0 时的坐标位置）
ops.node(601, ex0, 0.0, Height + z_offset + ez0 + root_L)
ops.node(701, ex0, gen3 / 2.0 * root_L, Height + z_offset + ez0 - 0.5 * root_L)
ops.node(801, ex0, -gen3 / 2.0 * root_L, Height + z_offset + ez0 - 0.5 * root_L)
# 2. 建立 3 个增设的【虚拟叶尖节点】（对应 131 米展向物理满长位置）
ops.node(699, ex0, 0.0, Height + z_offset + ez0 + max_L)
ops.node(799, ex0, gen3 / 2.0 * max_L, Height + z_offset + ez0 - 0.5 * max_L)
ops.node(899, ex0, -gen3 / 2.0 * max_L, Height + z_offset + ez0 - 0.5 * max_L)

# 3. 单元连结树：轮毂中心(191) -> 叶根节点(601/701/801)
ops.element("elasticBeamColumn", 191601, 191, 601, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 953)
ops.element("elasticBeamColumn", 191701, 191, 701, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 954)
ops.element("elasticBeamColumn", 191801, 191, 801, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 955)

# 4. 单元连结树：叶根节点 -> 虚拟叶尖节点（采用刚性梁，使整根叶片等效退化为完全刚性）
ops.element("elasticBeamColumn", 601699, 601, 699, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 953)
ops.element("elasticBeamColumn", 701799, 701, 799, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 954)
ops.element("elasticBeamColumn", 801899, 801, 899, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 955)

# 5. 边界释放与动力学属性集中分配（均分到叶根主控节点与叶尖节点）
m_half = m_blade_total / 2.0
for root_node in [601, 701, 801]:
    #ops.fix(root_node, 1, 0, 0, 0, 0, 0) #shx ops.fix(root_node, 1, 0, 0, 0, 0, 0)(root_node, 1, 1, 1, 1, 1, 1)
    ops.mass(root_node, m_half, m_half, m_half, m_half * 10, m_half * 10, m_half * 10)

for tip_node in [699, 799, 899]:
    ops.mass(tip_node, m_half, m_half, m_half, m_half * 10, m_half * 10, m_half * 10)

total += 3 * m_blade_total
# endregion
# opsvis.set_plot_props(point_size=6, line_width=3, cmap="jet", notebook=False)  # set notebook=False for practical use
# fig = opsvis.plot_model(show_nodal_loads=True, show_ele_loads=True, show_node_numbering=True)
# fig.show()  # fig.show() for practical use

# =============================================================================
# region 6. 重力静力平衡（与 Zwind_v2.2.1.py 一致，叶片按刚性模型节点）
# =============================================================================
ops.timeSeries("Constant", 1001)
ops.pattern("Plain", 1001, 1001)
for nid, m_h in hydro_node_mass.items():
    if m_h > 0.0:
        ops.load(nid, 0, 0, -m_h * G_ACC, 0, 0, 0)

ops.timeSeries("Constant", 1003)
ops.pattern("Plain", 1003, 1003)
for series in range(1, 13):
    base_id = series * 1000
    for i in range(1, 21):
        ops.load(base_id + i, 0, 0, -load_value1 * G_ACC, 0, 0, 0)
    for i in range(21, 29):
        ops.load(base_id + i, 0, 0, -load_value2 * G_ACC, 0, 0, 0)
    for i in range(29, 40):
        ops.load(base_id + i, 0, 0, -load_value3 * G_ACC, 0, 0, 0)

ops.timeSeries("Constant", 4)
ops.pattern("Plain", 4, 4)
for i in range(Numtower + 1):
    m_node = 0.0
    if i > 0:
        h_b = (TowerHtFract[i] - TowerHtFract[i - 1]) * Height
        m_node += (TowerMass[i - 1] + TowerMass[i]) / 2.0 * h_b / 2.0
    if i < Numtower:
        h_a = (TowerHtFract[i + 1] - TowerHtFract[i]) * Height
        m_node += (TowerMass[i] + TowerMass[i + 1]) / 2.0 * h_a / 2.0
    ops.load(80 + i, 0, 0, -m_node * G_ACC, 0, 0, 0)
ops.load(190, 0, 0, -NacMass1 * G_ACC, 0, 0, 0)
ops.load(191, 0, 0, -HubMass * G_ACC, 0, 0, 0)
for nid in [601, 701, 801, 699, 799, 899]:
    ops.load(nid, 0, 0, -m_half * G_ACC, 0, 0, 0)

# endregion
# =============================================================================
# region 7. HydroLoad + AeroLoad + ServoLoad 外部耦合
# =============================================================================
if Hydro:
    print(">>> 开启 HydroLoad...")
    ops.pattern("HydroLoad", 400, "-driver", "hydrodynNbody/hd_driver.inp")#_only

# 【直接使用真实的顶盘中心节点 1】
    # OpenSees 会生成 2 个独立的 Load 对象喂给 DLL，没有虚拟梁，没有病态矩阵！
    # interface_nid = foundation_data["interface_node"] 
    
    # # 第 1 行：PRP 运动学参考点
    # ops.load(interface_nid, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "-pattern", 400)
    
    # # 第 2 行：单体水动力接收点
    # ops.load(interface_nid, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 400)

    prp_nid = PRP_NODE
    # 注意：这两行加载的是同一个 PRP 节点
    ops.load(prp_nid, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "-pattern", 400) # 运动学输入标记
    ops.load(prp_nid, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 400) # 力输出标记
if Aero:
    ops.pattern("AeroLoad", 200, "-driver", "Aerodyn/ad_driver_servo.dvr")
    ops.load(190, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 200)
    ops.load(191, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 200)
    ops.load(601, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 200)
    ops.load(701, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 200)
    ops.load(801, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 200)
    for nid in range(80, 80 + Numtower + 1):
        ops.load(nid, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 200)

if Servo:
    ops.pattern("ServoLoad", 500, "-driver", "servoData_v2.2.8/ServoDyn2.2.8.dat")
    ops.load(GEN_NODE_TAG, 1, 1, 1, 1, 1, 1, "-pattern", 500)
    for tag in PROXY_NODES:
        ops.load(tag, 1, 1, 1, 1, 1, 1, "-pattern", 500)
# endregion

# =============================================================================
# region 8. 分区 Rayleigh 阻尼 \ 软起动函数
# =============================================================================

# ----------------------------------------------------------------------------
# 分区 Rayleigh 阻尼
# 原脚本使用 ops.rayleigh(alpha_m, beta_k, 0, 0) 全模型施加，
# beta_k 会作用到主轴、传动链和刚性梁等高刚度部件，容易形成很大的数值刹车。
# 这里改为按单元区域施加：浮体/塔筒保留阻尼，RNA/主轴/传动链/刚性梁仅保留极小阻尼。
# ----------------------------------------------------------------------------

def rayleigh_ab(zeta, w1, w2):
    alpha = zeta * (2.0 * w1 * w2) / (w1 + w2)
    beta = zeta * 2.0 / (w1 + w2)
    return alpha, beta


def apply_region_rayleigh(region_tag, ele_tags, alpha_m, beta_k, beta_k_init=0.0, beta_k_comm=0.0):
    ele_tags = [int(e) for e in ele_tags]
    if not ele_tags:
        return
    ops.region(
        int(region_tag),
        "-ele",
        *ele_tags,
        "-rayleigh",
        float(alpha_m),
        float(beta_k),
        float(beta_k_init),
        float(beta_k_comm),
    )


# 单元分区
FLOAT_ELE_TAGS = list(range(101, 118))  # 注意：新的动态模型单元编号从101开始，但可能数量不同，这里保留原范围，但实际单元编号由JSON生成，动态模型单元编号是101-112等，需动态获取
# 为了兼容，我们动态获取所有 optimized_leg 的单元编号
FLOAT_ELE_TAGS = [ele["id"] for ele in foundation_data["elements"] if ele["type"] == "optimized_leg"]
TOWER_ELE_TAGS = list(range(2001, 2000 + Numtower + 1))
RNA_RIGID_ELE_TAGS = [
    144190,    # 塔顶-机舱刚性连接
    999999,    # 机舱定子-发电机转子 DOF4 释放单元
    190193,    # 发电机转子-主轴根部传动链
    193191,    # 主轴根部-轮毂刚性梁
    901911, 902912, 903913,  # ServoDyn 桨距代理弹簧
    191601, 191701, 191801,  # 轮毂-叶根刚性梁
    601699, 701799, 801899,  # 叶根-虚拟叶尖刚性梁
]

if ENABLE_REGIONAL_DAMPING:
    float_alpha, float_beta = rayleigh_ab(DAMP_FLOAT_ZETA, DAMP_FLOAT_W1, DAMP_FLOAT_W2)
    tower_alpha, tower_beta = rayleigh_ab(DAMP_TOWER_ZETA, DAMP_TOWER_W1, DAMP_TOWER_W2)

    apply_region_rayleigh(9101, FLOAT_ELE_TAGS, float_alpha, float_beta, 0.0, 0.0)
    apply_region_rayleigh(9102, TOWER_ELE_TAGS, tower_alpha, tower_beta, 0.0, 0.0)
    apply_region_rayleigh(9103, RNA_RIGID_ELE_TAGS, DAMP_RNA_ALPHA_M, DAMP_RNA_BETA_K, 0.0, 0.0)

    print(
        "[INFO] Regional Rayleigh damping applied: "
        f"FLOAT zeta={DAMP_FLOAT_ZETA:g}, alpha={float_alpha:.3e}, beta={float_beta:.3e}; "
        f"TOWER zeta={DAMP_TOWER_ZETA:g}, alpha={tower_alpha:.3e}, beta={tower_beta:.3e}; "
        f"RNA alpha={DAMP_RNA_ALPHA_M:.3e}, beta={DAMP_RNA_BETA_K:.3e}."
    )
else:
    # 仅供回退测试：不推荐用于最终 Aero+Servo+Hydro 耦合计算
    ops.rayleigh(0.0, 0.0, 0.0, 0.0)

# -----------------------------------------------------------------------------
# 1. 主轴辅助力矩软启动（路径 A）
# -----------------------------------------------------------------------------
omega_target = Rated_Speed_LSS
use_start_assist = ENABLE_START_ASSIST and Aero and not ENABLE_DECAY_TEST

# 低速轴辅助力矩闭环参数
START_TORQUE_LIMIT = START_TORQUE_LIMIT_RATIO * Rated_Torque_LSS
START_KP = START_KP_RATIO * Rated_Torque_LSS / max(abs(omega_target), 1.0e-9)

# 动态重建辅助力矩 load pattern 的标签；不再使用 sp(193,4)
START_ASSIST_TAG_BASE = 8600000
_start_assist_pattern_tag = None
_start_assist_ts_tag = None
_start_assist_tag_count = 0


def smoothstep5(x):
    """五次 smoothstep：端点一阶、二阶导数为 0，用于温和加载/卸载。"""
    x = clamp_val(float(x), 0.0, 1.0)
    return x ** 3 * (10.0 - 15.0 * x + 6.0 * x ** 2)


def clear_start_assist_load():
    """移除上一步辅助力矩 pattern。timeSeries 若可移除则同步清理。"""
    global _start_assist_pattern_tag, _start_assist_ts_tag
    if _start_assist_pattern_tag is not None:
        try:
            ops.remove("pattern", _start_assist_pattern_tag)
        except Exception:
            try:
                ops.remove("loadPattern", _start_assist_pattern_tag)
            except Exception:
                pass
        _start_assist_pattern_tag = None
    if _start_assist_ts_tag is not None:
        try:
            ops.remove("timeSeries", _start_assist_ts_tag)
        except Exception:
            pass
        _start_assist_ts_tag = None


def apply_start_assist_torque(torque_lss):
    """在节点 193 的 DOF4 施加当前步辅助力矩；主轴自由度始终保持自由。"""
    global _start_assist_pattern_tag, _start_assist_ts_tag, _start_assist_tag_count
    clear_start_assist_load()
    if (not use_start_assist) or abs(torque_lss) < 1.0e-6:
        return

    _start_assist_tag_count += 1
    ts_tag = START_ASSIST_TAG_BASE + 2 * _start_assist_tag_count
    pattern_tag = START_ASSIST_TAG_BASE + 2 * _start_assist_tag_count + 1

    ops.timeSeries("Constant", ts_tag)
    ops.pattern("Plain", pattern_tag, ts_tag)
    ops.load(193, 0.0, 0.0, 0.0, torque_lss, 0.0, 0.0)

    _start_assist_ts_tag = ts_tag
    _start_assist_pattern_tag = pattern_tag


def calc_start_assist_torque(t, omega_lss, assist_state, unload_start_time):
    """根据当前 LSS 转速计算辅助起动力矩。"""
    if (not use_start_assist) or assist_state == "OFF":
        return 0.0

    omega_signed = omega_lss
    speed_error = max(0.0, omega_target - omega_signed)
    torque_cmd = START_KP * speed_error
    torque_cmd = clamp_val(torque_cmd, 0.0, START_TORQUE_LIMIT)

    # 避免 t=0 直接给阶跃力矩
    ramp_in = smoothstep5(t / max(START_RAMP_IN_TIME, DT))
    torque_cmd *= ramp_in

    # 达到目标转速且稳定后，平滑退出；退出阶段仍保留速度误差反馈，但逐渐乘 0
    if assist_state == "UNLOAD" and unload_start_time is not None:
        xi = (t - unload_start_time) / max(START_UNLOAD_TIME, DT)
        torque_cmd *= (1.0 - smoothstep5(xi))

    return torque_cmd
# endregion

# =============================================================================
# region 9. Transient 求解器与动态捕获主循环
# =============================================================================
# ---------- 新增：用于记录转角和内力的数组 ----------
num_steps = NSTEPS
num_units = len(foundation_data["opt_ele_tags"])  # 优化立柱数量（6 根）
node1_ry_array = np.zeros((1, num_steps))          # 节点1的ry转角
ele_forces_array = np.zeros((num_steps, 12, num_units))  # 单元内力 (步数 × 12 × 单元数)
step_counter = 0
# ----------------------------------------------------
# -----------------------------------------------------------------------------
# 2. 求解器设置
# -----------------------------------------------------------------------------
ops.wipeAnalysis()
ops.system("SparseGEN") # BandGeneral
ops.numberer("RCM")
ops.constraints("Transformation") 
ops.integrator("Newmark", 0.5, 0.25)
# # 使用 HHT 积分器，alpha 设为 0.9（介于 0.67 到 1.0 之间），
# # 这会像海绵一样专门吸收 0.01s 级别的高频振荡，而对长周期的塔筒晃动没有任何影响
# # 在 HHT 括号内完整传入参数：(alpha, gamma, beta)
# # 对应标准的 HHT 公式，alpha=0.9 既能消高频噪音，又不会篡改主时间步长
# ops.integrator("HHT", 0.9, 0.5, 0.25)
ops.algorithm("Newton")
ops.test("NormDispIncr", 1.0e-3, 100, 0)
ops.analysis("Transient")

# Aero+Servo 启动初期给传动链极小初速，减轻 DISCON 在零转速附近的数值问题
if Aero and Servo:
    ops.setNodeVel(193, 4, 0.05 )
    ops.setNodeVel(GEN_NODE_TAG, 4, 0.05 )

# 辅助力矩状态变量
assist_state = "ACCEL" if use_start_assist else "OFF"
assist_stable_start = None
assist_unload_start = None
assist_torque = 0.0
next_assist_update_time = 0.0

torqueCtrlPath = out_path("hubTorqueCtrl.out")
startAssistPath = out_path("startAssist.out")
start_time = time.time()
last_pitch_cmds = [0.0, 0.0, 0.0]
log_interval = max(1, int(0.5 / DT))

with open(torqueCtrlPath, "w") as torqueCtrlFile, open(startAssistPath, "w") as startAssistFile:
    torqueCtrlFile.write(
        "# time omega_lss_rpm omega_hss_rpm pitch1_deg gen_torque_lss elec_power_w\n"
    )
    startAssistFile.write(
        "# time assist_state omega193_rpm omega194_rpm assist_torque_lss_Nm assist_torque_limit_Nm\n"
    )
    with tqdm(total=NSTEPS, desc="20MW Aero+Servo+Hydro 时域分析", dynamic_ncols=True, leave=True) as pbar:

        t_current = 0.0
        step_idx = 0

        while t_current < TMAX:
            if Servo:
                for j, tag in enumerate(PROXY_NODES):
                    ops.setNodeDisp(tag, 4, last_pitch_cmds[j])

            # 路径 A：主轴始终自由；每 START_UPDATE_DT 更新一次辅助起动力矩
            if use_start_assist and t_current >= next_assist_update_time:
                omega193_now = ops.nodeVel(193, 4)
                assist_torque = calc_start_assist_torque(
                    t_current, omega193_now, assist_state, assist_unload_start
                )
                apply_start_assist_torque(assist_torque)
                next_assist_update_time = t_current + START_UPDATE_DT

            # 外接 Aero/Hydro/Servo DLL 与 OpenSees 时间步绑定，禁止事后改 dt 或切换算法重算
            ok = ops.analyze(1, DT)
            t_after = ops.getTime()

            if ok != 0:
                print(
                    f"\n[FATAL] analyze 失败 t={t_after:.4f}s（固定 DT={DT}s）。"
                    f"外接 DLL 已推进状态，不可变步长/换算法重试。"
                )
                print(
                    "        建议核对 hydrodynNbody/driver.out 该时刻 PRP 加速度与 HydroMxi/Myi/Mzi，"
                    "以及 OPSout/platform_accel.out。"
                )
                break

            t_current = t_after

            ops.reactions()
            # ----- 新增记录节点转角和单元内力 -----
            if step_counter < num_steps:
                # 记录节点1的ry转角 (自由度5)
                node1_ry = ops.nodeDisp(1, 5)
                node1_ry_array[0, step_counter] = node1_ry

                # 记录所有优化立柱的单元内力
                for i, ele_tag in enumerate(foundation_data["opt_ele_tags"]):
                    try:
                        force_response = ops.eleResponse(ele_tag, 'force')
                        if isinstance(force_response, list) and len(force_response) >= 12:
                            ele_forces_array[step_counter, :, i] = force_response[:12]
                        else:
                            ele_forces_array[step_counter, :len(force_response), i] = force_response
                    except Exception:
                        ele_forces_array[step_counter, :, i] = np.nan
                step_counter += 1
            # ------------------------------------------
            if Servo:#shx
                for j, tag in enumerate(PROXY_NODES):
                    raw_pitch = ops.nodeUnbalance(tag, 4)
                    if math.isnan(raw_pitch) or math.isinf(raw_pitch):
                        last_pitch_cmds[j] = 0.0
                    else:
                        last_pitch_cmds[j] = clamp_val(raw_pitch, 0.0, math.radians(90.0))
                        ops.setNodeDisp(tag, 4, last_pitch_cmds[j])

            # 启动判据使用主轴根部 193 的 LSS 转速；Servo 输出仍按 GEN_NODE_TAG 记录
            omega193 = ops.nodeVel(193, 4)
            omega_lss = ops.nodeVel(GEN_NODE_TAG, 4) if Servo else ops.nodeVel(191, 4)

            if use_start_assist and assist_state in ("ACCEL", "UNLOAD"):
                omega_check = omega193
                if assist_state == "ACCEL":
                    if omega_check >= START_TARGET_RATIO * omega_target:
                        if assist_stable_start is None:
                            assist_stable_start = t_after
                        elif (t_after - assist_stable_start) >= START_STABLE_TIME:
                            assist_state = "UNLOAD"
                            assist_unload_start = t_after
                            print(
                                f"\n[INFO] t={t_after:.2f}s LSS 已稳定达到 "
                                f"{START_TARGET_RATIO:.2f}*rated speed，开始在 "
                                f"{START_UNLOAD_TIME:.1f}s 内平滑卸载辅助力矩。"
                            )
                    else:
                        assist_stable_start = None
                elif assist_state == "UNLOAD":
                    if assist_unload_start is not None and (t_after - assist_unload_start) >= START_UNLOAD_TIME:
                        assist_state = "OFF"
                        assist_torque = 0.0
                        clear_start_assist_load()
                        print(
                            f"\n[INFO] t={t_after:.2f}s 辅助力矩已卸载完成，"
                            "主轴保持自由，由 AeroLoad + ServoLoad + HydroLoad 耦合控制。"
                        )

            omega_lss_rpm = omega_lss * 60.0 / (2.0 * PI)
            omega193_rpm = omega193 * 60.0 / (2.0 * PI)
            omega_hss_rpm = abs(omega_lss) * GBRatio * 60.0 / (2.0 * PI)
            pitch1_deg = math.degrees(last_pitch_cmds[0])

            gen_torque_lss = 0.0
            elec_power = 0.0
            if Servo:
                try:
                    dt_force = ops.eleResponse(190193, 'localForce')   # 获取局部力/矩
                    if dt_force and len(dt_force) >= 6:
                        gen_torque_lss = abs(dt_force[3])   # 索引3对应 Mx（扭转方向）
                    else:
                        gen_torque_lss = 0.0
                    elec_power = gen_torque_lss * abs(omega_lss)
                except:
                    gen_torque_lss = 0.0
                    elec_power = 0.0

            torqueCtrlFile.write(
                "%.6f %.6f %.6f %.6f %.6e %.6e\n"
                % (t_current, omega_lss_rpm, omega_hss_rpm, pitch1_deg, gen_torque_lss, elec_power)
            )
            startAssistFile.write(
                "%.6f %s %.6f %.6f %.6e %.6e\n"
                % (t_current, assist_state, omega193_rpm, omega_lss_rpm, assist_torque, START_TORQUE_LIMIT)
            )


            step_idx += 1
            progress_steps = int(t_current / DT)
            pbar.n = min(progress_steps, NSTEPS)
            pbar.refresh()

# ---------- 后处理：提取最大转角及其对应内力 ----------
if step_counter > 0:
    valid_ry = node1_ry_array[0, :step_counter]
    max_abs_idx = np.argmax(np.abs(valid_ry))
    max_abs_value = np.abs(valid_ry[max_abs_idx])
    max_actual_value = valid_ry[max_abs_idx]
    
    print(f"\n节点1最大转角（绝对值）: {max_abs_value:.6e} rad")
    print(f"对应实际转角值: {max_actual_value:.6e} rad")
    print(f"发生时间步索引: {max_abs_idx} (时间 = {max_abs_idx * DT:.3f} s)")

    # 提取该时刻所有优化立柱的内力 (12×num_units)
    forces_at_max = ele_forces_array[max_abs_idx, :, :]  # 形状 (12, num_units)
    print("\n该时刻各优化立柱的内力 (12分量 × 单元):")
    print(forces_at_max)

    # 保存到文件
    np.savetxt(out_path("max_force_matrix.txt"), forces_at_max, 
               header=f"Max force at time {max_abs_idx*DT:.3f}s, unit count = {num_units}", fmt='%.6e')
else:
    print("警告：未记录到任何数据。")
# ------------------------------------------------------

clear_start_assist_load()
ops.remove("recorders")
build_standard_response_outputs(OUT_DIR, num_lines=12)
print("Dynamic analysis done. AeroLoad + ServoLoad + HydroLoad coupled.")
# endregion
# =============================================================================
# region 10. 自动后处理：应力分析与强度利用率 (UC) 计算
# =============================================================================
# ---------- 后处理：提取最大转角及其对应内力 ----------
if step_counter > 0:
    valid_ry = node1_ry_array[0, :step_counter]
    max_abs_idx = np.argmax(np.abs(valid_ry))
    max_abs_value = np.abs(valid_ry[max_abs_idx])
    max_actual_value = valid_ry[max_abs_idx]
    
    print(f"\n节点1最大转角（绝对值）: {max_abs_value:.6e} rad")
    print(f"对应实际转角值: {max_actual_value:.6e} rad")
    print(f"发生时间步索引: {max_abs_idx} (时间 = {max_abs_idx * DT:.3f} s)")

    # 提取该时刻所有优化立柱的内力 (12×num_units)
    forces_at_max = ele_forces_array[max_abs_idx, :, :]  # 形状 (12, num_units)
    print("\n该时刻各优化立柱的内力 (12分量 × 单元):")
    print(forces_at_max)

    # 保存到文件
    np.savetxt(out_path("max_force_matrix.txt"), forces_at_max, 
               header=f"Max force at time {max_abs_idx*DT:.3f}s, unit count = {num_units}", fmt='%.6e')

    # =========================================================================
    # 【核心修改】：在这里直接定义并强制调用 UC 计算函数，绝不拖延到脚本最后！
    # =========================================================================
    def evaluate_column_stresses_instant(foundation_data, forces_matrix, Fy=355e6):
        print("\n" + "="*70)
        print("【立柱截面极限应力与强度利用率 (Unity Check) 报告】")
        print("="*70)
        
        T_wall = foundation_data["wall_thickness"]
        opt_legs = [ele for ele in foundation_data["elements"] if ele["type"] == "optimized_leg"]
        
        print(f"{'立柱 ID':<8} | {'外径 D (m)':<10} | {'最大拉应力 (MPa)':<15} | {'最大压应力 (MPa)':<15} | {'UC':<8}")
        print("-" * 70)
        
        uc_max_global = 0.0
        for i, ele in enumerate(opt_legs):
            ele_id = ele["id"]
            D_leg = ele["D"]
            
            A = np.pi * T_wall * (D_leg - T_wall)
            I = np.pi * (D_leg**4 - (D_leg - 2*T_wall)**4) / 64.
            W = I / (D_leg / 2.0)
            
            forces = forces_matrix[:, i]
            if np.isnan(forces).any() or np.isinf(forces).any():
                print(f"Ele {ele_id:<4} | {D_leg:<10.3f} | {'NaN':<15} | {'NaN':<15} | {'NaN':<8}")
                continue
                
            P1, My1, Mz1 = forces[0], forces[4], forces[5]
            P2, My2, Mz2 = forces[6], forces[10], forces[11]
            
            # 端点 1 应力
            sigma_a1 = -P1 / A 
            sigma_b1 = np.sqrt(My1**2 + Mz1**2) / W
            sigma_max1, sigma_min1 = sigma_a1 + sigma_b1, sigma_a1 - sigma_b1
            
            # 端点 2 应力
            sigma_a2 = P2 / A 
            sigma_b2 = np.sqrt(My2**2 + Mz2**2) / W
            sigma_max2, sigma_min2 = sigma_a2 + sigma_b2, sigma_a2 - sigma_b2
            
            max_tensile = max(sigma_max1, sigma_max2, 0.0)      
            max_compressive = min(sigma_min1, sigma_min2, 0.0)  
                
            abs_max_stress = max(abs(max_tensile), abs(max_compressive))
            uc = abs_max_stress / Fy
            uc_max_global = max(uc_max_global, uc)
            
            print(f"Ele {ele_id:<4} | {D_leg:<10.3f} | {max_tensile/1e6:<15.2f} | {max_compressive/1e6:<15.2f} | {uc:<8.3f}")
            
        print("-" * 70)
        print(f"最大强度利用率 (全局 UC_max): {uc_max_global:.3f}")
        if uc_max_global <= 1.0:
            print(">>> ✅ 结构强度校验通过 (UC <= 1.0)，满足船级社规范要求！")
        else:
            print(">>> ❌ 结构强度校验未通过 (UC > 1.0)！建议增加壁厚或优化结构。")
        print("="*70)

    # 强制执行计算！如果用的是更高强度的钢(如Q460)，把 355e6 改成 460e6
    try:
        evaluate_column_stresses_instant(foundation_data, forces_at_max, Fy=355e6)
    except Exception as e:
        print(f"\n[ERROR] UC 计算执行失败，原因: {e}")
    # =========================================================================

else:
    print("警告：未记录到任何数据。")
# ------------------------------------------------------

# (以下保留原代码的文件生成等收尾工作)
clear_start_assist_load()
try:
    ops.remove("recorders")
    build_standard_response_outputs(OUT_DIR, num_lines=12)
except Exception as e:
    print(f"\n[WARNING] 收尾日志文件处理报错 (UC已提前计算完成): {e}")

print("Dynamic analysis done. AeroLoad + ServoLoad + HydroLoad coupled.")