"""Tests for LangChain/LangGraph foundation and feature flags."""
from __future__ import annotations

import os

import pytest


def test_feature_flags_default_on(monkeypatch):
    monkeypatch.delenv("USE_LANGGRAPH_ASSISTANT", raising=False)
    monkeypatch.delenv("USE_LANGGRAPH_DEFAULT", raising=False)
    from backend.llm.feature_flags import clear_feature_flags_cache, get_feature_flags

    clear_feature_flags_cache()
    flags = get_feature_flags()
    assert flags.use_langgraph_assistant is True
    assert flags.use_langchain_client is True


def test_feature_flags_can_disable(monkeypatch):
    monkeypatch.setenv("USE_LANGGRAPH_ASSISTANT", "false")
    from backend.llm.feature_flags import clear_feature_flags_cache, get_feature_flags

    clear_feature_flags_cache()
    flags = get_feature_flags()
    assert flags.use_langgraph_assistant is False


def test_llm_settings_inherit_qwen_env(monkeypatch):
    monkeypatch.setenv("QWEN_MODEL", "qwen-test")
    monkeypatch.setenv("LLM_MAX_CONCURRENT", "3")
    from backend.llm.config import get_llm_settings

    get_llm_settings.cache_clear()
    s = get_llm_settings()
    assert s.model == "qwen-test"
    assert s.max_concurrent == 3


def test_langchain_available_or_skip():
    from backend.llm.models import langchain_available

    if not langchain_available():
        pytest.skip("langchain not installed in this environment")


def test_messages_to_langchain_roundtrip():
    from backend.llm.models import langchain_available, messages_to_langchain

    if not langchain_available():
        pytest.skip("langchain not installed")
    msgs = messages_to_langchain(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
    )
    assert len(msgs) == 2
    assert msgs[0].content == "sys"
    assert msgs[1].content == "hi"
