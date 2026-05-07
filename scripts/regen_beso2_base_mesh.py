#!/usr/bin/env python3
"""
用 Gmsh 从 OC4 设计域几何重新生成体网格，以 **更大的 Mesh.CharacteristicLengthMax** 减少单元数。

默认几何：examples/oc4/oc4_design_domain.igs（若无则尝试 .step）。
默认输出：examples/base/BESO2-FEMMeshGmsh_coarse.inp（不覆盖巨型细网格，避免误删）。

用法（仓库根目录，需 pip install gmsh meshio 或系统 gmsh）：
  python scripts/regen_beso2_base_mesh.py --char-max 12000
  python scripts/regen_beso2_base_mesh.py --char-max 8000 --out examples/base/BESO2-FEMMeshGmsh.inp

粗化后需在新生成的 INP 上重新指定与几何一致的 *NSET 与 *STEP（节点编号会变化）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _pick_cad() -> Path:
    oc4 = REPO / "examples" / "oc4"
    for name in ("oc4_design_domain.igs", "oc4_design_domain.iges", "oc4_design_domain.step", "oc4_design_domain.stp"):
        p = oc4 / name
        if p.is_file():
            return p
    raise FileNotFoundError(f"未找到设计域几何于 {oc4}（igs/iges/step）")


def main() -> int:
    ap = argparse.ArgumentParser(description="Gmsh 粗网格 → BESO 用 INP")
    ap.add_argument(
        "--char-max",
        type=float,
        default=10000.0,
        help="Gmsh Mesh.CharacteristicLengthMax（越大网格越稀，单位与几何一致，OC4 模型为 mm 量级）",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "examples" / "base" / "BESO2-FEMMeshGmsh_coarse.inp",
        help="输出 INP 路径",
    )
    ap.add_argument("--cad", type=Path, default=None, help="覆盖默认 CAD 路径")
    args = ap.parse_args()

    cad = args.cad.resolve() if args.cad else _pick_cad()
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    from backend.tools.gmsh_iges_to_inp import run_gmsh_iges_to_inp

    run_gmsh_iges_to_inp(cad, out, char_length_max=float(args.char_max))
    print(f"[OK] {cad.name} → {out} (char_max={args.char_max})")
    print("[INFO] 粗网格节点号与细网格不同；请在后处理中重新绑定系泊/塔顶 *NSET 与 *STEP。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
