from __future__ import annotations

"""
OC4 导管架：由原始梁系 IGS（如 oc4.igs）生成「实心设计域」IGES/STEP，供后续体网格与 BESO。

默认几何（``domain_envelope=triangle_prism``）对齐 **examples/beso/beso9/BESO9.FCStd**：
等边三棱柱 + 三顶角通高圆柱挖除（+ 可选中心孔），**不**挖桩靴（避免底面出现台阶状怪形）。

可选 ``domain_envelope=hull_bbox``：整装配轴对齐包围盒 slab（对齐 ``examples/beso/BESO3-Compound.iges`` 体量），
再布尔减去柱身/桩靴。

环境变量 ``OC4_DESIGN_DOMAIN_ENVELOPE=triangle`` / ``hull`` 可覆盖默认。
布尔：默认减去中心孔 + 三顶角；``--edge-columns-only`` 仅挖三角顶角。
"""

import argparse
import itertools
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

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


def normalize_domain_envelope(value: str | None) -> str:
    """``triangle_prism``（beso9 默认）或 ``hull_bbox``。"""
    s = str(value or "").strip().lower()
    if s in ("hull", "hull_bbox", "bbox", "compound", "slab"):
        return "hull_bbox"
    if s in ("triangle", "triangle_prism", "prism", "beso9", "tri", "triangular"):
        return "triangle_prism"
    env = (os.environ.get("OC4_DESIGN_DOMAIN_ENVELOPE") or "").strip().lower()
    if env.startswith("triangle") or env in ("prism", "beso9", "tri"):
        return "triangle_prism"
    if env in ("hull", "hull_bbox", "bbox", "compound", "slab"):
        return "hull_bbox"
    return "triangle_prism"


def _extract_revolution_cylinders_gmsh_raw(iges_path: Path) -> list[CylinderAxis]:
    """仅在解释器主线程中调用 Gmsh（会 register signal handlers）。"""
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


def _extract_revolution_cylinders_worker(iges_path_str: str) -> list[tuple[tuple[float, float, float], tuple[float, float, float], float]]:
    """供 ProcessPoolExecutor(spawn) 调用：在子进程主线程跑 Gmsh，返回可 pickle 的元组列表。"""
    cyls = _extract_revolution_cylinders_gmsh_raw(Path(iges_path_str))
    return [
        (
            (float(c.p0[0]), float(c.p0[1]), float(c.p0[2])),
            (float(c.p1[0]), float(c.p1[1]), float(c.p1[2])),
            float(c.radius),
        )
        for c in cyls
    ]


def _extract_revolution_cylinders(iges_path: Path) -> list[CylinderAxis]:
    """
    从 IGES 识别 revolution 圆柱轴。

    一律经 ``backend.gmsh_spawn.run_in_spawn_process`` 在 **spawn 子进程主线程** 里执行
    ``gmsh.initialize()``，避免 Uvicorn/Starlette 同步路由在线程池、或任意非预期线程里
    触发 ``signal only works in main thread of the main interpreter``。
    """
    from backend.gmsh_spawn import run_in_spawn_process

    ip = iges_path.resolve()
    raw_tuples = run_in_spawn_process(_extract_revolution_cylinders_worker, str(ip), timeout_s=3600.0)
    return [
        CylinderAxis(p0=np.asarray(t[0], dtype=float), p1=np.asarray(t[1], dtype=float), radius=float(t[2]))
        for t in raw_tuples
    ]


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


def _domain_volume_hull_bbox_slab(gmsh, src_iges: Path, z_bot: float, z_top: float) -> tuple[int, int]:
    """
    与 BESO3-Compound.iges / oc4.igs 整装配包围盒一致：merge 源文件 → 读包围盒 → 删导入体 →
    用 [xmin,xmax]×[ymin,ymax]×([z_bot,z_top]∩[zmin,zmax]) 建长方体设计域。
    """
    gmsh.merge(str(src_iges.resolve()))
    gmsh.model.occ.synchronize()
    hx0, hy0, hz0, hx1, hy1, hz1 = gmsh.model.getBoundingBox(-1, -1)
    ents = gmsh.model.getEntities()
    if ents:
        gmsh.model.occ.remove(ents, True)
    gmsh.model.occ.synchronize()
    zb0 = max(float(z_bot), float(hz0))
    zb1 = min(float(z_top), float(hz1))
    if zb1 <= zb0 + 1000.0:
        zb0, zb1 = float(z_bot), float(z_top)
    x0, y0 = float(hx0), float(hy0)
    dx = float(hx1) - float(hx0)
    dy = float(hy1) - float(hy0)
    dz = float(zb1) - float(zb0)
    if dx <= 1.0 or dy <= 1.0 or dz <= 1.0:
        raise ValueError(
            "源 IGS 装配包围盒过小或与竖向范围无交；可改用三棱柱包络："
            "环境变量 OC4_DESIGN_DOMAIN_ENVELOPE=triangle 或 API domain_envelope=triangle_prism。"
        )
    tag = int(gmsh.model.occ.addBox(x0, y0, float(zb0), dx, dy, dz))
    return (3, tag)


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


def _mean_triangle_edge_mm(pts_xy: list[np.ndarray]) -> float:
    arr = [np.asarray(p, dtype=float).reshape(-1)[:2] for p in pts_xy]
    if len(arr) < 3:
        return 0.0
    lens = [
        float(_norm(arr[i] - arr[(i + 1) % 3]))
        for i in range(3)
    ]
    return float(sum(lens) / 3.0)


def _beso9_corner_radius_mm(side_mm: float, shaft_rs: list[float] | None = None) -> float:
    """
    对齐 examples/beso/beso9：边长 95 m 时挖角 R≈7.5 m（约 7.9% 边长）。
    同时不低于柱身半径的放大值，保证孔洞可见。
    """
    side = max(float(side_mm), 1.0)
    r_side = 0.079 * side
    shafts = [float(r) for r in (shaft_rs or []) if r is not None and float(r) > 0.0]
    r_shaft = 1.35 * max(shafts) if shafts else 0.0
    return float(max(r_side, r_shaft, 2500.0))


def clamp_corner_r_mm(corner_r_mm: float, side_mm: float) -> float:
    """限制挖角半径，避免三孔过大掏空棱柱。"""
    side = max(float(side_mm), 1.0)
    # 顶点挖孔约一半在体外；允许约 55% 外接圆半径（口语常见 10–15 m 级）
    r_max = 0.55 * side / math.sqrt(3.0)
    return float(max(100.0, min(float(corner_r_mm), r_max)))


def coerce_corner_r_mm(value: Any, *, unit_hint: str | None = None) -> float | None:
    """
    将用户/工具输入规范为 mm。
    - 带单位 m/米 → ×1000
    - 纯数字：若 unit_hint 为 m 则按米；若数值落在 (0.5, 200] 且无 hint，按「米」理解（口语常见「15」=15m）；
      否则按 mm。
    """
    if value is None:
        return None
    uh = str(unit_hint or "").strip().lower()
    if isinstance(value, str):
        s = value.strip().lower().replace("，", ".")
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(mm|m|米)?", s)
        if not m:
            return None
        try:
            x = float(m.group(1))
        except ValueError:
            return None
        u = (m.group(2) or uh or "").replace("米", "m")
        if u in ("m", "米"):
            return float(x * 1000.0) if x > 0 else None
        if u == "mm":
            return float(x) if x > 0 else None
        if 0.5 < x <= 200.0:
            return float(x * 1000.0)
        return float(x) if x > 0 else None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if x <= 0:
        return None
    if uh in ("m", "米"):
        return float(x * 1000.0)
    if uh == "mm":
        return float(x)
    # 工具常直接传 mm（如 15000）；口语小数常为米
    if 0.5 < x <= 200.0:
        return float(x * 1000.0)
    return float(x)


def coerce_length_r_mm(value: Any, *, unit_hint: str | None = None) -> float | None:
    """长度半径（mm）规范化；与 ``coerce_corner_r_mm`` 同语义，供中心孔等复用。"""
    return coerce_corner_r_mm(value, unit_hint=unit_hint)


def _radius_unit_from_match(num: str, unit: str | None) -> str | None:
    if unit:
        return unit
    try:
        x = float(num)
    except ValueError:
        return None
    if x > 200:
        return "mm"
    return "m"


def _nearest_num_unit_mm(text: str, anchor: int, *, ahead: int = 28, behind: int = 8) -> float | None:
    """在关键词附近取最近的「数字+单位」并规范为 mm。"""
    t = str(text or "")
    lo = max(0, int(anchor) - int(behind))
    hi = min(len(t), int(anchor) + int(ahead))
    best: tuple[float, float] | None = None  # (dist, mm)
    for m in re.finditer(r"([-+]?\d+(?:\.\d+)?)\s*(mm|MM|m|M|米)", t[lo:hi]):
        abs_start = lo + m.start()
        dist = abs(abs_start - int(anchor))
        # 优先关键词之后的数字（「中心孔改为 3m」）
        if abs_start < int(anchor) - 2:
            dist += 50.0
        got = coerce_length_r_mm(m.group(1), unit_hint=m.group(2))
        if got is None:
            continue
        if best is None or dist < best[0]:
            best = (float(dist), float(got))
    return None if best is None else best[1]


def parse_center_hole_r_mm_from_text(text: str) -> float | None:
    """从自然语言提取**中间/中心圆孔**半径（mm），与边立柱挖去半径独立。"""
    t = str(text or "").strip()
    if not t:
        return None
    m = re.search(
        r"(?:center[_\s-]?hole[_\s-]?(?:r|radius)|central[_\s-]?hole[_\s-]?(?:r|radius)|"
        r"center_hole_r_mm)\s*[=:：]?\s*([-+]?\d+(?:\.\d+)?)\s*(mm|m)?",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        got = coerce_length_r_mm(m.group(1), unit_hint=m.group(2) or "mm")
        if got is not None:
            return got
    for m in re.finditer(
        r"中间\s*圆?孔|中心\s*圆?孔|中心孔|中间孔|中孔|center\s*hole|central\s*hole",
        t,
        flags=re.IGNORECASE,
    ):
        got = _nearest_num_unit_mm(t, m.end(), ahead=32, behind=4)
        if got is not None:
            return got
    m = re.search(
        r"(?:中间\s*圆?孔|中心\s*圆?孔|中心孔|中间孔).{0,14}半径\s*[=:：]?\s*"
        r"([-+]?\d+(?:\.\d+)?)\s*(mm|m|米)?",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        got = coerce_length_r_mm(m.group(1), unit_hint=_radius_unit_from_match(m.group(1), m.group(2)))
        if got is not None:
            return got
    return None


def parse_corner_r_mm_from_text(text: str) -> float | None:
    """从自然语言提取**边立柱/顶角边缘挖去**圆柱半径（mm）；不解析中间圆孔。"""
    t = str(text or "").strip()
    if not t:
        return None
    # 显式英文/参数名
    m = re.search(
        r"(?:corner[_\s-]?(?:r|radius)|digout[_\s-]?r)\s*[=:：]?\s*([-+]?\d+(?:\.\d+)?)\s*(mm|m)?",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        got = coerce_corner_r_mm(m.group(1), unit_hint=m.group(2) or "mm")
        if got is not None:
            return got
    # 关键词锚定：边立柱 / 挖角 / 顶角 / 边缘…
    for m in re.finditer(
        r"挖角|顶角|边缘(?:挖去|切角)?|切角|圆角|角部|顶点|角上|挖去|"
        r"边立柱|立柱|corner|digout|dig-?out",
        t,
        flags=re.IGNORECASE,
    ):
        # 跳过落在「中心/中间孔」短语内的噪声（极少）
        around = t[max(0, m.start() - 6) : m.end() + 6]
        if re.search(r"中间|中心|center\s*hole", around, re.I) and not re.search(
            r"边缘|边立柱|顶角|挖角|corner|digout", around, re.I
        ):
            continue
        got = _nearest_num_unit_mm(t, m.end(), ahead=32, behind=4)
        if got is not None:
            return got
    m = re.search(
        r"(?:挖角|顶角|边缘|切角|边立柱|立柱).{0,14}半径\s*[=:：]?\s*([-+]?\d+(?:\.\d+)?)\s*(mm|m|米)?",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        unit = _radius_unit_from_match(m.group(1), m.group(2))
        got = coerce_corner_r_mm(m.group(1), unit_hint=unit)
        if got is not None:
            return got
    return None


def _beso9_equilateral_vertices_xy(
    outer_xy: list[np.ndarray],
    *,
    xy_pad: float,
    center_xy: np.ndarray | None = None,
) -> list[np.ndarray]:
    """
    由外柱三角形生成 **等边** 三顶点（beso9），边长取外柱均边 + 外扩，
    朝向对齐到第一个外柱方位，避免不规则三角形导致侧面歪斜。
    """
    arr = np.asarray([np.asarray(p, dtype=float).reshape(-1)[:2] for p in outer_xy], dtype=float)
    if arr.shape[0] < 3:
        raise ValueError("需要至少三个外柱 xy 才能生成 beso9 等边三角形。")
    arr = arr[:3]
    c = np.asarray(center_xy, dtype=float).reshape(-1)[:2] if center_xy is not None else np.mean(arr, axis=0)
    side0 = _mean_triangle_edge_mm([arr[0], arr[1], arr[2]])
    # 外扩：在边长上加 2*pad/√3 量级，使顶点沿径向超出柱心
    side = max(side0 + 2.0 * float(xy_pad) / math.sqrt(3.0), side0 * 1.02, 1000.0)
    # 外接圆半径 R = side / √3
    R = side / math.sqrt(3.0)
    v0 = arr[0] - c
    ang0 = math.atan2(float(v0[1]), float(v0[0])) if _norm(v0) > 1.0e-9 else 0.0
    out: list[np.ndarray] = []
    for k in range(3):
        a = ang0 + k * (2.0 * math.pi / 3.0)
        out.append(np.array([float(c[0] + R * math.cos(a)), float(c[1] + R * math.sin(a))], dtype=float))
    return out


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


def _default_column_thresholds() -> dict[str, float]:
    return {
        "center_r_min": 1200.0,
        "center_r_max": 2200.0,
        "center_len_min": 20000.0,
        "vertical_r_min": 1200.0,
        "vertical_len_min": 5000.0,
        "outer_len_min": 18000.0,
    }


def _merge_column_thresholds(overrides: dict[str, Any] | None) -> dict[str, float]:
    base = _default_column_thresholds()
    if not overrides:
        return base
    out = dict(base)
    for k in base:
        if k in overrides and overrides[k] is not None:
            try:
                out[k] = float(overrides[k])
            except (TypeError, ValueError):
                pass
    return out


def _pick_oc4_key_columns(
    vertical: list[CylinderAxis],
    *,
    thresholds: dict[str, Any] | None = None,
) -> tuple[CylinderAxis, list[CylinderAxis], list[CylinderAxis | None], CylinderAxis | None]:
    """
    选择 OC4 关键柱：
    - center: 中央细柱（r≈1625, 长细比高）
    - outers: 三根外柱（r≈3000，绕中心 CCW 排序）
    - outer_bases: 与 outers 同序的一对一底座（大半径短柱段）
    - center_base: 中心柱下方粗底座（若有）

    ``thresholds`` 可覆盖半径/长度启发式（mm），便于 MW 缩放后的几何仍可识别。
    """
    th = _merge_column_thresholds(thresholds)
    center_cands = [
        c
        for c in vertical
        if th["center_r_min"] <= c.radius <= th["center_r_max"] and c.length >= th["center_len_min"]
    ]
    if not center_cands:
        raise ValueError(
            "未识别到中心细柱。"
            f"请检查源 CAD 是否为 OC4 族，或在会话 meta 中调整 column_pick_thresholds"
            f"（当前 center_r=[{th['center_r_min']:g},{th['center_r_max']:g}] mm，"
            f"center_len_min={th['center_len_min']:g} mm）。"
            "也可上传替换几何后重试。"
        )

    # 选更接近全局几何中心且 Y 偏上者，稳定落在 OC4 中柱
    xy_all = np.asarray([c.center[:2] for c in vertical], dtype=float)
    gc = np.mean(xy_all, axis=0)
    center_col = sorted(center_cands, key=lambda c: (_norm(c.center[:2] - gc), -float(c.center[1])))[0]

    outer_cands = [c for c in vertical if c.length >= th["outer_len_min"] and c is not center_col]
    if len(outer_cands) < 3:
        # 容错：用最长三根（除中心柱）作为外柱
        tmp = [c for c in vertical if c is not center_col]
        tmp = sorted(tmp, key=lambda c: c.length, reverse=True)
        outer_cands = tmp[:3]
    if len(outer_cands) < 3:
        raise ValueError(
            "未识别到足够外柱（需要 ≥3）。"
            f"当前 outer_len_min={th['outer_len_min']:g} mm；可放宽阈值或替换源 CAD。"
        )
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
    domain_envelope: str = "triangle_prism",
    column_pick_thresholds: dict[str, Any] | None = None,
    corner_r_mm: float | None = None,
    center_hole_r_mm: float | None = None,
    out_info: dict[str, Any] | None = None,
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

    domain_envelope = normalize_domain_envelope(domain_envelope)

    if beam_geom is None:
        th = _merge_column_thresholds(column_pick_thresholds)
        cyls = _extract_revolution_cylinders(src_iges)
        vertical = [c for c in cyls if abs(float(c.direction[2])) > 0.96]
        vertical = _merge_parallel_axis_pairs(vertical)
        vertical = [
            c
            for c in vertical
            if c.radius >= th["vertical_r_min"]
            and (c.length >= th["vertical_len_min"] or (c.length >= 350.0 and c.radius >= 2600.0 * (th["vertical_r_min"] / 1200.0)))
        ]
        if len(vertical) < 4:
            raise ValueError(
                "识别到的主立柱不足，无法构建设计域。"
                f"已应用阈值 vertical_r_min={th['vertical_r_min']:g} mm；"
                "可在会话 meta.column_pick_thresholds 中放宽，或替换源 CAD。"
            )
        center_col, outer_cols, outer_bases, center_base = _pick_oc4_key_columns(
            vertical, thresholds=th
        )

    # 须在 gmsh.initialize() 之前算完所有会 merge/mesh 的梁解析，否则会 finalize 掉当前会话

    # 仅构建布尔后的设计域实体；默认不再 merge 源 IGS，避免导出文件里整船架与设计域
    # 叠在一起（预览像“未挖孔”或严重错位）。需要对照原模型时设 include_source_geometry=True。
    import gmsh

    envelope = normalize_domain_envelope(domain_envelope)
    if envelope not in ("hull_bbox", "triangle_prism"):
        envelope = "triangle_prism"
    if include_source_geometry:
        envelope = "triangle_prism"

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("oc4_design_domain")
        if include_source_geometry:
            gmsh.merge(str(src_iges.resolve()))
            gmsh.model.occ.synchronize()

        # 1) 实心设计域：默认 triangle_prism（beso9 三棱柱）；hull_bbox 为整装配 slab
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

        if envelope == "hull_bbox":
            domain_vol = _domain_volume_hull_bbox_slab(gmsh, src_iges, z_bot, z_top)
            low_pts = []  # unused for hull cuts
            verts_xy: list[np.ndarray] = []
            shaft_rs_for_corner: list[float] = []
        else:
            # beso9：等边三棱柱底面（对齐 examples/beso/beso9），外扩由桩靴/柱间距推导
            if beam_geom is not None:
                xy_pad = _triangle_xy_pad_from_beam_geom(beam_geom)
                shaft_rs_for_corner = [float(r) for r in beam_geom.outer_shaft_rs]
            else:
                r_outer = float(np.mean([o.radius for o in outer_cols])) if outer_cols else 3000.0
                xy_pad = max(1600.0, 0.48 * r_outer)
                shaft_rs_for_corner = [float(o.radius) for o in outer_cols]
            outer_xy_arr = np.asarray(outer_xy, dtype=float)
            radial_origin = (
                np.mean(outer_xy_arr, axis=0) if outer_xy_arr.shape[0] >= 2 else np.asarray(cxy, dtype=float)
            )
            try:
                verts_xy = _beso9_equilateral_vertices_xy(
                    [np.asarray(p, dtype=float) for p in outer_xy],
                    xy_pad=float(xy_pad),
                    center_xy=np.asarray(cxy, dtype=float),
                )
            except Exception:
                # 回退：外柱点径向外扩（非等边）
                verts_xy = []
                for pxy in outer_xy:
                    vxy = np.asarray(pxy, dtype=float) - radial_origin
                    nv = _norm(vxy)
                    if nv <= 1.0e-9:
                        pxy2 = np.asarray(pxy, dtype=float).copy()
                    else:
                        pxy2 = np.asarray(pxy, dtype=float) + (vxy / nv) * xy_pad
                    verts_xy.append(np.asarray(pxy2, dtype=float).reshape(-1)[:2])
            low_pts = [np.array([float(v[0]), float(v[1]), float(z_bot)], dtype=float) for v in verts_xy]
            domain_vol = _triangle_prism(gmsh, low_pts, dz=float(z_top - z_bot))

        gmsh.model.occ.synchronize()

        # 2) 布尔挖孔
        z_span = float(z_top - z_bot)
        z_cut_pad = max(1200.0, min(6000.0, 0.06 * z_span))
        cut_tools: list[tuple[int, int]] = []
        if envelope == "triangle_prism":
            # beso9：仅在三顶角（+可选中心）挖通高圆柱；禁止挖桩靴，否则底面呈台阶怪形
            side_mm = _mean_triangle_edge_mm(verts_xy) if verts_xy else 95000.0
            if corner_r_mm is not None and float(corner_r_mm) > 0:
                corner_r = clamp_corner_r_mm(float(corner_r_mm), side_mm)
            else:
                corner_r = clamp_corner_r_mm(
                    _beso9_corner_radius_mm(side_mm, shaft_rs_for_corner),
                    side_mm,
                )
            if out_info is not None:
                out_info["corner_r_mm"] = float(corner_r)
                out_info["corner_r_requested_mm"] = (
                    float(corner_r_mm) if corner_r_mm is not None and float(corner_r_mm) > 0 else None
                )
                out_info["triangle_side_mm"] = float(side_mm)
                out_info["domain_z_span_mm"] = float(z_span)
                out_info["corner_centers_xy_mm"] = [
                    [float(v[0]), float(v[1])] for v in verts_xy
                ]
                out_info["domain_center_xy_mm"] = [float(cxy[0]), float(cxy[1])]
                # 对齐 BESO9.FCStd：Ø12 m 顶环圆周载荷（随边长略缩放，下限 6 m）
                load_d = float(max(6000.0, min(12000.0, 0.126 * float(side_mm))))
                out_info["load_diameter_mm"] = load_d
                out_info["load_radius_mm"] = load_d * 0.5
                out_info["load_application"] = "circumference_edge"
            r_eps = _boolean_radial_eps(corner_r)
            for vxy in verts_xy:
                _append_shaft_cut_xy(
                    cut_tools,
                    gmsh,
                    float(vxy[0]),
                    float(vxy[1]),
                    float(corner_r),
                    z_bot,
                    z_top,
                    z_cut_pad,
                    r_eps,
                )
            if cut_center_column:
                if center_hole_r_mm is not None and float(center_hole_r_mm) > 0:
                    cr = float(center_hole_r_mm)
                elif beam_geom is not None:
                    cr = float(beam_geom.center_shaft_r)
                else:
                    assert center_col is not None
                    cr = float(center_col.radius)
                # 中心孔与边立柱挖去半径独立：不再用 0.45*corner_r 耦合放大中心孔
                cr = float(max(cr, 100.0))
                if out_info is not None:
                    out_info["center_hole_r_mm"] = float(cr)
                    out_info["center_hole_r_requested_mm"] = (
                        float(center_hole_r_mm)
                        if center_hole_r_mm is not None and float(center_hole_r_mm) > 0
                        else None
                    )
                _append_shaft_cut_xy(
                    cut_tools,
                    gmsh,
                    float(cxy[0]),
                    float(cxy[1]),
                    cr,
                    z_bot,
                    z_top,
                    z_cut_pad,
                    _boolean_radial_eps(cr),
                )
        elif beam_geom is not None:
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
        if cut_tools:
            gmsh.model.occ.cut([domain_vol], cut_tools, removeObject=True, removeTool=True)

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
    parser.add_argument(
        "--envelope",
        choices=("hull_bbox", "triangle_prism"),
        default="triangle_prism",
        help="triangle_prism：beso9 式三棱柱包络（默认）；hull_bbox：整装配轴对齐包围盒 slab。",
    )
    args = parser.parse_args()
    build_oc4_design_domain_iges(
        Path(args.src_iges),
        Path(args.out_iges),
        out_step=Path(args.step) if args.step else None,
        cut_center_column=not args.edge_columns_only,
        include_source_geometry=bool(args.include_source),
        domain_envelope=str(args.envelope),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
