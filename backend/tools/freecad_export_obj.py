"""调用 FreeCAD 将 CAD（IGES/STEP）导出为 OBJ（预览用）。"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from backend.tools.freecad_iges_to_inp import _repo_root, mesh_python_exe, resolve_freecad_cmd


def runner_script() -> Path:
    p = _repo_root() / "scripts" / "freecad_export_obj_runner.py"
    if not p.is_file():
        raise FileNotFoundError(f"未找到 OBJ 导出 runner: {p}")
    return p


def run_freecad_export_obj(
    cad_path: Path,
    out_obj: Path,
    *,
    linear_deflection: float = 800.0,
    freecad_cmd: Path | None = None,
    timeout_s: float = 600.0,
) -> Path:
    cad_path = cad_path.resolve()
    out_obj = out_obj.resolve()
    out_obj.parent.mkdir(parents=True, exist_ok=True)
    cfg = {
        "cad_path": str(cad_path),
        "out_obj": str(out_obj),
        "linear_deflection": float(linear_deflection),
    }
    fc = resolve_freecad_cmd(freecad_cmd)
    exe = mesh_python_exe(fc)
    runner = runner_script()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".fcexpobj",
        delete=False,
        encoding="utf-8",
    ) as tf:
        json.dump(cfg, tf, indent=2)
        tmp_cfg = Path(tf.name)
    env = os.environ.copy()
    env["FC_EXPORT_OBJ_CONFIG"] = str(tmp_cfg)
    try:
        subprocess.run(
            [str(exe), str(runner)],
            cwd=str(_repo_root()),
            env=env,
            timeout=timeout_s if timeout_s > 0 else None,
            check=True,
        )
    finally:
        tmp_cfg.unlink(missing_ok=True)
    if not out_obj.is_file():
        raise RuntimeError(f"未生成 OBJ: {out_obj}")
    return out_obj


__all__ = ["run_freecad_export_obj", "runner_script"]
