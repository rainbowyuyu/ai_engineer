"""
将 OC4 设计域体网格 INP 划分为 example_3 风格：``design_space``（可优化）与
``nondesign_space``（柱走廊附近单元，不参与 BESO 密度更新）。

划分依据：与 ``oc4.igs`` 中识别的主柱轴线（中心柱 + 三根外柱）的径向距离，
小于 ``band_scale * R_shaft`` 的体单元归入 nondesign_space。

另：在网格末尾追加最小 *STEP（底面 z 固定 + 顶区单点竖向力），便于 CalculiX/BESO 冒烟；
真实系泊/风载需按新节点号自行替换（与旧 BESO2-FEMMeshGmsh.inp 不兼容）。
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from backend.tools.oc4_design_domain_iges import (
    CylinderAxis,
    _extract_revolution_cylinders,
    _merge_parallel_axis_pairs,
    _pick_oc4_key_columns,
)

_ELEM_HEAD = re.compile(
    r"^\*Element\s*,\s*TYPE\s*=\s*(\w+)\s*,\s*ELSET\s*=\s*(\S+)",
    re.IGNORECASE,
)
_ELEM_HEAD_NO_ELSET = re.compile(r"^\*Element\s*,\s*TYPE\s*=\s*(\w+)\s*$", re.IGNORECASE)


def _vertical_columns_from_oc4_iges(src_iges: Path) -> list[CylinderAxis]:
    cyls = _extract_revolution_cylinders(src_iges)
    vertical = [c for c in cyls if abs(float(c.direction[2])) > 0.96]
    vertical = _merge_parallel_axis_pairs(vertical)
    vertical = [
        c
        for c in vertical
        if c.radius >= 1200.0
        and (c.length >= 5000.0 or (c.length >= 350.0 and c.radius >= 2600.0))
    ]
    if len(vertical) < 4:
        raise ValueError(f"从 {src_iges} 识别到的主立柱不足 4 根，无法划分柱走廊。")
    center_col, outer_cols, _, _ = _pick_oc4_key_columns(vertical)
    return [center_col, *outer_cols]


def _dist_point_to_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    lab2 = float(np.dot(ab, ab))
    if lab2 <= 1.0e-18:
        return float(np.linalg.norm(p - a))
    t = float(np.dot(p - a, ab) / lab2)
    t = max(0.0, min(1.0, t))
    q = a + t * ab
    return float(np.linalg.norm(p - q))


def _in_any_column_corridor(
    centroid: np.ndarray,
    cols: list[CylinderAxis],
    band_scale: float,
) -> bool:
    for c in cols:
        d = _dist_point_to_segment(centroid, np.asarray(c.p0, dtype=float), np.asarray(c.p1, dtype=float))
        if d < float(c.radius) * band_scale:
            return True
    return False


def _parse_nodes(lines: list[str]) -> dict[int, np.ndarray]:
    nodes: dict[int, np.ndarray] = {}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip().upper().startswith("*NODE"):
            i += 1
            while i < n and not lines[i].strip().startswith("*"):
                parts = [p.strip() for p in lines[i].split(",")]
                if len(parts) >= 4 and parts[0].isdigit():
                    nid = int(parts[0])
                    nodes[nid] = np.array([float(parts[1]), float(parts[2]), float(parts[3])], dtype=float)
                i += 1
            continue
        i += 1
    if not nodes:
        raise ValueError("INP 中未解析到任何 *NODE 数据")
    return nodes


def _parse_volume_elements(lines: list[str]) -> tuple[list[tuple[int, str, list[int]]], set[int]]:
    """
    返回 (体单元列表, 所有出现的体单元号集合)。
    体单元类型：C3D4, C3D10, C3D8, C3D8R 等（以 C3D 开头）。
    """
    out: list[tuple[int, str, list[int]]] = []
    all_ids: set[int] = set()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        m = _ELEM_HEAD.match(s)
        m2 = _ELEM_HEAD_NO_ELSET.match(s) if not m else None
        if not m and not m2:
            i += 1
            continue
        typ = (m.group(1) if m else m2.group(1)).upper()
        if not typ.startswith("C3D"):
            i += 1
            continue
        i += 1
        while i < n and not lines[i].strip().startswith("*"):
            parts = [p.strip() for p in lines[i].split(",")]
            if not parts or not parts[0].isdigit():
                i += 1
                continue
            eid = int(parts[0])
            nids = [int(x) for x in parts[1:] if x.isdigit()]
            use: list[int] | None = None
            if typ == "C3D4" and len(nids) >= 4:
                use = nids[:4]
            elif typ == "C3D10" and len(nids) >= 10:
                use = nids[:10]
            elif typ in {"C3D8", "C3D8R", "C3D8I"} and len(nids) >= 8:
                use = nids[:8]
            if use is not None:
                all_ids.add(eid)
                out.append((eid, typ, use))
            i += 1
        continue
    return out, all_ids


def _centroid(nodes: dict[int, np.ndarray], nids: list[int]) -> np.ndarray:
    pts = np.stack([nodes[i] for i in nids if i in nodes], axis=0)
    return np.mean(pts, axis=0)


def _format_elset_block(name: str, ids: list[int], per_line: int = 16) -> list[str]:
    lines = [f"*ELSET, ELSET={name}"]
    for i in range(0, len(ids), per_line):
        chunk = ids[i : i + per_line]
        lines.append(", ".join(str(x) for x in chunk) + ",")
    return lines


def summarize_mesh_for_loads(mesh_inp: Path) -> dict[str, Any]:
    """
    为自然语言载荷解析提供网格摘要（节点 z 范围、最高节点、顶端若干节点号）。
    不读完整单元，仅 *NODE。
    """
    mesh_inp = mesh_inp.resolve()
    text = mesh_inp.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    nodes = _parse_nodes(lines)
    if not nodes:
        raise ValueError("网格中无节点，无法摘要")
    zvals = {nid: float(p[2]) for nid, p in nodes.items()}
    zmin = min(zvals.values())
    zmax = max(zvals.values())
    by_z_desc = sorted(nodes.keys(), key=lambda i: zvals[i], reverse=True)
    load_node_max_z = int(by_z_desc[0])
    sample_n = min(48, len(by_z_desc))
    top_node_ids_sample = [int(x) for x in by_z_desc[:sample_n]]
    return {
        "n_nodes": len(nodes),
        "z_min": zmin,
        "z_max": zmax,
        "load_node_max_z": load_node_max_z,
        "top_node_ids_sample": top_node_ids_sample,
    }


def _build_cload_entries(
    nodes: dict[int, np.ndarray],
    *,
    load_node_max_z: int,
    cload_mag: float,
    load_case: dict[str, Any] | None,
) -> tuple[list[tuple[int, int, float]], str]:
    """
    返回 ( (node_id, dof, magnitude), ... ) 与 cload_mode 标签。
    与 examples/oc4/from_cad_b31.inp 等一致：单条 *CLOAD 关键字下多行数据。
    """
    lc = dict(load_case) if load_case else {}
    mode = str(lc.get("cload_mode") or "single_top").strip().lower()
    dof = int(lc.get("cload_dof") or 3)
    if dof not in (1, 2, 3):
        dof = 3

    zvals = {nid: float(nodes[nid][2]) for nid in nodes}
    by_z_desc = sorted(nodes.keys(), key=lambda i: zvals[i], reverse=True)

    def _mag_one() -> float:
        v = lc.get("cload_mag")
        if v is not None:
            return float(v)
        return float(cload_mag)

    def _mag_each() -> float:
        v = lc.get("cload_each")
        if v is not None:
            return float(v)
        return float(cload_mag)

    if mode in ("single", "single_top", "max_z", "one_node"):
        mag = _mag_one()
        return [(int(load_node_max_z), dof, mag)], mode

    if mode in ("top_count", "count_top", "n_top"):
        n = int(lc.get("top_node_count") or lc.get("count") or 1)
        n = max(1, min(n, len(by_z_desc), 500))
        mag = _mag_each()
        return [(int(nid), dof, mag) for nid in by_z_desc[:n]], mode

    if mode in ("top_fraction", "fraction_top"):
        frac = float(lc.get("top_fraction") or lc.get("fraction") or 0.01)
        frac = max(1.0 / max(len(by_z_desc), 1), min(frac, 0.5))
        n = max(1, int(round(len(by_z_desc) * frac)))
        n = min(n, len(by_z_desc), 500)
        mag = _mag_each()
        return [(int(nid), dof, mag) for nid in by_z_desc[:n]], mode

    if mode == "explicit":
        raw = lc.get("explicit_cloads") or lc.get("cloads")
        if not isinstance(raw, list) or not raw:
            mag = _mag_one()
            return [(int(load_node_max_z), dof, mag)], "explicit_fallback"
        out: list[tuple[int, int, float]] = []
        node_set = set(nodes.keys())
        for item in raw:
            if not isinstance(item, dict):
                continue
            nid = int(item.get("node") or item.get("nid") or 0)
            d = int(item.get("dof") or dof)
            m = float(item.get("magnitude") or item.get("mag") or item.get("value") or 0.0)
            if nid not in node_set or d not in (1, 2, 3):
                continue
            out.append((nid, d, m))
        if not out:
            mag = _mag_one()
            return [(int(load_node_max_z), dof, mag)], "explicit_fallback"
        return out, mode

    mag = _mag_one()
    return [(int(load_node_max_z), dof, mag)], "single_top"


def partition_oc4_mesh_inp(
    mesh_inp: Path,
    src_oc4_iges: Path,
    out_inp: Path,
    *,
    band_scale: float = 1.22,
    z_fix_band: float = 800.0,
    cload_mag: float = -5.0e6,
    material_name: str | None = None,
    load_case: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    读取 meshio/Gmsh 风格体网格 INP，写出带 design_space / nondesign_space 与最小 *STEP 的 INP。

    Returns:
        统计 dict：n_design, n_nondesign, n_fixed_nodes, load_node, cload_mode, n_cload_lines 等。
    """
    mesh_inp = mesh_inp.resolve()
    text = mesh_inp.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    lc = dict(load_case) if load_case else {}
    band_scale = float(lc.get("band_scale", band_scale))
    z_fix_band = float(lc.get("z_fix_band", z_fix_band))
    band_scale = max(1.0, min(band_scale, 3.0))
    z_fix_band = max(10.0, z_fix_band)

    cols = _vertical_columns_from_oc4_iges(src_oc4_iges.resolve())
    nodes = _parse_nodes(lines)
    vol_elems, _ = _parse_volume_elements(lines)

    design: list[int] = []
    nondesign: list[int] = []
    for eid, typ, nids in vol_elems:
        c = _centroid(nodes, nids)
        if _in_any_column_corridor(c, cols, band_scale):
            nondesign.append(eid)
        else:
            design.append(eid)

    if not design:
        raise RuntimeError("design_space 为空：请减小 band_scale 或检查网格/柱识别。")
    if not nondesign:
        steal_n = max(8, len(design) // 8000)
        steal = set(sorted(design)[:steal_n])
        nondesign = list(steal)
        design = [x for x in design if x not in steal]

    zvals = np.array([nodes[i][2] for i in nodes], dtype=float)
    zmin = float(np.min(zvals))
    zmax = float(np.max(zvals))
    fixed_nodes = [nid for nid, p in nodes.items() if float(p[2]) <= zmin + z_fix_band]
    load_cand = [(nid, float(nodes[nid][2])) for nid in nodes]
    load_node = int(max(load_cand, key=lambda t: t[1])[0])

    cload_entries, cload_mode = _build_cload_entries(
        nodes,
        load_node_max_z=load_node,
        cload_mag=float(lc.get("cload_mag", cload_mag)),
        load_case=lc if lc else None,
    )

    mat = material_name
    if mat is None:
        for ln in lines:
            u = ln.strip().upper()
            if u.startswith("*MATERIAL"):
                if "NAME=" in u:
                    mat = ln.split("NAME=", 1)[1].split(",")[0].strip()
                elif "NAME =" in ln.upper():
                    mat = ln.upper().split("NAME =", 1)[1].split(",")[0].strip()
                break
        if mat is None:
            mat = "MSteel"

    solid_pat = re.compile(r"^\*Solid\s+section\s*,", re.IGNORECASE)
    idx_solid = next((i for i, ln in enumerate(lines) if solid_pat.match(ln.strip())), -1)
    if idx_solid < 0:
        raise RuntimeError("未找到 *SOLID SECTION，无法写入双截面（请确认 INP 含体网格与材料段）。")

    j = idx_solid + 1
    while j < len(lines) and not lines[j].strip().startswith("*"):
        j += 1

    idx_step = next((i for i, ln in enumerate(lines) if ln.strip().upper().startswith("*STEP")), len(lines))
    tail_before_step = lines[j:idx_step]

    head = lines[:idx_solid]
    mid: list[str] = [
        "** --- OC4 pipeline: design_space / nondesign_space (wiki example_3 style) ---",
    ]
    mid.extend(_format_elset_block("nondesign_space", sorted(nondesign)))
    mid.extend(_format_elset_block("design_space", sorted(design)))
    mid.append("**")
    mid.append(f"*Solid section, Elset=design_space, Material={mat}")
    mid.append(f"*Solid section, Elset=nondesign_space, Material={mat}")

    nset_blk = ["**", "*NSET, NSET=fixed_zmin"]
    for i in range(0, len(sorted(fixed_nodes)), 16):
        chunk = sorted(fixed_nodes)[i : i + 16]
        nset_blk.append(", ".join(str(x) for x in chunk) + ",")

    cload_lines = [f"{nid}, {d}, {mag:.12g}" for nid, d, mag in cload_entries]
    step_blk = [
        "** --- Static step (CalculiX): fixed_zmin boundary + concentrated loads (from_cad_b31 style) ---",
        "*STEP",
        "*STATIC",
        "1., 1., 1e-05, 1.",
        "*BOUNDARY",
        "fixed_zmin, 1, 3, 0",
        "*CLOAD",
        *cload_lines,
        "*NODE FILE",
        "U",
        "*EL FILE",
        "S",
        "*END STEP",
    ]

    out_lines = head + mid + tail_before_step + nset_blk + step_blk
    out_inp.parent.mkdir(parents=True, exist_ok=True)
    out_inp.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return {
        "n_design": len(design),
        "n_nondesign": len(nondesign),
        "n_fixed_nodes": len(fixed_nodes),
        "load_node": int(load_node),
        "cload_mode": cload_mode,
        "n_cload_lines": len(cload_entries),
        "cload_nodes": [int(t[0]) for t in cload_entries],
    }


def _iter_line(iterations_limit: int | str) -> str:
    if isinstance(iterations_limit, int):
        return f"iterations_limit = {iterations_limit}"
    return f'iterations_limit = "{iterations_limit}"'


def write_beso_conf_example3_style(
    target: Path,
    *,
    work_dir: Path,
    ccx_path: Path,
    inp_name: str,
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    iterations_limit: int | str = 8,
) -> None:
    """双域 ``design_space`` + ``nondesign_space``，与 wiki example_3 beso_conf 结构一致。"""
    work_dir = work_dir.resolve()
    ccx_path = ccx_path.resolve()
    il = _iter_line(iterations_limit)
    txt = f'''# Auto-generated by oc4_beso_full_pipeline (example_3 style: two elsets)

path = r"{work_dir}"
path_calculix = r"{ccx_path}"
file_name = "{inp_name}"

{il}

elset_name = "design_space"
domain_optimized[elset_name] = True
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

elset_name = "nondesign_space"
domain_optimized[elset_name] = False
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

mass_goal_ratio = {mass_goal_ratio}
filter_list = [["simple", {filter_radius}]]
optimization_base = "{optimization_base}"
save_iteration_results = 2
save_resulting_format = "inp vtk"
'''
    target.write_text(txt, encoding="utf-8")
