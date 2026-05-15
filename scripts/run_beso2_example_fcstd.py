#!/usr/bin/env python3
"""
从 examples/beso2 运行 BESO（需已存在 Analysis-beso.inp，由 FreeCAD 流水线生成）。

仓库根目录执行：
  .\\.venv\\Scripts\\python scripts\\run_beso2_example_fcstd.py

本脚本默认会清除进程内 ``BESO_ITERATIONS_LIMIT``（避免 PowerShell 里曾 ``$env:...=5`` 一直残留），
按 BESO ``iterations_limit="auto"`` 跑满。试跑限制迭代请传 ``--beso-iter-limit N``。

可选环境变量：
  CCX_PATH                CalculiX 可执行文件路径
  BESO_EXAMPLE_INP        主 INP 路径（默认 ``examples/beso2/Analysis-beso.inp``；流水线产物常为 ``_fc_work/Analysis-beso.inp``）
  BESO_EXAMPLE_OUT        BESO 工作目录（默认 ``<inp 父目录>/beso_output`` 或 ``examples/beso2/beso_output``）
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

EX_DIR = REPO / "examples" / "beso2"


def main() -> int:
    ap = argparse.ArgumentParser(description="从 examples/beso2 运行 BESO（Analysis-beso.inp）。")
    ap.add_argument(
        "--beso-iter-limit",
        type=int,
        default=None,
        metavar="N",
        help="正整数时本进程内限制 BESO 最大迭代步数；省略则清除 BESO_ITERATIONS_LIMIT，按 auto 跑满。",
    )
    args = ap.parse_args()
    if args.beso_iter_limit is not None:
        n = max(1, int(args.beso_iter_limit))
        os.environ["BESO_ITERATIONS_LIMIT"] = str(n)
        print(f"[INFO] --beso-iter-limit={n}（写入 beso_conf 的 iterations_limit）")
    else:
        os.environ.pop("BESO_ITERATIONS_LIMIT", None)
        print("[INFO] 已取消 BESO_ITERATIONS_LIMIT（按 BESO 自动 iterations_limit 跑满）。")

    env_inp = (os.environ.get("BESO_EXAMPLE_INP") or "").strip()
    inp_path = Path(env_inp).resolve() if env_inp else (EX_DIR / "Analysis-beso.inp").resolve()
    env_out = (os.environ.get("BESO_EXAMPLE_OUT") or "").strip()
    if env_out:
        out_dir = Path(env_out).resolve()
    elif inp_path.parent.name in ("_fc_work", "_beso_work"):
        out_dir = (inp_path.parent / "beso_output").resolve()
    else:
        out_dir = (EX_DIR / "beso_output").resolve()

    if not inp_path.is_file():
        print(
            f"[FAIL] 找不到 {inp_path}；请先用 FreeCAD 跑 freecad_fcstd_pipeline_runner，"
            "或设置 BESO_EXAMPLE_INP 指向生成的 Analysis-beso*.inp",
            file=sys.stderr,
        )
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    tpl = EX_DIR / "beso_conf.py"
    if tpl.is_file():
        shutil.copy2(tpl, out_dir / "beso_conf.py")
    elif (out_dir / "beso_conf.py").is_file():
        pass

    from backend.tools.beso import run_beso_job

    cancel = threading.Event()

    def on_log(line: str) -> None:
        print(line, flush=True)

    def on_vtk(rel: str) -> None:
        print(f"[VTK] {rel}", flush=True)

    try:
        run_beso_job(
            workspace_root=REPO,
            run_dir=out_dir,
            inp_path=str(inp_path),
            mass_goal_ratio=0.15,
            filter_radius=2.0,
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
