#!/usr/bin/env python3
"""
从仓库根目录调用 FreeCAD 内 Python，运行 ``beso_fcstd_fem_dual_domain_export.py``。

默认 FreeCAD：``D:\\freecad\\bin\\python.exe``（可用环境变量 ``FREECAD_PYTHON`` 覆盖）。

FEM 模式（文档内 FEM 完整时）::

    .\\.venv\\Scripts\\python scripts\\run_fcstd_fem_beso_dual_domain_export.py \\
        --fcstd examples/beso2/BESO3.FCStd --out examples/beso2/Analysis-beso-fem.inp

合并模式（FEM 无法写出时：体网格 INP + 含 *Step 的载荷模板）::

    .\\.venv\\Scripts\\python scripts\\run_fcstd_fem_beso_dual_domain_export.py \\
        --fcstd examples/beso2/BESO3.FCStd \\
        --mesh-inp examples/beso2/_fc_work/_mesh_volume.inp \\
        --step-template examples/beso2/Analysis-beso.inp \\
        --out examples/beso2/Analysis-beso-fem-merged.inp
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXPORTER = REPO / "scripts" / "beso_fcstd_fem_dual_domain_export.py"


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
