#!/usr/bin/env python3
"""
对 ``examples/oc4/oc4.igs`` 用方式 A（``run_freecad_iges_to_inp.py`` + FreeCAD Gmsh）
按多组参数依次生成体网格 INP，适合对比稀疏/粗细与阶次。

说明：此前若所有 INP 字节数完全一致，通常是因为 ``CharacteristicLength*`` 对
``App::PropertyLength`` 直接赋 ``float`` 未生效，Gmsh 一直用「无上限」尺寸；
已在 ``freecad_iges_to_inp_runner.py`` 中改为带单位的字符串赋值，并可用
``--mesh-size-from-curvature 0`` 减弱曲率加密、突出 ``--char-max`` 差异。

默认输出目录：``examples/oc4_freecad_sparse_mesh``（可用 ``--out-dir`` 覆盖）。

示例::

    python scripts/batch_oc4_freecad_mesh_variants.py
    python scripts/batch_oc4_freecad_mesh_variants.py --out-dir D:/tmp/oc4_meshes --max-runs 3
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RUN_SCRIPT = REPO / "scripts" / "run_freecad_iges_to_inp.py"
DEFAULT_CAD = REPO / "examples" / "oc4" / "oc4.igs"
DEFAULT_OUT_DIR = REPO / "examples" / "oc4_freecad_sparse_mesh"


@dataclass(frozen=True)
class Variant:
    """单条变体：生成文件名 ``oc4_{slug}.inp``，并附加这些 CLI 参数（在 --cad/--out 之后）。"""

    slug: str
    extra_args: tuple[str, ...]


# 跨多个 char_max 梯度；过大尺寸在本模型上会被几何离散「封顶」，彼此可能相同，故从中等往下拉开差距。
SPARSE_VARIANTS: tuple[Variant, ...] = (
    Variant("a01_xlarge_curv0", ("--preset", "xlarge", "--mesh-size-from-curvature", "0")),
    Variant("a02_char18k_curv0", ("--char-max", "18000", "--char-min", "0.1", "--mesh-size-from-curvature", "0")),
    Variant("a03_char12k_curv0", ("--char-max", "12000", "--char-min", "0.1", "--mesh-size-from-curvature", "0")),
    Variant("a04_char8k_curv0", ("--char-max", "8000", "--char-min", "0.08", "--mesh-size-from-curvature", "0")),
    Variant("a05_char5k_curv0", ("--char-max", "5000", "--char-min", "0.06", "--mesh-size-from-curvature", "0")),
    Variant("a06_char3200_curv0", ("--char-max", "3200", "--char-min", "0.04", "--mesh-size-from-curvature", "0")),
    Variant("a07_char2200_curv0", ("--char-max", "2200", "--char-min", "0.02", "--mesh-size-from-curvature", "0")),
    Variant("a08_fine_default_curv", ("--preset", "fine")),
    Variant("a09_medium_curv24", ("--preset", "medium", "--mesh-size-from-curvature", "24")),
    Variant("a10_medium_curv0", ("--preset", "medium", "--mesh-size-from-curvature", "0")),
    Variant("a11_auto_char_curv0", ("--auto-char", "--mesh-size-from-curvature", "0")),
    Variant("a12_coarse_no_opt_curv0", ("--preset", "coarse", "--no-optimize-std", "--mesh-size-from-curvature", "0")),
)


def main() -> int:
    ap = argparse.ArgumentParser(description="OC4.igs 方式 A 多参数批量网格 INP")
    ap.add_argument("--cad", type=Path, default=DEFAULT_CAD, help="输入 IGES/STEP")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="输出目录")
    ap.add_argument("--max-runs", type=int, default=0, help="仅跑前 N 条（0 表示全部）")
    ap.add_argument(
        "--no-check-beso",
        action="store_true",
        help="传给 run_freecad_iges_to_inp：跳过 BESO 单元类型校验（批量时若个别失败可开）",
    )
    ap.add_argument("--freecad-cmd", type=Path, default=None, help="可选：FreeCADCmd.exe")
    args = ap.parse_args()

    cad = args.cad.resolve()
    out_dir = args.out_dir.resolve()
    if not cad.is_file():
        print(f"[ERR] CAD 不存在: {cad}", file=sys.stderr)
        return 2
    if not RUN_SCRIPT.is_file():
        print(f"[ERR] 未找到: {RUN_SCRIPT}", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    variants = list(SPARSE_VARIANTS)
    if args.max_runs and args.max_runs > 0:
        variants = variants[: int(args.max_runs)]

    manifest: list[dict] = []
    started = datetime.now(timezone.utc).isoformat()

    for i, v in enumerate(variants, start=1):
        out_inp = out_dir / f"oc4_{v.slug}.inp"
        cmd: list[str] = [
            sys.executable,
            str(RUN_SCRIPT),
            "--cad",
            str(cad),
            "--out",
            str(out_inp),
            *v.extra_args,
        ]
        if args.no_check_beso:
            cmd.append("--no-check-beso")
        if args.freecad_cmd is not None:
            cmd.extend(["--freecad-cmd", str(args.freecad_cmd.resolve())])

        print(f"\n[{i}/{len(variants)}] {v.slug}\n  -> {out_inp.name}")
        print("  ", " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(REPO))
        rec = {
            "slug": v.slug,
            "extra_args": list(v.extra_args),
            "out_inp": str(out_inp),
            "exit_code": r.returncode,
            "bytes": out_inp.stat().st_size if out_inp.is_file() else None,
        }
        manifest.append(rec)
        if r.returncode != 0:
            print(f"[WARN] 退出码 {r.returncode}，继续下一条…", file=sys.stderr)

    meta = {
        "cad": str(cad),
        "out_dir": str(out_dir),
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "runner": str(RUN_SCRIPT),
        "note": (
            "若多个「很粗」变体字节数相同，多为几何/离散极限导致；"
            "缩小 characteristic_length_max 或调整 mesh_size_from_curvature 才会明显分叉。"
        ),
        "variants": [{"slug": v.slug, "extra_args": list(v.extra_args)} for v in variants],
        "runs": manifest,
    }
    (out_dir / "batch_manifest.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[OK] 清单已写: {out_dir / 'batch_manifest.json'}")
    failed = sum(1 for m in manifest if m["exit_code"] != 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
