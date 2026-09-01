"""Routing helpers prefer new LangGraph stack."""
from __future__ import annotations


def test_routing_helpers_default_on(monkeypatch):
    monkeypatch.delenv("USE_LEGACY_LLM", raising=False)
    monkeypatch.delenv("USE_LANGGRAPH_DEFAULT", raising=False)
    from backend.llm.feature_flags import clear_feature_flags_cache
    from backend.llm.routing import use_langgraph_assistant, use_langgraph_structured

    clear_feature_flags_cache()
    # When packages installed, helpers should be True
    from backend.llm.models import langgraph_available, langchain_available

    if langgraph_available():
        assert use_langgraph_assistant() is True
    if langchain_available():
        assert use_langgraph_structured() is True


def test_legacy_escape_disables_new_stack(monkeypatch):
    monkeypatch.setenv("USE_LEGACY_LLM", "true")
    from backend.llm.feature_flags import clear_feature_flags_cache
    from backend.llm.routing import (
        use_langchain_client,
        use_langgraph_assistant,
        use_langgraph_oc4_agent,
        use_langgraph_pipeline,
        use_langgraph_structured,
    )

    clear_feature_flags_cache()
    assert use_langchain_client() is False
    assert use_langgraph_assistant() is False
    assert use_langgraph_oc4_agent() is False
    assert use_langgraph_structured() is False
    assert use_langgraph_pipeline() is False
