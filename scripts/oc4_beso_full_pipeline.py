#!/usr/bin/env python3
"""
OC4 全流程（几何 → 体网格 → example_3 式双域 INP → beso_conf）：

1. 从 ``examples/oc4/oc4.igs``（或 ``--src``）用 ``build_oc4_design_domain_iges`` 生成实心设计域 CAD（IGES/STEP）；
2. 体网格：优先 ``--mesh-inp``（已含 C3D4/C3D8/C3D10 的 INP）；若未指定则尝试对 ``01_design_domain.step`` 调用 ``run_gmsh_iges_to_inp``（部分几何仅得壳网格时会失败，此时请用 FreeCAD 等生成体网格后再传入 ``--mesh-inp``）；
3. 按与挖孔一致的柱轴线，将体单元划入 ``design_space`` / ``nondesign_space``（后者 ``domain_optimized=False``），
   并追加**最小** ``*STEP``（底面 z 固定 + 顶区单点竖向力），结构与 wiki ``Analysis-1.inp`` 的双 ``*SOLID SECTION`` 一致；
4. 在工作目录生成 ``beso_conf.py``（双域，仿 ``beso/wiki_files/example_3/.../beso_conf.py``）。

说明：最小 *STEP 仅用于算例冒烟；与 ``BESO2-FEMMeshGmsh.inp`` 的系泊/塔顶节点组**不共用**（新网格节点号不同）。
若需真实海工边界，请在 ``03_for_beso.inp`` 上按几何重新建 ``*NSET`` 并替换 *STEP 段。

用法（仓库根）::

    python scripts/oc4_beso_full_pipeline.py
    python scripts/oc4_beso_full_pipeline.py --mesh-inp path/to/body_C3D4.inp
    python scripts/oc4_beso_full_pipeline.py --out-dir examples/oc4_beso_pipeline --char-max 90000
    python scripts/oc4_beso_full_pipeline.py --run-beso --beso-iter 3
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    ap = argparse.ArgumentParser(description="OC4：设计域 CAD → 体网格 → design/nondesign → beso_conf")
    ap.add_argument("--src", type=Path, default=REPO / "examples/oc4/oc4.igs", help="源 OC4 IGS")
    ap.add_argument("--out-dir", type=Path, default=REPO / "examples/oc4_beso_pipeline", help="输出目录")
    ap.add_argument(
        "--mesh-inp",
        type=Path,
        default=None,
        help="已有体网格 INP（C3D4/C3D8/C3D10）；若省略则尝试 Gmsh 对设计域 STEP 再 Merge 网格",
    )
    ap.add_argument(
        "--char-max",
        type=float,
        default=18000.0,
        help="仅用于自动 Gmsh 网格步：Mesh.CharacteristicLengthMax（过大易退化为壳/R3D）",
    )
    ap.add_argument("--band-scale", type=float, default=1.22, help="柱走廊径向倍数（相对柱半径）")
    ap.add_argument("--edge-columns-only", action="store_true", help="传给设计域生成：仅挖三根边柱")
    ap.add_argument("--ccx", type=Path, default=Path(os.environ.get("CCX_PATH") or r"D:\freecad\bin\ccx.exe"))
    ap.add_argument("--run-beso", action="store_true", help="在 out-dir 下跑少量 BESO 迭代（需 ccx）")
    ap.add_argument("--beso-iter", type=int, default=3, help="--run-beso 时 iterations_limit")
    ap.add_argument(
        "--save-every",
        type=int,
        default=1,
        help="beso_conf.save_iteration_results：每 N 轮保存中间 OBJ/INP；1=每轮最密",
    )
    args = ap.parse_args()

    src = args.src.resolve()
    out_dir = args.out_dir.resolve()
    if not src.is_file():
        print(f"[ERR] 找不到源 IGS: {src}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    design_iges = out_dir / "01_design_domain.igs"
    design_step = out_dir / "01_design_domain.step"
    mesh_inp = out_dir / "02_mesh_body.inp"
    final_inp = out_dir / "03_for_beso.inp"
    conf_py = out_dir / "beso_conf.py"

    print("[1/4] 生成设计域 CAD …")
    from backend.tools.oc4_design_domain_iges import build_oc4_design_domain_iges

    build_oc4_design_domain_iges(
        src,
        design_iges,
        out_step=design_step,
        cut_center_column=not args.edge_columns_only,
        include_source_geometry=False,
    )
    print(f"      -> {design_iges.name}, {design_step.name}")

    print("[2/4] 准备体网格 INP …")
    if args.mesh_inp is not None:
        mi = args.mesh_inp.resolve()
        if not mi.is_file():
            print(f"[ERR] --mesh-inp 不存在: {mi}", file=sys.stderr)
            return 2
        if mi != mesh_inp.resolve():
            shutil.copy2(mi, mesh_inp)
    else:
        from backend.tools.gmsh_iges_to_inp import run_gmsh_iges_to_inp

        try:
            run_gmsh_iges_to_inp(design_step, mesh_inp, char_length_max=float(args.char_max))
        except Exception as ex:
            print(
                "[ERR] 自动 Gmsh 体网格失败（设计域 STEP 常仅得壳元）。\n"
                "      请用 FreeCAD 等对 01_design_domain.step 生成体网格 INP，再运行：\n"
                f"      python scripts/oc4_beso_full_pipeline.py --mesh-inp <你的C3D4.inp> ...\n"
                f"      详情: {ex}",
                file=sys.stderr,
            )
            return 3

    raw = mesh_inp.read_text(encoding="utf-8", errors="ignore")
    if "C3D4" not in raw.upper() and "C3D10" not in raw.upper() and "C3D8" not in raw.upper():
        raise RuntimeError(
            "体网格 INP 中未找到 C3D4/C3D8/C3D10；Gmsh 可能只生成了壳/刚性片元。"
            " 请减小 --char-max（例如 8000～20000）后重试。"
        )
    print(f"      -> {mesh_inp.name} ({mesh_inp.stat().st_size} B)")

    print("[3/4] 划分 design_space / nondesign_space 并写最小 *STEP …")
    from backend.tools.inp_oc4_design_nondesign import partition_oc4_mesh_inp, write_beso_conf_example3_style

    stats = partition_oc4_mesh_inp(
        mesh_inp,
        src,
        final_inp,
        band_scale=float(args.band_scale),
    )
    print(f"      design={stats['n_design']}, nondesign={stats['n_nondesign']}, fixed_z_nodes={stats['n_fixed_nodes']}, cload_node={stats['load_node']}")

    print("[4/4] 写 beso_conf.py …")
    from backend.tools.inp_mesh_scan import beso_simple_filter_radius_min_for_connectivity

    fr_char = max(500.0, float(args.char_max) * 0.012)
    fr_floor = beso_simple_filter_radius_min_for_connectivity(final_inp)
    fr_use = max(fr_char, fr_floor)
    if fr_use > fr_char:
        print(f"      [INFO] simple 滤波半径 {fr_char:g} -> {fr_use:g}（保证优化域邻接，避免 prepare2s 除零）")
    se = max(1, int(args.save_every))
    write_beso_conf_example3_style(
        conf_py,
        work_dir=out_dir,
        ccx_path=args.ccx.resolve(),
        inp_name=final_inp.name,
        mass_goal_ratio=0.25,
        filter_radius=fr_use,
        optimization_base="failure_index",
        iterations_limit=int(args.beso_iter) if args.run_beso else 8,
        save_iteration_results=se,
    )
    print(f"      -> {conf_py.name}")

    beso_rt = REPO / "beso"
    for fn in ("beso_main.py", "beso_lib.py", "beso_filters.py", "beso_separate.py", "beso_plots.py"):
        shutil.copy2(beso_rt / fn, out_dir / fn)
    print(f"      -> 已复制 BESO 运行脚本到 {out_dir}（可在此目录执行 python beso_main.py {final_inp.name}）")

    if args.run_beso:
        os.environ["BESO_ITERATIONS_LIMIT"] = str(int(args.beso_iter))
        beso_out = out_dir / "beso_run"
        beso_out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(final_inp, beso_out / final_inp.name)
        write_beso_conf_example3_style(
            beso_out / "beso_conf.py",
            work_dir=beso_out,
            ccx_path=args.ccx.resolve(),
            inp_name=final_inp.name,
            mass_goal_ratio=0.25,
            filter_radius=fr_use,
            optimization_base="failure_index",
            iterations_limit=int(args.beso_iter),
            save_iteration_results=se,
        )
        from backend.tools.beso import run_beso_job

        cancel = threading.Event()

        def on_log(line: str) -> None:
            print(line, flush=True)

        def on_vtk(rel: str) -> None:
            print(f"[VTK] {rel}", flush=True)

        print(f"[BESO] 工作目录 {beso_out} …")
        run_beso_job(
            workspace_root=REPO,
            run_dir=beso_out,
            inp_path=str((beso_out / final_inp.name).resolve()),
            mass_goal_ratio=0.25,
            filter_radius=fr_use,
            optimization_base="failure_index",
            save_every=se,
            cancel_flag=cancel,
            on_log=on_log,
            on_vtk=on_vtk,
            on_artifact=None,
        )
        print(f"[OK] BESO 输出在: {beso_out}")

    print(f"[OK] 全流程产物目录: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
