#!/usr/bin/env python3
"""
BESO3 三套拓扑优化：全模型单域 + 论文 +X + 截图 -Z。

仓库根目录执行：
  python scripts/run_beso2_cases.py
  python scripts/run_beso2_cases.py --only export
  python scripts/run_beso2_cases.py --only beso --beso-iter-limit 10

环境变量：
  FREECAD_PYTHON / FREECAD_CMD
  SKIP_BESO=1          仅导出 INP
  BESO_ITERATIONS_LIMIT
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EX_DIR = REPO / "examples" / "beso2"
RUNNER = REPO / "scripts" / "freecad_fcstd_pipeline_runner.py"
SETUP = REPO / "scripts" / "setup_beso3_fem_fcstd.py"
BESO_RUN = REPO / "scripts" / "run_beso2_example_fcstd.py"

CASES = (
    {
        "id": "full",
        "fcpipeline": EX_DIR / "beso2_full.fcpipeline",
        "out_dir": EX_DIR / "beso_output_full",
        "conf_tpl": EX_DIR / "beso_conf_full.py",
        "inp_key": "Analysis-beso-full.inp",
        "entire_mesh": True,
    },
    {
        "id": "paper",
        "fcpipeline": EX_DIR / "beso2_paper.fcpipeline",
        "out_dir": EX_DIR / "beso_output_paper",
        "conf_tpl": EX_DIR / "beso_conf_dual.py",
        "inp_key": "Analysis-beso-paper.inp",
        "entire_mesh": False,
    },
    {
        "id": "screenshot_z",
        "fcpipeline": EX_DIR / "beso2_screenshot_z.fcpipeline",
        "out_dir": EX_DIR / "beso_output_screenshot_z",
        "conf_tpl": EX_DIR / "beso_conf_dual.py",
        "inp_key": "Analysis-beso-screenshot-z.inp",
        "entire_mesh": False,
    },
)


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
    raise FileNotFoundError("未找到 FreeCAD python.exe；设置 FREECAD_PYTHON 或 FREECAD_CMD")


def _run(cmd: list[str], *, env: dict | None = None, cwd: Path | None = None) -> int:
    print("[CMD]", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(cwd or REPO), env=env or os.environ.copy())
    return int(r.returncode or 0)


def _setup_fem(fc_py: Path, skip: bool, force: bool) -> int:
    if skip:
        print("[INFO] --skip-fem-setup")
        return 0
    ref = EX_DIR / "_work_common" / "fem_reference.inp"
    ref_z = EX_DIR / "_work_common" / "fem_reference_z.inp"
    if not force and ref.is_file() and ref_z.is_file():
        print("[INFO] 已有 FEM 参考 INP，跳过 setup（可用 --force-fem-setup 强制）")
        return 0
    return _run(
        [
            str(fc_py),
            str(SETUP),
            "--fcstd",
            str(EX_DIR / "BESO3.FCStd"),
            "--out-work",
            str(EX_DIR / "_work_common"),
        ]
    )


def _export_case(fc_py: Path, case: dict) -> int:
    cfg = case["fcpipeline"]
    if not cfg.is_file():
        print(f"[FAIL] 缺少配置: {cfg}", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["FC_FCSTD_PIPELINE_CONFIG"] = str(cfg.resolve())
    rc = _run([str(fc_py), str(RUNNER)], env=env)
    if rc != 0:
        return rc
    cfg_json = json.loads(cfg.read_text(encoding="utf-8-sig"))
    wd_raw = cfg_json.get("work_dir") or "_work"
    wd = Path(str(wd_raw))
    if not wd.is_absolute():
        wd = (cfg.parent / wd).resolve()
    man = wd / "beso_dual_domain_manifest.json"
    if not man.is_file():
        print(f"[WARN] 无 manifest: {man}", file=sys.stderr)
        return 0
    man_data = json.loads(man.read_text(encoding="utf-8"))
    d = int(man_data.get("design_space", 0))
    nd = int(man_data.get("nondesign_space", 0))
    tot = int(man_data.get("elements_total", 0))
    entire = bool(man_data.get("entire_mesh_design_space", False))
    print(f"[OK] {case['id']}: design={d} nondesign={nd} total={tot} entire_mesh={entire}")
    if case["entire_mesh"] and not entire:
        print(f"[FAIL] {case['id']} 应为全设计域", file=sys.stderr)
        return 3
    if not case["entire_mesh"] and nd < 1:
        print(f"[FAIL] {case['id']} nondesign 为空", file=sys.stderr)
        return 3
    if tot and d + nd != tot:
        print(f"[WARN] {case['id']}: design+nondesign != total", file=sys.stderr)
    return 0


def _beso_case(case: dict, iter_limit: int | None) -> int:
    cfg_json = json.loads(case["fcpipeline"].read_text(encoding="utf-8-sig"))
    out_raw = cfg_json.get("out_inp")
    inp = Path(str(out_raw))
    if not inp.is_absolute():
        inp = (case["fcpipeline"].parent / inp).resolve()
    if not inp.is_file():
        print(f"[FAIL] 缺少 INP: {inp}", file=sys.stderr)
        return 2
    out_dir = case["out_dir"].resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tpl = case["conf_tpl"]
    if tpl.is_file():
        import re

        conf_text = tpl.read_text(encoding="utf-8")
        conf_text = re.sub(
            r"^path = .*$",
            lambda _: f'path = r"{out_dir}"',
            conf_text,
            count=1,
            flags=re.M,
        )
        conf_text = re.sub(
            r"^file_name = .*$",
            lambda _: f'file_name = "{inp.name}"',
            conf_text,
            count=1,
            flags=re.M,
        )
        (out_dir / "beso_conf.py").write_text(conf_text, encoding="utf-8")
    env = os.environ.copy()
    env["BESO_EXAMPLE_INP"] = str(inp)
    env["BESO_EXAMPLE_OUT"] = str(out_dir)
    cmd = [sys.executable, str(BESO_RUN)]
    if iter_limit is not None:
        cmd.extend(["--beso-iter-limit", str(iter_limit)])
    return _run(cmd, env=env)


def main() -> int:
    ap = argparse.ArgumentParser(description="BESO3 三套拓扑优化编排")
    ap.add_argument("--only", choices=("export", "beso", "all"), default="all")
    ap.add_argument("--skip-fem-setup", action="store_true")
    ap.add_argument("--force-fem-setup", action="store_true")
    ap.add_argument("--case", choices=[c["id"] for c in CASES] + ["all"], default="all")
    ap.add_argument("--beso-iter-limit", type=int, default=None)
    args = ap.parse_args()

    cases = [c for c in CASES if args.case == "all" or c["id"] == args.case]
    fc_py = _freecad_python()

    if args.force_fem_setup:
        rc = _run(
            [
                str(fc_py),
                str(SETUP),
                "--fcstd",
                str(EX_DIR / "BESO3.FCStd"),
                "--out-work",
                str(EX_DIR / "_work_common"),
            ]
        )
        if rc != 0:
            return rc
    elif args.only in ("export", "all"):
        rc = _setup_fem(fc_py, args.skip_fem_setup, args.force_fem_setup)
        if rc != 0:
            return rc

    if args.only in ("export", "all"):
        if (os.environ.get("SKIP_BESO") or "").strip() not in ("1", "true", "yes"):
            pass
        for case in cases:
            rc = _export_case(fc_py, case)
            if rc != 0:
                return rc
        if (os.environ.get("SKIP_BESO") or "").strip() in ("1", "true", "yes"):
            print("[INFO] SKIP_BESO=1，跳过 BESO。")
            return 0

    if args.only in ("beso", "all"):
        if (os.environ.get("SKIP_BESO") or "").strip() in ("1", "true", "yes") and args.only == "beso":
            print("[INFO] SKIP_BESO=1")
            return 0
        for case in cases:
            rc = _beso_case(case, args.beso_iter_limit)
            if rc != 0:
                return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
