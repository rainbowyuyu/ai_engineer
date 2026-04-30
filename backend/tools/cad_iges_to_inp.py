"""
IGES → BESO 主 INP 的统一入口。

默认 **auto**：优先 **Open CASCADE** 曲面三角化（快，输出 S3 壳网格），失败或未安装 ``cadquery-ocp`` 时回退 **Gmsh**。

环境变量 ``CAD_IGES_BACKEND``：

- ``occ``：仅用 OCC（失败则抛错，不回退 Gmsh）。
- ``gmsh``：仅用 Gmsh（与旧行为一致）。
- ``auto`` 或未设置：OCC 优先，失败再 Gmsh。
"""
from __future__ import annotations

import os
from pathlib import Path

from backend.tools.gmsh_iges_to_inp import OUTPUT_INP_NAME, list_iges_in_dir, run_gmsh_iges_to_inp, suggest_char_length_max
from backend.tools.iges_occ_tess_to_inp import occ_sdk_available, run_occ_iges_to_inp


def cad_iges_backend() -> str:
    v = (os.environ.get("CAD_IGES_BACKEND") or "auto").strip().lower()
    if v in {"occ", "gmsh", "auto"}:
        return v
    return "auto"


def run_cad_iges_to_inp(
    iges_path: Path,
    dest_inp: Path,
    *,
    char_length_max: float | None = None,
    timeout_s: float | None = None,
    gmsh_bin: str | None = None,
    linear_deflection: float | None = None,
    angular_deflection: float | None = None,
) -> Path:
    mode = cad_iges_backend()
    kwargs_gmsh = {"char_length_max": char_length_max, "timeout_s": timeout_s, "gmsh_bin": gmsh_bin}
    kwargs_occ = {
        "char_length_max": char_length_max,
        "linear_deflection": linear_deflection,
        "angular_deflection": angular_deflection,
        "timeout_s": timeout_s,
        "gmsh_bin": gmsh_bin,
    }

    if mode == "gmsh":
        return run_gmsh_iges_to_inp(iges_path, dest_inp, **kwargs_gmsh)
    if mode == "occ":
        return run_occ_iges_to_inp(iges_path, dest_inp, **kwargs_occ)

    # auto
    if occ_sdk_available():
        try:
            return run_occ_iges_to_inp(iges_path, dest_inp, **kwargs_occ)
        except Exception as occ_err:
            try:
                return run_gmsh_iges_to_inp(iges_path, dest_inp, **kwargs_gmsh)
            except Exception as gmsh_err:
                raise RuntimeError(
                    "IGES→INP：Open CASCADE 与 Gmsh 均未成功。\n"
                    f"  OCC: {occ_err}\n"
                    f"  Gmsh: {gmsh_err}"
                ) from gmsh_err
    return run_gmsh_iges_to_inp(iges_path, dest_inp, **kwargs_gmsh)


__all__ = [
    "OUTPUT_INP_NAME",
    "cad_iges_backend",
    "list_iges_in_dir",
    "run_cad_iges_to_inp",
    "run_gmsh_iges_to_inp",
    "run_occ_iges_to_inp",
    "suggest_char_length_max",
    "occ_sdk_available",
]
