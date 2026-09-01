from __future__ import annotations

import json
from typing import Any, AsyncIterator


async def map_astream_events_to_assistant_ndjson(
    event_stream: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[str]:
    """
    Map LangGraph/LangChain astream_events v2 to legacy assistant NDJSON:
    thought / tool / final_reply / token (optional).
    """
    async for ev in event_stream:
        kind = ev.get("event") or ""
        data = ev.get("data") or {}
        name = ev.get("name") or ""

        if kind == "on_chat_model_stream":
            chunk = data.get("chunk")
            text = ""
            if chunk is not None:
                text = getattr(chunk, "content", None) or ""
            if text:
                yield json.dumps({"type": "token", "content": text}, ensure_ascii=False) + "\n"
            continue

        if kind == "on_chain_end" and name in ("agent", "llm", "AssistantGraph"):
            output = data.get("output") or {}
            if isinstance(output, dict):
                if output.get("final_reply"):
                    yield json.dumps(
                        {"type": "final_reply", "content": output["final_reply"]},
                        ensure_ascii=False,
                    ) + "\n"
                elif output.get("thought"):
                    yield json.dumps(
                        {"type": "thought", "content": output["thought"]},
                        ensure_ascii=False,
                    ) + "\n"
                tool = output.get("tool")
                if tool:
                    yield json.dumps({"type": "tool", "tool": tool}, ensure_ascii=False) + "\n"
            continue

        if kind == "on_tool_start":
            yield json.dumps(
                {
                    "type": "tool_start",
                    "name": ev.get("name") or name,
                    "input": data.get("input"),
                },
                ensure_ascii=False,
            ) + "\n"
            continue

        if kind == "on_tool_end":
            yield json.dumps(
                {
                    "type": "tool_end",
                    "name": ev.get("name") or name,
                    "output": data.get("output"),
                },
                ensure_ascii=False,
            ) + "\n"
            continue


def sse_line_from_token(token: str) -> str:
    payload = json.dumps({"choices": [{"delta": {"content": token}}]}, ensure_ascii=False)
    return f"data: {payload}\n\n"
