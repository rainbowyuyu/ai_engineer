"""Invoke FreeCADCmd to produce multi-view CAD line drawings + shaded sheet."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from backend.tools.freecad_iges_to_inp import _repo_root, mesh_python_exe, resolve_freecad_cmd


def runner_script() -> Path:
    p = _repo_root() / "scripts" / "freecad_drawing_pack_runner.py"
    if not p.is_file():
        raise FileNotFoundError(f"未找到 FreeCAD 出图 runner: {p}")
    return p


def run_freecad_drawing_views(
    cad_path: Path,
    out_dir: Path,
    *,
    linear_deflection: float = 1200.0,
    freecad_cmd: Path | None = None,
    timeout_s: float = 420.0,
) -> dict[str, Any]:
    """Run FreeCAD projection pack into ``out_dir``. Returns freecad_meta.json payload."""
    cad_path = cad_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not cad_path.is_file():
        raise FileNotFoundError(f"CAD 不存在: {cad_path}")

    cfg = {
        "cad_path": str(cad_path),
        "out_dir": str(out_dir),
        "linear_deflection": float(linear_deflection),
        "views": ["iso", "top", "front", "right"],
    }
    fc = resolve_freecad_cmd(freecad_cmd)
    exe = mesh_python_exe(fc)
    runner = runner_script()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".fcdraw", delete=False, encoding="utf-8") as tf:
        json.dump(cfg, tf, indent=2)
        tmp_cfg = Path(tf.name)
    env = os.environ.copy()
    env["FC_DRAWING_PACK_CONFIG"] = str(tmp_cfg)
    # Prefer D:\freecad when FREECAD_CMD unset but path exists
    if not env.get("FREECAD_CMD") and Path(r"D:\freecad\bin\FreeCADCmd.exe").is_file():
        env.setdefault("FREECAD_CMD", r"D:\freecad\bin\FreeCADCmd.exe")
    try:
        subprocess.run(
            [str(exe), str(runner)],
            cwd=str(_repo_root()),
            env=env,
            timeout=timeout_s if timeout_s > 0 else None,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or e.stdout or "")[-2000:]
        raise RuntimeError(f"FreeCAD 出图失败: {tail or e}") from e
    finally:
        tmp_cfg.unlink(missing_ok=True)

    meta_path = out_dir / "freecad_meta.json"
    if not meta_path.is_file():
        raise RuntimeError(f"未生成 freecad_meta.json: {out_dir}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


__all__ = ["run_freecad_drawing_views", "runner_script"]
