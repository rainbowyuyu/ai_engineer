# SPDX-License-Identifier: LGPL-2.1-or-later
"""
由 FreeCADCmd / 同目录 python.exe 执行：从 JSON 配置读取 CAD 路径，三角化后导出 Wavefront OBJ（用于前端预览）。

环境变量 ``FC_EXPORT_OBJ_CONFIG`` 指向 JSON 文件（扩展名建议 ``.fcexpobj``，勿用 .json）。
字段：
- cad_path: 输入 .igs/.iges/.stp/.step
- out_obj: 输出 .obj
- linear_deflection: float，LinearDeflection（模型单位，越大越快越粗），默认 800
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_CONFIG_EXT = ".fcexpobj"


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _config_path() -> Path:
    env = (os.environ.get("FC_EXPORT_OBJ_CONFIG") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        _die(f"FC_EXPORT_OBJ_CONFIG 指向的文件不存在: {env}", 2)
    for a in sys.argv[1:]:
        p = Path(a)
        if p.is_file() and p.suffix.lower() == _CONFIG_EXT:
            return p.resolve()
    _die(
        f"用法: FreeCADCmd.exe freecad_export_obj_runner.py <config{_CONFIG_EXT}>\n"
        f"或设置 FC_EXPORT_OBJ_CONFIG。",
        2,
    )


def main() -> int:
    try:
        import FreeCAD  # type: ignore
        import Import  # type: ignore
        import Mesh  # type: ignore
        import MeshPart  # type: ignore
        import Part  # type: ignore
    except ImportError:
        _die("未导入 FreeCAD。请使用 FreeCADCmd 执行本脚本。", 2)

    cfg_path = _config_path()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cad = Path(cfg["cad_path"]).resolve()
    out_obj = Path(cfg["out_obj"]).resolve()
    if not cad.is_file():
        _die(f"CAD 不存在: {cad}")
    out_obj.parent.mkdir(parents=True, exist_ok=True)
    linear_deflection = float(cfg.get("linear_deflection", 800.0))

    doc = FreeCAD.newDocument("ExportObj")
    try:
        Import.insert(str(cad), doc.Name)
        doc.recompute()
        shapes: list = []
        for o in doc.Objects:
            sh = getattr(o, "Shape", None)
            if sh is not None and not sh.isNull():
                shapes.append(sh)
        if not shapes:
            _die("文档中未找到可三角化的 Shape。")
        if len(shapes) == 1:
            shape = shapes[0]
        else:
            # 装配体多 Solid：合并为 Compound 再三角化，避免只预览到第一个零件
            shape = Part.makeCompound(shapes)
        mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=linear_deflection)
        mesh.write(str(out_obj))
    finally:
        FreeCAD.closeDocument(doc.Name)

    print(f"[OK] {cad.name} -> {out_obj} ({out_obj.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
