#!/usr/bin/env python3
"""FreeCAD runner: beso9-style prism design domain build + mesh.

Usage (FreeCAD python):
  freecad/bin/python.exe scripts/freecad_prism_design_domain.py build --spec prism_spec.json --out out.FCStd
  freecad/bin/python.exe scripts/freecad_prism_design_domain.py mesh --fcstd out.FCStd --out-inp 03_for_beso.inp
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
from pathlib import Path


def _load_spec(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("spec must be a JSON object")
    return data


def _f(spec: dict, key: str, default: float) -> float:
    v = spec.get(key, default)
    return float(v if v is not None else default)


def _ensure_qt() -> None:
    try:
        from PySide2 import QtCore  # type: ignore

        if QtCore.QCoreApplication.instance() is None:
            QtCore.QCoreApplication([])
    except Exception:
        try:
            from PySide6 import QtCore  # type: ignore

            if QtCore.QCoreApplication.instance() is None:
                QtCore.QCoreApplication([])
        except Exception:
            pass


def _equilateral_vertices(side: float) -> list[tuple[float, float]]:
    h = side * math.sqrt(3.0) / 2.0
    return [
        (0.0, 2.0 * h / 3.0),
        (side / 2.0, -h / 3.0),
        (-side / 2.0, -h / 3.0),
    ]


def _make_raised_ring(z_top: float, r_outer: float, wall: float, height: float):
    import Part  # noqa: PLC0415
    import FreeCAD as App  # noqa: PLC0415

    r_inner = max(r_outer - wall, r_outer * 0.5)
    outer = Part.makeCylinder(r_outer, height, App.Vector(0, 0, z_top), App.Vector(0, 0, 1))
    inner = Part.makeCylinder(r_inner, height + 2.0, App.Vector(0, 0, z_top - 1.0), App.Vector(0, 0, 1))
    return outer.cut(inner).removeSplitter()


def build_fcstd(spec: dict, out_fcstd: Path) -> None:
    _ensure_qt()
    import FreeCAD as App  # noqa: PLC0415
    import Part  # noqa: PLC0415
    import ObjectsFem  # noqa: PLC0415

    side = _f(spec, "side_mm", 95000.0)
    height_above = _f(spec, "height_above_mm", 17000.0)
    height_below = _f(spec, "height_below_mm", 21000.0)
    corner_r = _f(spec, "corner_r_mm", 7500.0)
    load_d = _f(spec, "load_diameter_mm", 12000.0)
    force_n = _f(spec, "force_n", 2.45e7)
    ring_h = _f(spec, "ring_h_mm", 100.0)
    ring_wall = _f(spec, "ring_wall_mm", 200.0)
    mesh_max = _f(spec, "mesh_max_mm", 2000.0)
    mesh_min = _f(spec, "mesh_min_mm", 1000.0)

    out_fcstd = out_fcstd.resolve()
    out_fcstd.parent.mkdir(parents=True, exist_ok=True)
    if out_fcstd.is_file():
        out_fcstd.unlink()

    doc = App.newDocument("BESO_PRISM")

    verts = _equilateral_vertices(side)
    wire = Part.makePolygon(
        [App.Vector(x, y, 0.0) for x, y in verts] + [App.Vector(verts[0][0], verts[0][1], 0.0)]
    )
    face = Part.Face(wire)
    if float(face.Area) <= 0:
        raise RuntimeError("triangular face area <= 0")

    solid = face.extrude(App.Vector(0, 0, height_above)).fuse(
        face.extrude(App.Vector(0, 0, -height_below))
    ).removeSplitter()

    z_bot0 = float(solid.BoundBox.ZMin)
    z_top0 = float(solid.BoundBox.ZMax)
    h_cut = (z_top0 - z_bot0) + 200.0
    for vx, vy in verts:
        cyl = Part.makeCylinder(
            corner_r,
            h_cut,
            App.Vector(vx, vy, z_bot0 - 100.0),
            App.Vector(0, 0, 1),
        )
        solid = solid.cut(cyl).removeSplitter()

    vol_after = float(solid.Volume)
    sharp_vol = float(face.Area) * (height_above + height_below)
    if vol_after >= sharp_vol * 0.999:
        raise RuntimeError(
            f"expected corner cylinder dig-outs (vol {vol_after:.3e} vs sharp {sharp_vol:.3e})"
        )

    r_outer = load_d / 2.0
    z_top_prism = float(solid.BoundBox.ZMax)
    ring = _make_raised_ring(z_top_prism, r_outer, ring_wall, ring_h)
    solid = solid.fuse(ring).removeSplitter()

    bf = doc.addObject("Part::Feature", "BooleanFragments")
    bf.Shape = solid
    pad = doc.addObject("Part::Feature", "Pad001")
    pad.Shape = solid
    pad.Visibility = False

    sh = bf.Shape
    z_top = float(sh.BoundBox.ZMax)
    z_bot = float(sh.BoundBox.ZMin)

    dir_face_idx = None
    best_top_a = -1.0
    for i, f in enumerate(sh.Faces):
        try:
            if type(f.Surface).__name__ != "Plane":
                continue
            n = f.normalAt(0.5, 0.5)
            if float(n.z) < 0.9:
                continue
            cz = float(f.CenterOfMass.z)
            if cz < z_top - ring_h - 50.0:
                continue
            a = float(f.Area)
            if a > best_top_a:
                best_top_a = a
                dir_face_idx = i + 1
        except Exception:
            continue
    if dir_face_idx is None:
        raise RuntimeError("no top +Z direction face")

    load_edge_idx = None
    best_score = 1e99
    for i, e in enumerate(sh.Edges):
        try:
            curve = e.Curve
            if type(curve).__name__ not in ("Circle", "ArcOfCircle"):
                continue
            r = float(curve.Radius)
            cz = float(curve.Center.z) if hasattr(curve.Center, "z") else float(e.CenterOfMass.z)
            dr = abs(r - r_outer)
            dz = abs(cz - z_top)
            if dr > 50.0 or dz > ring_h + 5.0:
                continue
            score = dr + dz * 0.1
            score -= min(float(e.Length), 2 * math.pi * r_outer) * 1e-6
            if score < best_score:
                best_score = score
                load_edge_idx = i + 1
        except Exception:
            continue
    if load_edge_idx is None:
        raise RuntimeError(f"outer load circumference Edge missing (R={r_outer})")

    fix_edges: list[int] = []
    arc_cand: list[tuple[float, int]] = []
    for i, e in enumerate(sh.Edges):
        try:
            curve = e.Curve
            if type(curve).__name__ not in ("Circle", "ArcOfCircle"):
                continue
            r = float(curve.Radius)
            if abs(r - corner_r) > 50.0:
                continue
            zs = [float(v.Point.z) for v in e.Vertexes]
            if not zs or abs(sum(zs) / len(zs) - z_bot) > 2.0:
                continue
            arc_cand.append((float(e.Length), i + 1))
        except Exception:
            continue
    arc_cand.sort(reverse=True)
    fix_edges = [e for _, e in arc_cand[:3]]
    if len(fix_edges) < 3:
        cand = []
        for i, e in enumerate(sh.Edges):
            try:
                zs = [float(v.Point.z) for v in e.Vertexes]
                if not zs or abs(sum(zs) / len(zs) - z_bot) > 2.0:
                    continue
                cname = type(e.Curve).__name__
                if cname not in ("Circle", "ArcOfCircle", "BSplineCurve"):
                    continue
                if float(e.Length) < 1000.0:
                    continue
                cand.append((float(e.Length), i + 1))
            except Exception:
                pass
        cand.sort(reverse=True)
        fix_edges = [e for _, e in cand[:3]]
    if len(fix_edges) < 3:
        raise RuntimeError(f"need 3 bottom fix edges, got {fix_edges}")

    analysis = ObjectsFem.makeAnalysis(doc, "Analysis")
    _mk_solver = getattr(ObjectsFem, "makeSolverCalculiXCcxTools", None) or getattr(
        ObjectsFem, "makeSolverCalculixCcxTools"
    )
    solver = _mk_solver(doc, "SolverCcxTools")
    solver.AnalysisType = "static"
    analysis.addObject(solver)

    mat = ObjectsFem.makeMaterialSolid(doc, "MaterialSolid")
    m = mat.Material
    m["Name"] = "Steel"
    m["YoungsModulus"] = "200000 MPa"
    m["PoissonRatio"] = "0.27"
    m["Density"] = "7833 kg/m^3"
    mat.Material = m
    analysis.addObject(mat)

    mesh = ObjectsFem.makeMeshGmsh(doc, "FEMMeshGmsh")
    mesh.Label = "FEMMeshGmsh002"
    mesh.Shape = bf
    for attr, val in (
        ("CharacteristicLengthMax", f"{mesh_max} mm"),
        ("CharacteristicLengthMin", f"{mesh_min} mm"),
    ):
        try:
            setattr(mesh, attr, val)
        except Exception:
            pass
    analysis.addObject(mesh)

    con_fix = ObjectsFem.makeConstraintFixed(doc, "ConstraintFixed")
    con_fix.References = [(bf, tuple(f"Edge{e}" for e in fix_edges))]
    analysis.addObject(con_fix)

    con_f = ObjectsFem.makeConstraintForce(doc, "ConstraintForce")
    con_f.References = [(bf, (f"Edge{load_edge_idx}",))]
    con_f.Force = f"{force_n} N"
    con_f.Direction = (bf, [f"Face{dir_face_idx}"])
    con_f.Reversed = False
    analysis.addObject(con_f)

    doc.recompute()
    dv = con_f.DirectionVector
    if float(dv.z) >= 0:
        raise RuntimeError(
            f"force must be -Z (downward); got DirectionVector={dv} Reversed={con_f.Reversed}"
        )
    doc.saveAs(str(out_fcstd))
    # optional STEP preview next to FCStd
    try:
        step_path = out_fcstd.with_suffix(".step")
        sh.exportStep(str(step_path))
        print("[OK] wrote", step_path, flush=True)
    except Exception as e:
        print("[WARN] STEP export:", e, flush=True)
    print("[OK] wrote", out_fcstd, flush=True)
    print(
        f"[OK] side={side} corner_R={corner_r} H=[{z_bot:.1f},{z_top:.1f}] "
        f"load=Edge{load_edge_idx} dir=Face{dir_face_idx} fix={fix_edges} F={force_n:g} N",
        flush=True,
    )
    App.closeDocument(doc.Name)


def mesh_fcstd(fcstd: Path, out_inp: Path, mesh_max: float, mesh_min: float) -> None:
    _ensure_qt()
    import FreeCAD as App  # noqa: PLC0415
    from femmesh import gmshtools  # noqa: PLC0415
    from femtools import ccxtools  # noqa: PLC0415

    fcstd = fcstd.resolve()
    out_inp = out_inp.resolve()
    out_dir = out_inp.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_mesh_work"
    work.mkdir(parents=True, exist_ok=True)

    doc = App.openDocument(str(fcstd))
    try:
        mesh = doc.getObject("FEMMeshGmsh")
        if mesh is None:
            raise RuntimeError("FEMMeshGmsh missing — run build first")
        for attr, val in (
            ("CharacteristicLengthMax", f"{mesh_max} mm"),
            ("CharacteristicLengthMin", f"{mesh_min} mm"),
        ):
            try:
                setattr(mesh, attr, val)
            except Exception:
                pass
        print("[INFO] create_mesh…", flush=True)
        err = gmshtools.GmshTools(mesh).create_mesh()
        if err:
            print("[WARN] create_mesh:", err, file=sys.stderr)
        fm = mesh.FemMesh
        print(f"[OK] mesh nodes={fm.NodeCount} volumes={fm.VolumeCount}", flush=True)

        analysis = next(
            (o for o in doc.Objects if getattr(o, "TypeId", "") == "Fem::FemAnalysis"),
            None,
        )
        if analysis is None:
            raise RuntimeError("Analysis missing")
        tools = ccxtools.FemToolsCcx(analysis=analysis)
        tools.update_objects()
        tools.setup_working_dir(str(work), create=True)
        tools.set_base_name("fem_reference")
        tools.write_inp_file()
        written = Path(tools.inp_file_name)
        dest = work / "fem_reference.inp"
        alt = work / "FEMMeshGmsh.inp"
        if written.is_file() and written.resolve() != dest.resolve():
            shutil.copy2(written, dest)
        if (not dest.is_file() or dest.stat().st_size < 10_000) and alt.is_file():
            shutil.copy2(alt, dest)
        if alt.is_file() and alt.stat().st_size > 10_000:
            if written.is_file() and "FEMMeshGmsh" in written.name:
                shutil.copy2(written, dest)
            elif dest.is_file() and dest.stat().st_size < alt.stat().st_size * 0.5:
                shutil.copy2(alt, dest)
        if not dest.is_file() or dest.stat().st_size < 10_000:
            raise RuntimeError(f"fem_reference.inp incomplete: {dest}")

        text = dest.read_text(encoding="utf-8", errors="ignore")
        z_loads: list[float] = []
        in_cload = False
        for line in text.splitlines():
            s = line.strip()
            if not s:
                if in_cload:
                    in_cload = False
                continue
            if s.startswith("**"):
                continue
            if s.startswith("*"):
                in_cload = s.upper().startswith("*CLOAD")
                continue
            if not in_cload:
                continue
            m = re.match(r"^([0-9]+)\s*,\s*3\s*,\s*([-0-9.eE+]+)\s*$", s)
            if m:
                z_loads.append(float(m.group(2)))
        if not z_loads:
            raise RuntimeError("INP has no DOF3 CLOAD entries")
        n_neg = sum(1 for v in z_loads if v < 0)
        n_pos = sum(1 for v in z_loads if v > 0)
        if n_pos > 0 or n_neg == 0:
            raise RuntimeError(
                f"force must be downward (-Z); got pos={n_pos} neg={n_neg} CLOADs on DOF3"
            )
        shutil.copy2(dest, out_inp)
        print("[OK]", out_inp, out_inp.stat().st_size, "bytes", flush=True)
        try:
            doc.save()
        except Exception as e:
            print("[WARN] FCStd save:", e, file=sys.stderr)
    finally:
        App.closeDocument(doc.Name)


def main() -> int:
    ap = argparse.ArgumentParser(description="Prism design domain FreeCAD runner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--spec", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)

    m = sub.add_parser("mesh")
    m.add_argument("--fcstd", type=Path, required=True)
    m.add_argument("--out-inp", type=Path, required=True)
    m.add_argument("--mesh-max", type=float, default=2000.0)
    m.add_argument("--mesh-min", type=float, default=1000.0)
    m.add_argument("--spec", type=Path, default=None)

    args = ap.parse_args()
    if args.cmd == "build":
        spec = _load_spec(args.spec)
        build_fcstd(spec, args.out)
        return 0
    if args.cmd == "mesh":
        mesh_max = float(args.mesh_max)
        mesh_min = float(args.mesh_min)
        if args.spec and args.spec.is_file():
            spec = _load_spec(args.spec)
            mesh_max = _f(spec, "mesh_max_mm", mesh_max)
            mesh_min = _f(spec, "mesh_min_mm", mesh_min)
        mesh_fcstd(args.fcstd, args.out_inp, mesh_max, mesh_min)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
