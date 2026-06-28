# SPDX-License-Identifier: LGPL-2.1-or-later
"""
在 FreeCAD 内为 BESO3（beso4）补全三角顶点侧立柱，写出含四柱（中央+三角顶点）的 STEP。

  D:\\freecad\\bin\\python.exe scripts/beso4_build_full_step.py \\
      --fcstd examples/beso4/BESO3.FCStd \\
      --out examples/beso4/_work/_fuse_export.step
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path


def _triangle_corner_xy(pad001_shape, z_level: float) -> list[tuple[float, float]]:
    """Pad001 顶面三角三顶点：去重后取最大面积三角形（避免倒角短边误判）。"""
    import itertools

    pts: list[tuple[float, float]] = []
    for v in pad001_shape.Vertexes:
        p = v.Point
        if abs(float(p.z) - z_level) < 50.0:
            pts.append((float(p.x), float(p.y)))
    if len(pts) < 3:
        bb = pad001_shape.BoundBox
        pts = [
            (float(bb.XMin), float(bb.YMin)),
            (float(bb.XMax), float(bb.YMin)),
            (float((bb.XMin + bb.XMax) / 2), float(bb.YMax)),
        ]
    unique: list[tuple[float, float]] = []
    for x, y in pts:
        if all((x - ux) ** 2 + (y - uy) ** 2 > 1.0e6 for ux, uy in unique):
            unique.append((x, y))
    if len(unique) <= 3:
        return unique[:3]

    def _area2(a, b, c) -> float:
        return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))

    best: tuple[tuple[float, float], ...] = tuple(unique[:3])
    best_a = _area2(*best)
    for combo in itertools.combinations(unique, 3):
        a2 = _area2(*combo)
        if a2 > best_a:
            best_a = a2
            best = combo
    return list(best)


def main() -> int:
    ap = argparse.ArgumentParser(description="BESO4 全几何 STEP（Body + 三角顶点侧立柱）")
    ap.add_argument("--fcstd", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pillar-radius-mm", type=float, default=3500.0)
    ap.add_argument("--footing-radius-mm", type=float, default=5500.0)
    ap.add_argument("--footing-height-mm", type=float, default=2500.0)
    args = ap.parse_args()

    import FreeCAD  # noqa: PLC0415
    import Part  # noqa: PLC0415

    fcstd = args.fcstd.resolve()
    out_step = args.out.resolve()
    out_step.parent.mkdir(parents=True, exist_ok=True)

    doc = FreeCAD.openDocument(str(fcstd))
    try:
        body = doc.getObject("Body")
        pad001 = doc.getObject("Pad001")
        if body is None or pad001 is None:
            raise RuntimeError("需要 Body 与 Pad001")
        body_sh = body.Shape
        pad001_sh = pad001.Shape
        z_min = float(body_sh.BoundBox.ZMin)
        z_top_pad = float(pad001_sh.BoundBox.ZMax)
        z_max = float(body_sh.BoundBox.ZMax)

        corners = _triangle_corner_xy(pad001_sh, z_top_pad)
        print("[INFO] triangle corners XY:", corners)

        fused = body_sh
        r_pillar = float(args.pillar_radius_mm)
        r_foot = float(args.footing_radius_mm)
        h_foot = float(args.footing_height_mm)

        for i, (x, y) in enumerate(corners):
            foot = Part.makeCylinder(
                r_foot,
                h_foot,
                FreeCAD.Vector(x, y, z_min),
                FreeCAD.Vector(0, 0, 1),
            )
            col = Part.makeCylinder(
                r_pillar,
                z_max - z_top_pad,
                FreeCAD.Vector(x, y, z_top_pad),
                FreeCAD.Vector(0, 0, 1),
            )
            fused = fused.fuse(foot).fuse(col)
            print(f"[INFO] corner pillar {i + 1}: ({x:.1f}, {y:.1f}) r={r_pillar} z {z_top_pad}..{z_max}")

        fused.exportStep(str(out_step))
        try:
            n_sol = len(fused.Solids)
            v = float(fused.Volume)
        except Exception:
            n_sol, v = -1, float("nan")
        print(f"[OK] exported {out_step} solids={n_sol} volume={v:.6g}")
    finally:
        FreeCAD.closeDocument(doc.Name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
