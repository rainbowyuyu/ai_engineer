from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class FeatureFlags:
    use_langchain_client: bool
    use_langgraph_assistant: bool
    use_langgraph_oc4_agent: bool
    use_langgraph_structured: bool
    use_langgraph_pipeline: bool
    allow_legacy_llm: bool


@lru_cache(maxsize=1)
def get_feature_flags() -> FeatureFlags:
    """Feature flags for LangGraph rollout (default all on).

    Set ``USE_LEGACY_LLM=true`` only when you intentionally need the old JSON
    tool loops / raw SSE paths. Prefer ``backend.llm.routing`` helpers in callers.
    """
    default_on = _env_bool("USE_LANGGRAPH_DEFAULT", True)
    return FeatureFlags(
        use_langchain_client=_env_bool("USE_LANGCHAIN_CLIENT", default_on),
        use_langgraph_assistant=_env_bool("USE_LANGGRAPH_ASSISTANT", default_on),
        use_langgraph_oc4_agent=_env_bool("USE_LANGGRAPH_OC4_AGENT", default_on),
        use_langgraph_structured=_env_bool("USE_LANGGRAPH_STRUCTURED", default_on),
        use_langgraph_pipeline=_env_bool("USE_LANGGRAPH_PIPELINE", default_on),
        allow_legacy_llm=_env_bool("USE_LEGACY_LLM", False),
    )


def clear_feature_flags_cache() -> None:
    get_feature_flags.cache_clear()
