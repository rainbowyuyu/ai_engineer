#!/usr/bin/env python3
"""校验 build_generated_code 在 OC4 场景下保留 scan_dir 双域 beso_conf，不覆盖为单 elset 模板。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.generator.core import build_generated_code, scan_input_directory


def main() -> int:
    scan_dir = ROOT / "examples" / "oc4_beso_pipeline"
    if not scan_dir.is_dir():
        print("SKIP: examples/oc4_beso_pipeline not found")
        return 0
    bundle = scan_input_directory(str(scan_dir))
    if Path(bundle.primary_inp or "").name.lower() != "03_for_beso.inp":
        print("FAIL: expected primary 03_for_beso.inp, got", bundle.primary_inp)
        return 1
    session_conf = scan_dir / "beso_conf.py"
    if not session_conf.is_file():
        print("FAIL: missing beso_conf.py in scan dir")
        return 1

    run_dir = ROOT / "examples" / "oc4_beso_pipeline" / "_verify_run_dir_dummy"
    gen = build_generated_code(
        bundle,
        run_dir=run_dir,
        ccx_path=Path(r"C:\dummy\ccx.exe"),
        mass_goal_ratio=0.25,
        filter_radius=99.0,
        optimization_base="failure_index",
        save_every=3,
    )
    conf = gen.files.get("beso_conf.py", "")
    if "domain_optimized[elset_name] = True" not in conf or "domain_optimized[elset_name] = False" not in conf:
        print("FAIL: dual-domain optimized flags missing from generated beso_conf.py")
        return 1
    if "design_space" not in conf or "nondesign_space" not in conf:
        print("FAIL: elset names design_space / nondesign_space missing")
        return 1
    if gen.field_sources.get("elset_name") != "oc4_session_beso_conf":
        print("FAIL: field_sources elset_name expected oc4_session_beso_conf, got", gen.field_sources.get("elset_name"))
        return 1
    if "mass_goal_ratio = 0.25" not in conf:
        print("FAIL: mass_goal_ratio not patched from user value")
        return 1
    if "filter_list" not in conf or "simple" not in conf:
        print("FAIL: filter_list missing or not simple filter after patch")
        return 1
    if "path = r" not in conf or "C:\\\\dummy\\\\ccx.exe" not in conf.replace("\\\\", "\\"):
        # Windows raw string in conf uses r"C:\dummy\ccx.exe"
        if r"C:\dummy\ccx.exe" not in conf and "dummy" not in conf:
            print("FAIL: path_calculix not patched")
            return 1
    print("OK: OC4 session beso_conf preserved and runtime fields patched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
