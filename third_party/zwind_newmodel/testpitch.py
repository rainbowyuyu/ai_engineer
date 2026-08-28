# endregion
# -*- coding: utf-8 -*-
# 自动化六自由度自由衰减测试套件 (已修复附加质量、PRP、重力加速度及压载水)

import numpy as np
import math as m
import time
import math
import sys
import os
import subprocess
from tqdm import tqdm
import json
from scipy.signal import find_peaks

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

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

import opensees as ops
import opstool as opst
import opstool.vis.pyvista as opsvis

OUT_DIR = os.path.join(current_dir, "OPSout")
os.makedirs(OUT_DIR, exist_ok=True)

def out_path(name: str) -> str:
    return os.path.join(OUT_DIR, name)

os.system("cls")
# endregion

def load_foundation_from_json(json_path):
    """读取优化几何 JSON，构建节点、单元（不加顶部刚性连接）"""
    import math
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    scale = 0.001  # mm → m
    nodes = {}
    elements = []
    mooring_nodes = []
    opt_ele_tags = []

    opt_info = data.get("optimization_info", {})
    wall_thickness = opt_info.get("wall_thickness_m", 0.06)

    hub = data["beso7_method1_topology_reconstructed"]["hub_top_plate"]
    nodes[1] = (hub["center_xy_mm"][0]*scale,
                hub["center_xy_mm"][1]*scale,
                hub["z_top_mm"]*scale)

    ele_id = 101

    fairlead_avg = {
        1: (-61.6, 0.0, 12.0),
        2: (30.8, 53.4, 12.0),
        3: (30.9, -53.4, 12.0),
    }

    legs_outer = data["beso3_reference_from_fcstd"]["edge_columns_nondesign"]
    for i, leg in enumerate(legs_outer):
        leg_id = i + 1
        leg_open = i + 4
        x_bot = leg["center_xy_mm"][0] * scale
        y_bot = leg["center_xy_mm"][1] * scale
        z_bot = leg["z_bottom_mm"] * scale
        x_top = leg["top_center_xy_mm"][0] * scale
        y_top = leg["top_center_xy_mm"][1] * scale
        z_top = leg["z_top_mm"] * scale

        top_nid = 10*leg_open + 1
        bot_nid = 10*leg_open + 2
        nodes[top_nid] = (x_top, y_top, z_top)
        nodes[bot_nid] = (x_bot, y_bot, z_bot)

        dia_m = leg["diameter_mm"] * scale
        elements.append({"id": ele_id, "n1": top_nid, "n2": bot_nid, "type": "optimized_leg", "D": dia_m})
        opt_ele_tags.append(ele_id)
        ele_id += 1
        mooring_nodes.append(top_nid)

    legs_inner = data["beso7_method1_topology_reconstructed"]["legs"]
    for i, leg in enumerate(legs_inner):
        bot_nid = 10*(i+4) + 2
        dia_m = leg["diameter_mm"] * scale
        elements.append({"id": ele_id, "n1": 1, "n2": bot_nid, "type": "optimized_leg", "D": dia_m})
        opt_ele_tags.append(ele_id)
        ele_id += 1

    angles = []
    for leg_id in [1, 2, 3]:
        top_nid = 10*(leg_id+3) + 1
        bot_nid = 10*(leg_id+3) + 2
        x_bot, y_bot, _ = nodes[bot_nid]
        x_top, y_top, _ = nodes[top_nid]
        x_fair, y_fair, _ = fairlead_avg[leg_id]

        angle_orig = math.atan2(y_top - y_bot, x_top - x_bot)
        angle_target = math.atan2(y_fair - y_bot, x_fair - x_bot)
        delta = angle_target - angle_orig
        delta = math.atan2(math.sin(delta), math.cos(delta))
        angles.append(delta)

    avg_delta = sum(angles) / len(angles)
    print(f"[INFO] 各立柱旋转角: {[math.degrees(a) for a in angles]}，平均: {math.degrees(avg_delta):.2f}°")

    cos_a = math.cos(avg_delta)
    sin_a = math.sin(avg_delta)
    rotated_nodes = {}
    for nid, (x, y, z) in nodes.items():
        x_new = x * cos_a - y * sin_a
        y_new = x * sin_a + y * cos_a
        rotated_nodes[nid] = (x_new, y_new, z)
    nodes = rotated_nodes

    return {
        "nodes": nodes,
        "elements": elements,
        "mooring_nodes": mooring_nodes,
        "interface_node": 1,
        "opt_ele_tags": opt_ele_tags,
        "wall_thickness": wall_thickness
    }

def find_closest_node(target_coords, node_dict):
    min_dist = float('inf')
    closest_id = None
    for nid, coords in node_dict.items():
        dist = np.linalg.norm(np.array(coords) - np.array(target_coords))
        if dist < min_dist:
            min_dist = dist
            closest_id = nid
    return closest_id
# endregion


if __name__ == "__main__":
    DOF_LABELS = {1: "Surge", 2: "Sway", 3: "Heave", 4: "Roll", 5: "Pitch", 6: "Yaw"}
    
    test_plan = {
        1: {"amp": 3.0e6,  "freq": 0.008, "excite": 150.0},
        2: {"amp": 3.0e6,  "freq": 0.008, "excite": 150.0},
        3: {"amp": 5.0e6,  "freq": 0.05,  "excite": 60.0},  
        4: {"amp": -1.0e8, "freq": 0.03,  "excite": 80.0},  
        5: {"amp": -1.0e8, "freq": 0.03,  "excite": 80.0},  
        6: {"amp": 2.0e8,  "freq": 0.01,  "excite": 120.0}, 
    }
    TOTAL_SIM_TIME = 300.0  

    # =========================================================================
    # 【主进程】负责循环派发任务、读取数据、FFT分析出图
    # =========================================================================
    if len(sys.argv) == 1:
        results = {}
        for dof in [1, 2, 3, 4, 5, 6]:
            print(f"\n{'='*70}\n🚀 派发独立子进程：测试 {DOF_LABELS[dof]} ({dof}-DOF)...\n{'='*70}")
            subprocess.run([sys.executable, __file__, f"--dof={dof}"])

            disp_file = out_path(f"platform_disp_DOF{dof}.out")
            if not os.path.exists(disp_file):
                results[DOF_LABELS[dof]] = {"Tn_time": np.nan, "fn_fft": np.nan, "Tn_fft": np.nan}
                continue
                
            data = np.loadtxt(disp_file)
            time_arr, disp_arr = data[:, 0], data[:, dof]  
            
            cfg = test_plan[dof]
            decay_mask = time_arr > (cfg["excite"] + 10.0)
            t_decay, d_decay = time_arr[decay_mask], disp_arr[decay_mask]
            
            if len(t_decay) < 100:
                results[DOF_LABELS[dof]] = {"Tn_time": np.nan, "fn_fft": np.nan, "Tn_fft": np.nan}
                continue
                
            d_decay_centered = d_decay - np.mean(d_decay)
            signal_for_peaks = -d_decay_centered if (np.mean(d_decay[:100]) < 0) else d_decay_centered
            peaks, _ = find_peaks(signal_for_peaks, distance=100, prominence=abs(np.max(signal_for_peaks)*0.05))
            time_period = np.mean(np.diff(t_decay[peaks])) if len(peaks) >= 2 else np.nan

            N, dt = len(d_decay_centered), np.mean(np.diff(t_decay))
            yf = np.fft.fft(d_decay_centered)
            xf = np.fft.fftfreq(N, d=dt)[:N//2]
            amp = 2.0 / N * np.abs(yf[0:N//2])
            
            max_amp_idx = np.argmax(amp[1:]) + 1  
            fft_fn = xf[max_amp_idx]
            fft_Tn = 1.0 / fft_fn if fft_fn > 0 else np.nan

            results[DOF_LABELS[dof]] = {"Tn_time": time_period, "fn_fft": fft_fn, "Tn_fft": fft_Tn}
            
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))
            ax1.plot(t_decay, d_decay, color='#1f77b4', linewidth=1.5, label=f"Time Response")
            if len(peaks) > 0: ax1.plot(t_decay[peaks], d_decay[peaks], "ro", markersize=5, label="Detected Peaks")
            ax1.set_title(f"{DOF_LABELS[dof]} Time Domain (Tn = {time_period:.2f} s)", fontweight='bold')
            ax1.set_xlabel("Time (s)"); ax1.set_ylabel("Response")
            ax1.grid(True, linestyle='--', alpha=0.6); ax1.legend()

            ax2.plot(xf, amp, color='#ff7f0e', linewidth=1.5, label="FFT Amplitude")
            ax2.plot(fft_fn, amp[max_amp_idx], "bo", markersize=6, label=f"Peak: {fft_fn:.4f} Hz")
            ax2.set_title(f"{DOF_LABELS[dof]} Frequency Domain (fn = {fft_fn:.4f} Hz)", fontweight='bold')
            ax2.set_xlabel("Frequency (Hz)"); ax2.set_ylabel("Amplitude")
            ax2.set_xlim(0, max(0.1, fft_fn * 4) if not np.isnan(fft_fn) else 0.5)
            ax2.grid(True, linestyle='--', alpha=0.6); ax2.legend()
            
            plt.tight_layout()
            plt.savefig(out_path(f"{DOF_LABELS[dof]}_Time_Freq_Decay.png"), dpi=300)
            plt.close()

        print("\n\n" + "="*80)
        print(f"| {'自由度 (DOF)':<12} | {'时域周期 Tn (s)':<15} | {'FFT 主频 fn (Hz)':<15} | {'FFT 倒推周期 Tn (s)':<18} |")
        print("| " + "-"*12 + " | " + "-"*17 + " | " + "-"*18 + " | " + "-"*19 + " |")
        for name, res in results.items():
            if np.isnan(res["Tn_time"]) and np.isnan(res["fn_fft"]):
                print(f"| {name:<14} | {'数据异常':<19} | {'数据异常':<20} | {'数据异常':<21} |")
            else:
                print(f"| {name:<14} | {res['Tn_time']:<20.2f} | {res['fn_fft']:<19.4f} | {res['Tn_fft']:<20.2f} |")
        print("="*80)
        sys.exit(0)

    # =========================================================================
    # 【子进程】物理建模
    # =========================================================================
    passed_dof = int(sys.argv[1].split("=")[1])
    target_dofs = [passed_dof]

    for target_dof in target_dofs:
        print(f"\n{'#'*60}\n🚀 开始物理仿真 {DOF_LABELS[target_dof]} ({target_dof}-DOF)\n{'#'*60}")
        cfg = test_plan[target_dof]

        DT = 0.01  
        TMAX = TOTAL_SIM_TIME
        NSTEPS = int(TMAX / DT)
        PI = math.pi
        G_ACC = 9.8  # 统一重力加速度

        Aero  = False
        Servo = False
        Hydro = True  

        ENABLE_DECAY_TEST = True
        DECAY_MONITOR_DOF = target_dof
        DECAY_AMP = cfg["amp"]
        DECAY_FREQ_HZ = cfg["freq"]
        DECAY_EXCITE_DURATION = cfg["excite"]
        DECAY_UNLOAD_RATIO = 0.05
        DECAY_PATTERN_TAG = 3001
        DECAY_TS_TAG = 3001
        DECAY_OMEGA = 2.0 * PI * DECAY_FREQ_HZ

        GBRatio = 74.627
        GenIner = 13000.0
        GenIner_LSS = GenIner * (GBRatio ** 2)
        DTTorSpr = 1.21e10
        DTTorDmp = 1.255e7
        HubMass = 130000.0
        HubIner = 934261.0
        Rated_Power = 20.0e6
        Rated_Speed_LSS = 7.56 * (2.0 * PI / 60.0)
        Rated_Speed_HSS = Rated_Speed_LSS * GBRatio
        Rated_Torque_LSS = Rated_Power / Rated_Speed_LSS / 0.85172 

        PROXY_NODES = [901, 902, 903]
        GEN_NODE_TAG = 194

        ENABLE_START_ASSIST = False  
        ENABLE_REGIONAL_DAMPING = True

        DAMP_FLOAT_ZETA = 0.02
        DAMP_FLOAT_W1 = 0.02
        DAMP_FLOAT_W2 = 0.50
        DAMP_TOWER_ZETA = 0.01
        DAMP_TOWER_W1 = 0.20
        DAMP_TOWER_W2 = 3.00
        DAMP_RNA_ALPHA_M = 1.0e-4
        DAMP_RNA_BETA_K = 1.0e-6

        def setup_pitch_proxy(proxy_tag, anchor_tag, mat_tag, elem_tag, x, y, z):
            ops.node(proxy_tag, x, y, z)
            ops.fix(proxy_tag, 1, 1, 1, 0, 1, 1)
            ops.mass(proxy_tag, 0.0, 0.0, 0.0, 1.0e-13, 0.0, 0.0)
            ops.uniaxialMaterial("Elastic", mat_tag, 1.0)
            ops.node(anchor_tag, x, y, z)
            ops.fix(anchor_tag, 1, 1, 1, 1, 1, 1)
            ops.element("zeroLength", elem_tag, anchor_tag, proxy_tag, "-mat", mat_tag, "-dir", 4)

        def clamp_val(v, lo, hi):
            if v < lo: return lo
            if v > hi: return hi
            return v

        ops.wipe()
        ops.model("BasicBuilder", "-ndm", 3, "-ndf", 6)

        ops.recorder("Element", "-file",  out_path("b1_force.out"), "-time", "-ele", 191601, "force")
        ops.recorder("Node", "-file", out_path("191_disp.out"), "-time", "-node", 191, "-dof", 1, 2, 3, 4, 5, 6,"disp")
        ops.recorder("Node", "-file", out_path("601_disp.out"), "-time", "-node", 601, "-dof", 1, 2, 3, 4, 5, 6,"disp")
        ops.recorder("Node", "-file", out_path("658_disp.out"), "-time", "-node", 658, "-dof", 1, 2, 3, 4, 5, 6,"disp")
        ops.recorder("Node", "-file", out_path("601vel.out"), "-time", "-node", 601, "-dof", 1, 2, 3, 4, 5, 6,"vel")
        ops.recorder("Node", "-file", out_path("801disp.out"), "-time", "-node", 801, "-dof", 1, 2, 3, 4, 5, 6,"disp")
        ops.recorder("Node", "-file", out_path("gen194_vel.out"), "-time", "-node", 194, "-dof", 4, "vel")
        ops.recorder("Node", "-file", out_path("191_vel.out"), "-time", "-node", 191, "-dof", 4, "vel")
        ops.recorder("Node", "-file", out_path("901_disp.out"), "-time", "-node", 901, "-dof", 4, "disp")
        ops.recorder("Node", "-file", out_path(f"platform_disp_DOF{target_dof}.out"), "-time", "-node", 1, "-dof", 1, 2, 3, 4, 5, 6, "disp")
        ops.recorder("Node", "-file", out_path("platform_accel.out"), "-time", "-node", 1, "-dof", 1, 2, 3, 4, 5, 6, "accel")
        ops.recorder("Node", "-file", out_path("tower_top_accel.out"), "-time", "-node", 144, "-dof", 1, 2, 3, 4, 5, 6, "accel")
        ops.recorder("Node", "-file", out_path("tower_top_disp.out"), "-time", "-node", 144, "-dof", 1, 2, 3, 4, 5, 6, "disp")
        ops.recorder("Element", "-file", out_path("tower_base_force.out"), "-time", "-ele", 2001, "globalForce")
        
        top_moor_eles = [100000*j + 38 for j in range(1, 13)]
        ops.recorder("Element", "-file", out_path("mooring_tension.out"), "-time", "-ele", *top_moor_eles, "globalForce")
        bot_moor_eles = [100000*j + 1 for j in range(1, 13)]
        ops.recorder("Element", "-file", out_path("mooring_anchor_tension.out"), "-time", "-ele", *bot_moor_eles, "globalForce")

        JSON_FILE = "optimized_geometry30.json"
        if not os.path.exists(JSON_FILE):
            raise FileNotFoundError(f"找不到 {JSON_FILE}，请检查路径。")
        foundation_data = load_foundation_from_json(JSON_FILE)

        T_wall = foundation_data["wall_thickness"]
        FE = 2.06e11                                   
        FG = FE / (2 * (1 + 0.3))                      

        ops.geomTransf("PDelta", 1, 0, 0, 1)
        ops.geomTransf("PDelta", 2, 0, 1, 0)
        ops.geomTransf("Linear", 3, 0, 0, 1)
        ops.geomTransf("Linear", 99, 1.0, 1.0, 1.0) 

        for nid, coords in foundation_data["nodes"].items():
            ops.node(nid, *coords)
            
        # 修正：直接使用节点 1 作为 PRP
        PRP_NODE = 1
        print("[INFO] 直接使用节点 1 作为水动力参考点 PRP")
        if ENABLE_DECAY_TEST:
            DECAY_MONITOR_NODE = PRP_NODE
            
        for ele in foundation_data["elements"]:
            n1, n2 = ele["n1"], ele["n2"]
            if ele["type"] == "optimized_leg":
                D_leg = ele["D"]  
                FA_leg = np.pi * T_wall * (D_leg - T_wall)
                FIy_leg = np.pi * (D_leg**4 - (D_leg - 2*T_wall)**4) / 64.0
                FIz_leg = FIy_leg
                FJ_leg = 2 * FIy_leg
                ops.element("elasticBeamColumn", ele["id"], n1, n2, FA_leg, FE, FG, FJ_leg, FIy_leg, FIz_leg, 2)
            elif ele["type"] == "rigid_link":
                ops.rigidLink("beam", n1, n2)

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
        hydro_node_mass = {nid: 0.0 for nid in foundation_data["nodes"]}
        hydro_node_I = {nid: np.zeros((3, 3)) for nid in foundation_data["nodes"]}

        for ele in foundation_data["elements"]:
            if ele["type"] == "optimized_leg":
                n1, n2 = ele["n1"], ele["n2"]
                L = np.linalg.norm(np.array(foundation_data["nodes"][ele["n2"]]) - np.array(foundation_data["nodes"][ele["n1"]]))
                D_leg = ele["D"]
                FA_leg = np.pi * T_wall * (D_leg - T_wall)
                FIy_leg = np.pi * (D_leg**4 - (D_leg - 2*T_wall)**4) / 64.0
                FJ_leg = 2 * FIy_leg
                hydro_mass_local(n1, n2, FA_leg, HY_RHO_STEEL, FJ_leg, L, hydro_node_mass, hydro_node_I)

        DISP_VOL = 23718.8  
        RHO_WATER = 1025.0
        TARGET_TOTAL_MASS = DISP_VOL * RHO_WATER  

        # 修正：压载水对齐到 0820 代码
        target_platform_mass = TARGET_TOTAL_MASS - 3.1e6
        current_steel_mass = sum(hydro_node_mass.values())
        total_ballast = target_platform_mass - current_steel_mass

        ballast_per_leg = total_ballast / 3.0
        for leg_id in [4, 5, 6]:
            bot_nid = 10 * leg_id + 2
            hydro_node_mass[bot_nid] += ballast_per_leg

        # 修正：读取 WAMIT 附加质量
        WAMIT_ULEN = 1.0
        WAMIT_ADDED_MASS_FILE = os.path.join(current_dir, "hydrodynNbody", "hydrodata", "beso7_nemoh_case_001.1")

        def read_wamit_infinite_frequency_diagonal(path):
            diagonal = np.full(6, np.nan)
            try:
                with open(path, "r", encoding="utf-8") as wamit_file:
                    for raw_line in wamit_file:
                        fields = raw_line.split()
                        if len(fields) < 4: continue
                        try:
                            omega, row, col, value = float(fields[0]), int(fields[1]), int(fields[2]), float(fields[3])
                        except ValueError: continue
                        if np.isclose(omega, -1.0) and row == col and 1 <= row <= 6:
                            diagonal[row - 1] = abs(value)
            except Exception as e:
                print(f"读取 WAMIT 文件失败，使用零附加质量: {e}")
                diagonal = np.zeros(6)
            if np.isnan(diagonal).any():
                diagonal = np.nan_to_num(diagonal)
            return diagonal

        WAMIT_ADDED_MASS_DIAG = np.abs(read_wamit_infinite_frequency_diagonal(WAMIT_ADDED_MASS_FILE)) * np.array([
            RHO_WATER * WAMIT_ULEN**3, RHO_WATER * WAMIT_ULEN**3, RHO_WATER * WAMIT_ULEN**3,
            RHO_WATER * WAMIT_ULEN**5, RHO_WATER * WAMIT_ULEN**5, RHO_WATER * WAMIT_ULEN**5,
        ])

        total_mass = 0
        for nid in foundation_data["nodes"]:
            m_struct = hydro_node_mass.get(nid, 0.0)
            total_mass += m_struct
            In = hydro_node_I.get(nid, np.zeros((3, 3)))
            
            if nid == foundation_data["interface_node"]:
                m_add, I_add = WAMIT_ADDED_MASS_DIAG[:3], WAMIT_ADDED_MASS_DIAG[3:]
            else:
                m_add, I_add = np.zeros(3), np.zeros(3)
                
            ops.mass(nid, 
                     m_struct + m_add[0], m_struct + m_add[1], m_struct + m_add[2], 
                     In[0, 0] + I_add[0], In[1, 1] + I_add[1], In[2, 2] + I_add[2])

        total = total_mass

        # =====================================================================
        # region 4. Moor 系泊结构
        # =====================================================================
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
            x_coords = locals()[f"x_coords_{base_id}"]
            y_coords = locals()[f"y_coords_{base_id}"]
            z_coords = locals()[f"z_coords_{base_id}"]
            for i in range(39):
                nid = base_id + i + 1
                ops.node(nid, x_coords[i], y_coords[i], z_coords[i])

        series_starts = [1001, 2001, 3001, 4001, 5001, 6001, 7001, 8001, 9001, 10001, 11001, 12001]
        load_value1 = 8000
        load_value2 = 13000
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
                else:
                    ops.mass(nid, load_value3, load_value3, load_value3, 0, 0, 0)
                    total += load_value3

        for base_id in base_ids:
            x_coords = locals()[f"x_coords_{base_id}"]
            y_coords = locals()[f"y_coords_{base_id}"]
            z_coords = locals()[f"z_coords_{base_id}"]
            for i in range(1, 40):
                node_id = 10 * base_id + i
                fixnode = node_id + 9000
                stiffnessnode = node_id + 900
                ops.node(fixnode, x_coords[i - 1], y_coords[i - 1], z_coords[i - 1])
                ops.fix(fixnode, 1, 1, 1, 1, 1, 1)  
                ops.uniaxialMaterial("ElasticPPGap", stiffnessnode, 3e6, 3e11, z_coords[i - 1] + 51, 0)
                ops.element("zeroLength", 10000 * base_id + i, base_id + i, fixnode, "-mat", stiffnessnode, "-dir", 3)

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

        MOOR_SEC_A = 8901  
        MOOR_SEC_B = 8902
        ops.section("Aggregator", MOOR_SEC_A, 2001, "P", 2002, "Mz", 2003, "My", 2004, "Vz", 2005, "Vz", 2006, "T")
        ops.section("Aggregator", MOOR_SEC_B, 2001, "P", 2002, "Mz", 2003, "My", 2004, "Vz", 2005, "Vz", 2006, "T")

        w1 = [0.424 * 6.28, 6.28 / 28.0]
        zeta1 = 0.05
        a_ray = 2.0 * (w1[0] * w1[1]) / (w1[0] + w1[1])
        b_ray = 2.0 / (w1[0] + w1[1])

        mn = foundation_data["mooring_nodes"]
        for j in range(1, 13):
            node_id = 1000 * j 
            element_id = 100000 * j 
            group_idx = (j - 1) // 4
            mooring_node = mn[group_idx % len(mn)]
            ops.equalDOF(mooring_node, node_id + 39, 1, 2, 3)
            for i in range(1, 39):
                ops.element("elasticBeamColumn", element_id + i, node_id + i, node_id + i + 1, MOOR_SEC_B, 1)
                ops.region(1, "-ele", element_id + i, "-rayleigh", a_ray * zeta1, b_ray * zeta1, 0, 0)

        for end_id in [1001, 2001, 3001, 4001, 5001, 6001, 7001, 8001, 9001, 10001, 11001, 12001]:
            ops.fix(end_id, 1, 1, 1, 0, 0, 0)  

        # =====================================================================
        # region 5. 塔架 + RNA
        # =====================================================================
        interface_nid = foundation_data["interface_node"]
        z_offset = foundation_data["nodes"][interface_nid][2] 

        Numtower = 64
        Height = 154.9 - z_offset

        TowerHtFract_str = "0.00000 0.00201 0.02246 0.04294 0.06342 0.08391 0.10439 0.12487 0.14535 0.16591 0.16796 0.17001 0.18756 0.20512 0.22268 0.24023 0.25779 0.27535 0.29290 0.31083 0.32875 0.34704 0.36533 0.38361 0.40190 0.42012 0.42195 0.42377 0.44236 0.46094 0.47952 0.49817 0.51683 0.53566 0.55450 0.57352 0.59254 0.61156 0.63072 0.64989 0.66920 0.68859 0.69027 0.69195 0.71024 0.72853 0.74682 0.76511 0.78339 0.80168 0.81997 0.83826 0.85655 0.87484 0.89312 0.91214 0.93116 0.95018 0.96920 0.97074 0.97228 0.98888 0.99517 0.99663 1.00000"
        TowerMass_str = "2.36733E+05 2.13075E+04 2.13075E+04 2.07157E+04 1.83482E+04 1.70171E+04 1.64252E+04 1.61293E+04 1.58333E+04 1.58333E+04 1.21862E+05 1.57496E+04 1.49995E+04 1.45507E+04 1.41081E+04 1.38128E+04 1.33811E+04 1.29557E+04 1.25349E+04 1.22533E+04 1.19744E+04 1.16965E+04 1.14218E+04 1.11510E+04 1.08828E+04 1.08134E+04 9.99814E+04 1.07418E+04 1.03527E+04 9.97016E+03 9.71324E+03 9.46015E+03 9.20942E+03 8.96156E+03 8.71659E+03 8.47359E+03 8.12514E+03 7.89067E+03 7.65962E+03 7.43066E+03 7.10224E+03 7.04268E+03 7.62340E+04 6.98652E+03 6.57534E+03 6.46832E+03 6.16814E+03 5.96961E+03 5.68118E+03 5.49039E+03 5.30322E+03 5.03102E+03 4.85161E+03 4.76080E+03 4.58457E+03 4.32833E+03 4.15914E+03 4.69765E+03 4.64697E+03 5.51041E+04 7.74494E+03 1.08429E+04 1.08429E+04 1.08429E+04 4.95647E+04"
        TowerFA_str = "1.0065E+13 1.0065E+13 1.0065E+13 9.7855E+12 8.6671E+12 8.0390E+12 7.7594E+12 7.6196E+12 7.4798E+12 7.4798E+12 7.4798E+12 7.3617E+12 6.8627E+12 6.5155E+12 6.1812E+12 5.9201E+12 5.6088E+12 5.3097E+12 5.0202E+12 4.7931E+12 4.5731E+12 4.3583E+12 4.1512E+12 3.9522E+12 3.7598E+12 3.6883E+12 3.6883E+12 3.6155E+12 3.3926E+12 3.1799E+12 3.0134E+12 2.8540E+12 2.7001E+12 2.5521E+12 2.4099E+12 2.2725E+12 2.1133E+12 1.9890E+12 1.8702E+12 1.7559E+12 1.6234E+12 1.5829E+12 1.5829E+12 1.5453E+12 1.4080E+12 1.3404E+12 1.2361E+12 1.1564E+12 1.0631E+12 9.9184E+11 9.2438E+11 8.4558E+11 7.8563E+11 7.4234E+11 6.8724E+11 6.2279E+11 5.7404E+11 6.2126E+11 6.0137E+11 6.0137E+11 1.0023E+12 1.4033E+12 1.4033E+12 1.4033E+12 1.4033E+12"
        TowerSS_str = TowerFA_str

        def _parse(s: str): return [float(x) for x in s.split()]

        TowerHtFract = _parse(TowerHtFract_str)
        TowerMass = _parse(TowerMass_str)
        TowerFA = _parse(TowerFA_str)
        TowerSS = _parse(TowerSS_str)

        E_tower = 2.1e11
        G_tower = 8.08e10
        rho_tower = 8500.0

        ops.geomTransf("PDelta", 950, 0, 1, 0)
        ops.geomTransf("Linear", 951, 0, 1, 0)

        for i in range(Numtower + 1):
            z = TowerHtFract[i] * Height + z_offset
            ops.node(80 + i, 0.0, 0.0, z)

        ops.equalDOF(interface_nid, 80, 1, 2, 3, 4, 5, 6)

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

        nacelle_z = Height + 1.75 + z_offset
        hub_x = -1.9
        hub_z = nacelle_z

        ops.node(190, 0.0, 0.0, nacelle_z)                 
        ops.node(194, 0.0, 0.0, nacelle_z)                 
        ops.node(193, 0.0, 0.0, nacelle_z)                 
        ops.node(191, hub_x, 0.0, hub_z)                   

        Arigid = 100.0
        Erigid = 1.0e11
        Grigid = 1.0e11
        Jrigid = 100.0
        Irigid = 100.0

        ops.geomTransf("Corotational", 952, 0, 1, 0)
        ops.geomTransf("Corotational", 953, 1, 0, 0)
        ops.geomTransf("Corotational", 954, 1, 0, 0)
        ops.geomTransf("Corotational", 955, 1, 0, 0)

        ops.element("elasticBeamColumn", 144190, 144, 190, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 950)

        ops.equalDOF(190, 194, 1, 2, 3, 5, 6)
        ops.uniaxialMaterial("Elastic", 999, 1.0)
        ops.element("zeroLength", 999999, 190, 194, "-mat", 999, "-dir", 4)

        ops.uniaxialMaterial("Elastic", 101, DTTorSpr)
        ops.uniaxialMaterial("Viscous", 102, DTTorDmp, 1.0)
        ops.uniaxialMaterial("Parallel", 103, 101, 102)
        ops.element("zeroLength", 190193, 194, 193, "-mat", 103, "-dir", 4)
        ops.equalDOF(190, 193, 1, 2, 3, 5, 6)

        ops.element("elasticBeamColumn", 193191, 193, 191, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 952)

        NacMass1 = 447000.0
        total += NacMass1 + HubMass
        ops.mass(190, NacMass1, NacMass1, NacMass1, 1e6, 1e6, 5311000.0)
        ops.mass(194, 0.0, 0.0, 0.0, GenIner_LSS, 0.0, 0.0)
        ops.mass(193, 0.0, 0.0, 0.0, 7.33e7, 0.0, 0.0)
        ops.mass(191, HubMass, HubMass, HubMass, HubIner, 1e7, 1e7)

        _pitch_proxy_cfg = [
            (901, 911, 911, 901911),
            (902, 912, 912, 902912),
            (903, 913, 913, 903913),
        ]
        for p_tag, a_tag, m_tag, e_tag in _pitch_proxy_cfg:
            setup_pitch_proxy(p_tag, a_tag, m_tag, e_tag, hub_x, 0.0, hub_z)

        ex0 = 5.0191
        ez0 = 1.912

        Bladelength_str = "0.0000 1.0001 2.0000 3.0000 5.5000 8.0000 10.5000 13.0000 15.5001 18.0001 20.5001 23.0001 25.4999 27.9999 30.4999 32.9999 35.5000 38.0000 40.5000 43.0000 45.5000 48.0000 50.5000 53.0000 55.5000 58.0000 60.5000 63.0000 65.5000 68.0000 70.5000 73.0000 75.5000 78.0000 80.5000 83.0000 85.5000 88.0000 90.5000 93.0000 95.5000 98.0001 100.5001 103.0001 105.5001 107.9999 110.4999 112.9999 115.4999 118.0000 120.5000 123.0000 125.5000 128.0000 129.5001 129.9999 130.5000 131.0000"
        Massblade_str = "16374.300 2475.250 1828.100 1727.750 1602.260 1566.230 1460.020 1320.830 1282.450 1159.130 1097.710 995.935 940.165 813.497 731.649 705.943 670.861 639.000 612.053 636.394 569.391 551.632 529.802 508.792 472.946 459.446 443.397 429.040 400.814 470.238 410.179 356.310 345.972 328.519 317.112 300.344 282.536 273.383 258.046 229.007 216.913 203.712 190.423 179.279 166.594 152.780 140.369 129.284 118.423 122.765 136.276 84.676 73.599 60.434 36.007 29.417 19.543 7.123"

        Bladelength = _parse(Bladelength_str)
        Massblade = _parse(Massblade_str)
        max_L = Bladelength[-1]       
        root_L = Bladelength[0]       

        m_blade_total = 0.0
        for i in range(1, len(Bladelength)):
            m_blade_total += (Bladelength[i] - Bladelength[i - 1]) * (Massblade[i - 1] + Massblade[i]) / 2.0

        gen3 = math.sqrt(3.0)

        ops.node(601, ex0, 0.0, Height + z_offset + ez0 + root_L)
        ops.node(701, ex0, gen3 / 2.0 * root_L, Height + z_offset + ez0 - 0.5 * root_L)
        ops.node(801, ex0, -gen3 / 2.0 * root_L, Height + z_offset + ez0 - 0.5 * root_L)
        ops.node(699, ex0, 0.0, Height + z_offset + ez0 + max_L)
        ops.node(799, ex0, gen3 / 2.0 * max_L, Height + z_offset + ez0 - 0.5 * max_L)
        ops.node(899, ex0, -gen3 / 2.0 * max_L, Height + z_offset + ez0 - 0.5 * max_L)

        ops.element("elasticBeamColumn", 191601, 191, 601, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 953)
        ops.element("elasticBeamColumn", 191701, 191, 701, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 954)
        ops.element("elasticBeamColumn", 191801, 191, 801, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 955)

        ops.element("elasticBeamColumn", 601699, 601, 699, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 953)
        ops.element("elasticBeamColumn", 701799, 701, 799, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 954)
        ops.element("elasticBeamColumn", 801899, 801, 899, Arigid, Erigid, Grigid, Jrigid, Irigid, Irigid, 955)

        m_half = m_blade_total / 2.0
        for root_node in [601, 701, 801]:
            ops.mass(root_node, m_half, m_half, m_half, m_half * 10, m_half * 10, m_half * 10)

        for tip_node in [699, 799, 899]:
            ops.mass(tip_node, m_half, m_half, m_half, m_half * 10, m_half * 10, m_half * 10)

        total += 3 * m_blade_total

        # =====================================================================
        # region 6. 重力静力平衡
        # =====================================================================
        fix_flags = [1, 1, 1, 1, 1, 1]
        fix_flags[target_dof - 1] = 0
        ops.fix(1, *fix_flags)
        ops.timeSeries("Constant", 1001)
        ops.pattern("Plain", 1001, 1001)
        
        # 修正：所有静态重力加载统一使用 G_ACC=9.8
        for nid, m_h in hydro_node_mass.items():
            if m_h > 0.0:
                ops.load(nid, 0, 0, -m_h * G_ACC, 0, 0, 0)

        ops.timeSeries("Constant", 1003)
        ops.pattern("Plain", 1003, 1003)
        for series in range(1, 13):
            base_id = series * 1000
            for i in range(1, 21): ops.load(base_id + i, 0, 0, -load_value1 * G_ACC, 0, 0, 0)
            for i in range(21, 29): ops.load(base_id + i, 0, 0, -load_value2 * G_ACC, 0, 0, 0)
            for i in range(29, 40): ops.load(base_id + i, 0, 0, -load_value3 * G_ACC, 0, 0, 0)

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

        ops.system("BandGeneral")
        ops.numberer("RCM")
        ops.constraints("Transformation")
        ops.integrator("LoadControl", 1.0)
        ops.test("NormDispIncr", 1.0e-4, 100, 0)
        ops.algorithm("Newton")
        ops.analysis("Static")
        ops.analyze(1)  
        ops.loadConst("-time", 0.0)

        # =====================================================================
        # region 7. HydroLoad + 衰减力载荷模式初始化
        # =====================================================================
        if Hydro:
            ops.pattern("HydroLoad", 400, "-driver", "hydrodynNbody/hd_driver.inp")
            ops.load(PRP_NODE, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "-pattern", 400)  
            ops.load(PRP_NODE, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-pattern", 400)  

        STAGE = "NORMAL_RUN"
        if ENABLE_DECAY_TEST:
            print(f">>> 衰减模式开启: 节点 {DECAY_MONITOR_NODE} [{DOF_LABELS.get(DECAY_MONITOR_DOF)}] "
                  f"AMP={DECAY_AMP:.3e}, Freq={DECAY_FREQ_HZ} Hz, 激励={DECAY_EXCITE_DURATION} s")
            ops.timeSeries("Constant", DECAY_TS_TAG)
            ops.pattern("Plain", DECAY_PATTERN_TAG, DECAY_TS_TAG)
            ops.load(DECAY_MONITOR_NODE, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            STAGE = "EXCITING"

        # =====================================================================
        # region 8. 阻尼
        # =====================================================================
        def rayleigh_ab(zeta, w1, w2):
            alpha = zeta * (2.0 * w1 * w2) / (w1 + w2)
            beta = zeta * 2.0 / (w1 + w2)
            return alpha, beta

        def apply_region_rayleigh(region_tag, ele_tags, alpha_m, beta_k, beta_k_init=0.0, beta_k_comm=0.0):
            ele_tags = [int(e) for e in ele_tags]
            if not ele_tags: return
            ops.region(int(region_tag), "-ele", *ele_tags, "-rayleigh", float(alpha_m), float(beta_k), float(beta_k_init), float(beta_k_comm))

        FLOAT_ELE_TAGS = [ele["id"] for ele in foundation_data["elements"] if ele["type"] == "optimized_leg"]
        TOWER_ELE_TAGS = list(range(2001, 2000 + Numtower + 1))
        RNA_RIGID_ELE_TAGS = [144190, 999999, 190193, 193191, 901911, 902912, 903913, 191601, 191701, 191801, 601699, 701799, 801899]

        if ENABLE_REGIONAL_DAMPING:
            float_alpha, float_beta = rayleigh_ab(DAMP_FLOAT_ZETA, DAMP_FLOAT_W1, DAMP_FLOAT_W2)
            tower_alpha, tower_beta = rayleigh_ab(DAMP_TOWER_ZETA, DAMP_TOWER_W1, DAMP_TOWER_W2)
            apply_region_rayleigh(9101, FLOAT_ELE_TAGS, float_alpha, float_beta, 0.0, 0.0)
            apply_region_rayleigh(9102, TOWER_ELE_TAGS, tower_alpha, tower_beta, 0.0, 0.0)
            apply_region_rayleigh(9103, RNA_RIGID_ELE_TAGS, DAMP_RNA_ALPHA_M, DAMP_RNA_BETA_K, 0.0, 0.0)
        else:
            ops.rayleigh(0.0, 0.0, 0.0, 0.0)

        # =====================================================================
        # region 9. Transient 求解器与动态捕获主循环
        # =====================================================================
        num_steps = NSTEPS
        num_units = len(foundation_data["opt_ele_tags"])
        node1_ry_array = np.zeros((1, num_steps))          
        ele_forces_array = np.zeros((num_steps, 12, num_units))  
        step_counter = 0

        def get_load_vector(dof, force_val):
            vec = [0.0] * 6
            if 1 <= dof <= 6:
                vec[dof - 1] = force_val
            return vec

        def remove_decay_load_pattern():
            try: ops.remove("loadPattern", DECAY_PATTERN_TAG)
            except: 
                try: ops.remove("pattern", DECAY_PATTERN_TAG)
                except: pass

        ops.wipeAnalysis()
        ops.system("SparseGEN")
        ops.numberer("RCM")
        ops.constraints("Transformation") 
        ops.integrator("Newmark", 0.5, 0.25)
        ops.algorithm("Newton") # 改回 Newton 以提速
        ops.test("NormDispIncr", 1.0e-3, 50, 0)
        ops.analysis("Transient")

        t_current = 0.0
        step_idx = 0

        with tqdm(total=NSTEPS, desc=f"DOF {target_dof} 分析进度", dynamic_ncols=True, leave=True) as pbar:
            while t_current < TMAX:
                if ENABLE_DECAY_TEST and STAGE == "EXCITING":
                    current_val = DECAY_AMP * math.sin(DECAY_OMEGA * t_current)
                    load_vec = get_load_vector(DECAY_MONITOR_DOF, current_val)
                    remove_decay_load_pattern()
                    ops.pattern("Plain", DECAY_PATTERN_TAG, DECAY_TS_TAG)
                    ops.load(DECAY_MONITOR_NODE, *load_vec)
                    
                    if (t_current >= DECAY_EXCITE_DURATION and abs(current_val) < abs(DECAY_AMP * DECAY_UNLOAD_RATIO)):
                        remove_decay_load_pattern()
                        STAGE = "DECAYING"
                        print(f"\n[{t_current:.2f}s] 能量注入完成，进入自由衰减状态！")

                ok = ops.analyze(1, DT)
                t_after = ops.getTime()

                if ok != 0:
                    print(f"\n[FATAL] analyze 失败 t={t_after:.4f}s")
                    break

                t_current = t_after
                ops.reactions()

                if step_counter < num_steps:
                    node1_ry = ops.nodeDisp(1, 5)
                    node1_ry_array[0, step_counter] = node1_ry
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

                step_idx += 1
                pbar.n = min(int(t_current / DT), NSTEPS)
                pbar.refresh()

        if ENABLE_DECAY_TEST:
            remove_decay_load_pattern()

        ops.wipe()