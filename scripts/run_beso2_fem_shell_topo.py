#!/usr/bin/env python3
"""
对 ``examples/beso2/_fem_beso_work/Analysis-beso-shell-dual.inp`` 运行 BESO（壳、双域）。

仓库根目录::

  set BESO_ITERATIONS_LIMIT=30
  .\\.venv\\Scripts\\python scripts\\run_beso2_fem_shell_topo.py

可选环境变量：``CCX_PATH``、``BESO_ITERATIONS_LIMIT``。
命令行：``--inp``、``--out-dir``、``--mass-goal``、``--filter-radius`` 覆盖默认。
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_INP = REPO / "examples" / "beso2" / "_fem_beso_work" / "Analysis-beso-shell-dual.inp"
DEFAULT_OUT = REPO / "examples" / "beso2" / "_fem_beso_work" / "beso_shell_topo_out"


def main() -> int:
    ap = argparse.ArgumentParser(description="BESO：beso2 FEM 壳双域 Analysis-beso-shell-dual.inp")
    ap.add_argument("--inp", type=Path, default=DEFAULT_INP, help="输入主 INP")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT, help="BESO 工作目录")
    ap.add_argument("--mass-goal", type=float, default=0.35, help="mass_goal_ratio")
    ap.add_argument("--filter-radius", type=float, default=1500.0, help="simple 滤波半径（与模型 mm 尺度匹配）")
    args = ap.parse_args()

    inp = args.inp.resolve()
    out = args.out_dir.resolve()
    if not inp.is_file():
        print(f"[FAIL] 找不到 {inp}；请先运行 run_beso_fem_shell_dual_domain_export.py 生成壳双域 INP。")
        return 2
    out.mkdir(parents=True, exist_ok=True)

    lim = (os.environ.get("BESO_ITERATIONS_LIMIT") or "").strip()
    if lim.isdigit() and int(lim) > 0:
        print(f"[INFO] BESO_ITERATIONS_LIMIT={lim}（覆盖 beso_conf）")
    else:
        print("[INFO] 未设置 BESO_ITERATIONS_LIMIT：beso_conf 使用 auto，由 beso_main 按质量目标估算迭代次数。")

    from backend.tools.beso import run_beso_job

    cancel = threading.Event()

    def on_log(line: str) -> None:
        print(line, flush=True)

    def on_vtk(rel: str) -> None:
        print(f"[VTK] {rel}", flush=True)

    try:
        run_beso_job(
            workspace_root=REPO,
            run_dir=out,
            inp_path=str(inp),
            mass_goal_ratio=float(args.mass_goal),
            filter_radius=float(args.filter_radius),
            optimization_base="stiffness",
            save_every=1,
            cancel_flag=cancel,
            on_log=on_log,
            on_vtk=on_vtk,
            on_artifact=None,
        )
    except KeyboardInterrupt:
        cancel.set()
        print("[INFO] 用户中断")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
