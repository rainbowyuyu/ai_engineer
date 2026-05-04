"""
将导管架梁拓扑（结点 + 线段 + 外半径）近似为圆柱壳三角网格，便于可视化「有粗细的结构」。

说明：这是 **仅用于显示** 的表面网格；CalculiX 中的 B31 仍是线单元力学模型。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def _orthonormal_frame(axis_unit: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ref = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(axis_unit, ref))) > 0.9:
        ref = np.array([1.0, 0.0, 0.0], dtype=float)
    v = np.cross(axis_unit, ref)
    nv = float(np.linalg.norm(v))
    if nv <= 1.0e-15:
        ref = np.array([0.0, 1.0, 0.0], dtype=float)
        v = np.cross(axis_unit, ref)
        nv = float(np.linalg.norm(v))
    v = v / nv
    w = np.cross(axis_unit, v)
    nw = float(np.linalg.norm(w))
    if nw <= 1.0e-15:
        return v, np.cross(v, axis_unit)
    return v, w / nw


def beam_topology_to_triangle_mesh(
    nodes: list[np.ndarray],
    elements: list[tuple[int, int, float]],
    *,
    n_facets: int = 16,
    outer_radius_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (points [N,3], triangles [M,3] int64).
    ``elements`` each row (node_a, node_b, outer_radius_mm).
    """
    nf = max(8, min(64, int(n_facets)))
    verts: list[list[float]] = []
    faces: list[tuple[int, int, int]] = []

    for a, b, R in elements:
        p0 = np.asarray(nodes[int(a)], dtype=float).ravel()[:3]
        p1 = np.asarray(nodes[int(b)], dtype=float).ravel()[:3]
        d = p1 - p0
        L = float(np.linalg.norm(d))
        if L <= 1.0e-9:
            continue
        u = d / L
        r = float(R) * float(outer_radius_scale)
        if not np.isfinite(r) or r <= 0.0:
            continue
        vhat, what = _orthonormal_frame(u)

        ring0: list[int] = []
        ring1: list[int] = []
        for i in range(nf):
            ang = (2.0 * np.pi * i) / nf
            c, s = float(np.cos(ang)), float(np.sin(ang))
            off = r * (c * vhat + s * what)
            ring0.append(len(verts))
            verts.append((p0 + off).tolist())
            ring1.append(len(verts))
            verts.append((p1 + off).tolist())

        for i in range(nf):
            i1 = (i + 1) % nf
            a0, a1 = ring0[i], ring0[i1]
            b0, b1 = ring1[i], ring1[i1]
            # outward-ish winding
            faces.append((a0, b0, b1))
            faces.append((a0, b1, a1))

    if not verts:
        raise ValueError("未生成任何三角面（检查 elements / 半径）")
    pts = np.asarray(verts, dtype=float)
    tri = np.asarray(faces, dtype=np.int64)
    return pts, tri


def write_wavefront_obj(path: Path, points: np.ndarray, triangles: np.ndarray) -> Path:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# jacket beam skin (cylinder approximation)")
    for row in points:
        lines.append(f"v {row[0]:.9f} {row[1]:.9f} {row[2]:.9f}")
    for a, b, c in triangles:
        lines.append(f"f {a + 1} {b + 1} {c + 1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_beam_skin_mesh(
    nodes: list[np.ndarray],
    elements: list[tuple[int, int, float]],
    dest: Path,
    *,
    n_facets: int = 16,
    outer_radius_scale: float = 1.0,
    fmt: str = "obj",
) -> Path:
    fmt = (fmt or "obj").lower().strip()
    pts, tri = beam_topology_to_triangle_mesh(
        nodes,
        elements,
        n_facets=n_facets,
        outer_radius_scale=outer_radius_scale,
    )
    dest = Path(dest)
    if fmt == "obj":
        return write_wavefront_obj(dest, pts, tri)
    if fmt in {"vtk", "vtu"}:
        try:
            import meshio

            meshio.write(dest, meshio.Mesh(pts, [("triangle", tri)]))
            return dest.resolve()
        except Exception as e:
            raise RuntimeError(f"写入 {fmt} 需要 meshio：{e}") from e
    raise ValueError(f"不支持格式: {fmt}")
