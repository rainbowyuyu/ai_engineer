"""LangChain / LangGraph LLM foundation layer."""

from backend.llm.config import LLMProviderSettings, get_llm_settings
from backend.llm.feature_flags import FeatureFlags, get_feature_flags
from backend.llm.models import get_chat_model, langchain_available, langgraph_available
from backend.llm.routing import (
    use_langchain_client,
    use_langgraph_assistant,
    use_langgraph_oc4_agent,
    use_langgraph_pipeline,
    use_langgraph_structured,
)

__all__ = [
    "LLMProviderSettings",
    "get_llm_settings",
    "FeatureFlags",
    "get_feature_flags",
    "get_chat_model",
    "langchain_available",
    "langgraph_available",
    "use_langchain_client",
    "use_langgraph_assistant",
    "use_langgraph_oc4_agent",
    "use_langgraph_pipeline",
    "use_langgraph_structured",
]
