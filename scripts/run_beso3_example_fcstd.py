#!/usr/bin/env python3
"""
beso3：若尚无扇区 INP，则从 Analysis-beso.inp 调用 inp_design_120_sectors；
再将 beso_conf 拷入 beso_output 并运行 BESO。

仓库根目录：
  .\\.venv\\Scripts\\python scripts\\run_beso3_example_fcstd.py

环境变量：
  BESO_ITERATIONS_LIMIT   限制迭代
  CCX_PATH
  REBUILD_SECTORS=1       强制重新划分扇区
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

EX_DIR = REPO / "examples" / "beso3"
INP_BASE = EX_DIR / "Analysis-beso.inp"
INP_SEC = EX_DIR / "Analysis-beso_sectors.inp"
MAP_JSON = EX_DIR / "symmetry_120_map.json"
OUT = EX_DIR / "beso_output"


def main() -> int:
    if not INP_BASE.is_file():
        print(f"[FAIL] 缺少 {INP_BASE}；请先按 examples/beso3/README.txt 用 FreeCAD 生成。")
        return 2
    rebuild = (os.environ.get("REBUILD_SECTORS") or "").strip() in ("1", "true", "yes")
    if rebuild or not INP_SEC.is_file() or not MAP_JSON.is_file():
        print("[INFO] 划分 design_s0/1/2 并写 symmetry_120_map.json …")
        cmd = [
            sys.executable,
            "-m",
            "backend.tools.inp_design_120_sectors",
            "--inp",
            str(INP_BASE),
            "--out",
            str(INP_SEC),
            "--map-out",
            str(MAP_JSON),
        ]
        extra = (os.environ.get("SECTOR_TOOL_EXTRA_ARGS") or "").strip()
        if extra:
            cmd.extend(extra.split())
        subprocess.check_call(cmd, cwd=str(REPO))

    OUT.mkdir(parents=True, exist_ok=True)
    tpl = EX_DIR / "beso_conf.py"
    if tpl.is_file():
        shutil.copy2(tpl, OUT / "beso_conf.py")
    elif (OUT / "beso_conf.py").is_file():
        pass
    shutil.copy2(MAP_JSON, OUT / "symmetry_120_map.json")

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
            inp_path=str(INP_SEC.resolve()),
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
