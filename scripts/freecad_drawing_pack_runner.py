# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FreeCADCmd / FreeCAD python.exe：从 STEP/IGES/STL 生成多视图线框投影（HLR 简化投影）。

环境变量 ``FC_DRAWING_PACK_CONFIG`` → JSON（``.fcdraw``）：
- cad_path: 输入 .step/.stp/.iges/.igs/.stl
- out_dir: 输出目录
- views: 可选 ["iso","top","front","right"]
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

_CONFIG_EXT = ".fcdraw"


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _config_path() -> Path:
    env = (os.environ.get("FC_DRAWING_PACK_CONFIG") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        _die(f"FC_DRAWING_PACK_CONFIG 不存在: {env}", 2)
    for a in sys.argv[1:]:
        p = Path(a)
        if p.is_file() and p.suffix.lower() == _CONFIG_EXT:
            return p.resolve()
    _die(f"用法: FreeCADCmd freecad_drawing_pack_runner.py <config{_CONFIG_EXT}>", 2)


def _as_vector(FreeCAD, x, y, z):
    return FreeCAD.Vector(float(x), float(y), float(z))


def _edge_sample_count(edge, default_samples: int = 24) -> int:
    """More samples for long / curved edges so cylinders don't look broken."""
    try:
        length = float(edge.Length)
    except Exception:
        length = 0.0
    try:
        curve = edge.Curve
        cname = type(curve).__name__.lower()
    except Exception:
        cname = ""
    if any(k in cname for k in ("circle", "ellipse", "bpline", "bezier", "hyperbola", "parabola")):
        n = max(default_samples, 36)
        if length > 0:
            n = max(n, min(96, int(length / 800.0) + 24))
        return n
    if length > 0:
        return max(4, min(48, int(length / 2500.0) + 4))
    return max(4, int(default_samples))


def _project_polylines(shape, direction, FreeCAD, *, max_edges: int = 20000, samples: int = 24):
    """Orthographic project shape edges onto plane ⟂ direction → 2D polylines.

    Note: ``Shape.project()`` often returns empty for complex IGES compounds; we
    project original edges by dropping the component along ``direction``.
    Prefer keeping all edges (cap only as last resort) so cylinders/bracing stay continuous.
    """
    d = direction.normalize()
    arb = FreeCAD.Vector(0, 0, 1) if abs(d.z) < 0.9 else FreeCAD.Vector(1, 0, 0)
    u = d.cross(arb)
    if u.Length < 1e-12:
        arb = FreeCAD.Vector(0, 1, 0)
        u = d.cross(arb)
    u.normalize()
    v = d.cross(u)
    v.normalize()
    basis = {"u": [u.x, u.y, u.z], "v": [v.x, v.y, v.z], "d": [d.x, d.y, d.z]}

    edges = list(getattr(shape, "Edges", None) or [])
    if len(edges) > max_edges:
        # Prefer longer edges when forced to cap (keeps primary structure)
        def _elen(e):
            try:
                return float(e.Length)
            except Exception:
                return 0.0

        edges = sorted(edges, key=_elen, reverse=True)[:max_edges]

    polys = []
    for e in edges:
        pts = None
        n_samp = _edge_sample_count(e, samples)
        try:
            pts = e.discretize(Number=n_samp)
        except Exception:
            try:
                pts = e.discretize(Distance=max(float(getattr(e, "Length", 1.0) or 1.0) / max(n_samp - 1, 1), 1.0))
            except Exception:
                try:
                    pts = [e.Vertexes[0].Point, e.Vertexes[-1].Point]
                except Exception:
                    continue
        poly = []
        for p in pts:
            poly.append([float(p.dot(u)), float(p.dot(v))])
        if len(poly) >= 2:
            # skip degenerate (all same point)
            if max(abs(poly[i][0] - poly[0][0]) for i in range(len(poly))) < 1e-12 and max(
                abs(poly[i][1] - poly[0][1]) for i in range(len(poly))
            ) < 1e-12:
                continue
            polys.append(poly)
    return polys, basis


def _project_polylines_from_mesh(mesh, direction, FreeCAD, *, max_edges: int = 20000):
    """Fallback: silhouette-ish edges from mesh topology (unique triangle edges)."""
    d = direction.normalize()
    arb = FreeCAD.Vector(0, 0, 1) if abs(d.z) < 0.9 else FreeCAD.Vector(1, 0, 0)
    u = d.cross(arb)
    if u.Length < 1e-12:
        arb = FreeCAD.Vector(0, 1, 0)
        u = d.cross(arb)
    u.normalize()
    v = d.cross(u)
    v.normalize()
    basis = {"u": [u.x, u.y, u.z], "v": [v.x, v.y, v.z], "d": [d.x, d.y, d.z]}
    try:
        pts3 = mesh.Points
        facets = mesh.Facets
    except Exception:
        return [], basis
    edge_set = set()
    for f in facets:
        idx = getattr(f, "PointIndices", None) or getattr(f, "Indices", None)
        if not idx or len(idx) < 3:
            continue
        a, b, c = int(idx[0]), int(idx[1]), int(idx[2])
        for e in ((a, b), (b, c), (c, a)):
            edge_set.add((min(e[0], e[1]), max(e[0], e[1])))
    polys = []
    for i, (ia, ib) in enumerate(edge_set):
        if i >= max_edges:
            break
        try:
            pa, pb = pts3[ia], pts3[ib]
            p0 = FreeCAD.Vector(pa.x, pa.y, pa.z) if hasattr(pa, "x") else FreeCAD.Vector(*pa)
            p1 = FreeCAD.Vector(pb.x, pb.y, pb.z) if hasattr(pb, "x") else FreeCAD.Vector(*pb)
        except Exception:
            continue
        polys.append([[float(p0.dot(u)), float(p0.dot(v))], [float(p1.dot(u)), float(p1.dot(v))]])
    return polys, basis


def _poly_len(poly) -> float:
    if len(poly) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(poly)):
        dx = float(poly[i][0]) - float(poly[i - 1][0])
        dy = float(poly[i][1]) - float(poly[i - 1][1])
        total += (dx * dx + dy * dy) ** 0.5
    return total


def _filter_short_polylines(polys, *, min_frac: float = 0.0015):
    """Drop tiny edges relative to view span (noise reduction, not true HLR)."""
    if not polys:
        return polys
    all_xy = [xy for poly in polys for xy in poly]
    if not all_xy:
        return polys
    xs = [p[0] for p in all_xy]
    ys = [p[1] for p in all_xy]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
    thr = span * min_frac
    kept = [p for p in polys if _poly_len(p) >= thr]
    return kept if kept else polys


def _bbox_from_shape(shape) -> dict:
    try:
        box = shape.BoundBox
        return {
            "xmin": float(box.XMin),
            "xmax": float(box.XMax),
            "ymin": float(box.YMin),
            "ymax": float(box.YMax),
            "zmin": float(box.ZMin),
            "zmax": float(box.ZMax),
            "dx": float(box.XLength),
            "dy": float(box.YLength),
            "dz": float(box.ZLength),
        }
    except Exception:
        return {"dx": 0.0, "dy": 0.0, "dz": 0.0}


def _guess_unit_and_span_mm(bbox: dict) -> tuple[str, float, dict]:
    """Return unit_guess, span_mm, bbox_mm."""
    dx = float(bbox.get("dx") or 0)
    dy = float(bbox.get("dy") or 0)
    dz = float(bbox.get("dz") or 0)
    span = max(dx, dy, dz, 0.0)
    if span <= 0:
        return "unknown", 0.0, {"dx": 0.0, "dy": 0.0, "dz": 0.0}
    if span >= 50:
        factor = 1.0
        unit = "mm (heuristic: large coords)"
    else:
        factor = 1000.0
        unit = "m→mm (heuristic: small coords)"
    bbox_mm = {"dx": dx * factor, "dy": dy * factor, "dz": dz * factor}
    return unit, span * factor, bbox_mm


def _write_svg(path: Path, polys, title: str, size: int = 640) -> None:
    all_xy = [xy for poly in polys for xy in poly]
    if not all_xy:
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
            f'<text x="20" y="40">{title}: empty</text></svg>',
            encoding="utf-8",
        )
        return
    xs = [p[0] for p in all_xy]
    ys = [p[1] for p in all_xy]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    dx = max(maxx - minx, 1e-9)
    dy = max(maxy - miny, 1e-9)
    pad = 0.08
    span = max(dx, dy)
    cx = 0.5 * (minx + maxx)
    cy = 0.5 * (miny + maxy)
    scale = (size * (1 - 2 * pad)) / span

    def map_pt(x, y):
        mx = size / 2 + (x - cx) * scale
        my = size / 2 - (y - cy) * scale
        return mx, my

    lengths = [_poly_len(p) for p in polys]
    thr = sorted(lengths)[int(0.75 * (len(lengths) - 1))] if lengths else 0.0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">',
        f'<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="16" y="28" font-family="Segoe UI,sans-serif" font-size="16" fill="#334155">{title}</text>',
    ]
    for poly, length in zip(polys, lengths):
        if len(poly) < 2:
            continue
        sw = 2.0 if length >= thr else 0.9
        d = "M " + " L ".join(f"{map_pt(x, y)[0]:.2f} {map_pt(x, y)[1]:.2f}" for x, y in poly)
        parts.append(f'<path d="{d}" fill="none" stroke="#1e293b" stroke-width="{sw}"/>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    try:
        import FreeCAD  # type: ignore
        import Import  # type: ignore
        import Mesh  # type: ignore
        import Part  # type: ignore
    except ImportError:
        _die("未导入 FreeCAD。请用 FreeCADCmd / FreeCAD python.exe 执行。", 2)

    cfg = json.loads(_config_path().read_text(encoding="utf-8"))
    cad = Path(cfg["cad_path"]).resolve()
    out_dir = Path(cfg["out_dir"]).resolve()
    if not cad.is_file():
        _die(f"CAD 不存在: {cad}")
    out_dir.mkdir(parents=True, exist_ok=True)

    view_names = cfg.get("views") or ["iso", "top", "front", "right"]
    directions = {
        "iso": _as_vector(FreeCAD, 1, 1, 1),
        "top": _as_vector(FreeCAD, 0, 0, 1),
        "front": _as_vector(FreeCAD, 0, -1, 0),
        "right": _as_vector(FreeCAD, 1, 0, 0),
    }

    doc = FreeCAD.newDocument("DrawingPack")
    try:
        ext = cad.suffix.lower()
        shape = None
        if ext in (".stl",):
            mesh = Mesh.Mesh(str(cad))
            shape = Part.Shape()
            shape.makeShapeFromMesh(mesh.Topology, 0.1)
        else:
            Import.insert(str(cad), doc.Name)
            doc.recompute()
            shapes = []
            for o in doc.Objects:
                sh = getattr(o, "Shape", None)
                if sh is not None and not sh.isNull():
                    shapes.append(sh)
            if not shapes:
                _die("未找到可投影的 Shape")
            shape = shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)

        # Tessellate for shaded fallback OBJ + optional mesh-edge projection
        linear_deflection = float(cfg.get("linear_deflection", 1200.0))
        mesh = None
        obj_path = None
        try:
            import MeshPart  # type: ignore

            mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=linear_deflection)
            obj_path = out_dir / "preview.obj"
            mesh.write(str(obj_path))
        except Exception as e:
            print(f"[WARN] OBJ tessellation skipped: {e}", file=sys.stderr)

        bbox = _bbox_from_shape(shape)
        unit_guess, span_mm, bbox_mm = _guess_unit_and_span_mm(bbox)

        views_payload = {}
        for name in view_names:
            direction = directions.get(name) or directions["iso"]
            polys, basis = _project_polylines(shape, direction, FreeCAD)
            if not polys and mesh is not None:
                polys, basis = _project_polylines_from_mesh(mesh, direction, FreeCAD)
            polys = _filter_short_polylines(polys)
            svg_path = out_dir / f"view_{name}.svg"
            _write_svg(svg_path, polys, name.upper())
            # Cap JSON only if huge; prefer longest polylines (better continuity)
            max_store = 20000
            if len(polys) <= max_store:
                store = polys
            else:
                store = sorted(polys, key=_poly_len, reverse=True)[:max_store]
            views_payload[name] = {
                "svg": svg_path.name,
                "polyline_count": len(polys),
                "stored_count": len(store),
                "basis": basis,
                "polylines": store,
            }

        meta = {
            "ok": True,
            "source": cad.name,
            "engine": "freecad",
            "views": {k: {"svg": v["svg"], "polyline_count": v["polyline_count"]} for k, v in views_payload.items()},
            "preview_obj": obj_path.name if obj_path else None,
            "bbox": bbox,
            "bbox_mm": bbox_mm,
            "span_mm": span_mm,
            "unit_guess": unit_guess,
        }
        (out_dir / "freecad_views.json").write_text(
            json.dumps({"meta": meta, "views": views_payload}, ensure_ascii=False),
            encoding="utf-8",
        )
        (out_dir / "freecad_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] FreeCAD drawing pack → {out_dir}")
        return 0
    finally:
        FreeCAD.closeDocument(doc.Name)


if __name__ == "__main__":
    raise SystemExit(main())
