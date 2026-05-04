"""
IGES 导管架 → 整体连通 B31 + PIPE 截面 INP。

流程：圆柱轴线抽取 → 线段对最近点切分（K/X 节点）→ 半径尺度合并 → 去短段 → 按半径分组与 t/D → 写出 CalculiX deck。
"""
from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np

from backend.tools.iges_beam_to_inp import (
    BeamSeg,
    _auto_merge_tol_from_segments,
    _beam_n1,
    _build_graph_elements,
    _cluster_radii,
    _enforce_global_connectivity,
    _extract_beam_segments_from_iges,
    _merge_nodes_and_segments,
    _radius_to_group,
    _segment_length,
)

os.environ.setdefault("QT_LOGGING_RULES", "qt.widgets.qgraphicsview.warning=false")


@dataclass
class RawSeg:
    p0: np.ndarray
    p1: np.ndarray
    r: float


@dataclass
class JacketDiagnostics:
    nodes: int = 0
    elements: int = 0
    components: int = 0
    dropped_micro: int = 0
    split_iterations: int = 0
    r_med: float = 0.0
    merge_tol_used: float = 0.0


def _segment_segment_closest(
    a0: np.ndarray,
    a1: np.ndarray,
    b0: np.ndarray,
    b1: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """
    两有限线段最近点及参数 s,t ∈ [0,1]（a0+s*(a1-a0), b0+t*(b1-b0)）。
    对凸二次距离在矩形域上用驻点 + 四边 + 四角枚举。
    """
    u = a1 - a0
    v = b1 - b0
    w0 = a0 - b0
    a = float(np.dot(u, u))
    b = float(np.dot(u, v))
    c = float(np.dot(v, v))
    d = float(np.dot(u, w0))
    e = float(np.dot(v, w0))
    det = a * c - b * b
    eps = 1.0e-18

    best_d = float("inf")
    best: tuple[np.ndarray, np.ndarray, float, float] | None = None

    def consider(p: np.ndarray, q: np.ndarray, s: float, t: float) -> None:
        nonlocal best_d, best
        dd = float(np.linalg.norm(p - q))
        if dd < best_d - 1.0e-15:
            best_d = dd
            best = (p.copy(), q.copy(), float(s), float(t))

    # 内部驻点（无限直线）
    if det > eps:
        s = (b * e - c * d) / det
        t = (a * e - b * d) / det
        if 0.0 <= s <= 1.0 and 0.0 <= t <= 1.0:
            consider(a0 + s * u, b0 + t * v, s, t)

    # 边 s=0
    if c > eps:
        t = e / c
        t = max(0.0, min(1.0, t))
        consider(a0, b0 + t * v, 0.0, t)
    # 边 s=1
    if c > eps:
        w1 = w0 + u
        t = float(np.dot(v, w1)) / c
        t = max(0.0, min(1.0, t))
        consider(a1, b0 + t * v, 1.0, t)
    # 边 t=0
    if a > eps:
        s = -d / a
        s = max(0.0, min(1.0, s))
        consider(a0 + s * u, b0, s, 0.0)
    # 边 t=1
    if a > eps:
        wm = w0 - v
        s = -float(np.dot(u, wm)) / a
        s = max(0.0, min(1.0, s))
        consider(a0 + s * u, b1, s, 1.0)

    # 四角（数值兜底）
    for s in (0.0, 1.0):
        for t in (0.0, 1.0):
            consider(a0 + s * u, b0 + t * v, s, t)

    assert best is not None
    p, q, s, t = best
    return p, q, float(np.linalg.norm(p - q)), s, t


def _beam_segs_to_raw(segs: list[BeamSeg]) -> list[RawSeg]:
    return [RawSeg(np.asarray(s.p0, dtype=float), np.asarray(s.p1, dtype=float), float(s.radius)) for s in segs]


def split_segments_at_intersections(
    segs: list[RawSeg],
    *,
    pair_tol_k: float = 0.6,
    pair_abs_min_mm: float = 4000.0,
    param_eps: float = 1.0e-5,
    max_iter: int = 12,
) -> tuple[list[RawSeg], int]:
    """迭代：线段对距离 ≤ max(k*min(r1,r2), pair_abs_min_mm) 时在对方线段内部插入分割点。"""
    current = list(segs)
    iters = 0
    for _ in range(max_iter):
        n = len(current)
        splits: list[set[float]] = [set() for _ in range(n)]
        changed = False
        for i in range(n):
            for j in range(i + 1, n):
                si, sj = current[i], current[j]
                r_tol = max(float(pair_tol_k) * min(si.r, sj.r), float(pair_abs_min_mm))
                _, _, dist, s_i, s_j = _segment_segment_closest(si.p0, si.p1, sj.p0, sj.p1)
                if dist > r_tol:
                    continue
                if param_eps < s_i < 1.0 - param_eps:
                    splits[i].add(float(s_i))
                    changed = True
                if param_eps < s_j < 1.0 - param_eps:
                    splits[j].add(float(s_j))
                    changed = True
        iters += 1
        if not changed:
            break
        new_segs: list[RawSeg] = []
        for idx, seg in enumerate(current):
            ts = sorted(splits[idx])
            u = seg.p1 - seg.p0
            pts = [seg.p0]
            for t in ts:
                pts.append(seg.p0 + float(t) * u)
            pts.append(seg.p1)
            for k in range(len(pts) - 1):
                if _segment_length(pts[k], pts[k + 1]) > 1.0e-9:
                    new_segs.append(RawSeg(pts[k], pts[k + 1], seg.r))
        current = new_segs
    return current, iters


def _drop_micro_segments(elements: list[tuple[int, int, float]], nodes: list[np.ndarray]) -> tuple[list[tuple[int, int, float]], int]:
    """去掉长度 < r/2 的梁段。"""
    out: list[tuple[int, int, float]] = []
    dropped = 0
    for a, b, r in elements:
        L = _segment_length(nodes[a], nodes[b])
        if L < 0.5 * max(r, 1.0e-9):
            dropped += 1
            continue
        out.append((a, b, r))
    return out, dropped


def default_td_by_group_index(group_index: int) -> float:
    """半径升序分组后的默认 t/D（壁厚/外径）。"""
    table = (0.022, 0.025, 0.04, 0.06)
    if group_index < len(table):
        return float(table[group_index])
    return float(table[-1])


def parse_td_overrides(items: list[str] | None) -> dict[float, float]:
    """['1200,0.04', '800,0.022'] → {1200.0: 0.04, ...}"""
    out: dict[float, float] = {}
    if not items:
        return out
    for chunk in items:
        parts = chunk.replace(",", " ").split()
        if len(parts) != 2:
            raise ValueError(f"无效的 --td 参数: {chunk}，应为 '半径,t/D'")
        out[float(parts[0])] = float(parts[1])
    return out


def td_for_radius(
    radius: float,
    sorted_radius_rank: int,
    overrides: dict[float, float],
) -> float:
    """优先匹配 overrides 中与半径最近的键；否则用默认分组表（按半径升序的第 sorted_radius_rank 组）。"""
    if overrides:
        best_k: float | None = None
        best_d = float("inf")
        for rk in overrides:
            d = abs(radius - rk)
            if d < best_d:
                best_d = d
                best_k = rk
        if best_k is not None:
            return float(overrides[best_k])
    return default_td_by_group_index(sorted_radius_rank)


def build_jacket_topology(
    segs: list[BeamSeg],
    *,
    merge_tol: float | None = None,
    pair_tol_k: float = 0.6,
    pair_abs_min_mm: float | None = None,
    split_param_eps: float = 1.0e-5,
    bridge_islands: bool = False,
) -> tuple[list[np.ndarray], list[tuple[int, int, float]], JacketDiagnostics]:
    """切分 + 合并 + 去短段 + 图去重边；不强行桥接孤立子图。"""
    raw_env = (os.environ.get("JACKET_PAIR_ABS_MIN_MM") or "").strip()
    pair_abs = float(pair_abs_min_mm) if pair_abs_min_mm is not None else (float(raw_env) if raw_env else 4000.0)
    raw = _beam_segs_to_raw(segs)
    split_raw, split_it = split_segments_at_intersections(
        raw,
        pair_tol_k=pair_tol_k,
        pair_abs_min_mm=pair_abs,
        param_eps=split_param_eps,
    )
    beam_like = [
        BeamSeg(p0=s.p0, p1=s.p1, radius=s.r, source="jacket_split") for s in split_raw
    ]
    rs = [float(s.radius) for s in beam_like if math.isfinite(s.radius) and s.radius > 0]
    r_med = float(np.median(np.asarray(rs, dtype=float))) if rs else 1.0
    if merge_tol is not None:
        tol_use = float(merge_tol)
    else:
        tol_use = max(1.0e-12, 0.15 * r_med)
    # K/X 斜距最近点可与轴线相距数千 mm；合并半径必须不小于切分门槛的一定比例
    tol_use = max(tol_use, 0.98 * pair_abs)

    nodes, elements = _merge_nodes_and_segments(beam_like, tol_use)
    elements, dropped = _drop_micro_segments(elements, nodes)
    elements = _build_graph_elements(nodes, elements)
    if bridge_islands:
        elements = _enforce_global_connectivity(nodes, elements)

    diag = JacketDiagnostics(
        nodes=len(nodes),
        elements=len(elements),
        dropped_micro=dropped,
        split_iterations=split_it,
        r_med=r_med,
        merge_tol_used=tol_use,
    )

    g = nx.Graph()
    for i in range(len(nodes)):
        g.add_node(i)
    for a, b, _ in elements:
        g.add_edge(a, b)
    diag.components = nx.number_connected_components(g)

    return nodes, elements, diag


def write_jacket_b31_pipe_inp(
    out_path: Path,
    nodes: list[np.ndarray],
    elements: list[tuple[int, int, float]],
    diag: JacketDiagnostics,
    *,
    td_overrides: dict[float, float] | None = None,
    young: float = 210000.0,
    nu: float = 0.3,
    force_top_load: float = -1000.0,
    heading_extra: str = "",
) -> None:
    """PIPE 空心圆管截面 + 底固定 + 顶部分载。"""
    td_overrides = td_overrides or {}
    if not nodes or not elements:
        raise ValueError("empty nodes or elements")

    radii = [r for _, _, r in elements]
    group_r = _cluster_radii(radii, tol=1.0e-6)
    sorted_gid_by_r = sorted(range(len(group_r)), key=lambda i: group_r[i])

    group_el: dict[int, list[int]] = {}
    for eid0, (_, _, r) in enumerate(elements):
        gid = _radius_to_group(r, group_r)
        group_el.setdefault(gid, []).append(eid0 + 1)

    zz = np.asarray([p[2] for p in nodes], dtype=float)
    zmin = float(np.min(zz))
    zmax = float(np.max(zz))
    ztol = max(1.0e-9, 1.0e-6 * max(1.0, zmax - zmin))
    nset_bottom = [i + 1 for i, p in enumerate(nodes) if abs(float(p[2]) - zmin) <= ztol]
    nset_top = [i + 1 for i, p in enumerate(nodes) if abs(float(p[2]) - zmax) <= ztol]
    if not nset_bottom:
        nset_bottom = [int(np.argmin(zz)) + 1]
    if not nset_top:
        nset_top = [int(np.argmax(zz)) + 1]

    lines: list[str] = []
    lines.append("**")
    lines.append("** IGES jacket → B31 PIPE (auto)")
    lines.append("**")
    lines.append("*Heading")
    lines.append(
        "Auto-generated jacket beam model; "
        f"nodes={diag.nodes}, beam_elems={diag.elements}, components={diag.components}, "
        f"dropped_micro={diag.dropped_micro}, split_iters={diag.split_iterations}, "
        f"r_med={diag.r_med:.6g}, merge_tol={diag.merge_tol_used:.6g}"
        + (f"; {heading_extra}" if heading_extra else "")
    )
    lines.append("**")
    lines.append("*Node, NSET=Nall")
    for i, p in enumerate(nodes, start=1):
        lines.append(f"{i}, {float(p[0]):.9f}, {float(p[1]):.9f}, {float(p[2]):.9f}")
    lines.append("*Element, TYPE=B31, ELSET=Eall")
    for i, (a, b, _) in enumerate(elements, start=1):
        lines.append(f"{i}, {a + 1}, {b + 1}")

    rank_of_gid = {gid: rnk for rnk, gid in enumerate(sorted_gid_by_r)}

    for gid in sorted(group_el.keys()):
        lines.append(f"*ELSET,ELSET=ESEC_{gid + 1}")
        ids = group_el[gid]
        for k in range(0, len(ids), 16):
            chunk = ids[k : k + 16]
            lines.append(", ".join(str(x) for x in chunk))

    lines.append("*MATERIAL, NAME=SolidMaterial")
    lines.append("*ELASTIC")
    lines.append(f"{young:g}, {nu:g}")

    for gid in sorted(group_el.keys()):
        gr = float(group_r[gid])
        el_ids = group_el[gid]
        if not el_ids:
            continue
        anchor_eid = el_ids[0]
        na, nb, _ = elements[anchor_eid - 1]
        n1 = _beam_n1(nodes[na], nodes[nb])
        td = td_for_radius(gr, rank_of_gid[gid], td_overrides)
        D = 2.0 * gr
        t_wall = float(td) * D
        lines.append(f"*BEAM SECTION,SECTION=PIPE,ELSET=ESEC_{gid + 1},MATERIAL=SolidMaterial")
        lines.append(f"{gr:.9f}, {t_wall:.9f}")
        lines.append(f"{n1[0]:.9f}, {n1[1]:.9f}, {n1[2]:.9f}")

    lines.append("*NSET,NSET=FemConstraintDisplacement")
    for k in range(0, len(nset_bottom), 16):
        lines.append(", ".join(str(x) for x in nset_bottom[k : k + 16]))
    lines.append("*NSET,NSET=FemLoadTop")
    for k in range(0, len(nset_top), 16):
        lines.append(", ".join(str(x) for x in nset_top[k : k + 16]))

    lines.append("*BOUNDARY")
    lines.append("FemConstraintDisplacement, 1, 6")
    lines.append("*STEP")
    lines.append("*STATIC")
    lines.append("1., 1., 1e-05, 1.")
    lines.append("*CLOAD")
    for nid in nset_top:
        lines.append(f"{nid}, 3, {float(force_top_load):.6f}")
    lines.append("*NODE FILE")
    lines.append("U")
    lines.append("*EL FILE")
    lines.append("S")
    lines.append("*END STEP")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_jacket_iges_to_inp(
    iges_path: Path,
    dest_inp: Path,
    *,
    merge_tol: float | None = None,
    pair_tol_k: float = 0.6,
    pair_abs_min_mm: float | None = None,
    td_overrides: dict[float, float] | None = None,
    force_top_load: float = -1000.0,
    bridge_islands: bool = True,
    surface_obj: Path | str | None = None,
    surface_facets: int = 16,
) -> tuple[Path, JacketDiagnostics]:
    segs = _extract_beam_segments_from_iges(Path(iges_path))
    if not segs:
        raise ValueError("No beam-like cylindrical segments were extracted from IGS.")
    req = float(merge_tol) if merge_tol is not None else 1.0e-3
    tol_eff = _auto_merge_tol_from_segments(segs, req)
    nodes, elements, diag = build_jacket_topology(
        segs,
        merge_tol=tol_eff,
        pair_tol_k=pair_tol_k,
        pair_abs_min_mm=pair_abs_min_mm,
        bridge_islands=bridge_islands,
    )
    write_jacket_b31_pipe_inp(
        Path(dest_inp),
        nodes,
        elements,
        diag,
        td_overrides=td_overrides,
        force_top_load=force_top_load,
    )
    if surface_obj:
        from backend.tools.jacket_beam_surface_mesh import write_beam_skin_mesh

        write_beam_skin_mesh(
            nodes,
            elements,
            Path(surface_obj),
            n_facets=int(surface_facets),
        )
    return Path(dest_inp).resolve(), diag


def main() -> int:
    parser = argparse.ArgumentParser(description="IGES jacket → connected B31 PIPE inp")
    parser.add_argument("iges", type=str)
    parser.add_argument("out_inp", type=str)
    parser.add_argument("--merge-tol", type=float, default=None)
    parser.add_argument("--pair-tol-k", type=float, default=0.6)
    parser.add_argument(
        "--pair-abs-min",
        type=float,
        default=None,
        help="切分距离绝对下限 mm（默认 4000 或环境变量 JACKET_PAIR_ABS_MIN_MM）",
    )
    parser.add_argument("--top-load", type=float, default=-1000.0)
    parser.add_argument(
        "--no-bridge",
        action="store_true",
        help="禁用分量间最短桥接（默认开启；IGES 缝隙时常需桥接才能单连通）",
    )
    parser.add_argument(
        "--td",
        action="append",
        default=None,
        help="覆盖 t/D：可多次指定，格式 R_mm,tDratio 例如 --td 1200,0.04",
    )
    parser.add_argument(
        "--surface-obj",
        type=str,
        default=None,
        help="额外导出圆柱壳三角网格 OBJ（仅可视化，不影响 B31 模型）",
    )
    parser.add_argument("--surface-facets", type=int, default=16, help="圆柱圆周分段数 8–64")
    args = parser.parse_args()
    td_map = parse_td_overrides(args.td)
    path, diag = convert_jacket_iges_to_inp(
        Path(args.iges),
        Path(args.out_inp),
        merge_tol=args.merge_tol,
        pair_tol_k=float(args.pair_tol_k),
        pair_abs_min_mm=args.pair_abs_min,
        td_overrides=td_map,
        force_top_load=float(args.top_load),
        bridge_islands=not bool(args.no_bridge),
        surface_obj=args.surface_obj,
        surface_facets=int(args.surface_facets),
    )
    print(path)
    print(
        f"nodes={diag.nodes} elems={diag.elements} components={diag.components} "
        f"dropped_micro={diag.dropped_micro} split_iters={diag.split_iterations}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
