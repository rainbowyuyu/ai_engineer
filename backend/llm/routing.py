"""Central routing: prefer LangGraph/LangChain; legacy only with USE_LEGACY_LLM=true."""
from __future__ import annotations

import os

from backend.llm.feature_flags import get_feature_flags
from backend.llm.models import langchain_available, langgraph_available


def _legacy_escape() -> bool:
    """Explicit opt-in to old JSON tool loops / raw HTTP streams."""
    raw = (os.environ.get("USE_LEGACY_LLM") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def use_langchain_client() -> bool:
    if _legacy_escape():
        return False
    if not langchain_available():
        return False
    return get_feature_flags().use_langchain_client


def use_langgraph_assistant() -> bool:
    if _legacy_escape():
        return False
    if not langgraph_available():
        return False
    return get_feature_flags().use_langgraph_assistant


def use_langgraph_oc4_agent() -> bool:
    if _legacy_escape():
        return False
    if not langgraph_available():
        return False
    return get_feature_flags().use_langgraph_oc4_agent


def use_langgraph_structured() -> bool:
    if _legacy_escape():
        return False
    if not langchain_available():
        return False
    return get_feature_flags().use_langgraph_structured


def use_langgraph_pipeline() -> bool:
    if _legacy_escape():
        return False
    if not langgraph_available():
        return False
    return get_feature_flags().use_langgraph_pipeline


def require_new_stack_or_raise(capability: str) -> None:
    """Raise if capability requested but packages missing (no silent fallback)."""
    if capability in ("assistant", "oc4", "pipeline") and not langgraph_available():
        from backend.llm.models import langgraph_import_error

        raise RuntimeError(
            "LangGraph 未安装，无法走新框架。"
            "请执行: pip install -r backend/requirements.txt"
            + (f" ({langgraph_import_error()})" if langgraph_import_error() else "")
        )
    if capability in ("client", "structured") and not langchain_available():
        from backend.llm.models import langchain_import_error

        raise RuntimeError(
            "LangChain 未安装，无法走新框架。"
            "请执行: pip install -r backend/requirements.txt"
            + (f" ({langchain_import_error()})" if langchain_import_error() else "")
        )
