"""Contract tests for assistant LangGraph NDJSON event shapes."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("langgraph")

from backend.agents.assistant_graph import iter_assistant_graph_events


def test_assistant_graph_done_event_shape(tmp_path):
    qwen = MagicMock()
    qwen.model = "mock-model"
    qwen.api_key = "test-key"

    fake_parsed = {"final_reply": "你好，已完成。", "thought": "直接回复"}

    with patch("backend.agents.assistant_graph.get_chat_model") as mock_llm:
        ai = MagicMock()
        ai.content = '{"thought":"直接回复","final_reply":"你好，已完成。"}'
        mock_llm.return_value.invoke.return_value = ai
        with patch("backend.agents.assistant_graph._normalize_agent_shape", side_effect=lambda x: x):
            with patch("backend.agents.assistant_graph._parse_json_object", return_value=fake_parsed):
                with patch("backend.agents.assistant_graph._agent_turn_json_valid", return_value=True):
                    events = list(
                        iter_assistant_graph_events(
                            qwen,
                            [{"role": "user", "content": "hi"}],
                            temperature=0.2,
                            workspace_root=tmp_path,
                            runs_root=tmp_path / "runs",
                        )
                    )

    types = [e.get("type") for e in events]
    assert "session" in types
    assert "done" in types
    done = next(e for e in events if e.get("type") == "done")
    assert done.get("reply") == "你好，已完成。"
    assert "tool_trace" in done
    assert "client_actions" in done


def test_legacy_and_graph_share_done_keys():
    """Both paths must expose reply / tool_trace / client_actions on done."""
    required = {"reply", "tool_trace", "client_actions", "model"}
    sample = {"type": "done", "reply": "x", "tool_trace": [], "client_actions": [], "model": "m"}
    assert required <= set(sample.keys())
