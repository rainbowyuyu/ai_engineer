"""BESO7 方法一：变径柱参数化重建（FreeCAD 子进程）。"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from backend.tools.freecad_inp_mesh_vtk import resolve_freecad_python

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REBUILD_SCRIPT = (
    _REPO_ROOT / "examples" / "beso" / "beso7" / "addition" / "method1_parametric" / "rebuild_parametric_fc.py"
)


def run_beso7_parametric_rebuild(
    *,
    measurements_path: Path,
    out_dir: Path,
    params: dict | None = None,
    preview_only: bool = True,
    freecad_python: Path | None = None,
    timeout_s: float = 180.0,
) -> Path:
    """根据 measurements.json + 用户缩放参数重建 preview.stl（及可选 STEP/FCStd）。"""
    meas = measurements_path.resolve()
    if not meas.is_file():
        raise FileNotFoundError(f"measurements.json 不存在: {meas}")
    if not _REBUILD_SCRIPT.is_file():
        raise FileNotFoundError(f"重建脚本不存在: {_REBUILD_SCRIPT}")

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    params_path: Path | None = None
    if params:
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        try:
            json.dump(params, tf, ensure_ascii=False)
            tf.close()
            params_path = Path(tf.name)
        except Exception:
            if params_path and params_path.is_file():
                params_path.unlink(missing_ok=True)
            raise

    exe = resolve_freecad_python(freecad_python)
    cmd = [
        str(exe),
        str(_REBUILD_SCRIPT),
        "--measurements-json",
        str(meas),
        "--out-dir",
        str(out_dir),
        "--write-measurements",
    ]
    if preview_only:
        cmd.append("--preview-only")
    if params_path:
        cmd.extend(["--params-json", str(params_path)])

    env = os.environ.copy()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
    finally:
        if params_path and params_path.is_file():
            params_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        raise RuntimeError(f"FreeCAD 重建失败 (code {proc.returncode}): {tail}")

    stl = out_dir / "preview.stl"
    if not stl.is_file():
        raise RuntimeError("重建完成但未生成 preview.stl")
    return stl
