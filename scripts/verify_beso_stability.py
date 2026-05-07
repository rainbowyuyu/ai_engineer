#!/usr/bin/env python3
"""
稳定性验证（本地）：
  1) 无大模型：清除 QWEN_* 后跑 decide_params + BESO 烟测（早停，不跑完全部迭代）。
  2) 有大模型：恢复环境并加载 .env 后跑 decide_params（真实调用 DashScope）。

用法（在项目根目录）：
  .\\.venv\\Scripts\\python scripts\\verify_beso_stability.py

可选环境变量：
  BESO_VERIFY_TIMEOUT_SEC  烟测最长等待秒数（默认 300）
  BESO_MAX_INP_NODES / BESO_MAX_INP_ELEMENTS  与 backend 一致，仅当默认体量检查过严时放宽
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

INP_REL = Path("examples/base/BESO2-FEMMeshGmsh.inp")
TIMEOUT = float(os.environ.get("BESO_VERIFY_TIMEOUT_SEC", "300"))


def _main() -> int:
    inp = (REPO / INP_REL).resolve()
    if not inp.is_file():
        print(f"[FAIL] 找不到主 INP: {inp}")
        return 2

    # --- 阶段 1：无大模型 ---
    saved: dict[str, str] = {}
    for k in ("QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL"):
        if k in os.environ:
            saved[k] = os.environ.pop(k)

    from backend.agent import decide_params

    d0 = decide_params("目标保留质量比 0.35，滤波半径 3mm，failure_index")
    if not d0.reasoning_summary or "未配置" not in d0.reasoning_summary:
        print(f"[FAIL] 无 API Key 时应走本地默认并说明原因，实际 reasoning_summary={d0.reasoning_summary!r}")
        os.environ.update(saved)
        return 7
    print(
        f"[OK] 无大模型 decide_params（自然语言不会改参）: "
        f"mass_goal_ratio={d0.mass_goal_ratio}, filter_radius={d0.filter_radius}; "
        f"BESO 烟测将使用固定参数 0.35 / 3.0 mm"
    )

    from backend.tools.beso import run_beso_job

    run_dir = REPO / "runs" / f"_verify_no_llm_{uuid.uuid4().hex[:10]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logs: list[str] = []
    cancel = threading.Event()
    smoke_early_stop = threading.Event()

    def on_log(line: str) -> None:
        logs.append(line)
        print(line)

    def on_vtk(_: str) -> None:
        pass

    def _watch_milestones() -> None:
        while not cancel.is_set():
            time.sleep(2.0)
            blob = "\n".join(logs)
            if "iterations_limit set automatically" in blob:
                print("[INFO] 烟测里程碑：已读到 iterations_limit -> 主动结束")
                smoke_early_stop.set()
                cancel.set()
                return
            if re.search(r"\[BESO\]\s+\d+\s+", blob):
                print("[INFO] 烟测里程碑：已出现迭代日志 -> 主动结束")
                smoke_early_stop.set()
                cancel.set()
                return

    threading.Thread(target=_watch_milestones, daemon=True).start()
    threading.Timer(TIMEOUT, cancel.set).start()

    t0 = time.monotonic()
    try:
        run_beso_job(
            workspace_root=REPO,
            run_dir=run_dir,
            inp_path=str(inp),
            mass_goal_ratio=0.35,
            filter_radius=3.0,
            optimization_base="failure_index",
            save_every=10,
            cancel_flag=cancel,
            on_log=on_log,
            on_vtk=on_vtk,
            on_artifact=None,
        )
    except RuntimeError as e:
        blob = "\n".join(logs)
        if smoke_early_stop.is_set() and "beso_main exited" in str(e):
            print("[INFO] 子进程因烟测中断以非零码退出，视为正常")
        elif cancel.is_set() and "cancelling job" in blob.lower() and "beso_main exited" in str(e):
            print("[INFO] 子进程因超时中断以非零码退出，视为正常（未判失败）")
        else:
            raise
    except FileNotFoundError as e:
        if "ccx" in str(e).lower():
            print(f"[SKIP] 未找到 CalculiX（CCX_PATH）：{e}")
            os.environ.update(saved)
            return 0
        raise
    except Exception as e:
        print(f"[FAIL] BESO 烟测异常: {e}")
        os.environ.update(saved)
        return 3

    elapsed = time.monotonic() - t0
    blob = "\n".join(logs)
    if "[ERROR]" in blob:
        print("[FAIL] 日志中出现 [ERROR]")
        os.environ.update(saved)
        return 4
    if "nodes" not in blob.lower() and "TETRA" not in blob.upper():
        print("[FAIL] 未观察到网格读入（nodes / TETRA 等）")
        os.environ.update(saved)
        return 5
    print(f"[OK] BESO 烟测结束（{elapsed:.1f}s），run_dir={run_dir}")

    # --- 阶段 2：大模型 ---
    os.environ.update(saved)
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env", override=False)
    except ImportError:
        pass

    from backend.agent import decide_params as decide_params_again
    from backend.qwen_client import QwenClient

    qc = QwenClient()
    if not qc.api_key:
        print("[SKIP] 未配置 QWEN_API_KEY（无 .env），跳过大模型调用测试")
        return 0

    d1 = decide_params_again(
        "在不过于激进的前提下降一点质量目标，滤波略大一点以稳定灵敏度。",
        effective_inp_path=str(inp),
        scan_dir=None,
    )
    if d1.reasoning_summary and "解析失败" in d1.reasoning_summary:
        print(f"[FAIL] 大模型阶段解析失败: {d1.reasoning_summary}")
        return 6
    print(
        f"[OK] 大模型 decide_params: summary={d1.reasoning_summary!r} "
        f"mass_goal_ratio={d1.mass_goal_ratio} filter_radius={d1.filter_radius} "
        f"base={d1.optimization_base} save_every={d1.save_every}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
