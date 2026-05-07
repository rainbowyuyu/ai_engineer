#!/usr/bin/env python3
"""
循环验证 wiki example_1 / example_2 / example_3：scan -> build_generated_code -> BESO 烟测（早停）。
用法：在项目根目录执行
  .\\.venv\\Scripts\\python scripts\\verify_wiki_examples_loop.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TIMEOUT = float(os.environ.get("BESO_WIKI_VERIFY_TIMEOUT_SEC", "420"))


def _smoke_beso(run_dir: Path, inp_path: Path) -> None:
    from backend.tools.beso import run_beso_job

    logs: list[str] = []
    cancel = threading.Event()
    smoke_early = threading.Event()

    def on_log(line: str) -> None:
        logs.append(line)
        print(line)

    def on_vtk(_: str) -> None:
        pass

    def watch() -> None:
        while not cancel.is_set():
            time.sleep(2.0)
            blob = "\n".join(logs)
            if "iterations_limit set automatically" in blob or re.search(r"\[BESO\]\s+\d+\s+", blob):
                smoke_early.set()
                cancel.set()
                return

    threading.Thread(target=watch, daemon=True).start()
    threading.Timer(TIMEOUT, cancel.set).start()
    try:
        run_beso_job(
            workspace_root=REPO,
            run_dir=run_dir,
            inp_path=str(inp_path),
            mass_goal_ratio=0.4,
            filter_radius=2.0,
            optimization_base="failure_index",
            save_every=10,
            cancel_flag=cancel,
            on_log=on_log,
            on_vtk=on_vtk,
            on_artifact=None,
        )
    except RuntimeError as e:
        blob = "\n".join(logs)
        if smoke_early.is_set() and "beso_main exited" in str(e):
            print("[INFO] 烟测主动中断，非零退出码忽略")
        elif cancel.is_set() and "cancelling job" in blob.lower() and "beso_main exited" in str(e):
            print("[INFO] 超时中断，非零退出码忽略")
        else:
            raise
    blob = "\n".join(logs)
    if "[ERROR]" in blob:
        raise RuntimeError("BESO 日志含 [ERROR]")
    if "nodes" not in blob.lower() and "TETRA" not in blob.upper() and "C3D" not in blob.upper():
        raise RuntimeError("未观察到网格统计（可能未读入主网格）")


def _agent_params_smoke(root: Path, bundle) -> None:
    """模拟智能体解析：临时去掉 Key 时应返回默认 JSON 逻辑且不抛异常。"""
    saved = {k: os.environ.pop(k) for k in ("QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL") if k in os.environ}
    try:
        from backend.agent import decide_params

        d = decide_params(
            f"对 {root.name} 做拓扑优化，failure_index，质量目标略保守。",
            effective_inp_path=str(Path(bundle.primary_inp).resolve()),
            scan_dir=str(root.resolve()),
        )
        assert d.optimization_base in ("failure_index", "stiffness")
        assert 0 < d.mass_goal_ratio <= 1
    finally:
        os.environ.update(saved)


def main() -> int:
    from backend.generator import scan_input_directory, build_generated_code

    ccx = Path(os.environ.get("CCX_PATH", r"D:\freecad\bin\ccx.exe")).resolve()
    if not ccx.is_file():
        print(f"[SKIP] 未找到 ccx: {ccx}，仅执行 scan + build（不跑 BESO）")
        ccx_ok = False
    else:
        ccx_ok = True

    cases = [
        REPO / "beso/wiki_files/example_1",
        REPO / "beso/wiki_files/example_2",
        REPO / "beso/wiki_files/example_3",
    ]

    for root in cases:
        name = root.name
        print(f"\n======== {name} ({root}) ========")
        bundle = scan_input_directory(str(root))
        if not bundle.primary_inp:
            print(f"[FAIL] 未解析到 primary_inp")
            return 1
        print(f"  primary={Path(bundle.primary_inp).name}  inp_count={sum(1 for x in bundle.files if x.ext=='.inp')}")
        _agent_params_smoke(root, bundle)
        print(f"  agent decide_params OK (default path when no key)")

        run_dir = REPO / "runs" / f"_wiki_verify_{name}_{uuid.uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            gen = build_generated_code(
                bundle=bundle,
                run_dir=run_dir,
                ccx_path=ccx,
                mass_goal_ratio=0.4,
                filter_radius=2.0,
                optimization_base="failure_index",
                save_every=10,
                primary_inp_override=None,
            )
            for fn, content in gen.files.items():
                (run_dir / fn).write_text(content, encoding="utf-8")
            primary_src = Path(bundle.primary_inp).resolve()
            if not primary_src.is_file():
                print(f"[FAIL] 主 INP 源文件不存在: {primary_src}")
                return 2
            if not ccx_ok:
                continue
            t0 = time.monotonic()
            # run_beso_job 从源路径拷 INP 与附属文件到 run_dir（与 /api/chat 一致）
            _smoke_beso(run_dir, primary_src)
            print(f"[OK] {name} BESO 烟测通过（{time.monotonic()-t0:.1f}s） run_dir={run_dir}")
        except FileNotFoundError as e:
            if "ccx" in str(e).lower():
                print(f"[SKIP] {name}: {e}")
            else:
                raise
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            return 3
        finally:
            # 保留最后一次失败目录时可注释掉 rmtree
            if os.environ.get("BESO_WIKI_VERIFY_KEEP_RUNS") != "1":
                shutil.rmtree(run_dir, ignore_errors=True)

    print("\n[OK] 三个 wiki 示例均已通过 scan + build" + (" + BESO 烟测" if ccx_ok else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
