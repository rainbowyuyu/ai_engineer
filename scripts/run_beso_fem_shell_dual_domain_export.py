#!/usr/bin/env python3
"""
从仓库根调用 FreeCAD 内 Python，运行 ``beso_fem_shell_dual_domain_export.py``。

FEM 壳网格（默认 ``examples/beso2/_fem_beso_work/FEMMeshGmsh001.inp``）→ 全模型双 Elset INP，
不经过 Gmsh 体网格流水线。

  .\\.venv\\Scripts\\python scripts\\run_beso_fem_shell_dual_domain_export.py \\
      --fcstd examples/beso2/BESO3.FCStd \\
      --mesh-inp examples/beso2/_fem_beso_work/FEMMeshGmsh001.inp \\
      --out examples/beso2/_fem_beso_work/Analysis-beso-shell-dual.inp
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXPORTER = REPO / "scripts" / "beso_fem_shell_dual_domain_export.py"


def _freecad_python() -> Path:
    env = (os.environ.get("FREECAD_PYTHON") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
    for name in ("FreeCADCmd.exe", "freecadcmd.exe"):
        w = shutil.which(name)
        if w:
            guess = Path(w).parent / "python.exe"
            if guess.is_file():
                return guess.resolve()
    default = Path(r"D:\freecad\bin\python.exe")
    if default.is_file():
        return default.resolve()
    raise FileNotFoundError("未找到 FreeCAD 的 python.exe；请设置 FREECAD_PYTHON。")


def main() -> int:
    if not EXPORTER.is_file():
        print(f"[ERR] 未找到 {EXPORTER}", file=sys.stderr)
        return 2
    fc_py = _freecad_python()
    r = subprocess.run([str(fc_py), str(EXPORTER), *sys.argv[1:]], cwd=str(REPO))
    return int(r.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
