#!/usr/bin/env python3
"""
BESO5.FCStd 拓扑优化：FEM 参考 BC → Gmsh 体网格 INP → BESO。

仓库根目录执行：
  python scripts/run_beso5_topo.py
  python scripts/run_beso5_topo.py --only export
  python scripts/run_beso5_topo.py --only beso --beso-iter-limit 10

环境变量：FREECAD_PYTHON / FREECAD_CMD / SKIP_BESO=1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EX_DIR = REPO / "examples" / "beso5"
CFG = EX_DIR / "beso5.fcpipeline"
RUNNER = REPO / "scripts" / "freecad_fcstd_pipeline_runner.py"
SETUP = REPO / "scripts" / "setup_beso3_fem_fcstd.py"
BESO_RUN = REPO / "scripts" / "run_beso2_example_fcstd.py"
CONF_TPL = EX_DIR / "beso_conf.py"


def _freecad_python() -> Path:
    env_py = (os.environ.get("FREECAD_PYTHON") or "").strip()
    if env_py:
        p = Path(env_py)
        if p.is_file():
            return p.resolve()
    env_cmd = (os.environ.get("FREECAD_CMD") or "").strip()
    if env_cmd:
        guess = Path(env_cmd).parent / "python.exe"
        if guess.is_file():
            return guess.resolve()
    default = Path(r"D:\freecad\bin\python.exe")
    if default.is_file():
        return default.resolve()
    raise FileNotFoundError("未找到 FreeCAD python.exe")


def _run(cmd: list[str], *, env: dict | None = None) -> int:
    print("[CMD]", " ".join(cmd))
    return int(subprocess.run(cmd, cwd=str(REPO), env=env or os.environ.copy()).returncode or 0)


def main() -> int:
    ap = argparse.ArgumentParser(description="BESO5 拓扑优化")
    ap.add_argument("--only", choices=("export", "beso", "all"), default="all")
    ap.add_argument("--skip-fem-setup", action="store_true")
    ap.add_argument("--beso-iter-limit", type=int, default=None)
    args = ap.parse_args()

    fc_py = _freecad_python()
    fcstd = EX_DIR / "BESO5.FCStd"
    work_common = EX_DIR / "_work_common"

    if args.only in ("export", "all") and not args.skip_fem_setup:
        ref = work_common / "fem_reference.inp"
        if not ref.is_file():
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
                print("[INFO] FCStd 只读，FEM 设置使用 --no-save-fcstd")
            rc = _run(cmd)
            if rc != 0 and not ref.is_file():
                return rc
            if rc != 0 and ref.is_file():
                print("[WARN] FEM 设置退出码非 0，但 fem_reference.inp 已存在，继续导出。")

    if args.only in ("export", "all"):
        if not CFG.is_file():
            print(f"[FAIL] 缺少 {CFG}", file=sys.stderr)
            return 2
        env = os.environ.copy()
        env["FC_FCSTD_PIPELINE_CONFIG"] = str(CFG.resolve())
        rc = _run([str(fc_py), str(RUNNER)], env=env)
        if rc != 0:
            return rc
        cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
        wd = EX_DIR / str(cfg.get("work_dir", "_work"))
        man = wd / "beso_dual_domain_manifest.json"
        if man.is_file():
            m = json.loads(man.read_text(encoding="utf-8"))
            print(
                f"[OK] design={m.get('design_space')} nondesign={m.get('nondesign_space')} "
                f"total={m.get('elements_total')}"
            )
        if (os.environ.get("SKIP_BESO") or "").strip() in ("1", "true", "yes"):
            print("[INFO] SKIP_BESO=1")
            return 0

    if args.only in ("beso", "all"):
        if (os.environ.get("SKIP_BESO") or "").strip() in ("1", "true", "yes") and args.only == "beso":
            return 0
        cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
        inp = (EX_DIR / cfg["out_inp"]).resolve()
        if not inp.is_file():
            print(f"[FAIL] 缺少 INP: {inp}", file=sys.stderr)
            return 2
        out_dir = (EX_DIR / "beso_output").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        if CONF_TPL.is_file():
            text = CONF_TPL.read_text(encoding="utf-8")
            text = re.sub(r"^path = .*$", lambda _: f'path = r"{out_dir}"', text, count=1, flags=re.M)
            text = re.sub(
                r"^file_name = .*$",
                lambda _: f'file_name = "{inp.name}"',
                text,
                count=1,
                flags=re.M,
            )
            (out_dir / "beso_conf.py").write_text(text, encoding="utf-8")
        env = os.environ.copy()
        env["BESO_EXAMPLE_INP"] = str(inp)
        env["BESO_EXAMPLE_OUT"] = str(out_dir)
        cmd = [sys.executable, str(BESO_RUN)]
        if args.beso_iter_limit is not None:
            cmd.extend(["--beso-iter-limit", str(max(1, int(args.beso_iter_limit)))])
        return _run(cmd, env=env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
