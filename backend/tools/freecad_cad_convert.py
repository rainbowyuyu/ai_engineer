"""调用 FreeCAD 在常见 CAD 格式之间转换（STEP / IGES / STL / BREP）。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from backend.tools.freecad_iges_to_inp import _repo_root, mesh_python_exe, resolve_freecad_cmd

TargetFormat = Literal["step", "iges", "stl", "brep"]

_FORMAT_SUFFIX: dict[str, str] = {
    "step": ".step",
    "iges": ".iges",
    "stl": ".stl",
    "brep": ".brep",
}

_INPUT_EXTS = frozenset({".igs", ".iges", ".stp", ".step", ".stl", ".brep"})


def runner_script() -> Path:
    p = _repo_root() / "scripts" / "freecad_cad_convert_runner.py"
    if not p.is_file():
        raise FileNotFoundError(f"未找到 CAD 转换 runner: {p}")
    return p


def path_under_workspace(path: Path, workspace_root: Path) -> bool:
    try:
        path.resolve().relative_to(workspace_root.resolve())
        return True
    except ValueError:
        return False


def resolve_workspace_path(raw: str, workspace_root: Path) -> Path:
    s = (raw or "").strip()
    if not s:
        raise ValueError("路径为空")
    p = Path(s).expanduser()
    if not p.is_absolute():
        p = (workspace_root / p).resolve()
    else:
        p = p.resolve()
    if not path_under_workspace(p, workspace_root):
        raise ValueError("路径必须位于 WORKSPACE_ROOT 工作区内")
    return p


def _out_suffix_for(target_format: str) -> str:
    k = str(target_format or "").strip().lower()
    if k not in _FORMAT_SUFFIX:
        raise ValueError(f"不支持的 target_format: {target_format}（允许 step / iges / stl / brep）")
    return _FORMAT_SUFFIX[k]


def run_freecad_cad_convert(
    input_path: Path,
    output_path: Path,
    *,
    freecad_cmd: Path | None = None,
    timeout_s: float = 600.0,
) -> Path:
    """在 FreeCAD 子进程内执行转换；input/output 须已由调用方校验为工作区内路径。"""
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    in_ext = input_path.suffix.lower()
    if in_ext not in _INPUT_EXTS:
        raise ValueError(f"不支持的输入扩展名: {in_ext}")
    out_ext = output_path.suffix.lower()
    if out_ext not in (".step", ".stp", ".iges", ".igs", ".stl", ".brep"):
        raise ValueError(f"不支持的输出扩展名: {out_ext}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 同格式直接复制，跳过 FreeCAD
    if in_ext == out_ext or (in_ext in (".stp", ".step") and out_ext in (".stp", ".step")):
        shutil.copy2(input_path, output_path)
        return output_path
    if in_ext in (".igs", ".iges") and out_ext in (".igs", ".iges"):
        shutil.copy2(input_path, output_path)
        return output_path

    cfg = {"input_path": str(input_path), "output_path": str(output_path)}
    fc = resolve_freecad_cmd(freecad_cmd)
    exe = mesh_python_exe(fc)
    runner = runner_script()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".fccadcv",
        delete=False,
        encoding="utf-8",
    ) as tf:
        json.dump(cfg, tf, indent=2)
        tmp_cfg = Path(tf.name)
    env = os.environ.copy()
    env["FC_CAD_CONVERT_CONFIG"] = str(tmp_cfg)
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
    if not output_path.is_file():
        raise RuntimeError(f"未生成输出文件: {output_path}")
    return output_path


def cad_convert_to_runs_subdir(
    input_path: Path,
    target_format: TargetFormat,
    *,
    workspace_root: Path,
    runs_root: Path,
    freecad_cmd: Path | None = None,
    timeout_s: float = 600.0,
) -> tuple[Path, str]:
    """
    写入 runs/_cad_convert/format/<task_id>/converted.<ext>。
    返回 (绝对输出路径, 浏览器可访问的 /runs/... 相对 URL 路径)。
    """
    if not path_under_workspace(input_path, workspace_root):
        raise ValueError("input_path 必须位于工作区内")
    suffix = _out_suffix_for(target_format)
    task_id = uuid.uuid4().hex
    out_dir = runs_root / "_cad_convert" / "format" / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"converted{suffix}"
    run_freecad_cad_convert(
        input_path,
        out_path,
        freecad_cmd=freecad_cmd,
        timeout_s=timeout_s,
    )
    rel = out_path.resolve().relative_to(runs_root.resolve())
    url_path = "/runs/" + rel.as_posix()
    return out_path, url_path


__all__ = [
    "cad_convert_to_runs_subdir",
    "path_under_workspace",
    "resolve_workspace_path",
    "run_freecad_cad_convert",
    "runner_script",
]
