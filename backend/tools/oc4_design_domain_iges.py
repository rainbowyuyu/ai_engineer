from __future__ import annotations

"""
OC4 导管架：由原始梁系 IGS（如 oc4.igs）生成「实心设计域」IGES/STEP，用途类比
examples/base/BESO2-FEMMeshGmsh.inp 中的实体设计域——后续可在 Gmsh 中体网格再供 BESO。

几何意图：
- 以外柱三角形为底、竖向拉伸的棱柱包络（包住下层水平弦杆与上部柱身/桩靴标高范围）；
- 布尔减去柱身/桩靴圆柱，使设计域在柱位开孔；
- 默认减去中心柱 + 三根边柱；若仅需挖三根边柱，使用 --edge-columns-only。
"""

import argparse
import itertools
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

# Suppress noisy Qt widget warnings in headless/batch conversion runs.
os.environ.setdefault("QT_LOGGING_RULES", "qt.widgets.qgraphicsview.warning=false")


@dataclass
class Oc4CutGeometry:
    """由梁中心线解析的 OC4 柱身/桩靴尺寸（避免 revolution 网格把外柱半径合成错误）。"""

    center_xy: np.ndarray
    outer_xy_ccw: list[np.ndarray]
    z_col_lo: float
    z_col_hi: float
    center_shaft_r: float
    outer_shaft_rs: list[float]
    center_pontoon: tuple[float, float, float, float, float] | None
    outer_pontoons: list[Optional[tuple[float, float, float, float, float]]]


@dataclass
class CylinderAxis:
    p0: np.ndarray
    p1: np.ndarray
    radius: float

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.p1 - self.p0))

    @property
    def direction(self) -> np.ndarray:
        v = self.p1 - self.p0
        n = float(np.linalg.norm(v))
        if n <= 0.0:
            return np.array([0.0, 0.0, 1.0], dtype=float)
        return v / n

    @property
    def center(self) -> np.ndarray:
        return 0.5 * (self.p0 + self.p1)


def _norm(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def _extract_revolution_cylinders(iges_path: Path) -> list[CylinderAxis]:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.merge(str(iges_path.resolve()))
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(2)
        surfaces = [t for d, t in gmsh.model.getEntities(2) if d == 2]
        out: list[CylinderAxis] = []
        for s in surfaces:
            try:
                st = gmsh.model.getType(2, int(s)).lower()
            except Exception:
                continue
            if "revolution" not in st:
                continue
            try:
                node_tags, coords, _ = gmsh.model.mesh.getNodes(2, int(s), includeBoundary=True)
            except Exception:
                continue
            if len(node_tags) < 16 or len(coords) < 48:
                continue
            pts = np.asarray(coords, dtype=float).reshape((-1, 3))
            c0 = pts.mean(axis=0)
            x = pts - c0
            cov = (x.T @ x) / max(1, x.shape[0] - 1)
            w, v = np.linalg.eigh(cov)
            axis = v[:, int(np.argmax(w))]
            axis = axis / max(_norm(axis), 1.0e-12)
            sproj = x @ axis
            smin = float(np.min(sproj))
            smax = float(np.max(sproj))
            p0 = c0 + smin * axis
            p1 = c0 + smax * axis
            if _norm(p1 - p0) <= 1.0e-6:
                continue
            proj = c0 + np.outer(sproj, axis)
            rr = np.linalg.norm(pts - proj, axis=1)
            r = float(np.median(rr))
            if not math.isfinite(r) or r <= 1.0:
                continue
            out.append(CylinderAxis(p0=p0, p1=p1, radius=r))
        return _dedup_cylinders(out)
    finally:
        gmsh.finalize()


def _dedup_cylinders(cyls: list[CylinderAxis]) -> list[CylinderAxis]:
    out: list[CylinderAxis] = []
    for c in cyls:
        uc = c.direction
        hit = False
        for i, t in enumerate(out):
            ut = t.direction
            if abs(float(np.dot(uc, ut))) < 0.99:
                continue
            rref = max(abs(c.radius), abs(t.radius), 1.0e-9)
            if abs(c.radius - t.radius) > 0.05 * rref:
                continue
            # 线偏距（用中心点近似）
            if _norm(c.center - t.center) > max(1500.0, 0.3 * rref):
                continue
            # 保留更长者
            if c.length > t.length:
                out[i] = c
            hit = True
            break
        if not hit:
            out.append(c)
    return out


def _triangle_wire(gmsh, pts: list[np.ndarray]) -> int:
    p_tags: list[int] = []
    for p in pts:
        p_tags.append(gmsh.model.occ.addPoint(float(p[0]), float(p[1]), float(p[2])))
    l1 = gmsh.model.occ.addLine(p_tags[0], p_tags[1])
    l2 = gmsh.model.occ.addLine(p_tags[1], p_tags[2])
    l3 = gmsh.model.occ.addLine(p_tags[2], p_tags[0])
    return gmsh.model.occ.addWire([l1, l2, l3], checkClosed=True)


def _triangle_prism(gmsh, pts_bottom: list[np.ndarray], dz: float) -> tuple[int, int]:
    """
    构建干净的三角柱设计域（单平面+拉伸），避免通过放样产生内部分割结构。
    返回拉伸得到的体 (dim=3, tag)。
    """
    wire = _triangle_wire(gmsh, pts_bottom)
    face = gmsh.model.occ.addPlaneSurface([wire])
    out = gmsh.model.occ.extrude([(2, face)], 0.0, 0.0, float(dz))
    for d, t in out:
        if int(d) == 3:
            return (3, int(t))
    raise RuntimeError("三角柱 extrude 未产生三维体。")


def _cluster_by_xy(cyls: list[CylinderAxis], tol: float = 5000.0) -> list[list[CylinderAxis]]:
    groups: list[list[CylinderAxis]] = []
    for c in cyls:
        p = c.center[:2]
        hit = None
        for g in groups:
            gc = np.mean(np.asarray([x.center[:2] for x in g], dtype=float), axis=0)
            if _norm(p - gc) <= tol:
                hit = g
                break
        if hit is None:
            groups.append([c])
        else:
            hit.append(c)
    return groups


def _pick_column_and_base(cluster: list[CylinderAxis]) -> tuple[CylinderAxis, CylinderAxis | None]:
    """
    在同一 xy 位置簇中选：
    - column: 细长主柱
    - base: 大半径短底座（可选）
    """
    if not cluster:
        raise ValueError("empty cluster")
    col = max(cluster, key=lambda c: c.length / max(c.radius, 1.0e-9))
    base_cands = [c for c in cluster if c.radius > 1.2 * col.radius and c.length < 0.8 * col.length]
    base = max(base_cands, key=lambda c: c.radius) if base_cands else None
    return col, base


def _merge_parallel_axis_pairs(vertical: list[CylinderAxis]) -> list[CylinderAxis]:
    """
    将同一圆柱被识别出的“双平行轴线”合并为真实中心轴：
    - 方向近似平行
    - 半径/长度近似一致
    - 两轴间距约为 2R
    """
    if not vertical:
        return []
    used: set[int] = set()
    out: list[CylinderAxis] = []
    cos_tol = math.cos(math.radians(2.0))
    for i, a in enumerate(vertical):
        if i in used:
            continue
        ua = a.direction
        La = a.length
        best_j = -1
        best_err = float("inf")
        for j in range(i + 1, len(vertical)):
            if j in used:
                continue
            b = vertical[j]
            ub = b.direction
            if abs(float(np.dot(ua, ub))) < cos_tol:
                continue
            rref = max(abs(a.radius), abs(b.radius), 1.0e-9)
            if abs(a.radius - b.radius) > 0.08 * rref:
                continue
            if abs(a.length - b.length) > 0.12 * max(La, b.length):
                continue
            dxy = _norm(a.center[:2] - b.center[:2])
            target = 2.0 * 0.5 * (a.radius + b.radius)
            err = abs(dxy - target)
            if dxy < 0.8 * target or dxy > 1.35 * target:
                continue
            if err < best_err:
                best_err = err
                best_j = j
        if best_j >= 0:
            b = vertical[best_j]
            used.add(i)
            used.add(best_j)
            p0 = 0.5 * (a.p0 + b.p0)
            p1 = 0.5 * (a.p1 + b.p1)
            out.append(CylinderAxis(p0=p0, p1=p1, radius=0.5 * (a.radius + b.radius)))
        else:
            used.add(i)
            out.append(a)
    return out


def _sort_outers_ccw(outers: list[CylinderAxis]) -> list[CylinderAxis]:
    """
    绕三根外柱围心逆时针排序。勿用中心柱 xy 作极角原点，否则中心略偏三角形
    围心时 atan2 会乱序，导致设计域三角与真实柱位旋转错位。
    """
    origin_xy = np.mean(np.asarray([c.center[:2] for c in outers], dtype=float), axis=0)

    def ang(c: CylinderAxis) -> float:
        d = c.center[:2] - origin_xy
        return math.atan2(float(d[1]), float(d[0]))

    return sorted(outers, key=ang)


def _beam_seg_mid_xyz(s) -> np.ndarray:
    return 0.5 * (np.asarray(s.p0, dtype=float) + np.asarray(s.p1, dtype=float))


def _cluster_beam_segs_by_mid_xy(segs: list, tol: float) -> list[list]:
    groups: list[list] = []
    for s in segs:
        xy = _beam_seg_mid_xyz(s)[:2]
        hit = None
        for g in groups:
            gc = np.mean([_beam_seg_mid_xyz(x)[:2] for x in g], axis=0)
            if _norm(xy - gc) <= tol:
                hit = g
                break
        if hit is None:
            groups.append([s])
        else:
            hit.append(s)
    return groups


def _cluster_representative_vertical_shaft(cluster: list) -> tuple[np.ndarray, float, float, float]:
    """
    用簇内最长竖向圆柱段代表整柱：中点 xy、半径取该段，z 取簇内并集。
    比单纯平均各段中点 xy 更贴近真实柱轴，布尔挖孔位置与半径与 IGS 一致。
    """
    if not cluster:
        raise ValueError("empty cluster")
    rep = max(
        cluster,
        key=lambda s: _norm(np.asarray(s.p1, dtype=float) - np.asarray(s.p0, dtype=float)),
    )
    p0 = np.asarray(rep.p0, dtype=float)
    p1 = np.asarray(rep.p1, dtype=float)
    mid = 0.5 * (p0 + p1)
    r = float(rep.radius)
    z_lo = min(min(float(s.p0[2]), float(s.p1[2])) for s in cluster)
    z_hi = max(max(float(s.p0[2]), float(s.p1[2])) for s in cluster)
    return mid[:2].copy(), r, z_lo, z_hi


def _triangle_area_xy2(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    ab = b - a
    ac = c - a
    return abs(float(ab[0] * ac[1] - ab[1] * ac[0])) * 0.5


def _sort_xy_ccw(points: list[np.ndarray], origin_xy: np.ndarray) -> list[np.ndarray]:
    def ang(p: np.ndarray) -> float:
        d = p - origin_xy
        return math.atan2(float(d[1]), float(d[0]))

    return sorted([p.copy() for p in points], key=ang)


def _greedy_match_xy_to_pontoons(
    query_xys: list[np.ndarray],
    targets: list[tuple[float, float, float, float, float]],
) -> tuple[list[tuple[float, float, float, float, float] | None], list[tuple[float, float, float, float, float]]]:
    if not targets:
        return [None] * len(query_xys), []
    pairs: list[tuple[float, int, int]] = []
    for i, q in enumerate(query_xys):
        for j, t in enumerate(targets):
            pairs.append((_norm(q[:2] - np.asarray(t[:2], dtype=float)), i, j))
    pairs.sort(key=lambda x: x[0])
    assigned_q: set[int] = set()
    assigned_j: set[int] = set()
    out: list[tuple[float, float, float, float, float] | None] = [None] * len(query_xys)
    for _, i, j in pairs:
        if i in assigned_q or j in assigned_j:
            continue
        out[i] = targets[j]
        assigned_q.add(i)
        assigned_j.add(j)
    unused = [targets[k] for k in range(len(targets)) if k not in assigned_j]
    return out, unused


def _oc4_cut_geometry_from_beams_segs(segs: list) -> Oc4CutGeometry | None:
    """
    由已解析的梁段列表构造 OC4 切口几何（半径、圆心均来自 IGS/OCC 圆柱段，不做尺度假设）。
    """
    vertical: list = []
    for s in segs:
        v = np.asarray(s.p1, dtype=float) - np.asarray(s.p0, dtype=float)
        L = _norm(v)
        if L <= 1.0e-9:
            continue
        if abs(float(v[2]) / L) < 0.85:
            continue
        vertical.append(s)

    shafts_long = [s for s in vertical if _norm(np.asarray(s.p1, dtype=float) - np.asarray(s.p0, dtype=float)) >= 15000.0]
    pontoon_segs = [
        s
        for s in vertical
        if _norm(np.asarray(s.p1, dtype=float) - np.asarray(s.p0, dtype=float)) <= 12000.0
        and float(s.radius) >= 3500.0
    ]
    if len(shafts_long) < 4 or len(pontoon_segs) < 3:
        return None

    shaft_specs: list[tuple[np.ndarray, float, float, float]] = []
    for g in _cluster_beam_segs_by_mid_xy(shafts_long, 6000.0):
        if not g:
            continue
        shaft_specs.append(_cluster_representative_vertical_shaft(g))

    center_cands = [(xy, r, z0, z1) for xy, r, z0, z1 in shaft_specs if 1100.0 <= r <= 2300.0]
    outer_cands = [(xy, r, z0, z1) for xy, r, z0, z1 in shaft_specs if 2400.0 <= r <= 4500.0]
    if not center_cands or len(outer_cands) < 3:
        return None

    center_xy, center_r, cz0, cz1 = max(center_cands, key=lambda t: (t[3] - t[2]))

    best_trip: tuple | None = None
    best_area = -1.0
    for trip in itertools.combinations(outer_cands, 3):
        xys = [t[0] for t in trip]
        area = _triangle_area_xy2(xys[0], xys[1], xys[2])
        if area > best_area:
            best_area = area
            best_trip = trip
    if best_trip is None:
        return None

    trip_xy = np.asarray([t[0] for t in best_trip], dtype=float)
    trip_centroid = np.mean(trip_xy, axis=0)
    outer_xy_ccw = _sort_xy_ccw([t[0].copy() for t in best_trip], trip_centroid)
    outer_rs: list[float] = []
    z_o_min = float("inf")
    z_o_max = float("-inf")
    for oxy in outer_xy_ccw:
        hit = min(best_trip, key=lambda t: float(np.sum((np.asarray(t[0], dtype=float) - np.asarray(oxy, dtype=float)) ** 2)))
        outer_rs.append(float(hit[1]))
        z_o_min = min(z_o_min, hit[2])
        z_o_max = max(z_o_max, hit[3])

    z_col_lo = min(cz0, z_o_min)
    z_col_hi = max(cz1, z_o_max)

    pontoon_targets: list[tuple[float, float, float, float, float]] = []
    for g in _cluster_beam_segs_by_mid_xy(pontoon_segs, 9000.0):
        if not g:
            continue
        rep = max(
            g,
            key=lambda s: _norm(np.asarray(s.p1, dtype=float) - np.asarray(s.p0, dtype=float)),
        )
        m = _beam_seg_mid_xyz(rep)
        z0 = min(float(rep.p0[2]), float(rep.p1[2]))
        z1 = max(float(rep.p0[2]), float(rep.p1[2]))
        pontoon_targets.append((float(m[0]), float(m[1]), float(rep.radius), z0, z1))

    outer_pontoons_l, unused_p = _greedy_match_xy_to_pontoons(outer_xy_ccw, pontoon_targets)
    center_pontoon: tuple[float, float, float, float, float] | None = None
    if unused_p:
        cp = min(unused_p, key=lambda p: _norm(np.asarray(p[:2], dtype=float) - center_xy))
        if _norm(np.asarray(cp[:2], dtype=float) - center_xy) <= 22000.0:
            center_pontoon = cp

    outer_pt_tuple: list[tuple[float, float, float, float, float] | None] = list(outer_pontoons_l)

    return Oc4CutGeometry(
        center_xy=center_xy.copy(),
        outer_xy_ccw=outer_xy_ccw,
        z_col_lo=float(z_col_lo),
        z_col_hi=float(z_col_hi),
        center_shaft_r=float(center_r),
        outer_shaft_rs=outer_rs,
        center_pontoon=center_pontoon,
        outer_pontoons=outer_pt_tuple,
    )


def _try_oc4_cut_geometry_from_beams(src_iges: Path) -> Oc4CutGeometry | None:
    try:
        from backend.tools.iges_beam_to_inp import _extract_beam_segments_from_iges  # type: ignore
        segs = _extract_beam_segments_from_iges(src_iges)
    except Exception:
        return None
    return _oc4_cut_geometry_from_beams_segs(segs)


def _horizontal_segments_lowest_tier(segs: list) -> list:
    """走向接近水平（与 IGS 弦杆识别一致）且处于全局最低水平层的梁段。"""
    horiz: list = []
    for s in segs:
        v = np.asarray(s.p1, dtype=float) - np.asarray(s.p0, dtype=float)
        L = _norm(v)
        if L <= 1.0e-9:
            continue
        if abs(float(v[2]) / L) > 0.28:
            continue
        horiz.append(s)
    if len(horiz) < 3:
        return []
    zcenters = [0.5 * (float(s.p0[2]) + float(s.p1[2])) for s in horiz]
    z0 = float(min(zcenters))
    z_tol = 2500.0
    bucket: list = []
    for s, zc in zip(horiz, zcenters):
        if abs(zc - z0) <= z_tol:
            bucket.append(s)
    return bucket


def _pontoon_top_z_from_beams(segs: list) -> float | None:
    """粗短竖向圆柱（桩靴）顶面 z：与外柱柱身起点一致，取自 IGS。"""
    best: float | None = None
    for s in segs:
        v = np.asarray(s.p1, dtype=float) - np.asarray(s.p0, dtype=float)
        L = _norm(v)
        if L <= 1.0e-9:
            continue
        if abs(float(v[2]) / L) < 0.85:
            continue
        if float(s.radius) < 4000.0:
            continue
        if L > 13000.0:
            continue
        z_hi = max(float(s.p0[2]), float(s.p1[2]))
        best = z_hi if best is None else max(best, z_hi)
    return best


def _design_domain_z_bounds_from_beams(segs: list) -> tuple[float, float] | None:
    """
    设计域竖向范围全部由梁段端点推导：
    - 顶：桩靴圆柱上端 z（柱身起始标高，OC4 外柱为 -14000）。
    - 底：最低层水平弦杆下端 z（轴线最低点 − 该层最大半径）。
    """
    bucket = _horizontal_segments_lowest_tier(segs)
    if not bucket:
        return None
    z_p_top = _pontoon_top_z_from_beams(segs)
    if z_p_top is None:
        return None
    r_max = max(float(s.radius) for s in bucket)
    z_end_min = min(min(float(s.p0[2]), float(s.p1[2])) for s in bucket)
    z_bot = float(z_end_min) - float(r_max)
    z_top = float(z_p_top)
    if z_top <= z_bot + 10.0:
        return None
    return z_bot, z_top


def _non_vertical_beam_z_span_and_pad(segs: list) -> tuple[float, float, float]:
    """
    水平 + 斜梁（排除近似竖杆）在全局的 z 范围，及竖向余量。
    用于把棱柱包络拉高/压低，包住上层甲板弦杆与下层水平梁系（原逻辑顶面仅用桩靴顶会偏矮）。
    """
    zs: list[float] = []
    rmax = 0.0
    for s in segs:
        v = np.asarray(s.p1, dtype=float) - np.asarray(s.p0, dtype=float)
        L = _norm(v)
        if L <= 1.0e-9:
            continue
        if abs(float(v[2]) / L) >= 0.82:
            continue
        zs.extend([float(s.p0[2]), float(s.p1[2])])
        rmax = max(rmax, float(s.radius))
    if len(zs) < 2:
        return 0.0, 0.0, 0.0
    span = float(max(zs) - min(zs))
    pad = max(5000.0, 1.4 * rmax, 0.045 * span)
    return float(min(zs)), float(max(zs)), float(pad)


def _merge_z_bounds_with_brace_envelope(z_base: tuple[float, float], segs: list) -> tuple[float, float]:
    """将弦杆/斜梁 z 包络与原有桩靴—底弦推导范围取并集。"""
    z_lo_b, z_hi_b = float(z_base[0]), float(z_base[1])
    lo, hi, pad = _non_vertical_beam_z_span_and_pad(segs)
    if not hi > lo:
        return z_lo_b, z_hi_b
    z_bot = min(z_lo_b, lo - pad)
    z_top = max(z_hi_b, hi + pad)
    if z_top <= z_bot + 500.0:
        return z_lo_b, z_hi_b
    return z_bot, z_top


def _triangle_xy_pad_from_beam_geom(beam_geom: Oc4CutGeometry) -> float:
    """
    三角柱顶点沿外柱径向外扩量：使底面三角形覆盖各外柱桩靴圆盘（由桩靴圆心相对柱轴几何推导）。
    """
    C = np.asarray(beam_geom.center_xy, dtype=float)
    pads: list[float] = []
    for oxy, op in zip(beam_geom.outer_xy_ccw, beam_geom.outer_pontoons):
        if op is None:
            continue
        O = np.asarray(oxy, dtype=float)
        P = np.asarray(op[:2], dtype=float)
        Rp = float(op[2])
        d_o = float(np.linalg.norm(O - C))
        if d_o <= 1.0e-6:
            continue
        u = (O - C) / d_o
        proj = float(np.dot(P - C, u))
        need_vertex_radius = proj + Rp
        pads.append(max(0.0, need_vertex_radius - d_o))
    if not pads:
        ro = float(np.mean(beam_geom.outer_shaft_rs)) if beam_geom.outer_shaft_rs else 3000.0
        return max(1600.0, 0.48 * ro)
    return float(max(pads)) + 10.0


def _greedy_match_outers_to_bases(outers: list[CylinderAxis], bases: list[CylinderAxis]) -> list[CylinderAxis | None]:
    """
    一对一匹配外柱与底座，避免“各自最近”把同一底座分给两根柱造成切口尺寸错误。
    """
    if not bases:
        return [None] * len(outers)
    pairs: list[tuple[float, int, int]] = []
    for i, oc in enumerate(outers):
        for j, bc in enumerate(bases):
            pairs.append((_norm(oc.center[:2] - bc.center[:2]), i, j))
    pairs.sort(key=lambda x: x[0])
    assigned_o: set[int] = set()
    assigned_b: set[int] = set()
    out: list[CylinderAxis | None] = [None] * len(outers)
    for _, i, j in pairs:
        if i in assigned_o or j in assigned_b:
            continue
        out[i] = bases[j]
        assigned_o.add(i)
        assigned_b.add(j)
    return out


def _pick_oc4_key_columns(
    vertical: list[CylinderAxis],
) -> tuple[CylinderAxis, list[CylinderAxis], list[CylinderAxis | None], CylinderAxis | None]:
    """
    选择 OC4 关键柱：
    - center: 中央细柱（r≈1625, 长细比高）
    - outers: 三根外柱（r≈3000，绕中心 CCW 排序）
    - outer_bases: 与 outers 同序的一对一底座（大半径短柱段）
    - center_base: 中心柱下方粗底座（若有）
    """
    center_cands = [c for c in vertical if 1200.0 <= c.radius <= 2200.0 and c.length >= 20000.0]
    if not center_cands:
        raise ValueError("未识别到中心细柱。")

    # 选更接近全局几何中心且 Y 偏上者，稳定落在 OC4 中柱
    xy_all = np.asarray([c.center[:2] for c in vertical], dtype=float)
    gc = np.mean(xy_all, axis=0)
    center_col = sorted(center_cands, key=lambda c: (_norm(c.center[:2] - gc), -float(c.center[1])))[0]

    outer_cands = [c for c in vertical if c.length >= 18000.0 and c is not center_col]
    if len(outer_cands) < 3:
        # 容错：用最长三根（除中心柱）作为外柱
        tmp = [c for c in vertical if c is not center_col]
        tmp = sorted(tmp, key=lambda c: c.length, reverse=True)
        outer_cands = tmp[:3]
    if len(outer_cands) < 3:
        raise ValueError("未识别到足够外柱。")
    # 从候选里选出面积最大的三角形（对应三外柱）
    best_trip: tuple[CylinderAxis, CylinderAxis, CylinderAxis] | None = None
    best_area = -1.0
    n = len(outer_cands)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                a = outer_cands[i].center[:2]
                b = outer_cands[j].center[:2]
                c = outer_cands[k].center[:2]
                ab = b - a
                ac = c - a
                area = abs(float(ab[0] * ac[1] - ab[1] * ac[0])) * 0.5
                if area > best_area:
                    best_area = area
                    best_trip = (outer_cands[i], outer_cands[j], outer_cands[k])
    if best_trip is None:
        raise ValueError("外柱三角形识别失败。")
    outers = _sort_outers_ccw(list(best_trip))

    r_outer_max = max(o.radius for o in outers)
    outer_ids = {id(o) for o in outers}
    base_cands = [
        c
        for c in vertical
        if id(c) != id(center_col)
        and id(c) not in outer_ids
        and c.length <= 12000.0
        and c.radius >= 0.9 * r_outer_max
    ]
    outer_bases = _greedy_match_outers_to_bases(outers, base_cands)

    center_base: CylinderAxis | None = None
    for c in vertical:
        if id(c) == id(center_col) or id(c) in outer_ids:
            continue
        if c.length > 12000.0 or c.radius < 1.15 * float(center_col.radius):
            continue
        if _norm(c.center[:2] - center_col.center[:2]) > 3500.0:
            continue
        if center_base is None or c.radius > center_base.radius:
            center_base = c

    return center_col, outers, outer_bases, center_base


def _estimate_brace_z_range(src_iges: Path) -> tuple[float, float] | None:
    """
    从原始 IGS 的梁中心线估计“上下斜梁”高度包络。
    """
    try:
        from backend.tools.iges_beam_to_inp import _extract_beam_segments_from_iges  # type: ignore
    except Exception:
        return None
    try:
        segs = _extract_beam_segments_from_iges(src_iges)
    except Exception:
        return None
    if not segs:
        return None
    z_vals: list[float] = []
    for s in segs:
        v = s.p1 - s.p0
        L = _norm(v)
        if L <= 1.0e-9:
            continue
        # 重点取斜梁/横梁，排除几乎竖向柱
        if abs(float(v[2]) / L) >= 0.8:
            continue
        z_vals.append(float(s.p0[2]))
        z_vals.append(float(s.p1[2]))
    if len(z_vals) < 4:
        return None
    zmin = float(min(z_vals))
    zmax = float(max(z_vals))
    return zmin, zmax


def _bottom_horizontal_chord_bucket(src_iges: Path) -> list:
    """
    识别最下层水平弦杆所在梁段分组（走向接近水平且处于全局最低水平层）。
    返回 BeamSeg 列表，供底面包络与半径读取。
    """
    try:
        from backend.tools.iges_beam_to_inp import BeamSeg, _extract_beam_segments_from_iges  # type: ignore
    except Exception:
        return []
    try:
        segs = _extract_beam_segments_from_iges(src_iges)
    except Exception:
        return []
    horiz: list[BeamSeg] = []
    for s in segs:
        v = s.p1 - s.p0
        L = _norm(v)
        if L <= 1.0e-9:
            continue
        if abs(float(v[2]) / L) > 0.28:
            continue
        horiz.append(s)
    if len(horiz) < 3:
        return []
    zcenters = [0.5 * (float(s.p0[2]) + float(s.p1[2])) for s in horiz]
    z0 = float(min(zcenters))
    bucket: list[BeamSeg] = []
    z_tol = 2500.0
    for s, zc in zip(horiz, zcenters):
        if abs(zc - z0) <= z_tol:
            bucket.append(s)
    return bucket


def _bottom_horizontal_envelope_z_low(src_iges: Path, margin: float = 600.0) -> float | None:
    """
    用最下层水平梁的原始端点 z 与半径估计包络底面 z：
    设计域底面应低于梁轴线高度一层半径 + margin，使实体包住下方弦杆。
    """
    bucket = _bottom_horizontal_chord_bucket(src_iges)
    if not bucket:
        return None
    z_end_min = min(min(float(s.p0[2]), float(s.p1[2])) for s in bucket)
    r_max = max(float(s.radius) for s in bucket)
    return float(z_end_min) - float(r_max) - float(margin)


def _vertical_cylinder_volume_tag(
    gmsh,
    cx: float,
    cy: float,
    z_lo: float,
    z_hi: float,
    radius: float,
) -> int:
    """轴线沿 +Z、竖直圆柱体（用于布尔减柱子）。"""
    h = float(z_hi - z_lo)
    if h <= 1.0e-6:
        h = 1.0
    return int(gmsh.model.occ.addCylinder(float(cx), float(cy), float(z_lo), 0.0, 0.0, h, float(radius)))


def _axis_vertical_z_span(col: CylinderAxis) -> tuple[float, float]:
    return float(min(col.p0[2], col.p1[2])), float(max(col.p0[2], col.p1[2]))


def _append_shaft_cut_xy(
    cut_tools: list[tuple[int, int]],
    gmsh,
    cx: float,
    cy: float,
    r: float,
    z_bot: float,
    z_top: float,
    z_cut_pad: float,
    r_cut_pad: float,
) -> None:
    cut_tools.append(
        (
            3,
            _vertical_cylinder_volume_tag(
                gmsh,
                float(cx),
                float(cy),
                z_bot - z_cut_pad,
                z_top + z_cut_pad,
                float(r) + r_cut_pad,
            ),
        )
    )


def _append_column_shaft_cut(
    cut_tools: list[tuple[int, int]],
    gmsh,
    col: CylinderAxis,
    z_bot: float,
    z_top: float,
    z_cut_pad: float,
    r_cut_pad: float,
) -> None:
    """柱身段：轴线位置与解析半径来自 revolution 识别。"""
    _append_shaft_cut_xy(
        cut_tools,
        gmsh,
        float(col.center[0]),
        float(col.center[1]),
        float(col.radius),
        z_bot,
        z_top,
        z_cut_pad,
        r_cut_pad,
    )


def _append_pontoon_tuple_cut(
    cut_tools: list[tuple[int, int]],
    gmsh,
    spec: tuple[float, float, float, float, float],
    z_bot: float,
    z_top: float,
    z_cut_pad: float,
    r_cut_pad: float,
) -> None:
    cx, cy, r, z0, z1 = spec
    zb_lo = max(z_bot - z_cut_pad, z0 - z_cut_pad)
    zb_hi = min(z_top + z_cut_pad, z1 + z_cut_pad)
    # 设计域较矮时交集可能过窄，改用整段棱柱高度承载桩靴圆柱，保证与大桩靴可靠相交
    if zb_hi <= zb_lo + 80.0:
        zb_lo = z_bot - z_cut_pad
        zb_hi = z_top + z_cut_pad
    if zb_hi <= zb_lo + 10.0:
        return
    cut_tools.append(
        (
            3,
            _vertical_cylinder_volume_tag(
                gmsh,
                float(cx),
                float(cy),
                zb_lo,
                zb_hi,
                float(r) + r_cut_pad,
            ),
        )
    )


def _boolean_radial_eps(r: float) -> float:
    """布尔运算微小半径裕量（mm），仅抵消 OCC 容差，数值来自 max(5, 0.15%·r)。"""
    return max(5.0, 0.0015 * float(r))


def _append_pontoon_base_cut(
    cut_tools: list[tuple[int, int]],
    gmsh,
    base: CylinderAxis,
    z_bot: float,
    z_top: float,
    z_cut_pad: float,
    r_cut_pad: float,
) -> None:
    """
    粗大底座：使用底座自身的 xy 中心与半径（可能与柱轴错位），竖向范围取底座轴段与设计域的交集。
    无交集则跳过，避免大半径工具沿全高误切。
    """
    z0, z1 = _axis_vertical_z_span(base)
    zb_lo = max(z_bot - z_cut_pad, z0 - z_cut_pad)
    zb_hi = min(z_top + z_cut_pad, z1 + z_cut_pad)
    if zb_hi <= zb_lo + 80.0:
        zb_lo = z_bot - z_cut_pad
        zb_hi = z_top + z_cut_pad
    if zb_hi <= zb_lo + 10.0:
        return
    cut_tools.append(
        (
            3,
            _vertical_cylinder_volume_tag(
                gmsh,
                float(base.center[0]),
                float(base.center[1]),
                zb_lo,
                zb_hi,
                float(base.radius) + r_cut_pad,
            ),
        )
    )


def build_oc4_design_domain_iges(
    src_iges: Path,
    out_iges: Path,
    *,
    out_step: Path | None = None,
    cut_center_column: bool = True,
    include_source_geometry: bool = False,
) -> Path:
    segs_cache: list | None = None
    try:
        from backend.tools.iges_beam_to_inp import _extract_beam_segments_from_iges  # type: ignore

        segs_cache = _extract_beam_segments_from_iges(src_iges)
    except Exception:
        segs_cache = None

    beam_geom = _oc4_cut_geometry_from_beams_segs(segs_cache) if segs_cache else None
    z_bounds = _design_domain_z_bounds_from_beams(segs_cache) if segs_cache else None

    brace_zr: tuple[float, float] | None = None
    z_low_envelope: float | None = None
    if z_bounds is None:
        brace_zr = _estimate_brace_z_range(src_iges)
        z_low_envelope = _bottom_horizontal_envelope_z_low(src_iges)

    center_col: CylinderAxis | None = None
    outer_cols: list[CylinderAxis] = []
    outer_bases: list[CylinderAxis | None] = []
    center_base: CylinderAxis | None = None

    if beam_geom is None:
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
            raise ValueError("识别到的主立柱不足，无法构建设计域。")
        center_col, outer_cols, outer_bases, center_base = _pick_oc4_key_columns(vertical)

    # 须在 gmsh.initialize() 之前算完所有会 merge/mesh 的梁解析，否则会 finalize 掉当前会话

    # 仅构建布尔后的设计域实体；默认不再 merge 源 IGS，避免导出文件里整船架与设计域
    # 叠在一起（预览像“未挖孔”或严重错位）。需要对照原模型时设 include_source_geometry=True。
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("oc4_design_domain")
        if include_source_geometry:
            gmsh.merge(str(src_iges.resolve()))
            gmsh.model.occ.synchronize()

        # 1) 构建中部“实心设计域”（三角柱体，接近图二绿色域）
        if beam_geom is not None:
            cxy = beam_geom.center_xy
            outer_xy = beam_geom.outer_xy_ccw
            z0_main = beam_geom.z_col_lo
            z1_main = beam_geom.z_col_hi
        else:
            assert center_col is not None
            cxy = center_col.center[:2]
            outer_xy = [o.center[:2].copy() for o in _sort_outers_ccw(list(outer_cols))]
            z0_main = float(min(center_col.p0[2], center_col.p1[2]))
            z1_main = float(max(center_col.p0[2], center_col.p1[2]))
        # 竖向：优先完全由 IGS 梁段推导（下层弦杆下端 ↔ 桩靴顶/柱身起点）；否则退回旧启发式
        if z_bounds is not None:
            z_bot, z_top = float(z_bounds[0]), float(z_bounds[1])
        elif brace_zr is not None:
            z_top = min(z1_main - 500.0, brace_zr[1] + 800.0)
            if z_low_envelope is not None:
                z_bot = min(z0_main + 100.0, float(z_low_envelope))
            else:
                z_bot = min(z0_main + 100.0, brace_zr[0] - 2500.0)
        else:
            z_top = z0_main + 0.78 * (z1_main - z0_main)
            z_bot = z0_main + 0.10 * (z1_main - z0_main)
        if z_top <= z_bot + 1000.0:
            z_bot = z0_main + 0.22 * (z1_main - z0_main)
            z_top = z0_main + 0.82 * (z1_main - z0_main)

        if segs_cache:
            z_bot, z_top = _merge_z_bounds_with_brace_envelope((z_bot, z_top), segs_cache)

        # 平面外扩：由桩靴圆心相对柱轴几何确定（与 oc4.igs 一致），不用经验系数
        low_pts: list[np.ndarray] = []
        if beam_geom is not None:
            xy_pad = _triangle_xy_pad_from_beam_geom(beam_geom)
        else:
            r_outer = float(np.mean([o.radius for o in outer_cols])) if outer_cols else 3000.0
            xy_pad = max(1600.0, 0.48 * r_outer)
        outer_xy_arr = np.asarray(outer_xy, dtype=float)
        # 外扩方向用三边柱围心 → 各顶点，避免中心柱 xy 与围心不一致时三角整体跑偏
        radial_origin = np.mean(outer_xy_arr, axis=0) if outer_xy_arr.shape[0] >= 2 else np.asarray(cxy, dtype=float)
        for pxy in outer_xy:
            vxy = np.asarray(pxy, dtype=float) - radial_origin
            nv = _norm(vxy)
            if nv <= 1.0e-9:
                pxy2 = np.asarray(pxy, dtype=float).copy()
            else:
                pxy2 = np.asarray(pxy, dtype=float) + (vxy / nv) * xy_pad
            low_pts.append(np.array([pxy2[0], pxy2[1], z_bot], dtype=float))
        prism_vol = _triangle_prism(gmsh, low_pts, dz=float(z_top - z_bot))

        gmsh.model.occ.synchronize()

        # 2) 扣除柱身 + 桩靴：优先用梁中心线原始半径与桩靴圆心（对称一致）；回退时用 revolution
        z_span = float(z_top - z_bot)
        z_cut_pad = max(1200.0, min(6000.0, 0.06 * z_span))
        cut_tools: list[tuple[int, int]] = []
        if beam_geom is not None:
            if cut_center_column:
                _append_shaft_cut_xy(
                    cut_tools,
                    gmsh,
                    float(beam_geom.center_xy[0]),
                    float(beam_geom.center_xy[1]),
                    beam_geom.center_shaft_r,
                    z_bot,
                    z_top,
                    z_cut_pad,
                    _boolean_radial_eps(beam_geom.center_shaft_r),
                )
                if beam_geom.center_pontoon is not None:
                    _append_pontoon_tuple_cut(
                        cut_tools,
                        gmsh,
                        beam_geom.center_pontoon,
                        z_bot,
                        z_top,
                        z_cut_pad,
                        _boolean_radial_eps(beam_geom.center_pontoon[2]),
                    )
            if len(beam_geom.outer_xy_ccw) != len(beam_geom.outer_shaft_rs) or len(beam_geom.outer_xy_ccw) != len(
                beam_geom.outer_pontoons
            ):
                raise ValueError("梁解析外柱与桩靴列表长度不一致。")
            for oxy, r_shaft, op in zip(beam_geom.outer_xy_ccw, beam_geom.outer_shaft_rs, beam_geom.outer_pontoons):
                _append_shaft_cut_xy(
                    cut_tools,
                    gmsh,
                    float(oxy[0]),
                    float(oxy[1]),
                    float(r_shaft),
                    z_bot,
                    z_top,
                    z_cut_pad,
                    _boolean_radial_eps(float(r_shaft)),
                )
                if op is not None:
                    _append_pontoon_tuple_cut(
                        cut_tools,
                        gmsh,
                        op,
                        z_bot,
                        z_top,
                        z_cut_pad,
                        _boolean_radial_eps(op[2]),
                    )
        else:
            assert center_col is not None
            if cut_center_column:
                _append_shaft_cut_xy(
                    cut_tools,
                    gmsh,
                    float(center_col.center[0]),
                    float(center_col.center[1]),
                    float(center_col.radius),
                    z_bot,
                    z_top,
                    z_cut_pad,
                    _boolean_radial_eps(float(center_col.radius)),
                )
                if center_base is not None:
                    _append_pontoon_base_cut(
                        cut_tools,
                        gmsh,
                        center_base,
                        z_bot,
                        z_top,
                        z_cut_pad,
                        _boolean_radial_eps(float(center_base.radius)),
                    )
            for oc, obase in zip(outer_cols, outer_bases):
                _append_shaft_cut_xy(
                    cut_tools,
                    gmsh,
                    float(oc.center[0]),
                    float(oc.center[1]),
                    float(oc.radius),
                    z_bot,
                    z_top,
                    z_cut_pad,
                    _boolean_radial_eps(float(oc.radius)),
                )
                if obase is not None:
                    _append_pontoon_base_cut(
                        cut_tools,
                        gmsh,
                        obase,
                        z_bot,
                        z_top,
                        z_cut_pad,
                        _boolean_radial_eps(float(obase.radius)),
                    )
        gmsh.model.occ.cut([prism_vol], cut_tools, removeObject=True, removeTool=True)

        gmsh.model.occ.synchronize()

        # Keep topology stable for IGES export; aggressive heal can break import
        # in some OCC readers for this specific model.
        try:
            gmsh.model.occ.removeAllDuplicates()
            gmsh.model.occ.synchronize()
        except Exception:
            pass

        out_iges = out_iges.resolve()
        out_iges.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(out_iges))
        if out_step is not None:
            out_step = out_step.resolve()
            out_step.parent.mkdir(parents=True, exist_ok=True)
            gmsh.write(str(out_step))
        return out_iges
    finally:
        try:
            gmsh.finalize()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Create OC4 design-domain style IGS from source IGS.")
    parser.add_argument("src_iges", type=str, help="Source IGES path")
    parser.add_argument("out_iges", type=str, help="Output IGES path")
    parser.add_argument(
        "--step",
        type=str,
        default=None,
        metavar="PATH",
        help="Also write STEP (.step/.stp) of the same model",
    )
    parser.add_argument(
        "--edge-columns-only",
        action="store_true",
        help="仅挖三根边柱（及桩靴），不挖中心柱；默认会同时挖中心柱与边柱。",
    )
    parser.add_argument(
        "--include-source",
        action="store_true",
        help="把源 IGS 几何一并 merge 进模型再导出（仅调试用，默认只导出设计域实体）。",
    )
    args = parser.parse_args()
    build_oc4_design_domain_iges(
        Path(args.src_iges),
        Path(args.out_iges),
        out_step=Path(args.step) if args.step else None,
        cut_center_column=not args.edge_columns_only,
        include_source_geometry=bool(args.include_source),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
