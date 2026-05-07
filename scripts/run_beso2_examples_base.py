#!/usr/bin/env python3
"""
不使用大模型，本地运行 examples/base/BESO2-FEMMeshGmsh.inp 的 BESO 拓扑优化，
所有中间与结果文件写入 examples/base/beso_output/（与 Web 任务 runs/ 分离）。

用法（项目根目录）：
  .\\.venv\\Scripts\\python scripts\\run_beso2_examples_base.py

可选环境变量：
  BESO_ITERATIONS_LIMIT        正整数时写入 beso_conf 限制迭代；不设则按 BESO 自动 iterations_limit 跑满（大网格可能极久）。
  BESO_MIN_VTK_BYTES_PER_ITER  父进程 meshio 预览前要求 fileNNN.vtk 最小字节数（默认 400000），避免读到未写完的 VTK。
  CCX_PATH                     CalculiX 可执行文件路径。

说明：BESO2-FEMMeshGmsh.inp 末尾为 wiki Analysis-1 式多组 *Boundary（bolt1_moor_faces…bolt6…）+ 塔顶 *CLOAD，并带 FreeCAD ** GroupID 节点组。
减少单元数请用 scripts/regen_beso2_base_mesh.py --char-max … 重生成体网格。主 INP 无 *STEP 时才拼接 BESO2_calculix_append.inp（空补片）。
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# 不使用大模型：避免误用环境中的 Key
for _k in ("QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL"):
    os.environ.pop(_k, None)

INP = REPO / "examples" / "base" / "BESO2-FEMMeshGmsh.inp"
APPEND = REPO / "examples" / "base" / "BESO2_calculix_append.inp"
OUT = REPO / "examples" / "base" / "beso_output"


def _mesh_only_inp(p: Path) -> bool:
    """主 INP 若不含 *STEP，则 CalculiX 无法出应力，BESO 会报 results not found。"""
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 3_000_000))
            tail = f.read().decode("utf-8", errors="ignore")
        return "*STEP" not in tail.upper()
    except OSError:
        return True


def main() -> int:
    if not INP.is_file():
        print(f"[FAIL] 找不到: {INP}")
        return 2
    if not APPEND.is_file():
        print(f"[FAIL] 找不到分析补片: {APPEND}")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    lim = (os.environ.get("BESO_ITERATIONS_LIMIT") or "").strip()
    if lim.isdigit() and int(lim) > 0:
        print(f"[INFO] BESO_ITERATIONS_LIMIT={lim}（限制迭代；正式跑请取消该环境变量）")
    else:
        print("[INFO] 未设置 BESO_ITERATIONS_LIMIT，将按 BESO 自动 iterations_limit 跑完全部迭代（耗时可很长）。")

    from backend.tools.beso import run_beso_job

    cancel = threading.Event()

    def on_log(line: str) -> None:
        print(line, flush=True)

    def on_vtk(rel: str) -> None:
        print(f"[VTK] {rel}", flush=True)

    inp_run = INP.resolve()
    if _mesh_only_inp(INP):
        stage = REPO / "runs" / "_beso2_merge_stage"
        stage.mkdir(parents=True, exist_ok=True)
        merged = stage / "BESO2_merged_for_beso.inp"
        merged.write_bytes(INP.read_bytes() + b"\n" + APPEND.read_bytes())
        inp_run = merged.resolve()
        print(f"[INFO] 主 INP 无 *STEP，已拼接 {APPEND.name} 到暂存文件再运行：{merged}")

    try:
        run_beso_job(
            workspace_root=REPO,
            run_dir=OUT.resolve(),
            inp_path=str(inp_run),
            mass_goal_ratio=0.4,
            filter_radius=2.0,
            optimization_base="failure_index",
            save_every=10,
            cancel_flag=cancel,
            on_log=on_log,
            on_vtk=on_vtk,
            on_artifact=None,
        )
    except KeyboardInterrupt:
        cancel.set()
        print("[INFO] 用户中断")
        return 130
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1
    print(f"[OK] 完成。结果目录: {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
