# SPDX-License-Identifier: LGPL-2.1-or-later
"""
在 FreeCAD Python 内为 BESO3.FCStd 配置 FEM 约束/载荷并写出参考 CalculiX INP。

  D:\\freecad\\bin\\python.exe scripts/setup_beso3_fem_fcstd.py \\
      --fcstd examples/beso2/BESO3.FCStd \\
      --out-work examples/beso2/_work_common

产出：
  - fem_reference.inp      （柱底固定 + 顶区 +X 281 kN，论文工况）
  - fem_reference_z.inp      （柱底固定 + 顶区 -Z 281 kN，截图竖向工况）
  - 回写 FCStd（约束与力对象）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_qt() -> None:
    try:
        from PySide2 import QtCore  # type: ignore

        if QtCore.QCoreApplication.instance() is None:
            QtCore.QCoreApplication(sys.argv)
    except Exception:
        try:
            from PySide6 import QtCore  # type: ignore

            if QtCore.QCoreApplication.instance() is None:
                QtCore.QCoreApplication(sys.argv)
        except Exception:
            pass


def _bottom_face_refs(geom_obj, z_frac: float = 0.02) -> list:
    sh = geom_obj.Shape
    bb = sh.BoundBox
    z_tol = max((bb.ZMax - bb.ZMin) * z_frac, 1.0)
    z_cut = bb.ZMin + z_tol
    refs = []
    for i, face in enumerate(sh.Faces):
        try:
            cz = float(face.CenterOfMass.z)
        except Exception:
            continue
        if cz <= z_cut:
            refs.append((geom_obj, f"Face{i + 1}"))
    return refs


def _top_face_refs(geom_obj, z_frac: float = 0.08) -> list:
    sh = geom_obj.Shape
    bb = sh.BoundBox
    z_tol = max((bb.ZMax - bb.ZMin) * z_frac, 1.0)
    z_cut = bb.ZMax - z_tol
    refs = []
    for i, face in enumerate(sh.Faces):
        try:
            cz = float(face.CenterOfMass.z)
        except Exception:
            continue
        if cz >= z_cut:
            refs.append((geom_obj, f"Face{i + 1}"))
    return refs


def _get_or_create_analysis(doc):
    import ObjectsFem  # noqa: PLC0415

    for o in doc.Objects:
        if getattr(o, "TypeId", "") == "Fem::FemAnalysis":
            return o
    return ObjectsFem.makeAnalysis(doc, "Analysis001")


def _get_or_create_solver(doc, analysis):
    import ObjectsFem  # noqa: PLC0415

    for o in analysis.Group:
        if "Fem::FemSolver" in getattr(o, "TypeId", ""):
            return o
    solver = ObjectsFem.makeSolverCalculixCcxTools(doc, "SolverCcxTools001")
    solver.AnalysisType = "static"
    solver.GeometricalNonlinearity = "linear"
    solver.SplitInputWriter = False
    analysis.addObject(solver)
    return solver


def _direction_ref(doc, axis: str):
    """全局 X/Y/Z 方向引用线（ConstraintForce.Direction 需绑定边）。"""
    import Part  # noqa: PLC0415

    name = f"_ForceDir{axis.upper()}"
    o = doc.getObject(name)
    if o is None:
        o = doc.addObject("Part::Feature", name)
        if axis.lower() == "x":
            o.Shape = Part.makeLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0))
        elif axis.lower() == "y":
            o.Shape = Part.makeLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0))
        else:
            o.Shape = Part.makeLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1))
    return o, ["Edge1"]


def _get_or_create_material(doc, analysis):
    import ObjectsFem  # noqa: PLC0415

    for o in analysis.Group:
        if getattr(o, "TypeId", "") in ("App::MaterialObjectPython", "Fem::MaterialCommon"):
            mat_obj = o
            break
    else:
        mat_obj = ObjectsFem.makeMaterialSolid(doc, "MaterialSolid001")
        analysis.addObject(mat_obj)
    mat = mat_obj.Material
    mat["Name"] = "Steel"
    mat["YoungsModulus"] = "200000 MPa"
    mat["PoissonRatio"] = "0.27"
    mat["Density"] = "7833 kg/m^3"
    mat_obj.Material = mat
    return mat_obj


def _get_or_create_mesh(doc, analysis, geom):
    import ObjectsFem  # noqa: PLC0415
    from femexamples.meshes import generate_mesh  # noqa: PLC0415

    mesh = None
    for o in doc.Objects:
        if o is None:
            continue
        tid = getattr(o, "TypeId", "") or ""
        if tid.startswith("Fem::") and "MeshGmsh" in (o.Name or ""):
            mesh = o
            break
    if mesh is None:
        mesh = ObjectsFem.makeMeshGmsh(doc, "FEMMeshGmsh001")
        analysis.addObject(mesh)
    mesh.Shape = geom
    mesh.SecondOrderLinear = False
    mesh.ElementOrder = "1st"
    mesh.CharacteristicLengthMax = "800 mm"
    mesh.CharacteristicLengthMin = "200 mm"
    doc.recompute()
    ok = generate_mesh.mesh_from_mesher(mesh, "gmsh")
    if not ok:
        raise RuntimeError("Gmsh FEM 网格生成失败")
    return mesh


def _write_inp(doc, analysis, work_dir: Path, base: str) -> Path:
    from femtools import ccxtools  # noqa: PLC0415

    tools = ccxtools.FemToolsCcx(analysis=analysis)
    tools.update_objects()
    tools.setup_working_dir(str(work_dir), create=True)
    tools.set_base_name(base)
    msg = tools.check_prerequisites()
    if msg:
        print(f"[WARN] FEM prerequisites: {msg.replace(chr(10), ' | ')}", file=sys.stderr)
    tools.write_inp_file()
    p = Path(tools.inp_file_name)
    if not p.is_file():
        raise RuntimeError(f"FEM 未写出 INP: {p}")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="BESO3 FCStd FEM 约束/载荷 + 参考 INP")
    ap.add_argument("--fcstd", type=Path, required=True)
    ap.add_argument("--out-work", type=Path, required=True)
    ap.add_argument("--force-n", type=float, default=281000.0, help="节点力合力标量 (N)")
    ap.add_argument("--no-save-fcstd", action="store_true")
    args = ap.parse_args()

    _ensure_qt()
    import FreeCAD  # noqa: PLC0415
    import ObjectsFem  # noqa: PLC0415

    fcstd = args.fcstd.resolve()
    work_dir = args.out_work.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    force_n = float(args.force_n)

    doc = FreeCAD.openDocument(str(fcstd))
    try:
        geom = (
            doc.getObject("Compound")
            or doc.getObject("Body")
            or doc.getObject("Pad001")
            or doc.getObject("Pad")
        )
        if geom is None:
            raise RuntimeError("未找到 Compound/Body/Pad001/Pad 几何体")

        analysis = _get_or_create_analysis(doc)
        _get_or_create_solver(doc, analysis)
        _get_or_create_material(doc, analysis)
        _get_or_create_mesh(doc, analysis, geom)

        bottom_refs = _bottom_face_refs(geom)
        if not bottom_refs:
            pad = doc.getObject("Pad")
            if pad is not None:
                bottom_refs = _bottom_face_refs(pad)
        if not bottom_refs:
            raise RuntimeError("未识别柱底面，请检查 Compound 几何")

        top_refs = _top_face_refs(geom)
        if not top_refs:
            pad001 = doc.getObject("Pad001")
            if pad001 is not None:
                top_refs = _top_face_refs(pad001)
        if not top_refs:
            raise RuntimeError("未识别顶面载荷区域")

        con_fixed = doc.getObject("ConstraintFixed")
        if con_fixed is None:
            for o in doc.Objects:
                if o is not None and getattr(o, "TypeId", "") == "Fem::ConstraintFixed":
                    con_fixed = o
                    break
        if con_fixed is None:
            con_fixed = ObjectsFem.makeConstraintFixed(doc, "ConstraintFixed")
            analysis.addObject(con_fixed)
        con_fixed.References = bottom_refs

        con_x = doc.getObject("ConstraintForcePaperX")
        if con_x is None:
            con_x = ObjectsFem.makeConstraintForce(doc, "ConstraintForcePaperX")
            analysis.addObject(con_x)
        con_x.References = top_refs
        con_x.Force = f"{force_n} N"
        con_x.Direction = _direction_ref(doc, "x")
        con_x.Reversed = False

        con_z = doc.getObject("ConstraintForceScreenshotZ")
        if con_z is None:
            con_z = ObjectsFem.makeConstraintForce(doc, "ConstraintForceScreenshotZ")
            analysis.addObject(con_z)
        con_z.References = top_refs
        con_z.Force = f"{force_n} N"
        con_z.Direction = _direction_ref(doc, "z")
        con_z.Reversed = True

        legacy = doc.getObject("ConstraintForce")
        if legacy is not None:
            try:
                analysis.removeObject(legacy)
            except Exception:
                pass
            try:
                doc.removeObject(legacy.Name)
            except Exception:
                pass

        doc.recompute()

        def _export_active(active_x: bool, active_z: bool, out_name: str) -> Path:
            con_x.Force = f"{force_n} N" if active_x else "0 N"
            con_z.Force = f"{force_n} N" if active_z else "0 N"
            doc.recompute()
            tmp_base = out_name.replace(".inp", "")
            p = _write_inp(doc, analysis, work_dir, tmp_base)
            dest = work_dir / out_name
            if p.resolve() != dest.resolve():
                dest.write_text(p.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            return dest

        p_x = _export_active(True, False, "fem_reference.inp")
        p_z = _export_active(False, True, "fem_reference_z.inp")
        print("[OK] fem_reference.inp:", p_x, p_x.stat().st_size)
        print("[OK] fem_reference_z.inp:", p_z, p_z.stat().st_size)

        if not args.no_save_fcstd:
            doc.save()
            print("[OK] saved FCStd:", fcstd)
    finally:
        FreeCAD.closeDocument(doc.Name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
