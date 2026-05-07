"""
Gmsh 在 initialize 时会注册信号处理；Uvicorn/Starlette 的同步路由跑在线程池里时会触发
``signal only works in main thread``。通过 spawn 子进程在子解释器主线程里执行 Gmsh 相关调用规避。
"""
from __future__ import annotations

import atexit
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_ctx = mp.get_context("spawn")
_pool: ProcessPoolExecutor | None = None


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=1, mp_context=_ctx)

        def _shutdown() -> None:
            global _pool
            ex, _pool = _pool, None
            if ex is not None:
                ex.shutdown(wait=True, cancel_futures=False)

        atexit.register(_shutdown)
    return _pool


def run_in_spawn_process(fn: Callable[..., T], /, *args: Any, timeout_s: float = 3600.0) -> T:
    """在单进程池（spawn）中执行 ``fn(*args)``，适用于 Gmsh/OCC 等依赖主线程信号的库。"""
    fut = _get_pool().submit(fn, *args)
    return fut.result(timeout=timeout_s)
