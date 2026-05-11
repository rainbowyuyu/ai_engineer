# SPDX-License-Identifier: LGPL-2.1-or-later
"""
FEM 壳网格 INP（如 FreeCAD 写出的 ``FEMMeshGmsh001.inp``）→ 全模型保留、按 Pad001 划分
``design_space`` / ``nondesign_space`` 的 **S6** 双 Elset deck，供 BESO 仅优化设计域。

与 Gmsh 体网格流水线无关：以 ``--mesh-inp`` 为壳单元与节点的真源；材料、*SHELL SECTION 厚度、
*STEP/*BOUNDARY/*CLOAD 等同文档一次 ``FemToolsCcx.write_inp_file()`` 结果对齐（节点数须一致）。

在 FreeCAD 自带 Python 中执行::

  D:\\freecad\\bin\\python.exe scripts/beso_fem_shell_dual_domain_export.py \\
      --fcstd examples/beso2/BESO3.FCStd \\
      --mesh-inp examples/beso2/_fem_beso_work/FEMMeshGmsh001.inp \\
      --out examples/beso2/_fem_beso_work/Analysis-beso-shell-dual.inp \\
      --allow-minimal-tail

可选：``--tail-inp`` 提供含 ``*Material``…``*End step`` 的片段（不依赖 FEM 检查）；工程上优先补全 FCStd 材料后去掉 ``--allow-minimal-tail``。
"""
from __future__ import annotations

import argparse
import json
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


def _parse_nodes(text: str) -> dict[int, tuple[float, float, float]]:
    nodes: dict[int, tuple[float, float, float]] = {}
    in_node = False

    def _is_coord(parts: list[str]) -> bool:
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
            continue
        if s.startswith("*") and not s.startswith("**"):
            in_node = False
            continue
        if in_node:
            parts = [p.strip() for p in s.split(",")]
            if _is_coord(parts):
                nodes[int(parts[0])] = (float(parts[1]), float(parts[2]), float(parts[3]))
    return nodes


def _parse_s6_elements(text: str) -> dict[int, tuple[int, int, int, int, int, int]]:
    """首个 ``*Element`` 且含 TYPE=S6 的块（与 FreeCAD 壳网格导出一致）。"""
    elements: dict[int, tuple[int, int, int, int, int, int]] = {}
    in_s6 = False
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        u = s.upper()
        if u.startswith("*ELEMENT"):
            in_s6 = "S6" in u
            continue
        if s.startswith("*") and not s.startswith("**"):
            in_s6 = False
            continue
        if in_s6:
            parts = [p.strip() for p in s.split(",")]
            if len(parts) >= 7 and all(p.lstrip("-").isdigit() for p in parts[:7]):
                eid = int(parts[0])
                elements[eid] = tuple(int(parts[j]) for j in range(1, 7))  # type: ignore[assignment]
    return elements


def _first_tail_start_line(lines: list[str]) -> int | None:
    """FreeCAD FEM：*PHYSICAL CONSTANTS 或 *MATERIAL 起为「无网格」尾部（材料、截面、Step）。"""
    for i, line in enumerate(lines):
        u = line.strip().upper()
        if u.startswith("*PHYSICAL CONSTANTS"):
            return i
    for i, line in enumerate(lines):
        u = line.strip().upper()
        if u.startswith("*MATERIAL"):
            return i
    return None


def _strip_shell_sections(tail_lines: list[str]) -> tuple[list[str], str | None, float | None]:
    """去掉 ``*Shell section`` 块，返回 (新行列表, 材料名, 厚度)。"""
    out: list[str] = []
    mat_name: str | None = None
    thickness: float | None = None
    i = 0
    n = len(tail_lines)
    shell_hdr = re.compile(r"^\s*\*shell\s+section\s*,", re.I)
    while i < n:
        line = tail_lines[i]
        if shell_hdr.match(line):
            m_el = re.search(r"ELSET\s*=\s*([^,\s]+)", line, re.I)
            m_mat = re.search(r"MATERIAL\s*=\s*([^,\s]+)", line, re.I)
            if m_mat and mat_name is None:
                mat_name = m_mat.group(1).strip()
            i += 1
            while i < n:
                t = tail_lines[i].strip()
                if t.startswith("*") and not t.startswith("**"):
                    break
                if t and not t.startswith("**") and thickness is None:
                    try:
                        thickness = float(t.split(",")[0].strip())
                    except ValueError:
                        pass
                i += 1
            continue
        out.append(line)
        i += 1
    return out, mat_name, thickness


def _first_material_name_in_lines(lines: list[str]) -> str | None:
    for line in lines:
        m = re.search(r"(?i)^\*\s*MATERIAL\s*,\s*NAME\s*=\s*([^\s,]+)", line.strip())
        if m:
            return m.group(1).strip()
    return None


def _anchor_and_load_nodes(
    nodes_m: dict[int, tuple[float, float, float]],
) -> tuple[int, int]:
    """最低 z 处一节点固定、最高 z 处一节点受载（用于无 FEM 模板时的最小静力步）。"""
    z_min = min(p[2] for p in nodes_m.values())
    z_max = max(p[2] for p in nodes_m.values())
    band = max(abs(z_max - z_min) * 1.0e-6, 0.01)
    cand_lo = [nid for nid, p in nodes_m.items() if p[2] <= z_min + band]
    cand_hi = [nid for nid, p in nodes_m.items() if p[2] >= z_max - band]
    return min(cand_lo), max(cand_hi)


def _minimal_tail_lines(
    n_anchor: int,
    n_load: int,
    cload_mag: float,
    young_mpa: float,
    poisson: float,
    density: float,
) -> list[str]:
    return [
        "** Minimal CalculiX tail (use when FEM check_prerequisites fails; replace with --tail-inp for production)\n",
        "*Physical constants, ABSOLUTE ZERO=0, STEFAN BOLTZMANN=5.670374419e-11\n",
        "*Material, name=Material-shell\n",
        "*Elastic\n",
        f"{young_mpa}, {poisson}\n",
        "*Density\n",
        f"{density}\n",
        "*Step\n",
        "*Static\n",
        "*Boundary\n",
        f"{n_anchor},1,3,0\n",
        "*Cload\n",
        f"{n_load},1,{cload_mag}\n",
        "*Node print, nset=Nall, frequency=1\n",
        "U\n",
        "*El print, elset=design_space, frequency=1\n",
        "S\n",
        "*End step\n",
    ]


def _insert_shell_before_step(
    tail_text: str,
    mat: str,
    th: float,
) -> str:
    m = re.search(r"(?mi)^\*Step\b", tail_text)
    if not m:
        raise RuntimeError("模板尾部中未找到 *Step")
    block = (
        f"**\n** BESO: dual shell sections (design_space / nondesign_space)\n"
        f"*Shell section, Elset=design_space, Material={mat}\n"
        f"{th}\n"
        f"*Shell section, Elset=nondesign_space, Material={mat}\n"
        f"{th}\n**\n"
    )
    return tail_text[: m.start()] + block + tail_text[m.start() :]


def _format_s6_block(lines: list[str], elset: str, eids: list[int], elems: dict[int, tuple[int, ...]]) -> None:
    lines.append(f"*Element, TYPE=S6, Elset={elset}\n")
    for eid in sorted(eids):
        n1, n2, n3, n4, n5, n6 = elems[eid]
        lines.append(f"{eid}, {n1}, {n2}, {n3}, {n4}, {n5}, {n6}\n")


def main() -> int:
    _ensure_qt_app()
    import FreeCAD  # noqa: PLC0415
    import FreeCAD as App  # noqa: PLC0415

    ap = argparse.ArgumentParser(
        description="FEM 壳网格 INP → 全模型 S6 双域（design_space + nondesign_space），不走 Gmsh 体网格"
    )
    ap.add_argument("--fcstd", type=Path, required=True)
    ap.add_argument(
        "--mesh-inp",
        type=Path,
        default=None,
        help="壳网格 INP（默认：--out 所在目录下 _fem_beso_work/FEMMeshGmsh001.inp）",
    )
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, default=None, help="FEM write_inp 工作目录（默认同 --out 父目录）")
    ap.add_argument("--design-solid", default="Pad001")
    ap.add_argument("--partition-tolerance-mm", type=float, default=None)
    ap.add_argument("--base-name", default="fem_shell_tpl", help="write_inp_file 基名（临时完整 deck）")
    ap.add_argument(
        "--tail-inp",
        type=Path,
        default=None,
        help="从该 INP 截取 *PHYSICAL CONSTANTS / *MATERIAL 起至文件末作为载荷/材料尾部（可不依赖 FEM check 通过）",
    )
    ap.add_argument(
        "--allow-minimal-tail",
        action="store_true",
        help="当 FEM 前置失败且未指定 --tail-inp 时，生成含固定点与 Cload 的最小 *Step（仅作连通性验证，工程上请换 --tail-inp）",
    )
    ap.add_argument("--shell-thickness", type=float, default=2.0, help="无模板解析厚度时使用 (mm，与模型单位一致)")
    ap.add_argument("--youngs-mpa", type=float, default=210000.0)
    ap.add_argument("--poisson", type=float, default=0.27)
    ap.add_argument("--density", type=float, default=7.833e-9)
    ap.add_argument("--minimal-cload", type=float, default=281000.0, help="最小尾部的 +X 节点力 (N)")
    args = ap.parse_args()

    fcstd = args.fcstd.resolve()
    out_inp = args.out.resolve()
    work_dir = (args.work_dir or out_inp.parent).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    mesh_inp = args.mesh_inp
    if mesh_inp is None:
        mesh_inp = out_inp.parent / "_fem_beso_work" / "FEMMeshGmsh001.inp"
    mesh_inp = mesh_inp.resolve()
    if not mesh_inp.is_file():
        print(f"[ERR] 壳网格 INP 不存在: {mesh_inp}", file=sys.stderr)
        return 2

    mesh_raw = mesh_inp.read_text(encoding="utf-8", errors="replace")
    nodes_m = _parse_nodes(mesh_raw)
    elems_m = _parse_s6_elements(mesh_raw)
    if not nodes_m or not elems_m:
        print(f"[ERR] 未能解析 S6 壳单元: nodes={len(nodes_m)} elements={len(elems_m)}", file=sys.stderr)
        return 3

    doc = FreeCAD.openDocument(str(fcstd))
    try:
        tpl_path: Path | None = None
        tpl_lines: list[str] | None = None
        skip_node_match = False

        if args.tail_inp is not None:
            tinp = args.tail_inp.resolve()
            if not tinp.is_file():
                print(f"[ERR] --tail-inp 不存在: {tinp}", file=sys.stderr)
                return 4
            tpl_raw = tinp.read_text(encoding="utf-8", errors="replace")
            tpl_lines = tpl_raw.splitlines(keepends=True)
            tpl_path = tinp
            skip_node_match = True
            print(f"[INFO] 使用外部尾部模板: {tinp.name}", file=sys.stderr)
        else:
            anas = [o for o in doc.Objects if getattr(o, "TypeId", "") == "Fem::FemAnalysis"]
            if not anas:
                print("[ERR] 文档中无 Fem::FemAnalysis（或指定 --tail-inp）", file=sys.stderr)
                return 4
            from femtools import ccxtools  # noqa: PLC0415

            tools = ccxtools.FemToolsCcx(analysis=anas[0])
            tools.update_objects()
            tools.setup_working_dir(str(work_dir), create=True)
            tools.set_base_name(str(args.base_name))
            msg = tools.check_prerequisites()
            if msg:
                if args.allow_minimal_tail:
                    n_lo, n_hi = _anchor_and_load_nodes(nodes_m)
                    tpl_lines = _minimal_tail_lines(
                        n_lo,
                        n_hi,
                        float(args.minimal_cload),
                        float(args.youngs_mpa),
                        float(args.poisson),
                        float(args.density),
                    )
                    tpl_path = None
                    skip_node_match = True
                    print(
                        "[WARN] FEM 前置未通过，已按 --allow-minimal-tail 生成最小 *Step；"
                        "工程载荷请补全 FCStd 材料/FEM 或使用 --tail-inp。\n"
                        + msg,
                        file=sys.stderr,
                    )
                else:
                    print(
                        "[ERR] FEM 前置检查未通过；可选：\n"
                        "  (1) 在 FCStd 中为材料填写杨氏模量/泊松比并补壳厚；\n"
                        "  (2) --tail-inp <含*Material…*End step的INP片段>；\n"
                        "  (3) --allow-minimal-tail（仅验证用）。\n"
                        + msg,
                        file=sys.stderr,
                    )
                    return 5
            else:
                tools.write_inp_file()
                tpl_path = Path(tools.inp_file_name)
                if not tpl_path.is_file():
                    print(f"[ERR] 未生成 FEM 模板: {tpl_path}", file=sys.stderr)
                    return 6
                tpl_raw = tpl_path.read_text(encoding="utf-8", errors="replace")
                tpl_lines = tpl_raw.splitlines(keepends=True)

        assert tpl_lines is not None

        if not skip_node_match and tpl_path is not None:
            tpl_raw = tpl_path.read_text(encoding="utf-8", errors="replace")
            nodes_t = _parse_nodes(tpl_raw)
            elems_t = _parse_s6_elements(tpl_raw)
            if len(nodes_m) != len(nodes_t):
                print(
                    f"[ERR] 节点数不一致: mesh-inp={len(nodes_m)} FEM模板={len(nodes_t)}；"
                    f"请使用与当前 FEM 分析同一次导出的壳网格 INP。",
                    file=sys.stderr,
                )
                return 7
            if set(nodes_m.keys()) != set(nodes_t.keys()):
                print("[ERR] 节点编号集合与 FEM 模板不一致。", file=sys.stderr)
                return 8
            if elems_m.keys() != elems_t.keys():
                print(
                    f"[WARN] 壳单元 id 集合与模板不完全一致 mesh={len(elems_m)} tpl={len(elems_t)}；"
                    f"仍以 --mesh-inp 为准划分。",
                    file=sys.stderr,
                )

        ts = _first_tail_start_line(tpl_lines)
        if ts is None:
            print("[ERR] 无法在模板中定位 *PHYSICAL CONSTANTS / *MATERIAL 起始行", file=sys.stderr)
            return 9
        tail_lines = tpl_lines[ts:]
        tail_filt, shell_mat, shell_th = _strip_shell_sections(tail_lines)
        mat = shell_mat or _first_material_name_in_lines(tail_filt) or "Material-shell"
        if shell_th is None:
            shell_th = float(args.shell_thickness)
            print(f"[WARN] 未能从模板解析壳厚，使用 --shell-thickness={shell_th}", file=sys.stderr)

        sh = _design_object_shape_global(doc, str(args.design_solid))
        if sh is None:
            print(f"[ERR] 设计域对象不存在: {args.design_solid}", file=sys.stderr)
            return 10
        tol = _partition_tolerance_mm(sh, args.partition_tolerance_mm)

        design: list[int] = []
        nondesign: list[int] = []
        for eid, (n1, n2, n3, _n4, _n5, _n6) in elems_m.items():
            p1, p2, p3 = nodes_m[n1], nodes_m[n2], nodes_m[n3]
            cx = (p1[0] + p2[0] + p3[0]) / 3.0
            cy = (p1[1] + p2[1] + p3[1]) / 3.0
            cz = (p1[2] + p2[2] + p3[2]) / 3.0
            v = App.Vector(cx, cy, cz)
            if sh.isInside(v, tol, True):
                design.append(eid)
            else:
                nondesign.append(eid)
        if not design or not nondesign:
            print(
                f"[ERR] 划分失败 design={len(design)} nondesign={len(nondesign)}；检查 {args.design_solid} 与网格",
                file=sys.stderr,
            )
            return 11

        node_block_lines: list[str] = []
        in_node = False
        for raw in mesh_raw.splitlines(keepends=True):
            u = raw.strip().upper()
            if u.startswith("*NODE"):
                in_node = True
                node_block_lines.append(raw)
                continue
            if in_node:
                st = raw.strip()
                if st.startswith("*") and not st.startswith("**"):
                    in_node = False
                    break
                node_block_lines.append(raw)
                continue

        out_lines: list[str] = [
            "** CalculiX: FEM shell mesh + Pad001 dual elset (full model, BESO optimizes design_space only)\n",
        ]
        out_lines.extend(node_block_lines)
        if not out_lines[-1].endswith("\n"):
            out_lines.append("\n")
        out_lines.append("**\n** Shell elements (all retained; nondesign_space not removed)\n")
        _format_s6_block(out_lines, "design_space", design, elems_m)
        _format_s6_block(out_lines, "nondesign_space", nondesign, elems_m)
        out_lines.append("**\n")

        tail_text = "".join(tail_filt)
        tail_text = _insert_shell_before_step(tail_text, mat, float(shell_th))
        out_lines.append(tail_text)
        if not tail_text.endswith("\n"):
            out_lines.append("\n")

        out_inp.parent.mkdir(parents=True, exist_ok=True)
        out_inp.write_text("".join(out_lines), encoding="utf-8", newline="\n")

        man = {
            "flow": "fem_shell_dual_domain",
            "fcstd": str(fcstd),
            "mesh_inp": str(mesh_inp),
            "fem_template_inp": str(tpl_path) if tpl_path else None,
            "out_inp": str(out_inp),
            "design_solid": str(args.design_solid),
            "shell_material": mat,
            "shell_thickness": float(shell_th),
            "design_space": len(design),
            "nondesign_space": len(nondesign),
            "elements_total": len(elems_m),
        }
        man_path = out_inp.parent / "beso_shell_dual_manifest.json"
        man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")

        print(f"[OK] 壳网格: {mesh_inp.name}")
        if tpl_path is not None:
            print(f"[OK] FEM/尾部模板: {tpl_path.name}")
        else:
            print("[OK] 尾部: 最小静力模板 (--allow-minimal-tail)")
        print(f"[OK] 写出: {out_inp}")
        print(f"[OK] design_space={len(design)} nondesign_space={len(nondesign)} total={len(elems_m)}")
        print(f"[OK] manifest: {man_path}")
        return 0
    finally:
        FreeCAD.closeDocument(doc.Name)


if __name__ == "__main__":
    raise SystemExit(main())
