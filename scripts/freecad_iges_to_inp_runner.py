# SPDX-License-Identifier: LGPL-2.1-or-later
"""
由 FreeCADCmd 加载执行：读取 JSON 配置，导入 CAD（IGS/IGES/STEP），Gmsh 剖分后写出 INP。

勿用系统 Python 直接运行本文件；请使用::

    FreeCADCmd.exe freecad_iges_to_inp_runner.py

    推荐由启动器设置环境变量 ``FC_IGES_MESH_CONFIG`` 指向配置文件（JSON 内容），
    勿将配置路径放在命令行参数中，否则 FreeCADCmd 会误当作工程文件打开。

配置为 JSON 文本，扩展名须为 ``.fcigesmesh``（勿用 ``.json``，否则 FreeCADCmd 会误走 FEM 网格导入）。
字段说明见同目录 ``run_freecad_iges_to_inp.py`` 的 epilog / 源码内 ``build_config``。

重要：``characteristic_length_max`` / ``min`` 的数值按 ``length_unit``（默认 ``mm``）解释，
并以 ``\"80000 mm\"`` 形式写入 FreeCAD 的 ``PropertyLength``；勿依赖对 mesh 对象直接赋裸 ``float``。
可选 ``mesh_size_from_curvature``（整数，0 表示关闭曲率相关加密）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 勿使用 .json 扩展名：FreeCADCmd 会把 *.json 交给 FEM 的 YAML/JSON 网格导入器。
_CONFIG_EXT = ".fcigesmesh"


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _config_path() -> Path:
    env = (os.environ.get("FC_IGES_MESH_CONFIG") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        _die(f"环境变量 FC_IGES_MESH_CONFIG 指向的文件不存在: {env}", 2)
    for a in sys.argv[1:]:
        p = Path(a)
        if p.is_file() and p.suffix.lower() == _CONFIG_EXT:
            return p.resolve()
    _die(
        f"用法: FreeCADCmd.exe freecad_iges_to_inp_runner.py <config{_CONFIG_EXT}>\n"
        f"或通过环境变量 FC_IGES_MESH_CONFIG 指向配置文件（JSON 内容，扩展名需为 {_CONFIG_EXT}）。",
        2,
    )


def _length_quantity_str(value_mm: float, unit: str) -> str:
    """
    FemMeshGmsh 的 CharacteristicLength* 为 App::PropertyLength：
    直接赋 float 常无法写入有效值，会保持默认 0（Gmsh 中等价于无上限），导致所有参数组合生成同一网格。
    使用带单位的字符串赋值（与 FreeCAD FEM 示例一致）。
    """
    u = (unit or "mm").strip() or "mm"
    v = float(value_mm)
    if v <= 0.0:
        return f"0 {u}"
    return f"{v} {u}"


def _pick_shape_object(doc, strategy: str):
    import Part

    strategy = (strategy or "largest_volume").strip().lower()
    cands = []
    for o in doc.Objects:
        if not getattr(o, "Shape", None) or o.Shape.isNull():
            continue
        st = o.Shape.ShapeType
        if st in ("Solid", "CompSolid", "Shell", "Compound", "Face"):
            cands.append(o)
    if not cands:
        _die("文档中未找到可剖分的 Part 形状（请先确认 CAD 已成功导入）。")
    if strategy in ("first", "0"):
        return cands[0]
    if strategy in ("largest_volume", "largest", "volume"):
        best = None
        best_v = -1.0
        for o in cands:
            try:
                v = float(o.Shape.Volume)
            except Exception:
                v = 0.0
            if v > best_v:
                best_v = v
                best = o
        return best or cands[0]
    _die(f"未知 compound_part_strategy: {strategy!r}，可用 first | largest_volume")


def main() -> int:
    try:
        import FreeCAD  # type: ignore
    except ImportError:
        _die("未导入 FreeCAD。请使用安装目录下的 FreeCADCmd.exe 执行本脚本。", 2)

    cfg_path = _config_path()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    cad = Path(cfg["cad_path"]).resolve()
    out_inp = Path(cfg["out_inp"]).resolve()
    if not cad.is_file():
        _die(f"CAD 文件不存在: {cad}")

    out_inp.parent.mkdir(parents=True, exist_ok=True)

    import Part  # type: ignore

    import ObjectsFem  # type: ignore
    from femmesh.gmshtools import GmshTools  # type: ignore

    doc = FreeCAD.newDocument("IgesToInp")
    try:
        Part.insert(str(cad), doc.Name)
        doc.recompute()

        part_obj = _pick_shape_object(doc, str(cfg.get("compound_part_strategy", "largest_volume")))

        mesh = ObjectsFem.makeMeshGmsh(doc, "GmshMesh")
        mesh.Shape = part_obj

        length_unit = str(cfg.get("length_unit", "mm"))
        cl_max = float(cfg.get("characteristic_length_max", 1e4))
        cl_min = float(cfg.get("characteristic_length_min", 0.0))
        mesh.CharacteristicLengthMax = _length_quantity_str(cl_max, length_unit)
        mesh.CharacteristicLengthMin = _length_quantity_str(cl_min, length_unit)
        mesh.ElementOrder = str(cfg.get("element_order", "1st"))
        mesh.ElementDimension = str(cfg.get("element_dimension", "From Shape"))
        mesh.GeometryTolerance = float(cfg.get("geometry_tolerance", 0.0))

        if "optimize_std" in cfg:
            mesh.OptimizeStd = bool(cfg["optimize_std"])

        if "mesh_size_from_curvature" in cfg and hasattr(mesh, "MeshSizeFromCurvature"):
            mesh.MeshSizeFromCurvature = int(cfg["mesh_size_from_curvature"])

        doc.recompute()
        print(
            f"[CFG] CharacteristicLengthMax={mesh.CharacteristicLengthMax!s} "
            f"Min={mesh.CharacteristicLengthMin!s} "
            f"MeshSizeFromCurvature={getattr(mesh, 'MeshSizeFromCurvature', 'n/a')}"
        )

        tools = GmshTools(mesh)
        ok = tools.run(True)
        if not ok:
            _die("Gmsh 子进程 waitForFinished 失败（超时或异常）。")

        if mesh.FemMesh is None or mesh.FemMesh.NodeCount < 1:
            _die("Gmsh 结束后 FemMesh 为空；请增大 characteristic_length_max 或检查几何是否封闭。")

        mesh.FemMesh.write(str(out_inp))
    finally:
        FreeCAD.closeDocument(doc.Name)

    print(f"[OK] {cad.name} -> {out_inp} ({out_inp.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
