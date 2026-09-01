from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from backend.qwen_runtime_config import get_qwen_config


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class LLMProviderSettings:
    api_key: str | None
    base_url: str
    model: str
    connect_timeout_s: float
    read_timeout_s: float
    assistant_read_timeout_s: float
    max_concurrent: int
    agent_max_concurrent: int
    requests_per_minute: int
    tool_pool_workers: int
    langsmith_api_key: str | None
    langsmith_project: str | None


@lru_cache(maxsize=1)
def get_llm_settings() -> LLMProviderSettings:
    runtime = get_qwen_config()
    read_raw = (
        os.environ.get("LLM_HTTP_READ_TIMEOUT_S", "").strip()
        or os.environ.get("QWEN_HTTP_READ_TIMEOUT_S", "").strip()
        or os.environ.get("QWEN_HTTP_TIMEOUT_S", "").strip()
    )
    read_s = 480.0
    if read_raw:
        try:
            read_s = max(120.0, float(read_raw))
        except ValueError:
            pass
    connect_s = max(10.0, _env_float("LLM_HTTP_CONNECT_TIMEOUT_S", _env_float("QWEN_HTTP_CONNECT_TIMEOUT_S", 45.0)))
    assistant_read = _env_float("QWEN_ASSISTANT_CHAT_READ_TIMEOUT_S", 900.0)
    assistant_read = max(120.0, assistant_read)
    return LLMProviderSettings(
        api_key=runtime.api_key or os.environ.get("QWEN_API_KEY") or os.environ.get("LLM_API_KEY"),
        base_url=(
            runtime.base_url
            or os.environ.get("LLM_BASE_URL")
            or os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        ),
        model=runtime.model or os.environ.get("LLM_MODEL") or os.environ.get("QWEN_MODEL", "qwen-plus"),
        connect_timeout_s=connect_s,
        read_timeout_s=read_s,
        assistant_read_timeout_s=assistant_read,
        max_concurrent=max(1, _env_int("LLM_MAX_CONCURRENT", 8)),
        agent_max_concurrent=max(1, _env_int("AGENT_MAX_CONCURRENT", _env_int("LLM_AGENT_MAX_CONCURRENT", 4))),
        requests_per_minute=max(0, _env_int("LLM_REQUESTS_PER_MIN", 0)),
        tool_pool_workers=max(1, _env_int("LLM_TOOL_POOL_WORKERS", 4)),
        langsmith_api_key=os.environ.get("LANGSMITH_API_KEY") or None,
        langsmith_project=os.environ.get("LANGSMITH_PROJECT") or None,
    )
