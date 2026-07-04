#!/usr/bin/env python3
"""
用钢量计算 CLI — 输入 parameters_summary.json / optimized_geometry.json，输出 JSON 报告。

示例:
  python scripts/compute_steel_mass.py examples/beso/beso7/addition/method1_parametric/parameters_summary.json
  python scripts/compute_steel_mass.py parameters_summary.json -o steel_report.json --target-mw 20
  python scripts/compute_steel_mass.py parameters_summary.json --no-optimize --scale 1.0
  python scripts/compute_steel_mass.py parameters_summary.json --merge-geometry -o enriched_geometry.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.tools.mixed_platform_steel import (  # noqa: E402
    attach_steel_to_geometry,
    compute_steel_report,
    default_params_from_geometry,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="混合平台用钢量计算（restruction4 模型）")
    parser.add_argument("input_json", type=Path, help="几何 JSON（如 parameters_summary.json）")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="输出 JSON 路径（默认：<输入名>_steel_report.json）",
    )
    parser.add_argument("--target-mw", type=float, default=None, help="目标单机容量 MW（默认 20）")
    parser.add_argument("--draft", type=float, default=None, help="吃水 m（默认 20）")
    parser.add_argument("--wall", type=float, default=None, help="结构壁厚 m（默认 0.06）")
    parser.add_argument("--base-mw", type=float, default=None, help="基准功率 MW（默认 5）")
    parser.add_argument("--no-optimize", action="store_true", help="仅按 s0 缩放，不做 x 优化")
    parser.add_argument("--scale", type=float, default=None, help="指定水平缩放因子（跳过优化）")
    parser.add_argument(
        "--merge-geometry",
        action="store_true",
        help="同时输出带 validation_overrides.steel_mass_t 的几何 JSON",
    )
    parser.add_argument("--stdout", action="store_true", help="仅打印到 stdout，不写文件")
    args = parser.parse_args()

    inp = args.input_json.resolve()
    if not inp.is_file():
        print(f"文件不存在: {inp}", file=sys.stderr)
        return 1

    geometry = json.loads(inp.read_text(encoding="utf-8"))
    params = default_params_from_geometry(geometry)
    if args.draft is not None:
        params["draft"] = args.draft
    if args.wall is not None:
        params["wall_thickness"] = args.wall
        params["top_plate_wall_thickness"] = args.wall
    if args.base_mw is not None:
        params["rated_power_MW"] = args.base_mw

    report = compute_steel_report(
        geometry,
        target_power_mw=args.target_mw,
        params=params,
        optimize=not args.no_optimize,
        scale_factor=args.scale,
    )
    report["input_file"] = str(inp)
    report["input_title"] = geometry.get("title")

    payload: dict = report
    if args.merge_geometry:
        payload = {
            "steel_report": report,
            "geometry_with_steel": attach_steel_to_geometry(geometry, report),
        }

    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.stdout:
        print(text)
        return 0

    out = args.output
    if out is None:
        suffix = "_steel_enriched.json" if args.merge_geometry else "_steel_report.json"
        out = inp.with_name(inp.stem + suffix)
    out.write_text(text, encoding="utf-8")
    print(f"已写入: {out}")
    steel = report.get("steel_summary") or report.get("steel_report", {}).get("steel_summary")
    if steel:
        print(
            f"  结构钢量: {steel['struct_mass_t']:.1f} t | "
            f"钢耗: {steel['steel_intensity_t_per_MW']:.1f} t/MW | "
            f"静倾角: {steel['pitch_angle_deg']:.2f}°"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
