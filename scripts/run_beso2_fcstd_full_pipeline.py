#!/usr/bin/env python3
"""
beso2 完整流程（仓库根目录执行）：

1. 用 **FreeCAD 自带 Python**（默认 ``D:\\freecad\\bin\\python.exe``）跑
   ``freecad_fcstd_pipeline_runner.py``，配置默认 ``examples/beso2/beso2.fcpipeline``（**BESO3.FCStd + 纵向 Z 向力**）。
   覆盖配置：运行前设置 ``FC_FCSTD_PIPELINE_CONFIG`` 指向其它 ``*.fcpipeline`` 绝对路径。
   装配 ``Part::Compound``（与文档 ``Compound`` 一致）→ STEP → Gmsh 体网格 →
   按 ``Pad001`` 划分 **design_space** 与 **nondesign_space** → 写出 ``Analysis-beso.inp``。
2. 校验流水线 ``work_dir`` 下 ``beso_dual_domain_manifest.json`` 中单元数之和。
3. 若未设 ``SKIP_BESO=1``，再运行 ``run_beso2_example_fcstd.py``（BESO 需双域 ``beso_conf``，由 ``backend/tools/beso.py`` 根据 INP 自动生成）。

FreeCAD FEM 参考（CalculiX 写出 INP）：``Mod/Fem/femtools/ccxtools.py`` 中 ``FemToolsCcx.write_inp_file`` →
``femsolver.calculix.writer.FemInputWriterCcx``；本流程体网格优先走 **Gmsh + 全装配 STEP**，
避免文档内 FEM 分析仅关联子部件时漏掉柱体等非设计域。

环境变量：
  FREECAD_PYTHON   覆盖默认的 FreeCAD 内 python.exe
  FREECAD_CMD      若未设置 FREECAD_PYTHON，可用其所在目录推导 python.exe
  BESO_ITERATIONS_LIMIT
  SKIP_BESO=1      只导出 INP，不跑 BESO
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_DEFAULT_CFG = REPO / "examples" / "beso2" / "beso2.fcpipeline"


def _pipeline_config_path() -> Path:
    env_c = (os.environ.get("FC_FCSTD_PIPELINE_CONFIG") or "").strip()
    if env_c:
        p = Path(env_c)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"FC_FCSTD_PIPELINE_CONFIG 不是有效文件: {env_c}")
    if not _DEFAULT_CFG.is_file():
        raise FileNotFoundError(f"缺少默认流水线配置: {_DEFAULT_CFG}")
    return _DEFAULT_CFG.resolve()


def _freecad_python() -> Path:
    env_py = (os.environ.get("FREECAD_PYTHON") or "").strip()
    if env_py:
        p = Path(env_py)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"FREECAD_PYTHON 无效: {env_py}")
    env_cmd = (os.environ.get("FREECAD_CMD") or "").strip()
    if env_cmd:
        guess = Path(env_cmd).parent / "python.exe"
        if guess.is_file():
            return guess.resolve()
    for name in ("FreeCADCmd.exe", "freecadcmd.exe"):
        w = shutil.which(name)
        if w:
            guess = Path(w).parent / "python.exe"
            if guess.is_file():
                return guess.resolve()
    default = Path(r"D:\freecad\bin\python.exe")
    if default.is_file():
        return default.resolve()
    raise FileNotFoundError(
        "未找到 FreeCAD 的 python.exe；请设置 FREECAD_PYTHON 或 FREECAD_CMD（指向 FreeCADCmd.exe）。"
    )


def main() -> int:
    try:
        cfg_path = _pipeline_config_path()
    except FileNotFoundError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 2
    fc_py = _freecad_python()
    runner = REPO / "scripts" / "freecad_fcstd_pipeline_runner.py"
    if not runner.is_file():
        print(f"[FAIL] 未找到 {runner}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["FC_FCSTD_PIPELINE_CONFIG"] = str(cfg_path)
    print("[INFO] FC_FCSTD_PIPELINE_CONFIG=", cfg_path)
    print("[INFO] FreeCAD Python:", fc_py)
    r = subprocess.run([str(fc_py), str(runner)], cwd=str(REPO), env=env)
    if r.returncode != 0:
        return int(r.returncode or 1)

    cfg_dir = cfg_path.parent.resolve()
    cfg_json = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    wd_raw = cfg_json.get("work_dir") or "_fc_work"
    work_dir = Path(str(wd_raw))
    if not work_dir.is_absolute():
        work_dir = (cfg_dir / work_dir).resolve()
    man_path = work_dir / "beso_dual_domain_manifest.json"
    if man_path.is_file():
        man = json.loads(man_path.read_text(encoding="utf-8"))
        nd = int(man.get("nondesign_space", 0))
        d = int(man.get("design_space", 0))
        tot = int(man.get("elements_total", 0))
        print("[OK] manifest:", man_path)
        print(f"    design_space={d} nondesign_space={nd} total={tot}")
        if tot and d + nd != tot:
            print("[WARN] design + nondesign 与 total 不一致，请检查划分。", file=sys.stderr)
        if nd < 1:
            print("[FAIL] nondesign_space 为空。", file=sys.stderr)
            return 3
    else:
        print("[WARN] 未生成 manifest，跳过计数校验", file=sys.stderr)

    if (os.environ.get("SKIP_BESO") or "").strip() in ("1", "true", "yes"):
        print("[INFO] SKIP_BESO=1，跳过 BESO。")
        return 0

    beso_script = REPO / "scripts" / "run_beso2_example_fcstd.py"
    r2 = subprocess.run([sys.executable, str(beso_script)], cwd=str(REPO), env=os.environ.copy())
    return int(r2.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
