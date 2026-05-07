#!/usr/bin/env python3
"""
OC4 载荷 INP 分区防错逻辑自检（不跑 Gmsh/IGES，仅校验解析与写出前校验函数）。
用法：在项目根执行  python scripts/verify_inp_oc4_partition_checks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 仓库根
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.tools.inp_oc4_design_nondesign import (  # noqa: E402
    _inject_missing_material_blocks_for_solid_refs,
    _reorder_pre_step_materials_before_solids,
    _validate_oc4_partition_output,
    _sanitize_ccx_material_name,
    _canon_material_name,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    # 1) 写出前校验：材料与固体截面一致
    ok_lines = [
        "*NODE",
        "1, 0, 0, 0",
        "2, 1, 0, 0",
        "3, 0, 1, 0",
        "4, 0, 0, 1",
        "*ELEMENT, TYPE=C3D4, ELSET=E1",
        "1, 1, 2, 3, 4",
        "*MATERIAL, NAME=SteelMat",
        "*ELASTIC",
        "210000, 0.3",
        "*SOLID SECTION, ELSET=E1, MATERIAL=SteelMat",
        "*STEP",
        "*STATIC",
        "1,1,1e-5,1",
        "*END STEP",
    ]
    w = _validate_oc4_partition_output(ok_lines)
    _assert(isinstance(w, list), "warnings 应为 list")

    # 1b) *SOLIDSECTION 在 *MATERIAL 之前 → 重排后材料应位于固体截面之前（CalculiX 顺序要求）
    messy = [
        "*NODE",
        "1, 0, 0, 0",
        "2, 1, 0, 0",
        "3, 0, 1, 0",
        "4, 0, 0, 1",
        "*ELEMENT, TYPE=C3D4, ELSET=E1",
        "1, 1, 2, 3, 4",
        "*SOLIDSECTION, ELSET=E1, MATERIAL=SteelMat",
        "*MATERIAL, NAME=SteelMat",
        "*ELASTIC",
        "210000, 0.3",
        "*STEP",
        "*STATIC",
        "1,1,1e-5,1",
        "*END STEP",
    ]

    def _first_idx(rows: list[str], pred) -> int:
        for i, ln in enumerate(rows):
            if pred(ln):
                return i
        raise SystemExit("FAIL: 未找到匹配行")

    _assert(
        _first_idx(messy, lambda ln: "SOLIDSECTION" in ln.upper())
        < _first_idx(messy, lambda ln: ln.strip().upper().startswith("*MATERIAL")),
        "messy 用例应为固体截面在材料之前",
    )
    fixed = _reorder_pre_step_materials_before_solids(messy)
    imat = _first_idx(fixed, lambda ln: ln.strip().upper().startswith("*MATERIAL"))
    isol = _first_idx(fixed, lambda ln: "SOLID" in ln.upper() and ln.strip().startswith("*"))
    _assert(imat < isol, "重排后 *MATERIAL 应在 *SOLID 之前")
    _validate_oc4_partition_output(fixed)

    # 1c) 仅有 *Solid section 无 *MATERIAL（runs/.../03_for_beso 旧版故障）→ 注入后应通过校验
    orphan = [
        "*NODE",
        "1, 0, 0, 0",
        "*ELEMENT, TYPE=C3D4, ELSET=E1",
        "1, 1, 2, 3, 4",
        "*Solid section, Elset=E1, Material=MSteel",
        "*STEP",
        "*STATIC",
        "1,1,1e-5,1",
        "*END STEP",
    ]
    fixed_o = _inject_missing_material_blocks_for_solid_refs(orphan)
    _assert(len(fixed_o) > len(orphan), "应插入材料块")
    _validate_oc4_partition_output(fixed_o)

    bad_lines = list(ok_lines)
    _si = next(i for i, ln in enumerate(bad_lines) if "*SOLID" in ln.upper())
    bad_lines[_si] = "*SOLID SECTION, ELSET=E1, MATERIAL=Ghost"
    try:
        _validate_oc4_partition_output(bad_lines)
    except ValueError as e:
        _assert("Ghost" in str(e) or "材料" in str(e), f"期望材料校验失败，得到: {e}")
    else:
        raise SystemExit("FAIL: 应抛出 ValueError（未知材料）")

    # 2) 材料名校正：无法匹配时回退 defined[0]
    _assert(_canon_material_name(["MSteel"], "wrong") == "MSteel", "canon 应回退到 defined[0]")

    # 3) 清洗非法字符
    _assert(_sanitize_ccx_material_name("  OK-1.x  ") == "OK-1.x", "sanitize ASCII")
    _assert(_sanitize_ccx_material_name("@@@") == "MSteel", "sanitize 全非法应回退")

    print("OK: verify_inp_oc4_partition_checks passed")


if __name__ == "__main__":
    main()
