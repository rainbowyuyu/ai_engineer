"""LangGraph-based assistant agent (JSON tool protocol, legacy NDJSON events)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated, Any, Iterator, TypedDict

from backend.assistant_tool_loop import (
    MAX_ASSISTANT_TOOL_TURNS,
    _artifacts_from_tool_extra,
    _run_assistant_tool,
    _sanitize,
    append_tools_system_block,
)
from backend.llm.models import get_chat_model, get_llm_settings
from backend.oc4_design_domain_agent import (
    _agent_turn_json_valid,
    _normalize_agent_shape,
    _parse_json_object,
)
from backend.qwen_client import QwenClient

logger = logging.getLogger(__name__)

_JSON_REPAIR = (
    "上一条「助手」输出无法按约定解析为单个 JSON 对象。"
    "请**只**输出一个合法 JSON（不要 Markdown 围栏），键为 thought / tool / final_reply。"
)


def _merge_events(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return left + right


class AssistantGraphState(TypedDict, total=False):
    base_messages: list[dict[str, Any]]
    history: list[dict[str, Any]]
    turn: int
    max_turns: int
    temperature: float
    model: str
    workspace_root: str
    runs_root: str
    design_checklist_id: str | None
    client_actions: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    events: Annotated[list[dict[str, Any]], _merge_events]
    final_reply: str | None
    error: str | None
    done: bool


def _llm_node(state: AssistantGraphState) -> dict[str, Any]:
    turn = int(state.get("turn") or 0) + 1
    max_turns = int(state.get("max_turns") or MAX_ASSISTANT_TOOL_TURNS)
    events: list[dict[str, Any]] = [{"type": "turn", "turn": turn, "max": max_turns}]
    ws = Path(state["workspace_root"])
    round_msgs = [*state["base_messages"], *state.get("history", [])]
    try:
        from backend.llm.models import messages_to_langchain

        llm = get_chat_model(model=state.get("model"), temperature=float(state.get("temperature") or 0.2))
        ai = llm.invoke(messages_to_langchain(round_msgs))
        content = getattr(ai, "content", "") or ""
    except Exception as e:
        err = _sanitize(str(e), ws)
        events.append({"type": "error", "message": err})
        return {
            "turn": turn,
            "events": events,
            "error": err,
            "done": True,
            "final_reply": f"模型调用失败: {err}",
        }

    data = _normalize_agent_shape(_parse_json_object(content) or {})
    if not _agent_turn_json_valid(data) and (content or "").strip():
        try:
            repair = [
                *round_msgs,
                {"role": "assistant", "content": (content or "")[:12_000]},
                {"role": "user", "content": _JSON_REPAIR},
            ]
            ai2 = llm.invoke(messages_to_langchain(repair))
            content2 = getattr(ai2, "content", "") or ""
            data = _normalize_agent_shape(_parse_json_object(content2) or {})
        except Exception:
            pass

    thought = str(data.get("thought") or "").strip()
    if thought:
        events.append({"type": "thinking", "text": thought})

    fr = data.get("final_reply")
    if isinstance(fr, str) and fr.strip():
        text = fr.strip()
        events.append({"type": "reply_start", "length": len(text)})
        chunk_size = 44
        for i in range(0, len(text), chunk_size):
            events.append({"type": "delta", "text": text[i : i + chunk_size]})
        return {
            "turn": turn,
            "events": events,
            "final_reply": text,
            "done": True,
        }

    tool = data.get("tool")
    if not isinstance(tool, dict) or not str(tool.get("name") or "").strip():
        msg = "（模型未给出有效的 tool 或 final_reply，请重试或缩短上文。）"
        events.append({"type": "reply_start", "length": len(msg)})
        events.append({"type": "delta", "text": msg})
        return {
            "turn": turn,
            "events": events,
            "final_reply": msg,
            "done": True,
        }

    tname = str(tool.get("name") or "").strip()
    targs = tool.get("arguments") if isinstance(tool.get("arguments"), dict) else {}
    events.append(
        {
            "type": "tool_start",
            "name": tname,
            "arguments_preview": json.dumps(targs, ensure_ascii=False)[:800],
        }
    )
    return {
        "turn": turn,
        "events": events,
        "_pending_tool": {"name": tname, "args": targs, "raw": data},
    }


def _tool_node(state: AssistantGraphState) -> dict[str, Any]:
    pending = state.get("_pending_tool") or {}
    tname = str(pending.get("name") or "")
    targs = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    data = pending.get("raw") if isinstance(pending.get("raw"), dict) else {}
    ws = Path(state["workspace_root"])
    runs = Path(state["runs_root"])
    client_actions = list(state.get("client_actions") or [])
    tool_trace = list(state.get("tool_trace") or [])
    events: list[dict[str, Any]] = []

    ok, summary, extra = _run_assistant_tool(
        tname,
        targs,
        workspace_root=ws,
        runs_root=runs,
        client_actions=client_actions,
        design_checklist_id=state.get("design_checklist_id"),
    )
    ex = extra if isinstance(extra, dict) else {}
    artifacts = _artifacts_from_tool_extra(ex)
    arg_snip = json.dumps(targs, ensure_ascii=False)[:800]
    tool_trace.append(
        {
            "name": tname,
            "ok": ok,
            "summary": _sanitize(summary, ws),
            "arguments_preview": arg_snip,
            "artifacts": artifacts,
        }
    )
    events.append(
        {
            "type": "tool_done",
            "name": tname,
            "ok": ok,
            "summary": _sanitize(summary, ws),
            "artifacts": artifacts,
        }
    )
    hist_tool = json.dumps(data, ensure_ascii=False)[:12_000]
    hist_res = json.dumps({"ok": ok, "summary": summary, **ex}, ensure_ascii=False)[:24_000]
    history = list(state.get("history") or [])
    history.append({"role": "assistant", "content": hist_tool})
    history.append({"role": "user", "content": f"工具结果:\n{hist_res}"})
    return {
        "events": events,
        "history": history,
        "client_actions": client_actions,
        "tool_trace": tool_trace,
        "_pending_tool": None,
    }


def _route_after_llm(state: AssistantGraphState) -> str:
    if state.get("done") or state.get("final_reply"):
        return "end"
    if state.get("_pending_tool"):
        return "tools"
    turn = int(state.get("turn") or 0)
    max_turns = int(state.get("max_turns") or MAX_ASSISTANT_TOOL_TURNS)
    if turn >= max_turns:
        return "end"
    return "end"


def _route_after_tools(state: AssistantGraphState) -> str:
    turn = int(state.get("turn") or 0)
    max_turns = int(state.get("max_turns") or MAX_ASSISTANT_TOOL_TURNS)
    if turn >= max_turns:
        return "end"
    return "llm"


def _build_assistant_graph():
    from langgraph.graph import END, StateGraph

    g = StateGraph(AssistantGraphState)
    g.add_node("llm", _llm_node)
    g.add_node("tools", _tool_node)
    g.set_entry_point("llm")
    g.add_conditional_edges("llm", _route_after_llm, {"tools": "tools", "end": END})
    g.add_conditional_edges("tools", _route_after_tools, {"llm": "llm", "end": END})
    return g.compile()


_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_assistant_graph()
    return _GRAPH


def iter_assistant_graph_events(
    qwen: QwenClient,
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    workspace_root: Path,
    runs_root: Path,
    design_checklist_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield legacy assistant NDJSON events via LangGraph state machine."""
    msgs = append_tools_system_block(messages)
    init: AssistantGraphState = {
        "base_messages": msgs,
        "history": [],
        "turn": 0,
        "max_turns": MAX_ASSISTANT_TOOL_TURNS,
        "temperature": temperature,
        "model": qwen.model or get_llm_settings().model,
        "workspace_root": str(workspace_root.resolve()),
        "runs_root": str(runs_root.resolve()),
        "design_checklist_id": design_checklist_id,
        "client_actions": [],
        "tool_trace": [],
        "events": [],
    }
    yield {"type": "session", "model": qwen.model}

    graph = _get_graph()
    final: AssistantGraphState = dict(init)
    for update in graph.stream(init, stream_mode="updates"):
        for _node, delta in update.items():
            if not isinstance(delta, dict):
                continue
            for ev in delta.get("events") or []:
                yield ev
            final.update({k: v for k, v in delta.items() if k != "events"})
            if delta.get("events"):
                final.setdefault("events", [])
                final["events"] = final["events"] + delta["events"]

    turn = int(final.get("turn") or 0)
    max_turns = int(final.get("max_turns") or MAX_ASSISTANT_TOOL_TURNS)
    reply = final.get("final_reply")
    if not reply and turn >= max_turns:
        reply = f"（超过最大工具轮数 {max_turns}，请分步说明需求。）"
        yield {"type": "reply_start", "length": len(reply)}
        yield {"type": "delta", "text": reply}
    elif not reply:
        reply = final.get("error") or "（助手未产生回复。）"

    yield {
        "type": "done",
        "reply": reply,
        "client_actions": final.get("client_actions") or [],
        "tool_trace": final.get("tool_trace") or [],
        "model": qwen.model,
    }


def run_assistant_graph(
    qwen: QwenClient,
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    workspace_root: Path,
    runs_root: Path,
    design_checklist_id: str | None = None,
) -> dict[str, Any]:
    reply = ""
    client_actions: list[dict[str, Any]] = []
    tool_trace: list[dict[str, Any]] = []
    model = qwen.model
    for ev in iter_assistant_graph_events(
        qwen,
        messages,
        temperature=temperature,
        workspace_root=workspace_root,
        runs_root=runs_root,
        design_checklist_id=design_checklist_id,
    ):
        if ev.get("type") == "done":
            reply = str(ev.get("reply") or "")
            client_actions = list(ev.get("client_actions") or [])
            tool_trace = list(ev.get("tool_trace") or [])
            model = ev.get("model") or model
    return {
        "reply": reply,
        "client_actions": client_actions,
        "tool_trace": tool_trace,
        "model": model,
    }


__all__ = ["iter_assistant_graph_events", "run_assistant_graph"]
