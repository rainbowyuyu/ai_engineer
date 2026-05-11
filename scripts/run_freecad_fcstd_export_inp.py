#!/usr/bin/env python3
"""
从 FCStd 生成完整 CalculiX INP。默认 **fuse_all_solids**（``--no-fuse-all-solids`` 可关）：**跳过 FEM**，用 FCStd 内全部有体积实体 Compound + Gmsh，保证非设计域与整体设计域在同一 INP；``fuse_all_solids`` 关闭时仍为 FEM 优先，失败再按 Pad+Pad001 或配置融合。

使用仓库根目录下的 ``D:\\freecad\\bin\\python.exe``（或 ``--freecad-cmd`` / ``FREECAD_CMD``）执行
``freecad_fcstd_pipeline_runner.py``。

勿将 JSON 配置路径作为额外 argv 传给 FreeCADCmd（会误打开文档）；通过环境变量传递。

示例::

    python scripts/run_freecad_fcstd_export_inp.py \\
        --fcstd examples/beso/input.FCStd \\
        --out examples/beso/Analysis-export.inp
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = Path(__file__).resolve().parent / "freecad_fcstd_pipeline_runner.py"


def _resolve_freecad_cmd(explicit: Path | None) -> Path:
    if explicit is not None:
        p = explicit.resolve()
        if not p.is_file():
            raise FileNotFoundError(f"--freecad-cmd 无效: {p}")
        return p
    env = (os.environ.get("FREECAD_CMD") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"FREECAD_CMD 不存在: {env}")
    for name in ("FreeCADCmd.exe", "freecadcmd.exe"):
        w = shutil.which(name)
        if w:
            return Path(w).resolve()
    guess = Path(r"D:\freecad\bin\freecadcmd.exe")
    if guess.is_file():
        return guess.resolve()
    raise FileNotFoundError("未找到 FreeCADCmd.exe；请设置 FREECAD_CMD 或 --freecad-cmd。")


def _mesh_python_exe(freecad_cmd: Path) -> Path:
    py = freecad_cmd.parent / "python.exe"
    if py.is_file():
        return py.resolve()
    return freecad_cmd.resolve()


def main() -> int:
    ap = argparse.ArgumentParser(description="FCStd → CalculiX INP（Chen2026/BESO 前置）")
    ap.add_argument("--fcstd", type=Path, required=True, help="输入 .FCStd")
    ap.add_argument("--out", type=Path, required=True, help="输出 .inp")
    ap.add_argument("--work-dir", type=Path, default=None, help="中间文件目录（默认同输出目录）")
    ap.add_argument("--freecad-cmd", type=Path, default=None, help="FreeCADCmd.exe 路径")
    ap.add_argument("--mesh-preset", default="xlarge", choices=("fine", "medium", "coarse", "xlarge"))
    ap.add_argument("--design-solid", default="Pad001", help="设计域 Part 对象名（默认 Pad001）")
    ap.add_argument(
        "--no-fuse-all-solids",
        action="store_true",
        help="Gmsh 回退时仅融合 Pad+Pad001（旧行为；一般勿用，易导致非设计域零件未进网格）",
    )
    args = ap.parse_args()

    fcstd = args.fcstd.resolve()
    out_inp = args.out.resolve()
    if not fcstd.is_file():
        print(f"[ERR] FCStd 不存在: {fcstd}", file=sys.stderr)
        return 2
    work_dir = (args.work_dir or out_inp.parent).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "fcstd_path": str(fcstd),
        "out_inp": str(out_inp),
        "work_dir": str(work_dir),
        "repo_root": str(REPO),
        "mesh_preset": args.mesh_preset,
        "design_solid_name": args.design_solid,
        "fuse_all_solids": not args.no_fuse_all_solids,
        "fuse_solid_names": ["Pad", "Pad001"],
    }

    fc = _resolve_freecad_cmd(args.freecad_cmd)
    mesh_exe = _mesh_python_exe(fc)
    if not RUNNER.is_file():
        raise FileNotFoundError(f"未找到 runner: {RUNNER}")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".fcpipeline", delete=False, encoding="utf-8") as tf:
        json.dump(cfg, tf, indent=2)
        tmp_cfg = Path(tf.name)

    env = os.environ.copy()
    env["FC_FCSTD_PIPELINE_CONFIG"] = str(tmp_cfg)
    try:
        cmd = [str(mesh_exe), str(RUNNER)]
        print("[INFO] FC_FCSTD_PIPELINE_CONFIG=", tmp_cfg)
        print("[INFO] executor:", mesh_exe)
        r = subprocess.run(cmd, cwd=str(REPO), env=env)
        if r.returncode != 0:
            return int(r.returncode or 1)
    finally:
        tmp_cfg.unlink(missing_ok=True)

    if not out_inp.is_file():
        print(f"[ERR] 未生成: {out_inp}", file=sys.stderr)
        return 1
    print("[OK]", out_inp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
