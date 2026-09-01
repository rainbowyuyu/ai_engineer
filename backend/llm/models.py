from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from backend.llm.config import get_llm_settings

logger = logging.getLogger(__name__)

_LANGCHAIN_IMPORT_ERROR: str | None = None

try:
    from langchain_openai import ChatOpenAI

    _LANGCHAIN_OK = True
except ImportError as exc:
    ChatOpenAI = None  # type: ignore[misc, assignment]
    _LANGCHAIN_OK = False
    _LANGCHAIN_IMPORT_ERROR = str(exc)


def langchain_available() -> bool:
    return _LANGCHAIN_OK


def langchain_import_error() -> str | None:
    return _LANGCHAIN_IMPORT_ERROR


_LANGGRAPH_IMPORT_ERROR: str | None = None

try:
    import langgraph  # noqa: F401

    _LANGGRAPH_OK = True
except ImportError as exc:
    _LANGGRAPH_OK = False
    _LANGGRAPH_IMPORT_ERROR = str(exc)


def langgraph_available() -> bool:
    return _LANGGRAPH_OK


def langgraph_import_error() -> str | None:
    return _LANGGRAPH_IMPORT_ERROR


@lru_cache(maxsize=8)
def get_chat_model(
    *,
    model: str | None = None,
    temperature: float = 0.2,
    read_timeout_s: float | None = None,
) -> Any:
    if not _LANGCHAIN_OK:
        raise RuntimeError(
            "LangChain 未安装。请执行: pip install -r backend/requirements.txt"
            + (f" ({_LANGCHAIN_IMPORT_ERROR})" if _LANGCHAIN_IMPORT_ERROR else "")
        )
    settings = get_llm_settings()
    if not settings.api_key:
        raise RuntimeError("QWEN_API_KEY / LLM_API_KEY 未设置")
    timeout = read_timeout_s if read_timeout_s is not None else settings.read_timeout_s
    kwargs: dict[str, Any] = {
        "model": model or settings.model,
        "api_key": settings.api_key,
        "base_url": settings.base_url.rstrip("/"),
        "temperature": temperature,
        "timeout": timeout,
        "max_retries": 2,
    }
    if settings.langsmith_api_key:
        import os

        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        if settings.langsmith_project:
            os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    return ChatOpenAI(**kwargs)


def messages_to_langchain(messages: list[dict[str, Any]]) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    out = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        content = m.get("content") or ""
        if role == "system":
            out.append(SystemMessage(content=str(content)))
        elif role == "assistant":
            out.append(AIMessage(content=str(content)))
        else:
            out.append(HumanMessage(content=str(content)))
    return out


def langchain_to_openai_response(ai_msg: Any) -> dict[str, Any]:
    content = getattr(ai_msg, "content", "") or ""
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "model": get_llm_settings().model,
    }
