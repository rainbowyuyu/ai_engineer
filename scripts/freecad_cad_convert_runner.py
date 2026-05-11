# SPDX-License-Identifier: LGPL-2.1-or-later
"""
由 FreeCADCmd / 同目录 python.exe 执行：将 CAD 转为 STEP / IGES / STL / BREP。

环境变量 ``FC_CAD_CONVERT_CONFIG`` 指向 JSON（扩展名建议 ``.fccadcv``）。
字段：
- input_path: 输入 .igs/.iges/.stp/.step/.stl/.brep
- output_path: 输出文件路径（扩展名决定格式）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_CONFIG_EXT = ".fccadcv"


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _config_path() -> Path:
    env = (os.environ.get("FC_CAD_CONVERT_CONFIG") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        _die(f"FC_CAD_CONVERT_CONFIG 指向的文件不存在: {env}", 2)
    for a in sys.argv[1:]:
        p = Path(a)
        if p.is_file() and p.suffix.lower() == _CONFIG_EXT:
            return p.resolve()
    _die(
        f"用法: FreeCADCmd.exe freecad_cad_convert_runner.py <config{_CONFIG_EXT}>\n"
        f"或设置 FC_CAD_CONVERT_CONFIG。",
        2,
    )


def main() -> int:
    try:
        import FreeCAD  # type: ignore
        import Import  # type: ignore
        import Mesh  # type: ignore
        import Part  # type: ignore
    except ImportError:
        _die("未导入 FreeCAD。请使用 FreeCADCmd 执行本脚本。", 2)

    cfg_path = _config_path()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cad = Path(cfg["input_path"]).resolve()
    out_path = Path(cfg["output_path"]).resolve()
    if not cad.is_file():
        _die(f"输入文件不存在: {cad}")
    out_ext = out_path.suffix.lower()
    if out_ext not in (".step", ".stp", ".iges", ".igs", ".stl", ".brep"):
        _die(f"不支持的输出扩展名: {out_ext}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = FreeCAD.newDocument("CadConvert")
    try:
        Import.insert(str(cad), doc.Name)
        doc.recompute()
        solids = []
        meshes = []
        for o in doc.Objects:
            sh = getattr(o, "Shape", None)
            if sh is not None and not sh.isNull():
                solids.append(o)
                continue
            mesh = getattr(o, "Mesh", None)
            if mesh is not None and getattr(mesh, "CountPoints", 0) > 0:
                meshes.append(o)

        if solids:
            Part.export(solids, str(out_path))
        elif meshes:
            if out_ext == ".stl":
                if len(meshes) == 1:
                    meshes[0].Mesh.write(str(out_path))
                else:
                    Mesh.export(meshes, str(out_path))
            else:
                _die("文档中只有网格对象，无法导出为 STEP/IGES/BREP；请改用 target_format=stl。")
        else:
            _die("文档中未找到可导出的实体或网格。")
    finally:
        FreeCAD.closeDocument(doc.Name)

    if not out_path.is_file():
        _die(f"未生成输出: {out_path}")
    print(f"[OK] {cad.name} -> {out_path.name} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
