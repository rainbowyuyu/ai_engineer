"""使用 FreeCAD Fem.FemMesh 将网格 INP 转为 VTK 文本（供 Web 预览）。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "scripts" / "freecad_inp_mesh_to_vtk.py"


def resolve_freecad_python(explicit: Path | None = None) -> Path:
    if explicit is not None:
        p = explicit.resolve()
        if not p.is_file():
            raise FileNotFoundError(str(p))
        return p
    env_py = (os.environ.get("FREECAD_PYTHON") or "").strip()
    if env_py:
        p = Path(env_py)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"FREECAD_PYTHON 指向的文件不存在: {env_py}")
    env_cmd = (os.environ.get("FREECAD_CMD") or "").strip()
    if env_cmd:
        fc = Path(env_cmd)
        if fc.is_file():
            guess = fc.parent / "python.exe"
            if guess.is_file():
                return guess.resolve()
    win = Path(r"D:\freecad\bin\python.exe")
    if win.is_file():
        return win.resolve()
    raise FileNotFoundError(
        "未找到 FreeCAD 的 python.exe：请设置环境变量 FREECAD_PYTHON 或 FREECAD_CMD（FreeCADCmd 同目录下应有 python.exe）。"
    )


def convert_inp_to_vtk_file(
    inp_path: Path,
    out_vtk: Path,
    *,
    timeout_s: float = 180.0,
    freecad_python: Path | None = None,
) -> Path:
    exe = resolve_freecad_python(freecad_python)
    if not _RUNNER.is_file():
        raise FileNotFoundError(f"缺少脚本: {_RUNNER}")
    inp_path = inp_path.resolve()
    out_vtk = out_vtk.resolve()
    out_vtk.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe), str(_RUNNER), str(inp_path), str(out_vtk)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()
        if len(tail) > 6000:
            tail = tail[:6000] + "\n…"
        raise RuntimeError(tail or f"FreeCAD 子进程退出码 {proc.returncode}")
    if not out_vtk.is_file():
        raise RuntimeError("转换完成但未找到输出 VTK 文件")
    return out_vtk
