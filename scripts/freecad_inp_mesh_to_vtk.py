#!/usr/bin/env python3
"""
在 FreeCAD 的 Python 中运行：读取 CalculiX 网格 INP，写出 Legacy ASCII VTK（供前端结果查看器解析）。

用法（需使用 FreeCAD 自带的 python.exe）::

    D:\\freecad\\bin\\python.exe scripts/freecad_inp_mesh_to_vtk.py mesh.inp out.vtk
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: freecad_inp_mesh_to_vtk.py <input.inp> <output.vtk>", file=sys.stderr)
        return 2
    inp = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    if not inp.is_file():
        print(f"[ERR] INP 不存在: {inp}", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    import FreeCAD  # noqa: F401
    import Fem

    mesh = Fem.FemMesh()
    mesh.read(str(inp))
    mesh.write(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
