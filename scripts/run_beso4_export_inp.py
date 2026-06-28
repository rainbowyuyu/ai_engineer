#!/usr/bin/env python3
"""
将 examples/beso4/BESO3.FCStd 全模型导出为 CalculiX INP（含网格、材料、边界与载荷）。

默认按 FCStd 内 Label=FEMMeshGmsh004 的 Gmsh 网格（几何=Compound）生成体网格，与 FreeCAD FEM 视图一致。

  python scripts/run_beso4_export_inp.py
  python scripts/run_beso4_export_inp.py --skip-fem-setup
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EX_DIR = REPO / "examples" / "beso4"
CFG = EX_DIR / "beso4_export.fcpipeline"
RUNNER = REPO / "scripts" / "freecad_fcstd_pipeline_runner.py"
SETUP = REPO / "scripts" / "setup_beso3_fem_fcstd.py"


def _freecad_python() -> Path:
    for p in (
        os.environ.get("FREECAD_PYTHON", "").strip(),
        str(Path(r"D:\freecad\bin\python.exe")),
    ):
        if p and Path(p).is_file():
            return Path(p).resolve()
    env_cmd = (os.environ.get("FREECAD_CMD") or "").strip()
    if env_cmd:
        g = Path(env_cmd).parent / "python.exe"
        if g.is_file():
            return g.resolve()
    raise FileNotFoundError("未找到 FreeCAD python.exe")


def main() -> int:
    ap = argparse.ArgumentParser(description="BESO4 FCStd → 全模型 INP")
    ap.add_argument("--skip-fem-setup", action="store_true")
    args = ap.parse_args()

    fc_py = _freecad_python()
    fcstd = EX_DIR / "BESO3.FCStd"
    work_common = EX_DIR / "_work_common"
    if not fcstd.is_file():
        print(f"[FAIL] 缺少 {fcstd}", file=sys.stderr)
        return 2

    ref = work_common / "fem_reference.inp"
    if not args.skip_fem_setup and not ref.is_file():
        cmd = [
            str(fc_py),
            str(SETUP),
            "--fcstd",
            str(fcstd),
            "--out-work",
            str(work_common),
        ]
        if not os.access(fcstd, os.W_OK):
            cmd.append("--no-save-fcstd")
        print("[CMD]", " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(REPO))
        if r.returncode != 0 and not ref.is_file():
            return int(r.returncode or 1)
        if r.returncode != 0 and ref.is_file():
            print("[WARN] FEM 设置非零退出，但 fem_reference.inp 已生成，继续。")

    if not CFG.is_file():
        print(f"[FAIL] 缺少 {CFG}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["FC_FCSTD_PIPELINE_CONFIG"] = str(CFG.resolve())
    print("[CMD]", fc_py, RUNNER)
    r = subprocess.run([str(fc_py), str(RUNNER)], cwd=str(REPO), env=env)
    if r.returncode != 0:
        return int(r.returncode or 1)

    out_inp = EX_DIR / "Analysis-beso.inp"
    man = EX_DIR / "_work" / "beso_dual_domain_manifest.json"
    if man.is_file():
        m = json.loads(man.read_text(encoding="utf-8"))
        print(
            f"[OK] nodes={m.get('nodes')} elements={m.get('elements_total')} "
            f"design_space={m.get('design_space')} entire_mesh={m.get('entire_mesh_design_space')}"
        )
    if out_inp.is_file():
        print("[OK]", out_inp, f"({out_inp.stat().st_size} bytes)")
    else:
        print(f"[FAIL] 未生成 {out_inp}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
