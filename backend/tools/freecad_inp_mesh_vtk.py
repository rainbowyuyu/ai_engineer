"""将 CalculiX/Abaqus 体网格 INP 转为 VTK（供 Web 三维预览）。

优先使用 **meshio**（UTF-8 读入；多块同类型体单元合并），避免 FreeCAD ``Fem.FemMesh.read``
在多段 ``*ELEMENT``（如 ``design_space`` 与 ``nondesign_space`` 各一段 C3D4）时只保留第一段，
导致预览仅显示部分体积。失败时回退 FreeCAD 子进程。
"""
from __future__ import annotations

import io
import os
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "scripts" / "freecad_inp_mesh_to_vtk.py"


def _merge_meshio_cells_same_type(mesh: "meshio.Mesh") -> "meshio.Mesh":
    """多块同类型体单元（如两段 C3D4）合并为一块，便于 VTK 完整显示。"""
    import meshio

    groups: dict[str, list[np.ndarray]] = defaultdict(list)
    order: list[str] = []
    for c in mesh.cells:
        if c.type not in order:
            order.append(c.type)
        groups[c.type].append(np.asarray(c.data))
    cells_out: list[tuple[str, np.ndarray]] = []
    for typ in order:
        arrs = groups[typ]
        if len(arrs) == 1:
            cells_out.append((typ, arrs[0]))
        else:
            cells_out.append((typ, np.vstack(arrs)))
    return meshio.Mesh(points=mesh.points, cells=cells_out)


def _inp_to_vtk_via_meshio(inp_path: Path, out_vtk: Path) -> None:
    import meshio
    from meshio.abaqus._abaqus import read_buffer

    text = inp_path.read_text(encoding="utf-8", errors="replace")
    mesh = read_buffer(io.StringIO(text))
    if mesh.points.size == 0 or not mesh.cells:
        raise RuntimeError("meshio: INP 中无有效节点或单元")
    mesh = _merge_meshio_cells_same_type(mesh)
    meshio.write(out_vtk, mesh, file_format="vtk")


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
    inp_path = inp_path.resolve()
    out_vtk = out_vtk.resolve()
    out_vtk.parent.mkdir(parents=True, exist_ok=True)

    try:
        _inp_to_vtk_via_meshio(inp_path, out_vtk)
        if out_vtk.is_file() and out_vtk.stat().st_size > 0:
            return out_vtk
    except Exception:
        pass

    exe = resolve_freecad_python(freecad_python)
    if not _RUNNER.is_file():
        raise FileNotFoundError(f"缺少脚本: {_RUNNER}")
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
