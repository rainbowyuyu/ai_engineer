# SPDX-License-Identifier: LGPL-2.1-or-later
"""
在 **FreeCAD 自带 Python** 中执行（勿用仓库 .venv 直接跑）：

  D:\\freecad\\bin\\python.exe scripts/beso_fcstd_fem_dual_domain_export.py \\
      --fcstd examples/beso2/BESO3.FCStd --out examples/beso2/Analysis-beso-fem.inp --work-dir examples/beso2/_fem_export

流程（与 ``backend/oc4_methodology_chen2026.py`` 中 FCStd 基线一致）：

1. 使用 FreeCAD FEM **FemToolsCcx.write_inp_file**（内部 ``femsolver.calculix.writer.FemInputWriterCcx``）
   写出 CalculiX INP，**保留**文档中已配置的 ``*STEP``、``*BOUNDARY``、``*CLOAD``、幅值、输出请求等。
2. 按论文/仓库定标：**设计域** = 体单元重心落在 **Pad001**（可配置）实体 ``Shape.isInside`` 内；
   **非设计域** = 其余体单元；两域共用同一网格节点，**界面共节点连接**。
3. 将原 INP 中体积 ``*Element``（C3D4/C3D10 线性角点）替换为 ``Elset=design_space`` / ``Elset=nondesign_space``，
   并写两条 ``*Solid section`` 指向同一材料名（与 BESO ``domain_optimized['nondesign_space']=False`` 一致：非设计域不删减材料，但仍参与整体刚度）。

依赖：``femtools.ccxtools``（见 FreeCAD ``Mod/Fem/femtools/ccxtools.py``）。

若 ``check_prerequisites`` 失败，请在 FCStd 中补全 FEM 网格、材料、约束与力后再导出。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _ensure_qt_app() -> None:
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


def _geometry_shape(obj):
    import Part  # noqa: PLC0415

    sh = getattr(obj, "Shape", None)
    if sh is None or not isinstance(sh, Part.Shape):
        return None
    try:
        if sh.isNull():
            return None
    except Exception:
        return None
    return sh


def _design_object_shape_global(doc, design_name: str):
    import Part  # noqa: PLC0415

    o = doc.getObject(design_name)
    if o is None:
        return None
    try:
        sh = Part.getShape(o, "", False, False, True)
        if sh is not None and not sh.isNull():
            return sh
    except TypeError:
        try:
            sh = Part.getShape(o, "", False, True)
            if sh is not None and not sh.isNull():
                return sh
        except Exception:
            pass
    except Exception:
        pass
    return _geometry_shape(o)


def _partition_tolerance_mm(shape, override_mm: float | None) -> float:
    import Part  # noqa: PLC0415

    if override_mm is not None and float(override_mm) > 0.0:
        return float(override_mm)
    if not isinstance(shape, Part.Shape) or shape.isNull():
        return 1.0e-4
    try:
        diag = float(shape.BoundBox.DiagonalLength)
    except Exception:
        diag = 1.0
    return max(diag * 1.0e-8, 1.0e-4)


def _parse_nodes_and_volume_elements(text: str) -> tuple[dict[int, tuple[float, float, float]], dict[int, tuple[int, int, int, int]]]:
    """扫描 *NODE 与 C3D4/C3D10（二阶取前四个角点）单元。"""
    nodes: dict[int, tuple[float, float, float]] = {}
    elements: dict[int, tuple[int, int, int, int]] = {}
    in_node = False
    in_el = False
    el_type = ""

    def _is_coord_line(parts: list[str]) -> bool:
        if len(parts) < 4:
            return False
        try:
            int(parts[0])
            float(parts[1])
            float(parts[2])
            float(parts[3])
        except ValueError:
            return False
        return True

    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        u = s.upper()
        if u.startswith("*NODE"):
            in_node = True
            in_el = False
            continue
        if u.startswith("*ELEMENT"):
            in_node = False
            in_el = "C3D4" in u or "C3D10" in u
            el_type = "C3D10" if "C3D10" in u else ("C3D4" if "C3D4" in u else "")
            continue
        if s.startswith("*"):
            in_node = False
            in_el = False
            continue
        if in_node:
            parts = [p.strip() for p in s.split(",")]
            if _is_coord_line(parts):
                nid = int(parts[0])
                nodes[nid] = (float(parts[1]), float(parts[2]), float(parts[3]))
            continue
        if in_el and el_type:
            parts = [p.strip() for p in s.split(",")]
            if len(parts) >= 5 and all(p.lstrip("-").replace(".", "", 1).isdigit() for p in parts[:5]):
                eid = int(parts[0])
                if el_type == "C3D4":
                    elements[eid] = (int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
                else:
                    elements[eid] = (int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
    return nodes, elements


def _strip_volume_elements_and_solid_sections(pre_step: str) -> str:
    """去掉 *STEP 之前的体积单元行及 *Solid section 块，便于重写双 Elset。"""
    lines = pre_step.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    n = len(lines)

    def _is_volume_element_header(st: str) -> bool:
        u = st.strip().upper()
        return u.startswith("*ELEMENT") and ("C3D4" in u or "C3D10" in u)

    def _is_solid_section_header(st: str) -> bool:
        u = st.strip().upper()
        return u.startswith("*SOLID") and "SECTION" in u

    while i < n:
        line = lines[i]
        st = line.strip()
        if _is_volume_element_header(st):
            i += 1
            while i < n:
                t = lines[i].strip()
                if t.startswith("*") and not t.startswith("**"):
                    break
                if t.startswith("*") and t.startswith("**"):
                    i += 1
                    continue
                if not t:
                    i += 1
                    continue
                i += 1
            continue
        if _is_solid_section_header(st):
            i += 1
            while i < n:
                t = lines[i].strip()
                if t.startswith("**"):
                    i += 1
                    continue
                if t.startswith("*") and not t.startswith(","):
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    return "".join(out)


def _first_material_name(pre_step: str) -> str | None:
    m = re.search(r"(?im)^\*\s*MATERIAL\s*,\s*NAME\s*=\s*([^\s,]+)", pre_step)
    return m.group(1).strip() if m else None


def _remove_node_block(pre_step: str) -> str:
    """去掉 *NODE … 块（换用外部体网格的节点定义）。"""
    lines = pre_step.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip().upper().startswith("*NODE"):
            i += 1
            while i < n:
                t = lines[i].strip()
                if t.startswith("*") and not t.startswith("**"):
                    break
                if t.startswith("**"):
                    out.append(lines[i])
                    i += 1
                    continue
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def _merge_mesh_and_step_template(
    mesh_inp: Path,
    step_template_inp: Path,
    out_inp: Path,
    doc,
    design_solid: str,
    partition_tol_mm: float | None,
) -> tuple[int, int, str]:
    """体网格 INP + 含 *STEP 的模板 INP → 双域完整 deck（节点以 mesh_inp 为准）。"""
    import FreeCAD as App  # noqa: PLC0415

    mesh_raw = mesh_inp.read_text(encoding="utf-8", errors="replace")
    tmpl_raw = step_template_inp.read_text(encoding="utf-8", errors="replace")
    m_step = re.search(r"(?m)^\*Step\b", tmpl_raw, re.IGNORECASE)
    if not m_step:
        raise RuntimeError(f"模板中未找到 *Step: {step_template_inp}")
    tmpl_pre = tmpl_raw[: m_step.start()]
    tmpl_post = tmpl_raw[m_step.start() :]

    nodes, elements = _parse_nodes_and_volume_elements(mesh_raw)
    if not nodes or not elements:
        raise RuntimeError(f"mesh_inp 无体单元: nodes={len(nodes)} elements={len(elements)}")

    sh = _design_object_shape_global(doc, design_solid)
    if sh is None:
        raise RuntimeError(f"设计域对象不存在: {design_solid}")
    tol = _partition_tolerance_mm(sh, partition_tol_mm)
    design: list[int] = []
    nondesign: list[int] = []
    for eid, (n1, n2, n3, n4) in elements.items():
        pts = [nodes[n1], nodes[n2], nodes[n3], nodes[n4]]
        cx = sum(p[0] for p in pts) / 4.0
        cy = sum(p[1] for p in pts) / 4.0
        cz = sum(p[2] for p in pts) / 4.0
        v = App.Vector(cx, cy, cz)
        if sh.isInside(v, tol, True):
            design.append(eid)
        else:
            nondesign.append(eid)
    if not design or not nondesign:
        raise RuntimeError(f"划分失败 design={len(design)} nondesign={len(nondesign)}")

    mesh_pre = _strip_volume_elements_and_solid_sections(mesh_raw).rstrip() + "\n"
    tmpl_pre_stripped = _strip_volume_elements_and_solid_sections(tmpl_pre)
    tmpl_rest = _remove_node_block(tmpl_pre_stripped).lstrip("\n")
    if "*MATERIAL" not in tmpl_rest.upper():
        tmpl_rest = (
            "*Material, Name=Material-1\n"
            "*Elastic\n"
            "200000, 0.27\n"
            "*Density\n"
            "7.833e-9\n"
            "**\n" + tmpl_rest
        )

    mat = _first_material_name(tmpl_rest) or "Material-1"

    out_lines: list[str] = [
        "** CalculiX deck: volume mesh + step template + Pad001 dual elset (merge mode)\n",
        mesh_pre,
        tmpl_rest.rstrip() + "\n",
        "**\n** --- BESO dual domain (Chen2026 FCStd: Pad001 vs rest) ---\n",
    ]
    _format_c3d4_block(out_lines, "design_space", design, elements)
    _format_c3d4_block(out_lines, "nondesign_space", nondesign, elements)
    out_lines.append("**\n")
    out_lines.append(f"*Solid section, Elset=design_space, Material={mat}\n")
    out_lines.append(f"*Solid section, Elset=nondesign_space, Material={mat}\n")
    out_lines.append(tmpl_post.lstrip("\n"))

    out_inp.parent.mkdir(parents=True, exist_ok=True)
    out_inp.write_text("".join(out_lines), encoding="utf-8", newline="\n")
    return len(design), len(nondesign), mat


def _format_c3d4_block(lines: list[str], elset: str, eids: list[int], elements: dict[int, tuple[int, int, int, int]]) -> None:
    lines.append(f"*Element, TYPE=C3D4, Elset={elset}\n")
    for eid in sorted(eids):
        a, b, c, d = elements[eid]
        lines.append(f"{eid}, {a}, {b}, {c}, {d}\n")


def main() -> int:
    _ensure_qt_app()
    import FreeCAD  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="FCStd FEM → CalculiX INP（保留载荷）+ Pad001 双域 Elset")
    ap.add_argument("--fcstd", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, default=None, help="FEM 写出目录（默认：输出文件同目录/_fem_beso_work）")
    ap.add_argument("--design-solid", default="Pad001", help="设计域 PartDesign/实体名（默认 Pad001）")
    ap.add_argument(
        "--partition-tolerance-mm",
        type=float,
        default=None,
        help="isInside 容差 (mm)；默认 max(对角线·1e-8, 1e-4)",
    )
    ap.add_argument("--base-name", default="beso_fem_export", help="FemTools 写出主 INP 基名")
    ap.add_argument(
        "--mesh-inp",
        type=Path,
        default=None,
        help="合并模式：已有体网格 INP（如 Gmsh 的 C3D4），与 --step-template 组合；不依赖 FEM 可写",
    )
    ap.add_argument(
        "--step-template",
        type=Path,
        default=None,
        help="合并模式：含 *STEP/*BOUNDARY/*Cload 的完整或片段 INP（如手工或旧 Analysis-beso.inp）",
    )
    args = ap.parse_args()

    fcstd = args.fcstd.resolve()
    out_inp = args.out.resolve()
    work_dir = (args.work_dir or (out_inp.parent / "_fem_beso_work")).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    doc = FreeCAD.openDocument(str(fcstd))
    try:
        if args.mesh_inp is not None:
            if args.step_template is None:
                print("[ERR] 合并模式需同时指定 --mesh-inp 与 --step-template", file=sys.stderr)
                return 10
            mesh_inp = args.mesh_inp.resolve()
            st = args.step_template.resolve()
            if not mesh_inp.is_file() or not st.is_file():
                print("[ERR] mesh 或 step 模板文件不存在", file=sys.stderr)
                return 11
            d, nd, mat = _merge_mesh_and_step_template(
                mesh_inp,
                st,
                out_inp,
                doc,
                str(args.design_solid),
                args.partition_tolerance_mm,
            )
            print(f"[OK] merge 模式  mesh={mesh_inp.name}  step_tpl={st.name}")
            print(f"[OK] 写出: {out_inp}  design_space={d} nondesign_space={nd}  material={mat}")
            return 0

        anas = [o for o in doc.Objects if getattr(o, "TypeId", "") == "Fem::FemAnalysis"]
        if not anas:
            print("[ERR] 文档中无 Fem::FemAnalysis（或改用 --mesh-inp + --step-template）", file=sys.stderr)
            return 3
        analysis = anas[0]

        from femtools import ccxtools  # noqa: PLC0415

        tools = ccxtools.FemToolsCcx(analysis=analysis)
        tools.update_objects()
        tools.setup_working_dir(str(work_dir), create=True)
        tools.set_base_name(str(args.base_name))
        msg = tools.check_prerequisites()
        if msg:
            print("[WARN] FEM 前置检查未通过:\n" + msg, file=sys.stderr)
            print(
                "[INFO] 可改用合并模式：先得到体网格 INP，再指定含载荷的模板，例如：\n"
                f"  --mesh-inp <体网格.inp> --step-template <含*Step的.inp>",
                file=sys.stderr,
            )
            return 4
        tools.write_inp_file()
        fem_inp = Path(tools.inp_file_name)
        if not fem_inp.is_file():
            print(f"[ERR] 未生成 INP: {fem_inp}", file=sys.stderr)
            return 5
        raw = fem_inp.read_text(encoding="utf-8", errors="replace")

        m_step = re.search(r"(?m)^\*Step\b", raw, re.IGNORECASE)
        if not m_step:
            print("[ERR] INP 中未找到 *Step", file=sys.stderr)
            return 6
        pre = raw[: m_step.start()]
        post = raw[m_step.start() :]

        nodes, elements = _parse_nodes_and_volume_elements(raw)
        if not nodes or not elements:
            print(f"[ERR] 未能解析体单元（nodes={len(nodes)} elements={len(elements)}）", file=sys.stderr)
            return 7

        sh = _design_object_shape_global(doc, str(args.design_solid))
        if sh is None:
            print(f"[ERR] 设计域对象不存在或无形状: {args.design_solid}", file=sys.stderr)
            return 8
        tol = _partition_tolerance_mm(sh, args.partition_tolerance_mm)
        import FreeCAD as App  # noqa: PLC0415

        design: list[int] = []
        nondesign: list[int] = []
        for eid, (n1, n2, n3, n4) in elements.items():
            pts = [nodes[n1], nodes[n2], nodes[n3], nodes[n4]]
            cx = sum(p[0] for p in pts) / 4.0
            cy = sum(p[1] for p in pts) / 4.0
            cz = sum(p[2] for p in pts) / 4.0
            v = App.Vector(cx, cy, cz)
            if sh.isInside(v, tol, True):
                design.append(eid)
            else:
                nondesign.append(eid)
        if not design or not nondesign:
            print(
                f"[ERR] 划分失败 design={len(design)} nondesign={len(nondesign)}；检查网格与 {args.design_solid}",
                file=sys.stderr,
            )
            return 9

        pre_stripped = _strip_volume_elements_and_solid_sections(pre)
        mat = _first_material_name(pre_stripped) or "Material-1"
        if not re.search(r"(?im)^\*\s*MATERIAL\s*,\s*NAME\s*=\s*" + re.escape(mat), pre_stripped):
            mat = "Material-1"

        out_lines: list[str] = []
        out_lines.append(pre_stripped.rstrip() + "\n")
        out_lines.append("**\n** --- BESO dual domain (Chen2026 FCStd: Pad001 vs rest) ---\n")
        _format_c3d4_block(out_lines, "design_space", design, elements)
        _format_c3d4_block(out_lines, "nondesign_space", nondesign, elements)
        out_lines.append("**\n")
        out_lines.append(f"*Solid section, Elset=design_space, Material={mat}\n")
        out_lines.append(f"*Solid section, Elset=nondesign_space, Material={mat}\n")
        out_lines.append(post.lstrip("\n"))

        out_inp.parent.mkdir(parents=True, exist_ok=True)
        out_inp.write_text("".join(out_lines), encoding="utf-8", newline="\n")
        print(f"[OK] FEM 源: {fem_inp}")
        print(f"[OK] 写出: {out_inp}  design_space={len(design)} nondesign_space={len(nondesign)}  material={mat}")
        return 0
    finally:
        FreeCAD.closeDocument(doc.Name)


if __name__ == "__main__":
    raise SystemExit(main())
