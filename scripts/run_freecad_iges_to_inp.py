#!/usr/bin/env python3
"""
方式 A：用 FreeCADCmd + Gmsh（FEM 工作台）将 IGES/STEP 转为 INP。

- 网格密度等通过 CLI 或 JSON 配置；支持 ``--preset`` 与 ``--hint``（自然语言关键词）微调。
- 大模型建议：``--preset xlarge`` 或 ``--hint 粗``，并适当增大 ``--char-max``。

示例（仓库根目录）::

    python scripts/run_freecad_iges_to_inp.py --cad examples/oc4/oc4_design_domain.igs --out out/mesh.inp
    python scripts/run_freecad_iges_to_inp.py --cad model.igs --out mesh.inp --preset xlarge --hint 更粗
    python scripts/run_freecad_iges_to_inp.py --cad model.igs --out mesh.inp --config my_mesh.fcigesmesh

手写配置时使用 JSON 内容、扩展名 ``.fcigesmesh``；勿用 ``.json``（FreeCADCmd 会把 ``*.json`` 当作 FEM 网格导入）。

环境变量 ``FREECAD_CMD`` 可指向 ``FreeCADCmd.exe``（默认尝试 ``D:\\freecad\\bin\\freecadcmd.exe``）。
若同目录存在 ``python.exe``，启动器会**优先用它**执行 runner（与仅装 FreeCAD 的方式 A 一致；部分版本下
``FreeCADCmd.exe`` 不会执行脚本的 ``main``）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = Path(__file__).resolve().parent / "freecad_iges_to_inp_runner.py"


def _suggest_char_max_from_file_size(cad: Path) -> float:
    """与 ``backend.tools.freecad_iges_to_inp.suggest_char_length_max`` 一致，大 IGES 默认可剖分。"""
    from backend.tools.freecad_iges_to_inp import suggest_char_length_max

    return float(suggest_char_length_max(cad))


_PRESETS: dict[str, dict[str, float | str]] = {
    "fine": {
        "characteristic_length_max": 3000.0,
        "characteristic_length_min": 0.05,
        "element_order": "1st",
    },
    "medium": {
        "characteristic_length_max": 12000.0,
        "characteristic_length_min": 0.1,
        "element_order": "1st",
    },
    "coarse": {
        "characteristic_length_max": 40000.0,
        "characteristic_length_min": 1.0,
        "element_order": "1st",
    },
    "xlarge": {
        "characteristic_length_max": 80000.0,
        "characteristic_length_min": 5.0,
        "element_order": "1st",
    },
}


def _resolve_freecad_cmd(explicit: Path | None) -> Path:
    if explicit is not None:
        p = explicit.resolve()
        if not p.is_file():
            raise FileNotFoundError(f"FREECAD_CMD / --freecad-cmd 无效: {p}")
        return p
    env = (os.environ.get("FREECAD_CMD") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"环境变量 FREECAD_CMD 指向的文件不存在: {env}")
    for name in ("FreeCADCmd.exe", "freecadcmd.exe"):
        w = shutil.which(name)
        if w:
            return Path(w).resolve()
    guess = Path(r"D:\freecad\bin\freecadcmd.exe")
    if guess.is_file():
        return guess.resolve()
    raise FileNotFoundError(
        "未找到 FreeCADCmd.exe：请设置环境变量 FREECAD_CMD，或使用 --freecad-cmd 指定完整路径。"
    )


def _mesh_python_exe(freecad_cmd: Path) -> Path:
    """同目录 ``python.exe`` 存在则用之跑 FEM 脚本；否则退回 ``freecadcmd``。"""
    py = freecad_cmd.parent / "python.exe"
    if py.is_file():
        return py.resolve()
    return freecad_cmd.resolve()


def _norm_hint(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def apply_natural_language_hints(
    cfg: dict,
    hints: list[str],
) -> dict:
    """根据中英文关键词调整配置（在 preset/CLI 数值之后叠加）。"""
    out = dict(cfg)
    char_max = float(out.get("characteristic_length_max", 12000.0))
    char_min = float(out.get("characteristic_length_min", 0.0))
    order = str(out.get("element_order", "1st"))

    blob = _norm_hint(" ".join(hints))
    if not blob:
        out["characteristic_length_max"] = char_max
        out["characteristic_length_min"] = char_min
        out["element_order"] = order
        return out

    # 密度 / 尺寸（支持简短提示词如「粗」「细」「稀」）
    if blob in {"粗", "稀", "疏"} or any(
        k in blob for k in ("更粗", "粗一点", "稀疏", "coarser", "sparse", "粗网格")
    ):
        char_max *= 1.65
        char_min = max(char_min, char_min * 1.2) if char_min > 0 else char_min
    if blob in {"细", "密"} or any(
        k in blob for k in ("更细", "细一点", "加密", "finer", "dense", "细网格")
    ):
        char_max /= 1.65
        char_min = max(1e-6, char_min * 0.85) if char_min > 0 else char_min
    if any(k in blob for k in ("大模型", "很大", "超大", "xlarge", "large model", "百万单元")):
        char_max = max(char_max, float(_PRESETS["xlarge"]["characteristic_length_max"]))
        char_min = max(char_min, float(_PRESETS["xlarge"]["characteristic_length_min"]))

    # 单元阶次
    if any(k in blob for k in ("二阶", "2阶", "second", "2nd order", " quadratic")):
        order = "2nd"
    if any(k in blob for k in ("一阶", "1阶", "first", "linear", "1st order")):
        order = "1st"

    out["characteristic_length_max"] = char_max
    out["characteristic_length_min"] = char_min
    out["element_order"] = order
    return out


def build_config(args: argparse.Namespace) -> dict:
    if args.config_path:
        p = Path(args.config_path).resolve()
        if not p.is_file():
            raise SystemExit(f"配置文件不存在: {p}")
        cfg = json.loads(p.read_text(encoding="utf-8"))
        if "cad_path" not in cfg:
            if not args.cad:
                raise SystemExit("JSON 缺少 cad_path 且未提供 --cad")
            cfg["cad_path"] = str(Path(args.cad).resolve())
        if "out_inp" not in cfg:
            if not args.out:
                raise SystemExit("JSON 缺少 out_inp 且未提供 --out")
            cfg["out_inp"] = str(Path(args.out).resolve())
        hints: list[str] = list(args.hint or [])
        cfg = apply_natural_language_hints(cfg, hints)
        if getattr(args, "mesh_size_from_curvature", None) is not None:
            cfg["mesh_size_from_curvature"] = int(args.mesh_size_from_curvature)
        return cfg

    cad = Path(args.cad).resolve()
    base: dict = {
        "cad_path": str(cad),
        "out_inp": str(Path(args.out).resolve()),
        "compound_part_strategy": args.part_strategy,
        "element_dimension": args.element_dimension,
        "geometry_tolerance": float(args.geometry_tolerance),
        "optimize_std": bool(args.optimize_std),
        "length_unit": str(args.length_unit),
    }

    if args.preset:
        preset = _PRESETS.get(args.preset)
        if not preset:
            raise SystemExit(f"未知 preset: {args.preset!r}，可选: {', '.join(sorted(_PRESETS))}")
        base.update(preset)

    if args.auto_char:
        base["characteristic_length_max"] = _suggest_char_max_from_file_size(cad)
    if args.char_max is not None:
        base["characteristic_length_max"] = float(args.char_max)
    if args.char_min is not None:
        base["characteristic_length_min"] = float(args.char_min)
    if args.element_order:
        base["element_order"] = args.element_order

    base.setdefault("characteristic_length_min", 0.0)
    base.setdefault("element_order", "1st")
    if "characteristic_length_max" not in base:
        base["characteristic_length_max"] = _suggest_char_max_from_file_size(cad) if args.auto_char else 12000.0

    hints: list[str] = list(args.hint or [])
    base = apply_natural_language_hints(base, hints)
    if getattr(args, "mesh_size_from_curvature", None) is not None:
        base["mesh_size_from_curvature"] = int(args.mesh_size_from_curvature)
    return base


def main() -> int:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    ap = argparse.ArgumentParser(
        description="调用 FreeCADCmd + Gmsh 将 IGES/STEP 转为 INP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
preset 说明（单位与 CAD 一致，常见为 mm）:
  fine     — 较细，单元多
  medium   — 默认量级
  coarse   — 粗网格，利于试算
  xlarge   — 大几何/解析优先，单元少

--hint 可多次给出，支持与 preset/数值叠加，例如:
  --hint "更粗" --hint "大模型"
  --hint "二阶加密"   (会偏向 2nd 且略减小尺寸)
        """.strip(),
    )
    ap.add_argument("--cad", type=Path, help="输入 .igs/.iges/.stp/.step")
    ap.add_argument("--out", type=Path, help="输出 .inp 路径")
    ap.add_argument(
        "--config",
        dest="config_path",
        type=Path,
        default=None,
        metavar="PATH",
        help="直接使用 JSON 配置文件（建议扩展名 .fcigesmesh；勿用 .json，FreeCADCmd 会误导入）",
    )
    ap.add_argument("--freecad-cmd", type=Path, default=None, help="FreeCADCmd.exe 路径")
    ap.add_argument("--preset", choices=sorted(_PRESETS), default=None, help="网格密度预设")
    ap.add_argument(
        "--hint",
        action="append",
        default=[],
        metavar="TEXT",
        help="自然语言提示（可多次），如「更粗」「大模型」「二阶」",
    )
    ap.add_argument("--auto-char", action="store_true", help="按 CAD 文件大小自动估计 char_max（可与 preset 叠加后被覆盖）")
    ap.add_argument("--char-max", type=float, default=None, help="Gmsh CharacteristicLengthMax（覆盖 preset）")
    ap.add_argument("--char-min", type=float, default=None, help="Gmsh CharacteristicLengthMin")
    ap.add_argument("--element-order", choices=("1st", "2nd"), default=None, help="单元阶次")
    ap.add_argument(
        "--element-dimension",
        default="From Shape",
        help="From Shape | 3D | 2D | 1D（默认 From Shape）",
    )
    ap.add_argument("--geometry-tolerance", type=float, default=0.0, help="0 表示使用 Gmsh 默认")
    ap.add_argument(
        "--length-unit",
        default="mm",
        help="CharacteristicLength* 写入 FreeCAD 时使用的单位（默认 mm，与 OC4 等模型一致）",
    )
    ap.add_argument(
        "--mesh-size-from-curvature",
        type=int,
        default=None,
        metavar="N",
        help="Gmsh Mesh.MeshSizeFromCurvature（0=关闭曲率加密，仅全局尺寸主导；不传则保持 FreeCAD 默认）",
    )
    ap.add_argument("--optimize-std", action=argparse.BooleanOptionalAction, default=True, help="Gmsh 标准优化")
    ap.add_argument(
        "--part-strategy",
        default="largest_volume",
        choices=("largest_volume", "first"),
        help="多实体时选择用于剖分的 Part 对象",
    )
    ap.add_argument("--check-beso", action=argparse.BooleanOptionalAction, default=True, help="用仓库规则校验 INP 单元类型")
    args = ap.parse_args()

    if args.config_path:
        if not Path(args.config_path).is_file():
            ap.error(f"--config 文件不存在: {args.config_path}")
    elif not args.cad or not args.out:
        ap.error("请提供 --cad 与 --out，或使用 --config 配置文件")

    cfg = build_config(args)
    fc = _resolve_freecad_cmd(args.freecad_cmd)
    mesh_exe = _mesh_python_exe(fc)
    if not RUNNER.is_file():
        raise FileNotFoundError(f"未找到 runner: {RUNNER}")

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".fcigesmesh",
        delete=False,
        encoding="utf-8",
    ) as tf:
        json.dump(cfg, tf, indent=2)
        tmp_cfg = Path(tf.name)

    # 勿把配置路径放在 argv：FreeCADCmd 会对额外参数尝试「打开文档」，未知扩展名会报错。
    env = os.environ.copy()
    env["FC_IGES_MESH_CONFIG"] = str(tmp_cfg)
    try:
        cmd = [str(mesh_exe), str(RUNNER)]
        print("[INFO] FC_IGES_MESH_CONFIG=", tmp_cfg)
        print("[INFO] mesh executor:", mesh_exe.name, "|", " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(REPO), env=env)
        if r.returncode != 0:
            return int(r.returncode or 1)
    finally:
        tmp_cfg.unlink(missing_ok=True)

    out_inp = Path(cfg["out_inp"])
    if not out_inp.is_file():
        print(f"[ERR] 未生成输出文件: {out_inp}", file=sys.stderr)
        return 1

    if args.check_beso:
        try:
            from backend.tools.inp_beso_compat import assert_inp_supported_by_beso

            assert_inp_supported_by_beso(out_inp)
            print("[OK] BESO 单元类型校验通过")
        except Exception as e:
            print(f"[WARN] BESO 校验未通过或跳过: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
