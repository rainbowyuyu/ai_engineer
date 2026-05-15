#!/usr/bin/env python3
"""
对 ``examples/beson1/_work/Analysis-vol.inp`` 运行 BESO（需已由 FreeCAD 流水线生成）。

仓库根目录执行：
  .\\.venv\\Scripts\\python scripts\\run_beson1_beso.py
  .\\.venv\\Scripts\\python scripts\\run_beson1_beso.py --beso-iter-limit 5

环境变量 ``CCX_PATH`` 可覆盖默认的 CalculiX 路径（与 ``backend/tools/beso.py`` 一致）。
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

INP = REPO / "examples" / "beson1" / "_work" / "Analysis-vol.inp"
OUT = REPO / "examples" / "beson1" / "_work" / "beso_output"


def main() -> int:
    ap = argparse.ArgumentParser(description="从 examples/beson1/_work 运行 BESO（Analysis-vol.inp）。")
    ap.add_argument(
        "--beso-iter-limit",
        type=int,
        default=None,
        metavar="N",
        help="正整数时限制 BESO 最大迭代步数；省略则按 beso_conf 的 auto。",
    )
    args = ap.parse_args()
    if args.beso_iter_limit is not None:
        os.environ["BESO_ITERATIONS_LIMIT"] = str(max(1, int(args.beso_iter_limit)))
    elif "BESO_ITERATIONS_LIMIT" not in os.environ:
        pass
    # 若未传参且环境变量已存在，则保留（便于 PowerShell 中 $env:BESO_ITERATIONS_LIMIT=5）

    if not INP.is_file():
        print(
            f"[FAIL] 找不到 {INP}；请先设置 FC_FCSTD_PIPELINE_CONFIG 为 "
            f"examples/beson1/beson1_vol.fcpipeline 并用 FreeCAD 运行 freecad_fcstd_pipeline_runner.py",
            file=sys.stderr,
        )
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    from backend.tools.beso import run_beso_job

    cancel = threading.Event()

    def on_log(line: str) -> None:
        print(line, flush=True)

    def on_vtk(rel: str) -> None:
        print(f"[VTK] {rel}", flush=True)

    try:
        run_beso_job(
            workspace_root=REPO,
            run_dir=OUT.resolve(),
            inp_path=str(INP.resolve()),
            mass_goal_ratio=0.15,
            filter_radius=2.0,
            optimization_base="stiffness",
            save_every=1,
            cancel_flag=cancel,
            on_log=on_log,
            on_vtk=on_vtk,
            on_artifact=None,
        )
    except FileNotFoundError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        cancel.set()
        print("[INFO] 用户中断")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
