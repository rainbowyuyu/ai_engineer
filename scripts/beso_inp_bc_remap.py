# SPDX-License-Identifier: LGPL-2.1-or-later
"""
从 FreeCAD FEM 写出的 CalculiX INP 中抽取 *Step 内的 *BOUNDARY / *CLOAD，
按坐标最近邻映射到另一套体网格节点（如 Gmsh 的 _mesh_volume.inp），供 BESO 双域 INP 使用。
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path


def _dist2(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    dx, dy, dz = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return dx * dx + dy * dy + dz * dz


def parse_inp_nodes(text: str) -> dict[int, tuple[float, float, float]]:
    nodes: dict[int, tuple[float, float, float]] = {}
    in_node = False
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        u = s.upper()
        if u.startswith("*NODE"):
            in_node = True
            continue
        if s.startswith("*"):
            in_node = False
            continue
        if in_node:
            parts = [p.strip() for p in s.split(",")]
            if len(parts) >= 4:
                try:
                    nid = int(parts[0])
                    nodes[nid] = (float(parts[1]), float(parts[2]), float(parts[3]))
                except ValueError:
                    continue
    return nodes


def parse_nsets(text: str) -> dict[str, list[int]]:
    """解析 *Nset / *NSET，NAME= 或 NSET= 形式；收集连续数据行中的整数节点号。"""
    out: dict[str, list[int]] = {}
    current: str | None = None
    int_re = re.compile(r"-?\d+")

    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        u = s.upper()
        if u.startswith("*NSET"):
            m = re.search(r"(?:NAME|NSET)\s*=\s*([^,\s]+)", s, re.I)
            current = m.group(1).strip() if m else None
            if current is not None:
                out.setdefault(current, [])
            continue
        if s.startswith("*"):
            current = None
            continue
        if current is None:
            continue
        for tok in s.replace("\t", " ").split(","):
            t = tok.strip()
            if not t:
                continue
            if t.lstrip("-").isdigit():
                out[current].append(int(t))
    return out


def _slice_first_step(text: str) -> str:
    m = re.search(r"(?im)^\*Step\b", text)
    if not m:
        return ""
    start = m.start()
    m2 = re.search(r"(?im)^\*End step\b", text[start:])
    if m2:
        return text[start : start + m2.end()]
    return text[start:]


def _parse_boundary_lines(data_lines: list[str]) -> list[tuple[str, int]]:
    """
    返回 (目标, dof) 列表：目标为 nset 名，或节点号十进制字符串。
    支持 ``ConstraintFixed,1`` 与 ``123, 1, 3, 0``（节点 123 的 dof 1–3）。
    """
    specs: list[tuple[str, int]] = []
    for raw in data_lines:
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) < 2:
            continue
        a, b = parts[0], parts[1]
        try:
            dof1 = int(b)
        except ValueError:
            continue
        if a.lstrip("-").isdigit():
            if len(parts) >= 4:
                try:
                    dof2 = int(parts[2])
                except ValueError:
                    dof2 = dof1
                lo, hi = (dof1, dof2) if dof1 <= dof2 else (dof2, dof1)
                for d in range(lo, hi + 1):
                    specs.append((a, d))
            else:
                specs.append((a, dof1))
        else:
            specs.append((a, dof1))
    return specs


def _parse_cload_lines(data_lines: list[str]) -> list[tuple[int, int, float]]:
    rows: list[tuple[int, int, float]] = []
    for raw in data_lines:
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        parts = [p.strip() for p in s.split(",")]
        if len(parts) < 3:
            continue
        try:
            nid = int(parts[0])
            dof = int(parts[1])
            val = float(parts[2])
        except ValueError:
            continue
        rows.append((nid, dof, val))
    return rows


def _extract_boundary_cload_blocks(step_text: str) -> tuple[list[str], list[str]]:
    lines = [ln.rstrip("\n") for ln in step_text.splitlines()]
    b_data: list[str] = []
    c_data: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        lu = lines[i].strip().upper()
        if lu.startswith("*BOUNDARY"):
            i += 1
            while i < n:
                s = lines[i].strip()
                if not s or s.startswith("**"):
                    i += 1
                    continue
                if s.startswith("*"):
                    break
                b_data.append(s)
                i += 1
            continue
        if lu.startswith("*CLOAD"):
            i += 1
            while i < n:
                s = lines[i].strip()
                if not s or s.startswith("**"):
                    i += 1
                    continue
                if s.startswith("*"):
                    break
                c_data.append(s)
                i += 1
            continue
        i += 1
    return b_data, c_data


def bottom_fix_nodes_for_volume_mesh(
    nodes: dict[int, tuple[float, float, float]],
    elements: dict[int, tuple[int, int, int, int]],
    design: list[int],
    nondesign: list[int],
    fix_band_mm: float,
) -> list[int]:
    """
    与 ``freecad_fcstd_pipeline_runner._assemble_out_inp`` 一致：非设计域 z 最低一带节点，
    不足 3 个时退回全模型 z_min 底带，避免欠约束。
    """
    z_coords = [p[2] for p in nodes.values()]
    z_min = min(z_coords)
    nondesign_nodes: set[int] = set()
    for eid in nondesign:
        a, b, c, d = elements[eid]
        nondesign_nodes.update((a, b, c, d))
    bottom_nd: list[int] = []
    if nondesign_nodes:
        z_min_nd = min(nodes[n][2] for n in nondesign_nodes)
        band = float(fix_band_mm)
        bottom_nd = [nid for nid in nondesign_nodes if nodes[nid][2] <= z_min_nd + band]
    if len(bottom_nd) >= 3:
        return bottom_nd
    band = float(fix_band_mm)
    bottom = [nid for nid, p in nodes.items() if p[2] <= z_min + band]
    if nondesign and len(bottom_nd) < 3:
        print(
            f"[WARN] bottom_fix：非设计域底带 (Δz={band}) 内节点仅 {len(bottom_nd)} 个，"
            "已退回全模型 z_min 底带，避免欠约束。",
            file=sys.stderr,
        )
    return bottom


def top_load_node_for_volume_mesh(
    nodes: dict[int, tuple[float, float, float]],
    *,
    top_band_mm: float,
) -> int:
    """与 ``_assemble_out_inp`` 一致：最高 z 附近窗口内选载荷节点。"""
    z_max = max(p[2] for p in nodes.values())
    z_lo = z_max - max(float(top_band_mm), 1e-6)
    load_cand = [(nid, p) for nid, p in nodes.items() if p[2] >= z_lo]
    load_cand.sort(key=lambda t: (-t[1][2], abs(t[1][0]) + abs(t[1][1])))
    return load_cand[0][0]


def _nearest_mesh_node(
    target_nodes: dict[int, tuple[float, float, float]],
    p: tuple[float, float, float],
) -> tuple[int, float]:
    best_id = -1
    best_d2 = float("inf")
    for nid, q in target_nodes.items():
        d2 = _dist2(p, q)
        if d2 < best_d2:
            best_d2, best_id = d2, nid
    return best_id, math.sqrt(best_d2)


def _remap_nid(
    old_nid: int,
    ref_nodes: dict[int, tuple[float, float, float]],
    target_nodes: dict[int, tuple[float, float, float]],
    max_dist: float,
    cache: dict[int, tuple[int, float]],
) -> tuple[int, float] | None:
    if old_nid in cache:
        t = cache[old_nid]
        if t[0] < 0:
            return None
        return t
    p = ref_nodes.get(old_nid)
    if p is None:
        cache[old_nid] = (-1, float("nan"))
        return None
    nid, dist = _nearest_mesh_node(target_nodes, p)
    if nid < 0 or dist > max_dist:
        cache[old_nid] = (-1, dist)
        return None
    cache[old_nid] = (nid, dist)
    return nid, dist


def build_remapped_beso_step_bc(
    fem_reference_inp: Path,
    target_nodes: dict[int, tuple[float, float, float]],
    *,
    max_dist_mm: float = 300.0,
    nset_prefix: str = "beso_fc_",
    bottom_fix_fallback_nodes: list[int] | None = None,
    bottom_fix_only_if_no_fem_boundary: bool = True,
    fallback_cload_xyz: tuple[float, float, float] | None = None,
    top_load_pick_band_mm: float = 1600.0,
) -> tuple[str, str, dict[str, object]]:
    """
    返回 (pre_step_nset_block, step_bc_body, stats)。

    - pre_step_nset_block: 插入在 *Material 之前的 *Nset 文本（可能为空）。
    - step_bc_body: 从 *Boundary 到 *Cload 结束（不含 *Step / *Static），调用方包在外层 Step 内。
    - bottom_fix_fallback_nodes: 当 FEM 映射无固定约束时，追加与流水线一致的 ``bottom_fix`` 底带。
    - fallback_cload_xyz: 当映射后无任何 Cload 时，在顶区节点上施加 (fx,fy,fz)（全近 0 时 fx 默认 281000）。
    """
    raw = fem_reference_inp.read_text(encoding="utf-8", errors="replace")
    ref_nodes = parse_inp_nodes(raw)
    nsets = parse_nsets(raw)
    step = _slice_first_step(raw)
    b_lines, c_lines = _extract_boundary_cload_blocks(step)
    b_specs = _parse_boundary_lines(b_lines)
    c_rows = _parse_cload_lines(c_lines)

    max_d = float(max_dist_mm)
    cache: dict[int, tuple[int, float]] = {}
    skipped_boundary = 0
    skipped_cload = 0

    # --- boundary: nset 名 -> 需要固定的 dof 集合；节点号 -> dof 集合
    nset_dofs: dict[str, set[int]] = {}
    node_dofs: dict[int, set[int]] = {}
    for target, dof in b_specs:
        if target.lstrip("-").isdigit():
            oid = int(target)
            m = _remap_nid(oid, ref_nodes, target_nodes, max_d, cache)
            if m is None or m[0] < 0:
                skipped_boundary += 1
                continue
            nid = m[0]
            node_dofs.setdefault(nid, set()).add(dof)
        else:
            nset_dofs.setdefault(target, set()).add(dof)

    def _append_nset_block(lines: list[str], name: str, ids: list[int]) -> None:
        lines.append(f"**\n*Nset, Nset={name}\n")
        pos = 0
        for nid in ids:
            if pos < 8:
                lines.append(f"{nid}, ")
                pos += 1
            else:
                lines.append(f"{nid},\n")
                pos = 1
                lines.append(f"{nid}, ")
        lines.append("\n")

    new_nset_lines: list[str] = []
    nset_rename: dict[str, str] = {}

    for orig_name, dofs in nset_dofs.items():
        old_ids = nsets.get(orig_name, [])
        if not old_ids:
            continue
        mapped: list[int] = []
        for oid in old_ids:
            m = _remap_nid(oid, ref_nodes, target_nodes, max_d, cache)
            if m is None or m[0] < 0:
                skipped_boundary += 1
                continue
            mapped.append(m[0])
        mapped = sorted(set(mapped))
        if not mapped:
            continue
        new_nm = f"{nset_prefix}{orig_name.replace(' ', '_')}"
        nset_rename[orig_name] = new_nm
        _append_nset_block(new_nset_lines, new_nm, mapped)

    bc_body: list[str] = []
    bc_body.append("**\n*Boundary, op=NEW\n")
    bc_body.append("*Boundary\n")
    for orig_name, dofs in sorted(nset_dofs.items(), key=lambda x: x[0]):
        new_nm = nset_rename.get(orig_name)
        if not new_nm:
            continue
        for dof in sorted(dofs):
            bc_body.append(f"{new_nm},{dof}\n")

    for nid in sorted(node_dofs.keys()):
        ds = sorted(node_dofs[nid])
        i = 0
        while i < len(ds):
            j = i
            while j + 1 < len(ds) and ds[j + 1] == ds[j] + 1:
                j += 1
            bc_body.append(f"{nid}, {ds[i]}, {ds[j]}, 0\n")
            i = j + 1

    if b_specs and not nset_rename and not node_dofs:
        print(
            "[WARN] FEM 参考 *BOUNDARY 未映射出任何约束（nset 无节点或全部超出距离阈值；"
            "纯节点形式边界也未成功）。请检查参考 INP 与 ``fem_bc_remap_max_dist_mm``。",
            file=sys.stderr,
        )

    used_bottom_fb = False
    if bottom_fix_fallback_nodes:
        need_fb = (not bottom_fix_only_if_no_fem_boundary) or (not nset_rename and not node_dofs)
        if need_fb:
            _append_nset_block(
                new_nset_lines, "bottom_fix", sorted(set(bottom_fix_fallback_nodes))
            )
            bc_body.append("** bottom_fix fallback (FEM 无有效固定集或显式关闭仅 FEM 固定时)\n")
            bc_body.append("bottom_fix, 1, 1, 0\n")
            bc_body.append("bottom_fix, 2, 2, 0\n")
            bc_body.append("bottom_fix, 3, 3, 0\n")
            used_bottom_fb = True
            print(
                f"[INFO] 已追加底带固定 bottom_fix：{len(set(bottom_fix_fallback_nodes))} 个节点。",
                file=sys.stderr,
            )

    # CLOAD: 合并 (新节点, dof) 力值
    acc: dict[tuple[int, int], float] = {}
    max_map_err = 0.0
    for oid, dof, val in c_rows:
        m = _remap_nid(oid, ref_nodes, target_nodes, max_d, cache)
        if m is None or m[0] < 0:
            skipped_cload += 1
            continue
        nid, dist = m
        max_map_err = max(max_map_err, dist)
        acc[(nid, dof)] = acc.get((nid, dof), 0.0) + val

    used_cload_fb = False
    if not acc and fallback_cload_xyz is not None:
        fx, fy, fz = (float(fallback_cload_xyz[0]), float(fallback_cload_xyz[1]), float(fallback_cload_xyz[2]))
        eps = 1e-9
        if abs(fx) < eps and abs(fy) < eps and abs(fz) < eps:
            fx = 281000.0
        nid_ld = top_load_node_for_volume_mesh(target_nodes, top_band_mm=float(top_load_pick_band_mm))
        if abs(fx) >= eps:
            acc[(nid_ld, 1)] = acc.get((nid_ld, 1), 0.0) + fx
        if abs(fy) >= eps:
            acc[(nid_ld, 2)] = acc.get((nid_ld, 2), 0.0) + fy
        if abs(fz) >= eps:
            acc[(nid_ld, 3)] = acc.get((nid_ld, 3), 0.0) + fz
        used_cload_fb = True
        print(
            f"[INFO] FEM Cload 映射为空，已使用顶区单点载荷回退：node={nid_ld} fx={fx} fy={fy} fz={fz}",
            file=sys.stderr,
        )

    bc_body.append("**\n*Cload, op=NEW\n")
    bc_body.append("*Cload\n")
    for (nid, dof) in sorted(acc.keys(), key=lambda t: (t[0], t[1])):
        bc_body.append(f"{nid}, {dof}, {acc[(nid, dof)]}\n")

    stats: dict[str, object] = {
        "reference_inp": str(fem_reference_inp),
        "max_dist_mm": max_d,
        "skipped_boundary_specs": skipped_boundary,
        "skipped_cload_rows": skipped_cload,
        "cload_pairs": len(acc),
        "max_remap_distance_mm": max_map_err,
        "bottom_fix_fallback_used": used_bottom_fb,
        "cload_top_fallback_used": used_cload_fb,
    }
    return "".join(new_nset_lines), "".join(bc_body), stats


def write_beso_inp_with_remapped_bc(
    *,
    out_inp: Path,
    design: list[int],
    nondesign: list[int],
    nodes: dict[int, tuple[float, float, float]],
    elements: dict[int, tuple[int, int, int, int]],
    E_mpa: float,
    nu: float,
    density: float,
    fem_reference_inp: Path,
    max_dist_mm: float,
    fix_z_band_mm: float = 800.0,
    bottom_fix_fallback: bool = True,
    bottom_fix_only_if_no_fem_boundary: bool = True,
    cload_fallback_if_empty: bool = True,
    cload_fx: float = 281000.0,
    cload_fy: float = 0.0,
    cload_fz: float = 0.0,
    single_design_domain: bool = False,
) -> dict[str, object]:
    """写出与 _assemble_out_inp 相同结构的双域 INP，边界与 Cload 来自 FEM 参考并按坐标映射。"""
    bottom_nodes: list[int] | None = None
    if bottom_fix_fallback:
        bottom_nodes = bottom_fix_nodes_for_volume_mesh(
            nodes, elements, design, nondesign, float(fix_z_band_mm)
        )
    fb_xyz = (float(cload_fx), float(cload_fy), float(cload_fz)) if cload_fallback_if_empty else None
    nset_blk, bc_body, stats = build_remapped_beso_step_bc(
        fem_reference_inp,
        nodes,
        max_dist_mm=max_dist_mm,
        bottom_fix_fallback_nodes=bottom_nodes,
        bottom_fix_only_if_no_fem_boundary=bottom_fix_only_if_no_fem_boundary,
        fallback_cload_xyz=fb_xyz,
        top_load_pick_band_mm=max(float(fix_z_band_mm) * 2.0, 1.0),
    )
    with out_inp.open("w", encoding="utf-8", newline="\n") as fo:
        fo.write("** Full model for BESO (FCStd pipeline + FEM BC remap)\n")
        fo.write("*Heading\n")
        if single_design_domain:
            fo.write("Model: full volume as design_space + boundary/CLOAD from FEM reference\n")
        else:
            fo.write("Model: volume mesh + boundary/CLOAD remapped from FEM reference INP\n")
        fo.write("**\n*Node, NSET=Nall\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            fo.write(f"{nid}, {x}, {y}, {z}\n")
        fo.write("**\n** Volume elements\n")
        fo.write("*Element, TYPE=C3D4, Elset=design_space\n")
        for eid in sorted(design):
            a, b, c, d = elements[eid]
            fo.write(f"{eid}, {a}, {b}, {c}, {d}\n")
        if not single_design_domain:
            fo.write("*Element, TYPE=C3D4, Elset=nondesign_space\n")
            for eid in sorted(nondesign):
                a, b, c, d = elements[eid]
                fo.write(f"{eid}, {a}, {b}, {c}, {d}\n")
        if nset_blk.strip():
            fo.write(nset_blk)
        if single_design_domain:
            fo.write("**\n** Materials (MPa, t/mm^3) — 全设计域单材料\n")
            fo.write("*Material, Name=Material-design\n")
            fo.write("*Elastic\n")
            fo.write(f"{E_mpa}, {nu}\n")
            fo.write("*Density\n")
            fo.write(f"{density}\n")
            fo.write("**\n")
            fo.write("*Solid section, Elset=design_space, Material=Material-design\n")
        else:
            fo.write("**\n** Materials (MPa, t/mm^3)\n")
            fo.write("*Material, Name=Material-design\n")
            fo.write("*Elastic\n")
            fo.write(f"{E_mpa}, {nu}\n")
            fo.write("*Density\n")
            fo.write(f"{density}\n")
            fo.write("*Material, Name=Material-nondesign\n")
            fo.write("*Elastic\n")
            fo.write(f"{E_mpa}, {nu}\n")
            fo.write("*Density\n")
            fo.write(f"{density}\n")
            fo.write("**\n")
            fo.write("*Solid section, Elset=design_space, Material=Material-design\n")
            fo.write("*Solid section, Elset=nondesign_space, Material=Material-nondesign\n")
        fo.write("**\n*Step\n*Static\n")
        fo.write(bc_body)
        fo.write("**\n*Node file\n")
        fo.write("RF, U\n")
        fo.write("*El file\n")
        fo.write("S\n")
        fo.write("*End step\n")
    stats["out_inp"] = str(out_inp)
    return stats
