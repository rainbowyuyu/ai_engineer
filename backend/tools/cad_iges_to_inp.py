"""
IGES/STEP → BESO 主 INP 的统一入口。

仅使用 **FreeCAD FEM + Gmsh**（``backend.tools.freecad_iges_to_inp``，对应
``scripts/freecad_iges_to_inp_runner.py``）。环境变量 ``FREECAD_CMD`` 可指向 ``FreeCADCmd.exe``。

为兼容旧调用签名，以下参数会被忽略：``gmsh_bin``、``linear_deflection``、``angular_deflection``。
"""
from __future__ import annotations

import threading
from pathlib import Path

from backend.tools.freecad_iges_to_inp import (
    OUTPUT_INP_NAME,
    default_coarse_char_length_max,
    list_iges_in_dir,
    run_freecad_cad_to_inp,
    suggest_char_length_max,
)


def run_cad_iges_to_inp(
    iges_path: Path,
    dest_inp: Path,
    *,
    char_length_max: float | None = None,
    timeout_s: float | None = None,
    gmsh_bin: str | None = None,
    linear_deflection: float | None = None,
    angular_deflection: float | None = None,
    char_length_min: float | None = None,
    element_order: str | None = None,
    mesh_size_from_curvature: int | None = None,
    compound_part_strategy: str | None = None,
    element_dimension: str | None = None,
    geometry_tolerance: float | None = None,
    optimize_std: bool | None = None,
    length_unit: str | None = None,
    freecad_cmd: Path | None = None,
    cancel_event: threading.Event | None = None,
    proc_box: list | None = None,
) -> Path:
    _ = (gmsh_bin, linear_deflection, angular_deflection)
    kw: dict = {
        "char_length_max": char_length_max,
        "timeout_s": timeout_s,
        "cancel_event": cancel_event,
        "proc_box": proc_box,
    }
    if char_length_min is not None:
        kw["char_length_min"] = float(char_length_min)
    if element_order is not None:
        kw["element_order"] = str(element_order)
    if mesh_size_from_curvature is not None:
        kw["mesh_size_from_curvature"] = int(mesh_size_from_curvature)
    if compound_part_strategy is not None:
        kw["compound_part_strategy"] = str(compound_part_strategy)
    if element_dimension is not None:
        kw["element_dimension"] = str(element_dimension)
    if geometry_tolerance is not None:
        kw["geometry_tolerance"] = float(geometry_tolerance)
    if optimize_std is not None:
        kw["optimize_std"] = bool(optimize_std)
    if length_unit is not None:
        kw["length_unit"] = str(length_unit)
    if freecad_cmd is not None:
        kw["freecad_cmd"] = freecad_cmd
    return run_freecad_cad_to_inp(iges_path, dest_inp, **kw)


__all__ = [
    "OUTPUT_INP_NAME",
    "default_coarse_char_length_max",
    "list_iges_in_dir",
    "run_cad_iges_to_inp",
    "run_freecad_cad_to_inp",
    "suggest_char_length_max",
]
