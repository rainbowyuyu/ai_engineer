"""调用 FreeCAD 将 CAD（IGES/STEP）导出为 STEP。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.tools.freecad_iges_to_inp import _repo_root, mesh_python_exe, resolve_freecad_cmd


def runner_script() -> Path:
    p = _repo_root() / "scripts" / "freecad_export_step_runner.py"
    if not p.is_file():
        raise FileNotFoundError(f"未找到 STEP 导出 runner: {p}")
    return p


def run_freecad_export_step(
    cad_path: Path,
    out_step: Path,
    *,
    freecad_cmd: Path | None = None,
    timeout_s: float = 600.0,
) -> Path:
    cad_path = cad_path.resolve()
    out_step = out_step.resolve()
    out_step.parent.mkdir(parents=True, exist_ok=True)
    ext = cad_path.suffix.lower()
    if ext in (".stp", ".step"):
        shutil.copy2(cad_path, out_step)
        return out_step

    cfg = {"cad_path": str(cad_path), "out_step": str(out_step)}
    fc = resolve_freecad_cmd(freecad_cmd)
    exe = mesh_python_exe(fc)
    runner = runner_script()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".fcexpstp",
        delete=False,
        encoding="utf-8",
    ) as tf:
        json.dump(cfg, tf, indent=2)
        tmp_cfg = Path(tf.name)
    env = os.environ.copy()
    env["FC_EXPORT_STEP_CONFIG"] = str(tmp_cfg)
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
    if not out_step.is_file():
        raise RuntimeError(f"未生成 STEP: {out_step}")
    return out_step


__all__ = ["run_freecad_export_step", "runner_script"]
