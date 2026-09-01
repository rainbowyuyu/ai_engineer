from __future__ import annotations

import asyncio
import functools
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, Iterable, Sequence, TypeVar

from backend.llm.config import get_llm_settings

T = TypeVar("T")

_llm_semaphore: asyncio.Semaphore | None = None
_agent_semaphore: asyncio.Semaphore | None = None
_tool_executor: ThreadPoolExecutor | None = None
_rate_lock = asyncio.Lock()
_rate_timestamps: list[float] = []


def reset_concurrency_state() -> None:
    """Test helper: drop cached semaphores / pools so env changes apply."""
    global _llm_semaphore, _agent_semaphore, _tool_executor, _rate_timestamps
    _llm_semaphore = None
    _agent_semaphore = None
    if _tool_executor is not None:
        _tool_executor.shutdown(wait=False, cancel_futures=True)
        _tool_executor = None
    _rate_timestamps = []


def get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(get_llm_settings().max_concurrent)
    return _llm_semaphore


def get_agent_semaphore() -> asyncio.Semaphore:
    """Caps parallel agent / subgraph fan-out (distinct from per-call LLM slots)."""
    global _agent_semaphore
    if _agent_semaphore is None:
        _agent_semaphore = asyncio.Semaphore(get_llm_settings().agent_max_concurrent)
    return _agent_semaphore


def get_tool_executor() -> ThreadPoolExecutor:
    global _tool_executor
    if _tool_executor is None:
        _tool_executor = ThreadPoolExecutor(
            max_workers=get_llm_settings().tool_pool_workers,
            thread_name_prefix="llm-tool",
        )
    return _tool_executor


async def acquire_rate_limit() -> None:
    rpm = get_llm_settings().requests_per_minute
    if rpm <= 0:
        return
    async with _rate_lock:
        now = time.monotonic()
        window_start = now - 60.0
        while _rate_timestamps and _rate_timestamps[0] < window_start:
            _rate_timestamps.pop(0)
        if len(_rate_timestamps) >= rpm:
            wait_s = 60.0 - (now - _rate_timestamps[0])
            if wait_s > 0:
                await asyncio.sleep(wait_s)
        _rate_timestamps.append(time.monotonic())


async def run_sync_tool(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        get_tool_executor(),
        functools.partial(fn, *args, **kwargs),
    )


async def with_llm_slot(coro_factory: Callable[[], Any]) -> Any:
    await acquire_rate_limit()
    async with get_llm_semaphore():
        return await coro_factory()


async def with_agent_slot(coro_factory: Callable[[], Any]) -> Any:
    async with get_agent_semaphore():
        return await coro_factory()


async def gather_limited(
    factories: Sequence[Callable[[], Awaitable[T]]],
    *,
    limit: int | None = None,
    return_exceptions: bool = False,
) -> list[T | BaseException]:
    """Run coroutine factories with a shared concurrency cap (agent pool)."""
    if not factories:
        return []
    cap = max(1, int(limit if limit is not None else get_llm_settings().agent_max_concurrent))
    sem = asyncio.Semaphore(cap)

    async def _one(factory: Callable[[], Awaitable[T]]) -> T:
        async with sem:
            return await factory()

    return list(await asyncio.gather(*(_one(f) for f in factories), return_exceptions=return_exceptions))


async def map_agent_jobs(
    items: Iterable[Any],
    worker: Callable[[Any], Awaitable[T]],
    *,
    limit: int | None = None,
    return_exceptions: bool = False,
) -> list[T | BaseException]:
    bag = list(items)
    return await gather_limited(
        [lambda x=item: worker(x) for item in bag],
        limit=limit,
        return_exceptions=return_exceptions,
    )
