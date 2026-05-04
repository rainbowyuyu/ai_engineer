from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np

# Suppress noisy Qt widget warnings in headless/batch conversion runs.
os.environ.setdefault("QT_LOGGING_RULES", "qt.widgets.qgraphicsview.warning=false")


@dataclass
class BeamSeg:
    p0: np.ndarray
    p1: np.ndarray
    radius: float
    source: str


@dataclass
class LineSeg:
    p0: np.ndarray
    p1: np.ndarray


def _try_import_occ():
    try:
        from OCC.Core.BRep import BRep_Tool  # type: ignore
        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface  # type: ignore
        from OCC.Core.GeomAbs import GeomAbs_Cylinder  # type: ignore
        from OCC.Core.IGESControl import IGESControl_Reader  # type: ignore
        from OCC.Core.IFSelect import IFSelect_RetDone  # type: ignore
        from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_VERTEX  # type: ignore
        from OCC.Core.TopExp import TopExp_Explorer  # type: ignore
        from OCC.Core.TopoDS import topods_Face, topods_Vertex  # type: ignore

        return {
            "BRep_Tool": BRep_Tool,
            "BRepAdaptor_Surface": BRepAdaptor_Surface,
            "GeomAbs_Cylinder": GeomAbs_Cylinder,
            "IGESControl_Reader": IGESControl_Reader,
            "IFSelect_RetDone": IFSelect_RetDone,
            "TopAbs_FACE": TopAbs_FACE,
            "TopAbs_VERTEX": TopAbs_VERTEX,
            "TopExp_Explorer": TopExp_Explorer,
            "topods_Face": topods_Face,
            "topods_Vertex": topods_Vertex,
        }
    except Exception:
        return None


def _canon_dir(v: np.ndarray) -> np.ndarray:
    u = _unit(v)
    for x in u:
        if abs(float(x)) > 1.0e-12:
            if x < 0:
                return -u
            break
    return u


def _line_offset_key(point: np.ndarray, direction: np.ndarray) -> np.ndarray:
    return point - direction * float(np.dot(point, direction))


def _occ_extract_cylinder_segments(iges_path: Path) -> list[BeamSeg]:
    occ = _try_import_occ()
    if occ is None:
        return []

    reader = occ["IGESControl_Reader"]()
    status = reader.ReadFile(str(iges_path.resolve()))
    if status != occ["IFSelect_RetDone"]:
        return []
    reader.TransferRoots()
    shape = reader.OneShape()
    exp = occ["TopExp_Explorer"](shape, occ["TopAbs_FACE"])
    raw: list[BeamSeg] = []
    while exp.More():
        face = occ["topods_Face"](exp.Current())
        surf = occ["BRepAdaptor_Surface"](face, True)
        if surf.GetType() != occ["GeomAbs_Cylinder"]:
            exp.Next()
            continue
        cyl = surf.Cylinder()
        axis = cyl.Axis()
        loc = axis.Location()
        dire = axis.Direction()
        p = np.asarray([loc.X(), loc.Y(), loc.Z()], dtype=float)
        d = _canon_dir(np.asarray([dire.X(), dire.Y(), dire.Z()], dtype=float))
        radius = float(cyl.Radius())

        vx = occ["TopExp_Explorer"](face, occ["TopAbs_VERTEX"])
        ts: list[float] = []
        while vx.More():
            vtx = occ["topods_Vertex"](vx.Current())
            pp = occ["BRep_Tool"].Pnt(vtx)
            q = np.asarray([pp.X(), pp.Y(), pp.Z()], dtype=float)
            ts.append(float(np.dot(q - p, d)))
            vx.Next()
        if len(ts) < 2:
            exp.Next()
            continue
        tmin = min(ts)
        tmax = max(ts)
        if tmax - tmin <= 1.0e-6:
            exp.Next()
            continue
        p0 = p + d * tmin
        p1 = p + d * tmax
        raw.append(BeamSeg(p0=p0, p1=p1, radius=radius, source="occ_cylinder"))
        exp.Next()

    # 同轴同半径分组并合并区间
    groups: list[dict] = []
    cos_tol = math.cos(math.radians(2.0))
    for s in raw:
        d = _canon_dir(s.p1 - s.p0)
        if _segment_length(s.p0, s.p1) <= 1.0e-6:
            continue
        ref = _line_offset_key(s.p0, d)
        hit = None
        for g in groups:
            if abs(float(np.dot(d, g["d"]))) < cos_tol:
                continue
            rref = max(abs(g["r"]), abs(s.radius), 1.0e-9)
            if abs(g["r"] - s.radius) > 0.03 * rref:
                continue
            if _norm(ref - g["ref"]) > max(1.0e-3, 0.1 * s.radius):
                continue
            hit = g
            break
        if hit is None:
            groups.append({"d": d, "ref": ref, "r": s.radius, "ints": [(s.p0, s.p1)]})
        else:
            hit["ints"].append((s.p0, s.p1))

    merged: list[BeamSeg] = []
    for g in groups:
        d = g["d"]
        ref = g["ref"]
        ts: list[float] = []
        for a, b in g["ints"]:
            ts.append(float(np.dot(a - ref, d)))
            ts.append(float(np.dot(b - ref, d)))
        t0 = min(ts)
        t1 = max(ts)
        if t1 - t0 <= 1.0e-6:
            continue
        p0 = ref + d * t0
        p1 = ref + d * t1
        merged.append(BeamSeg(p0=p0, p1=p1, radius=float(g["r"]), source="occ_merged"))
    return _cleanup_duplicate_beam_segments(_dedup_segments(merged, pos_tol=1.0e-3, ang_tol_deg=2.0))


def _norm(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def _unit(v: np.ndarray) -> np.ndarray:
    n = _norm(v)
    if n <= 0.0:
        return np.array([1.0, 0.0, 0.0], dtype=float)
    return v / n


def _segment_length(p0: np.ndarray, p1: np.ndarray) -> float:
    return _norm(p1 - p0)


def _curve_radius_from_length(gmsh, curve_tag: int) -> float | None:
    try:
        if gmsh.model.getType(1, curve_tag).lower() != "circle":
            return None
    except Exception:
        return None
    try:
        length = float(gmsh.model.occ.getMass(1, int(curve_tag)))
    except Exception:
        return None
    if not math.isfinite(length) or length <= 0.0:
        return None
    return length / (2.0 * math.pi)


def _extract_from_revolution_surface(gmsh, s_tag: int) -> BeamSeg | None:
    try:
        s_type = gmsh.model.getType(2, s_tag).lower()
    except Exception:
        return None
    if "revolution" not in s_type:
        return None
    try:
        bnd = gmsh.model.getBoundary([(2, int(s_tag))], oriented=False, recursive=False)
    except Exception:
        return None
    circles: list[int] = [t for d, t in bnd if d == 1 and gmsh.model.getType(1, t).lower() == "circle"]
    if len(circles) < 2:
        return None
    c_data: list[tuple[np.ndarray, float, int]] = []
    for c in circles:
        try:
            ctr = np.asarray(gmsh.model.occ.getCenterOfMass(1, int(c)), dtype=float)
        except Exception:
            continue
        r = _curve_radius_from_length(gmsh, int(c))
        if r is None:
            continue
        c_data.append((ctr, float(r), int(c)))
    if len(c_data) < 2:
        return None
    best_i, best_j = 0, 1
    best_d = -1.0
    for i in range(len(c_data)):
        for j in range(i + 1, len(c_data)):
            d = _norm(c_data[i][0] - c_data[j][0])
            if d > best_d:
                best_d = d
                best_i, best_j = i, j
    p0 = c_data[best_i][0]
    p1 = c_data[best_j][0]
    if _segment_length(p0, p1) <= 1.0e-9:
        return None
    r = 0.5 * (c_data[best_i][1] + c_data[best_j][1])
    return BeamSeg(p0=p0, p1=p1, radius=float(r), source="analytic")


def _extract_from_circle_boundaries(gmsh, s_tag: int) -> BeamSeg | None:
    """
    从任意面上“成对圆边”提取柱轴，避免对自由曲面做宽松拟合造成乱线。
    """
    try:
        bnd = gmsh.model.getBoundary([(2, int(s_tag))], oriented=False, recursive=False)
    except Exception:
        return None
    circles: list[tuple[np.ndarray, float]] = []
    for d, t in bnd:
        if d != 1:
            continue
        try:
            if gmsh.model.getType(1, int(t)).lower() != "circle":
                continue
            ctr = np.asarray(gmsh.model.occ.getCenterOfMass(1, int(t)), dtype=float)
        except Exception:
            continue
        r = _curve_radius_from_length(gmsh, int(t))
        if r is None or r <= 0.0:
            continue
        circles.append((ctr, float(r)))
    if len(circles) < 2:
        return None
    # 仅连接半径相近的圆，过滤装饰边与复杂拼接边。
    best: tuple[np.ndarray, np.ndarray, float] | None = None
    best_d = -1.0
    for i in range(len(circles)):
        c1, r1 = circles[i]
        for j in range(i + 1, len(circles)):
            c2, r2 = circles[j]
            r_ref = max(abs(r1), abs(r2), 1.0e-9)
            if abs(r1 - r2) > 0.05 * r_ref:
                continue
            d = _norm(c1 - c2)
            if d > best_d:
                best_d = d
                best = (c1, c2, 0.5 * (r1 + r2))
    if best is None or best_d <= 1.0e-9:
        return None
    p0, p1, r = best
    return BeamSeg(p0=p0, p1=p1, radius=float(r), source="circle_pair")


def _fit_axis_from_surface_nodes_strict(gmsh, s_tag: int) -> BeamSeg | None:
    """
    对疑似柱面做严格拟合：
    - 仅接受“沿轴向拉长 + 径向半径稳定”的面
    - 过滤平面/自由曲面，避免错误抽线
    """
    try:
        node_tags, coords, _ = gmsh.model.mesh.getNodes(2, int(s_tag), includeBoundary=True)
    except Exception:
        return None
    if len(node_tags) < 24 or len(coords) < 72:
        return None
    pts = np.asarray(coords, dtype=float).reshape((-1, 3))
    center = pts.mean(axis=0)
    x = pts - center

    cov = (x.T @ x) / max(1, x.shape[0] - 1)
    w, v = np.linalg.eigh(cov)
    order = np.argsort(w)[::-1]
    w = w[order]
    v = v[:, order]
    # w[0] 最大方向作为轴向
    axis = _unit(v[:, 0])
    s = x @ axis
    smin = float(np.min(s))
    smax = float(np.max(s))
    span = smax - smin
    if span <= 1.0e-6:
        return None

    proj = center + np.outer(s, axis)
    rr = np.linalg.norm(pts - proj, axis=1)
    r_med = float(np.median(rr))
    if not math.isfinite(r_med) or r_med <= 1.0e-6:
        return None
    r_std = float(np.std(rr))
    cv = r_std / max(r_med, 1.0e-12)

    # 柱面判据（经验阈值，偏保守）
    # 1) 沿轴向明显拉长
    if span < 1.2 * r_med:
        return None
    # 2) 半径应较稳定
    if cv > 0.20:
        return None
    # 3) 避免近平面：最小主值不能极小（相对第二主值）
    #    平面通常 w2 << w1，且法向离散很小
    if w[2] < 0.01 * max(w[1], 1.0e-12):
        return None

    p0 = center + smin * axis
    p1 = center + smax * axis
    if _segment_length(p0, p1) <= 1.0e-6:
        return None
    return BeamSeg(p0=p0, p1=p1, radius=r_med, source="fit_strict")


def _dedup_segments(segs: list[BeamSeg], pos_tol: float = 1.0e-3, ang_tol_deg: float = 3.0) -> list[BeamSeg]:
    if not segs:
        return []
    out: list[BeamSeg] = []
    cos_tol = math.cos(math.radians(float(ang_tol_deg)))

    def same_line(a: BeamSeg, b: BeamSeg) -> bool:
        ua = _unit(a.p1 - a.p0)
        ub = _unit(b.p1 - b.p0)
        if abs(float(np.dot(ua, ub))) < cos_tol:
            return False
        # 端点无序比对
        d1 = _norm(a.p0 - b.p0) + _norm(a.p1 - b.p1)
        d2 = _norm(a.p0 - b.p1) + _norm(a.p1 - b.p0)
        if min(d1, d2) > 4.0 * pos_tol:
            return False
        # 半径近似一致
        rref = max(abs(a.radius), abs(b.radius), 1.0e-9)
        if abs(a.radius - b.radius) > 0.15 * rref:
            return False
        return True

    for s in segs:
        hit = False
        for i, t in enumerate(out):
            if same_line(s, t):
                # 取更长者，提升稳定性
                if _segment_length(s.p0, s.p1) > _segment_length(t.p0, t.p1):
                    out[i] = s
                hit = True
                break
        if not hit:
            out.append(s)
    return out


def _vertical_segment_metadata(seg: BeamSeg) -> dict[str, float] | None:
    """若线段近似平行全局 Z，返回 z 跨度、XY 中点与长度（用于去重）。"""
    p0 = np.asarray(seg.p0, dtype=float)
    p1 = np.asarray(seg.p1, dtype=float)
    u = p1 - p0
    L = float(np.linalg.norm(u))
    if L <= 1.0e-9:
        return None
    u = u / L
    if abs(float(u[2])) < 0.92:
        return None
    zmin = float(min(p0[2], p1[2]))
    zmax = float(max(p0[2], p1[2]))
    return {
        "zmin": zmin,
        "zmax": zmax,
        "mx": float(0.5 * (p0[0] + p1[0])),
        "my": float(0.5 * (p0[1] + p1[1])),
        "L": L,
        "radius": float(seg.radius),
    }


def _z_overlap_fraction(a: dict[str, float], b: dict[str, float]) -> float:
    lo = max(a["zmin"], b["zmin"])
    hi = min(a["zmax"], b["zmax"])
    if hi <= lo + 1.0e-6:
        return 0.0
    span = min(a["zmax"] - a["zmin"], b["zmax"] - b["zmin"])
    return float(hi - lo) / max(span, 1.0e-9)


def _remove_mirror_duplicate_vertical_beams(segs: list[BeamSeg]) -> list[BeamSeg]:
    """
    去掉关于 YZ 或 XZ 平面镜像重复的竖向杆轴（IGES 常见双面 / 对称冗余）。
    保留 Y（或 X）坐标较大的一侧以贴合 OC4 甲板坐标习惯。
    """
    vert_idx: list[int] = []
    meta: list[dict[str, float]] = []
    for i, s in enumerate(segs):
        m = _vertical_segment_metadata(s)
        if m is None:
            continue
        vert_idx.append(i)
        meta.append(m)

    removed: set[int] = set()
    for ii in range(len(vert_idx)):
        i = vert_idx[ii]
        if i in removed:
            continue
        ai = meta[ii]
        for jj in range(ii + 1, len(vert_idx)):
            j = vert_idx[jj]
            if j in removed:
                continue
            aj = meta[jj]
            r_ref = max(ai["radius"], aj["radius"], 1.0)
            if abs(ai["radius"] - aj["radius"]) > 0.03 * r_ref:
                continue
            L_ref = max(ai["L"], aj["L"], 1.0)
            if abs(ai["L"] - aj["L"]) > 0.03 * L_ref:
                continue
            if _z_overlap_fraction(ai, aj) < 0.85:
                continue
            # 仅处理靠近 Y 轴 (|x| 小) 的 XZ 镜面重复：如 (0,±y0) 双圆柱 CAD 面。
            # 对在 ±X 成对的真实立柱（如 ±28310）不误判。
            y_mirror = (
                abs(ai["mx"] - aj["mx"]) < 800.0
                and abs(ai["my"] + aj["my"]) < 800.0
                and abs(ai["my"]) > 150.0
                and abs(aj["my"]) > 150.0
                and (abs(ai["mx"]) + abs(aj["mx"])) < 3500.0
            )
            if not y_mirror:
                continue
            keep_i = ai["my"] >= aj["my"]
            if keep_i:
                removed.add(j)
            else:
                removed.add(i)
                break
    return [s for k, s in enumerate(segs) if k not in removed]


def _suppress_redundant_line_pairs_vs_analytic(segs: list[BeamSeg]) -> list[BeamSeg]:
    """
    line_pair 由平行边推断半径时，常与已有 analytic 圆柱描述同一物理立柱；
    轴在 XY 上靠近且 Z 向跨度重叠则丢弃 line_pair，避免双竖杆与错误拓扑。
    """
    analytics: list[dict[str, float]] = []
    for s in segs:
        if s.source != "analytic":
            continue
        m = _vertical_segment_metadata(s)
        if m is not None:
            analytics.append(m)

    out: list[BeamSeg] = []
    for s in segs:
        if s.source != "line_pair":
            out.append(s)
            continue
        lm = _vertical_segment_metadata(s)
        if lm is None:
            out.append(s)
            continue
        drop = False
        for am in analytics:
            if _z_overlap_fraction(lm, am) < 0.75:
                continue
            dh = math.hypot(lm["mx"] - am["mx"], lm["my"] - am["my"])
            ra, rl = am["radius"], lm["radius"]
            coax_tol = min(ra, rl) + 0.55 * max(ra, rl) + 400.0
            if dh <= coax_tol:
                drop = True
                break
        if not drop:
            out.append(s)
    return out


def _cleanup_duplicate_beam_segments(segs: list[BeamSeg]) -> list[BeamSeg]:
    if not segs:
        return segs
    s1 = _remove_mirror_duplicate_vertical_beams(segs)
    return _suppress_redundant_line_pairs_vs_analytic(s1)


def _extract_unique_line_edges(gmsh) -> list[LineSeg]:
    out: list[LineSeg] = []
    seen: set[tuple[int, int]] = set()
    for d, t in gmsh.model.getEntities(1):
        if d != 1:
            continue
        try:
            if gmsh.model.getType(1, int(t)).lower() != "line":
                continue
            b = gmsh.model.getBoundary([(1, int(t))], oriented=False, recursive=False)
        except Exception:
            continue
        pts = [int(tag) for bd, tag in b if bd == 0]
        if len(pts) != 2:
            continue
        a, b_ = min(pts[0], pts[1]), max(pts[0], pts[1])
        if (a, b_) in seen:
            continue
        seen.add((a, b_))
        try:
            p0 = np.asarray(gmsh.model.getValue(0, int(a), []), dtype=float)
            p1 = np.asarray(gmsh.model.getValue(0, int(b_), []), dtype=float)
        except Exception:
            continue
        if _segment_length(p0, p1) <= 1.0e-6:
            continue
        out.append(LineSeg(p0=p0, p1=p1))
    return out


def _centerlines_from_parallel_line_pairs(lines: list[LineSeg]) -> list[BeamSeg]:
    if not lines:
        return []
    used: set[int] = set()
    out: list[BeamSeg] = []
    cos_tol = math.cos(math.radians(5.0))

    def orient_pair(a: LineSeg, b: LineSeg) -> tuple[np.ndarray, np.ndarray, float]:
        d_same = _norm(a.p0 - b.p0) + _norm(a.p1 - b.p1)
        d_swap = _norm(a.p0 - b.p1) + _norm(a.p1 - b.p0)
        if d_same <= d_swap:
            return b.p0, b.p1, d_same
        return b.p1, b.p0, d_swap

    for i in range(len(lines)):
        if i in used:
            continue
        li = lines[i]
        ui = _unit(li.p1 - li.p0)
        Li = _segment_length(li.p0, li.p1)
        best_j = -1
        best_score = float("inf")
        best_b0: np.ndarray | None = None
        best_b1: np.ndarray | None = None
        for j in range(i + 1, len(lines)):
            if j in used:
                continue
            lj = lines[j]
            Lj = _segment_length(lj.p0, lj.p1)
            if abs(Li - Lj) > 0.08 * max(Li, Lj):
                continue
            uj = _unit(lj.p1 - lj.p0)
            if abs(float(np.dot(ui, uj))) < cos_tol:
                continue
            b0, b1, score = orient_pair(li, lj)
            d0 = _norm(li.p0 - b0)
            d1 = _norm(li.p1 - b1)
            dmean = 0.5 * (d0 + d1)
            if dmean <= 100.0 or dmean >= 15000.0:
                continue
            if abs(d0 - d1) > 0.35 * max(dmean, 1.0e-9):
                continue
            # 梁长应显著大于直径，避免把短边/装饰边误配成杆件
            if Li < 1.2 * dmean:
                continue
            if score < best_score:
                best_j = j
                best_score = score
                best_b0 = b0
                best_b1 = b1
        if best_j >= 0 and best_b0 is not None and best_b1 is not None:
            used.add(i)
            used.add(best_j)
            p0 = 0.5 * (li.p0 + best_b0)
            p1 = 0.5 * (li.p1 + best_b1)
            d0 = _norm(li.p0 - best_b0)
            d1 = _norm(li.p1 - best_b1)
            r = 0.25 * (d0 + d1)
            if _segment_length(p0, p1) > 1.0e-6 and r > 1.0e-6:
                out.append(BeamSeg(p0=p0, p1=p1, radius=float(r), source="line_pair"))
    return out


def _snap_linepair_endpoints_to_analytic_axes(segs: list[BeamSeg]) -> list[BeamSeg]:
    """
    将 line_pair 端点吸附到 analytic 圆柱轴线上，修正“贴外壁”的误差。
    """
    refs: list[BeamSeg] = [s for s in segs if s.source == "analytic" and s.radius > 500.0]
    if not refs:
        return segs

    out: list[BeamSeg] = []
    for s in segs:
        if s.source != "line_pair":
            out.append(s)
            continue
        p0 = s.p0.copy()
        p1 = s.p1.copy()
        for p in (p0, p1):
            best_ref: BeamSeg | None = None
            best_d = float("inf")
            for r in refs:
                u = _unit(r.p1 - r.p0)
                if _norm(r.p1 - r.p0) <= 1.0e-9:
                    continue
                # 近似按有限轴段投影
                t = float(np.dot(p - r.p0, u))
                t = max(0.0, min(t, _norm(r.p1 - r.p0)))
                q = r.p0 + t * u
                d = _norm(p - q)
                if d < best_d:
                    best_d = d
                    best_ref = r
            if best_ref is None:
                continue
            # 若端点离某圆柱轴足够近，认为其属于该杆件连接点，吸附到轴心
            if best_d <= max(1.25 * best_ref.radius, 1200.0):
                u = _unit(best_ref.p1 - best_ref.p0)
                t = float(np.dot(p - best_ref.p0, u))
                t = max(0.0, min(t, _norm(best_ref.p1 - best_ref.p0)))
                p[:] = best_ref.p0 + t * u
        if _segment_length(p0, p1) > 1.0e-6:
            out.append(BeamSeg(p0=p0, p1=p1, radius=s.radius, source=s.source))
    return out


def _filter_line_pair_segments(segs: list[BeamSeg]) -> list[BeamSeg]:
    """
    过滤明显重复/伪线：
    - line_pair 半径过大通常是由大圆柱侧壁边误配导致（analytic 已覆盖）
    """
    out: list[BeamSeg] = []
    for s in segs:
        if s.source == "line_pair" and s.radius >= 2000.0:
            continue
        out.append(s)
    return out


def _extract_beam_segments_from_iges(iges_path: Path) -> list[BeamSeg]:
    occ_segs = _occ_extract_cylinder_segments(iges_path)
    if occ_segs:
        return list(occ_segs)

    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.merge(str(iges_path.resolve()))
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(2)
        surfaces = [t for _, t in gmsh.model.getEntities(2)]
        segs: list[BeamSeg] = []
        used: set[int] = set()
        for s in surfaces:
            seg = _extract_from_revolution_surface(gmsh, int(s))
            if seg is not None:
                segs.append(seg)
                used.add(int(s))
        for s in surfaces:
            if int(s) in used:
                continue
            seg = _extract_from_circle_boundaries(gmsh, int(s))
            if seg is not None:
                segs.append(seg)
                used.add(int(s))
        for s in surfaces:
            if int(s) in used:
                continue
            seg = _fit_axis_from_surface_nodes_strict(gmsh, int(s))
            if seg is not None:
                segs.append(seg)
        line_edges = _extract_unique_line_edges(gmsh)
        segs.extend(_centerlines_from_parallel_line_pairs(line_edges))
        # 忠实还原 IGS 杆系：保留 line_pair 候选；随后去掉镜像重复柱与 shadow analytic 的 line_pair。
        return _cleanup_duplicate_beam_segments(_dedup_segments(segs, pos_tol=1.0e-3, ang_tol_deg=3.0))
    finally:
        gmsh.finalize()


def _merge_nodes_and_segments(segs: list[BeamSeg], merge_tol: float) -> tuple[list[np.ndarray], list[tuple[int, int, float]]]:
    cell_size = max(merge_tol, 1.0e-12)
    inv = 1.0 / cell_size
    nodes: list[np.ndarray] = []
    buckets: dict[tuple[int, int, int], list[int]] = {}

    def key(p: np.ndarray) -> tuple[int, int, int]:
        q = np.floor(p * inv).astype(np.int64)
        return (int(q[0]), int(q[1]), int(q[2]))

    def get_node_id(p: np.ndarray) -> int:
        ck = key(p)
        best: int | None = None
        best_d = float("inf")
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    nk = (ck[0] + dx, ck[1] + dy, ck[2] + dz)
                    for nid in buckets.get(nk, []):
                        d = _norm(nodes[nid] - p)
                        if d <= merge_tol and d < best_d:
                            best_d = d
                            best = nid
        if best is not None:
            return best
        nid = len(nodes)
        nodes.append(p.copy())
        buckets.setdefault(ck, []).append(nid)
        return nid

    elements: list[tuple[int, int, float]] = []
    for seg in segs:
        n1 = get_node_id(seg.p0)
        n2 = get_node_id(seg.p1)
        if n1 == n2:
            continue
        if _segment_length(nodes[n1], nodes[n2]) <= 1.0e-12:
            continue
        elements.append((n1, n2, float(seg.radius)))
    return nodes, elements


def _auto_merge_tol_from_segments(segs: list[BeamSeg], requested_tol: float) -> float:
    req = float(requested_tol)
    if req > 1.0:
        return req
    rs = [float(s.radius) for s in segs if s.radius > 0.0 and math.isfinite(s.radius)]
    if not rs:
        return max(req, 1.0e-3)
    r_med = float(np.median(np.asarray(rs, dtype=float)))
    # 对 CAD 导出的组合几何，端点偏差常在数百~上千；采用半径尺度的温和合并。
    return max(req, 0.35 * r_med)


def _build_graph_elements(
    nodes: list[np.ndarray], elements: list[tuple[int, int, float]]
) -> list[tuple[int, int, float]]:
    g = nx.Graph()
    for i in range(len(nodes)):
        g.add_node(i)
    for a, b, r in elements:
        if a == b:
            continue
        if g.has_edge(a, b):
            rr = float(g[a][b]["radius"])
            g[a][b]["radius"] = 0.5 * (rr + float(r))
        else:
            g.add_edge(a, b, radius=float(r))
    out: list[tuple[int, int, float]] = []
    for a, b, data in g.edges(data=True):
        out.append((int(a), int(b), float(data.get("radius", 1.0))))
    return out


class DSU:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            self.p[ra] = rb
        elif self.r[ra] > self.r[rb]:
            self.p[rb] = ra
        else:
            self.p[rb] = ra
            self.r[ra] += 1


def _enforce_global_connectivity(nodes: list[np.ndarray], elements: list[tuple[int, int, float]]) -> list[tuple[int, int, float]]:
    if not nodes:
        return elements
    radii = [r for _, _, r in elements]
    bridge_r = float(np.median(radii)) if radii else 1.0
    out = list(elements)

    while True:
        dsu = DSU(len(nodes))
        for a, b, _ in out:
            dsu.union(a, b)
        groups: dict[int, list[int]] = {}
        for i in range(len(nodes)):
            groups.setdefault(dsu.find(i), []).append(i)
        comps = list(groups.values())
        if len(comps) <= 1:
            break
        best_pair: tuple[int, int] | None = None
        best_d = float("inf")
        for i in range(len(comps)):
            ai = comps[i]
            for j in range(i + 1, len(comps)):
                bj = comps[j]
                for a in ai:
                    pa = nodes[a]
                    for b in bj:
                        d = _norm(pa - nodes[b])
                        if d < best_d:
                            best_d = d
                            best_pair = (a, b)
        if best_pair is None:
            break
        a, b = best_pair
        if a != b and _segment_length(nodes[a], nodes[b]) > 1.0e-12:
            out.append((a, b, bridge_r))
        else:
            break
    return out


def _cluster_radii(radii: list[float], tol: float = 1.0e-6) -> list[float]:
    if not radii:
        return []
    vals = sorted(float(r) for r in radii if r > 0.0 and math.isfinite(r))
    if not vals:
        return []
    groups: list[list[float]] = [[vals[0]]]
    for r in vals[1:]:
        g = groups[-1]
        ref = sum(g) / len(g)
        if abs(r - ref) <= max(tol, tol * abs(ref)):
            g.append(r)
        else:
            groups.append([r])
    return [float(sum(g) / len(g)) for g in groups]


def _radius_to_group(radius: float, group_r: list[float]) -> int:
    best = 0
    best_d = float("inf")
    for i, r in enumerate(group_r):
        d = abs(radius - r)
        if d < best_d:
            best = i
            best_d = d
    return best


def _beam_n1(node_a: np.ndarray, node_b: np.ndarray) -> np.ndarray:
    axis = _unit(node_b - node_a)
    ref = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(axis, ref))) > 0.9:
        ref = np.array([1.0, 0.0, 0.0], dtype=float)
    v = np.cross(axis, ref)
    if _norm(v) <= 1.0e-12:
        ref = np.array([0.0, 1.0, 0.0], dtype=float)
        v = np.cross(axis, ref)
    return _unit(v)


def write_b31_inp(
    out_path: Path,
    nodes: list[np.ndarray],
    elements: list[tuple[int, int, float]],
    *,
    force_top_load: float = -1000.0,
    diagnostics_comment: str | None = None,
) -> None:
    if not nodes:
        raise ValueError("No nodes generated from IGS.")
    if not elements:
        raise ValueError("No beam elements generated from IGS.")
    group_r = _cluster_radii([r for _, _, r in elements], tol=1.0e-6)
    if not group_r:
        raise ValueError("No valid radius groups generated.")
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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        if diagnostics_comment:
            f.write("**\n")
            for line in diagnostics_comment.strip().split("\n"):
                f.write(f"** {line}\n")
            f.write("**\n")
        f.write("*Node, NSET=Nall\n")
        for i, p in enumerate(nodes, start=1):
            f.write(f"{i}, {p[0]:.9f}, {p[1]:.9f}, {p[2]:.9f}\n")
        f.write("*Element, TYPE=B31, ELSET=Eall\n")
        for i, (a, b, _) in enumerate(elements, start=1):
            f.write(f"{i}, {a + 1}, {b + 1}\n")

        for gid in sorted(group_el):
            f.write(f"*ELSET,ELSET=ESEC_{gid + 1}\n")
            ids = group_el[gid]
            for k in range(0, len(ids), 16):
                f.write(", ".join(str(x) for x in ids[k : k + 16]) + "\n")

        f.write("*MATERIAL, NAME=SolidMaterial\n")
        f.write("*ELASTIC\n")
        f.write("210000, 0.3\n")

        for gid, r in enumerate(group_r, start=1):
            anchor_eid = group_el[gid - 1][0]
            na, nb, _ = elements[anchor_eid - 1]
            n1 = _beam_n1(nodes[na], nodes[nb])
            f.write(f"*BEAM SECTION,SECTION=CIRC,ELSET=ESEC_{gid},MATERIAL=SolidMaterial\n")
            f.write(f"{r:.9f}\n")
            f.write(f"{n1[0]:.9f}, {n1[1]:.9f}, {n1[2]:.9f}\n")

        f.write("*NSET,NSET=FemConstraintDisplacement\n")
        for k in range(0, len(nset_bottom), 16):
            f.write(", ".join(str(x) for x in nset_bottom[k : k + 16]) + "\n")
        f.write("*NSET,NSET=FemLoadTop\n")
        for k in range(0, len(nset_top), 16):
            f.write(", ".join(str(x) for x in nset_top[k : k + 16]) + "\n")

        f.write("*BOUNDARY\n")
        f.write("FemConstraintDisplacement, 1, 6\n")

        f.write("*STEP\n")
        f.write("*STATIC\n")
        f.write("1., 1., 1e-05, 1.\n")
        f.write("*CLOAD\n")
        for nid in nset_top:
            f.write(f"{nid}, 3, {float(force_top_load):.6f}\n")
        f.write("*NODE FILE\n")
        f.write("U\n")
        f.write("*EL FILE\n")
        f.write("S\n")
        f.write("*END STEP\n")


def convert_iges_to_b31_inp(
    iges_path: Path,
    out_path: Path,
    *,
    merge_tol: float = 1.0e-3,
    force_top_load: float = -1000.0,
    enforce_connectivity: bool = False,
    use_pipe: bool = False,
    pair_tol_k: float = 0.6,
    td_overrides: dict[float, float] | None = None,
    pair_abs_min_mm: float | None = None,
    no_bridge: bool = False,
    surface_obj: Path | str | None = None,
    surface_facets: int = 16,
) -> Path:
    do_bridge = bool(enforce_connectivity) or (not bool(no_bridge))
    if use_pipe:
        from backend.tools.iges_jacket_to_b31_inp import convert_jacket_iges_to_inp

        path, _diag = convert_jacket_iges_to_inp(
            iges_path.resolve(),
            out_path.resolve(),
            merge_tol=float(merge_tol) if merge_tol is not None else None,
            pair_tol_k=float(pair_tol_k),
            pair_abs_min_mm=pair_abs_min_mm,
            td_overrides=dict(td_overrides or {}),
            force_top_load=float(force_top_load),
            bridge_islands=do_bridge,
            surface_obj=surface_obj,
            surface_facets=int(surface_facets),
        )
        return path

    segs = _extract_beam_segments_from_iges(iges_path.resolve())
    if not segs:
        raise ValueError("No beam-like cylindrical segments were extracted from IGS.")
    tol_use = _auto_merge_tol_from_segments(segs, float(merge_tol))

    from backend.tools.iges_jacket_to_b31_inp import build_jacket_topology

    nodes, elements, diag = build_jacket_topology(
        segs,
        merge_tol=tol_use,
        pair_tol_k=float(pair_tol_k),
        bridge_islands=do_bridge,
    )
    comment = (
        f"topology: nodes={diag.nodes} beam_elems={diag.elements} components={diag.components} "
        f"dropped_micro={diag.dropped_micro} split_iters={diag.split_iterations} "
        f"r_med={diag.r_med:.6g} merge_tol={diag.merge_tol_used:.6g}"
    )
    write_b31_inp(
        out_path.resolve(),
        nodes,
        elements,
        force_top_load=float(force_top_load),
        diagnostics_comment=comment,
    )
    if surface_obj:
        from backend.tools.jacket_beam_surface_mesh import write_beam_skin_mesh

        write_beam_skin_mesh(nodes, elements, Path(surface_obj), n_facets=int(surface_facets))
    return out_path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert IGS/IGES rods to Abaqus B31 inp.")
    parser.add_argument("iges", type=str, help="Input IGES/IGS path")
    parser.add_argument("out_inp", type=str, help="Output Abaqus inp path")
    parser.add_argument("--merge-tol", type=float, default=1.0e-3, help="Node merge tolerance")
    parser.add_argument("--top-load", type=float, default=-1000.0, help="Top node F3 load")
    parser.add_argument("--enforce-connectivity", action="store_true", help="Bridge nearest endpoints to force one component")
    parser.add_argument(
        "--pipe",
        action="store_true",
        help="使用 jacket 管线输出 PIPE 截面（iges_jacket_to_b31_inp）",
    )
    parser.add_argument("--pair-tol-k", type=float, default=0.6, help="线段对切分阈值系数 k（距离<=k*min(r1,r2)）")
    parser.add_argument(
        "--td",
        action="append",
        default=None,
        help="PIPE t/D 覆盖：半径mm,tDratio，可多次指定（仅 --pipe）",
    )
    parser.add_argument(
        "--no-bridge",
        action="store_true",
        help="与 --pipe / jacket 联用时禁用分量桥接（默认启用桥接）",
    )
    parser.add_argument(
        "--pair-abs-min",
        type=float,
        default=None,
        help="与 --pipe 联用时覆盖切分绝对下限 mm",
    )
    parser.add_argument(
        "--surface-obj",
        type=str,
        default=None,
        help="导出圆柱壳 OBJ 网格用于可视化（可与 PIPE/CIRC 同时使用）",
    )
    parser.add_argument("--surface-facets", type=int, default=16, help="圆柱圆周分段数")
    args = parser.parse_args()

    td_map = None
    if args.td:
        from backend.tools.iges_jacket_to_b31_inp import parse_td_overrides

        td_map = parse_td_overrides(args.td)

    convert_iges_to_b31_inp(
        Path(args.iges),
        Path(args.out_inp),
        merge_tol=float(args.merge_tol),
        force_top_load=float(args.top_load),
        enforce_connectivity=bool(args.enforce_connectivity),
        use_pipe=bool(args.pipe),
        pair_tol_k=float(args.pair_tol_k),
        td_overrides=td_map,
        pair_abs_min_mm=args.pair_abs_min,
        no_bridge=bool(args.no_bridge),
        surface_obj=args.surface_obj,
        surface_facets=int(args.surface_facets),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
