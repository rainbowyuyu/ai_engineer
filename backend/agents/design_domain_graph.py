"""LangGraph design-domain agent with SqliteSaver checkpoints.

plan_draft / plan_build / conversational agent all run on LangChain + LangGraph
(no silent yield-from of the legacy JSON tool-loop iterators).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Annotated, Any, Iterator, TypedDict

from backend.llm.models import get_chat_model, get_llm_settings, messages_to_langchain
from backend.oc4_design_domain_agent import (
    MAX_AGENT_TURNS,
    _agent_turn_json_valid,
    _append_build_history,
    _default_plan_build_steps,
    _design_domain_agent_model,
    _get_session_dir,
    _iter_plan_rail_events_from_buffer,
    _iter_tool_file_touch_events,
    _list_files_summary,
    _llm_plan_build_json,
    _merge_mesh_into_steps,
    _normalize_agent_shape,
    _parse_json_object,
    _resolve_mesh_cl_max,
    _run_tool,
    _tool_result_payload,
    _workspace_root,
    _yield_fallback_plan_rail_steps,
)
from backend.oc4_methodology_chen2026 import LLM_CONTEXT_BLOCK_ZH
from backend.oc4_design_domain_service import merge_session_meta, read_session_meta, session_progress_flags
from backend.qwen_client import QwenClient

logger = logging.getLogger(__name__)

_JSON_REPAIR_USER = (
    "请只输出一个合法 JSON 对象（thought / tool / final_reply），不要 Markdown 围栏。"
)


def _merge_events(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return left + right


class DesignDomainState(TypedDict, total=False):
    session_id: str
    user_message: str
    system: str
    history: list[dict[str, str]]
    turn: int
    max_turns: int
    model: str
    events: Annotated[list[dict[str, Any]], _merge_events]
    final_reply: str | None
    done: bool
    ok: bool
    _pending_tool: dict[str, Any] | None


def _checkpoint_path() -> Path:
    root = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()
    p = root / "runs" / "_checkpoints" / "oc4_design_domain.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _get_checkpointer():
    from backend.llm.checkpoints import get_sqlite_saver_cached

    return get_sqlite_saver_cached(str(_checkpoint_path()))


def _build_system_prompt(session_id: str) -> tuple[Path, str]:
    sdir = _get_session_dir(session_id)
    meta = read_session_meta(sdir)
    summ = meta.get("geometry_summary") or {}
    prog = session_progress_flags(sdir)
    files_snip = _list_files_summary(sdir, max_depth=6, max_lines=80)
    from backend.oc4_design_domain_agent import _MAX_SESSION_WRITE_BYTES

    system = (
        "你是 OC4 设计域会话内的执行智能体。你必须通过工具完成构建、导出、网格、载荷与收尾；"
        "不要编造文件路径。每次回复必须是**一个** JSON 对象（不要 Markdown 围栏），键如下：\n"
        '- "thought": string，简短中文思考；\n'
        '- 若需调用工具: "tool": {"name": string, "arguments": object}；\n'
        '- 若已可回答用户、无需再调工具: "final_reply": string。\n'
        "允许的工具名：list_files, read_file, write_file, run_build, run_export_source_preview, run_export_obj, "
        "run_mesh, run_loads, finalize。\n"
        f"单文件 write_file 不超过 {_MAX_SESSION_WRITE_BYTES // 1024}KB。\n"
        f"当前进度标记: {json.dumps(prog, ensure_ascii=False)}\n"
        f"几何摘要: {json.dumps(summ, ensure_ascii=False)[:4000]}\n"
        f"文件树摘要:\n{files_snip[:6000]}\n\n{LLM_CONTEXT_BLOCK_ZH}"
    )
    return sdir, system


def _dd_llm_node(state: DesignDomainState) -> dict[str, Any]:
    turn = int(state.get("turn") or 0) + 1
    events: list[dict[str, Any]] = []
    sdir = _get_session_dir(state["session_id"])
    ws = _workspace_root()
    messages: list[dict[str, str]] = [{"role": "system", "content": state["system"]}]
    messages.extend(state.get("history") or [])
    if turn == 1:
        messages.append({"role": "user", "content": state["user_message"]})
    else:
        messages.append({"role": "user", "content": "继续：根据工具结果决定下一步（仍只输出一个 JSON）。"})

    try:
        llm = get_chat_model(model=state.get("model"), temperature=0.15)
        ai = llm.invoke(messages_to_langchain(messages))
        content = getattr(ai, "content", "") or ""
    except Exception as e:
        events.append({"type": "error", "message": f"模型调用失败: {e}"})
        return {"turn": turn, "events": events, "done": True, "ok": False}

    data = _normalize_agent_shape(_parse_json_object(content) or {})
    if not _agent_turn_json_valid(data) and (content or "").strip():
        try:
            repair = [
                *messages,
                {"role": "assistant", "content": (content or "")[:12_000]},
                {"role": "user", "content": _JSON_REPAIR_USER},
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
        events.append({"type": "assistant", "text": fr.strip()})
        return {"turn": turn, "events": events, "final_reply": fr.strip(), "done": True, "ok": True}

    tool = data.get("tool")
    if not isinstance(tool, dict) or not str(tool.get("name") or "").strip():
        events.append({"type": "error", "message": "模型未给出 tool 或 final_reply"})
        return {"turn": turn, "events": events, "done": True, "ok": False}

    tname = str(tool.get("name") or "").strip()
    targs = tool.get("arguments") if isinstance(tool.get("arguments"), dict) else {}
    events.append({"type": "tool", "name": tname, "args": targs})
    return {
        "turn": turn,
        "events": events,
        "_pending_tool": {"name": tname, "args": targs, "raw": data, "sdir": str(sdir), "ws": str(ws)},
    }


def _dd_tool_node(state: DesignDomainState) -> dict[str, Any]:
    pending = state.get("_pending_tool") or {}
    tname = str(pending.get("name") or "")
    targs = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    data = pending.get("raw") if isinstance(pending.get("raw"), dict) else {}
    sdir = Path(pending.get("sdir") or _get_session_dir(state["session_id"]))
    ws = Path(pending.get("ws") or _workspace_root())
    events: list[dict[str, Any]] = []

    ok, summary, extra = _run_tool(tname, targs, sdir=sdir, workspace_root=ws)
    events.append(_tool_result_payload(tname, ok, targs, summary, extra))
    for fe in _iter_tool_file_touch_events(tname, ok, sdir, extra):
        events.append(fe)

    hist_res = json.dumps({"ok": ok, "summary": summary, **(extra if isinstance(extra, dict) else {})}, ensure_ascii=False)[
        :24_000
    ]
    history = list(state.get("history") or [])
    history.append({"role": "assistant", "content": json.dumps(data, ensure_ascii=False)[:12_000]})
    history.append({"role": "user", "content": f"工具结果:\n{hist_res}"})
    return {"events": events, "history": history, "_pending_tool": None}


def _route_after_llm(state: DesignDomainState) -> str:
    if state.get("done"):
        return "end"
    if state.get("_pending_tool"):
        return "tools"
    return "end"


def _route_after_tools(state: DesignDomainState) -> str:
    turn = int(state.get("turn") or 0)
    if turn >= int(state.get("max_turns") or MAX_AGENT_TURNS):
        return "end"
    return "llm"


def _build_design_domain_graph():
    from langgraph.graph import END, StateGraph

    g = StateGraph(DesignDomainState)
    g.add_node("llm", _dd_llm_node)
    g.add_node("tools", _dd_tool_node)
    g.set_entry_point("llm")
    g.add_conditional_edges("llm", _route_after_llm, {"tools": "tools", "end": END})
    g.add_conditional_edges("tools", _route_after_tools, {"llm": "llm", "end": END})
    return g.compile(checkpointer=_get_checkpointer())


_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_design_domain_graph()
    return _GRAPH


def iter_design_domain_graph_agent_events(session_id: str, user_message: str) -> Iterator[dict[str, Any]]:
    """LangGraph + checkpoint agent stream (legacy NDJSON event shapes)."""
    qwen = QwenClient(model=_design_domain_agent_model())
    if not qwen.api_key:
        yield {"type": "error", "message": "未配置 QWEN_API_KEY"}
        yield {"type": "done", "ok": False}
        return

    user0 = (user_message or "").strip()
    if not user0:
        yield {"type": "error", "message": "message 为空"}
        yield {"type": "done", "ok": False}
        return

    try:
        _, system = _build_system_prompt(session_id)
    except Exception as e:
        yield {"type": "error", "message": str(e)}
        yield {"type": "done", "ok": False}
        return

    yield {"type": "meta", "model": qwen.model, "protocol": "langgraph_json_tool"}

    init: DesignDomainState = {
        "session_id": session_id,
        "user_message": user0,
        "system": system,
        "history": [],
        "turn": 0,
        "max_turns": MAX_AGENT_TURNS,
        "model": qwen.model or get_llm_settings().model,
        "events": [],
    }
    config = {"configurable": {"thread_id": session_id}}
    graph = _get_graph()
    final: DesignDomainState = dict(init)
    ok = True
    try:
        for update in graph.stream(init, config=config, stream_mode="updates"):
            for _node, delta in update.items():
                if not isinstance(delta, dict):
                    continue
                for ev in delta.get("events") or []:
                    yield ev
                final.update({k: v for k, v in delta.items() if k != "events"})
                if delta.get("done"):
                    ok = bool(delta.get("ok", ok))
    except Exception as e:
        logger.exception("design domain graph failed")
        yield {"type": "error", "message": str(e)[:1200]}
        yield {"type": "done", "ok": False}
        return

    turn = int(final.get("turn") or 0)
    if not final.get("done") and turn >= int(final.get("max_turns") or MAX_AGENT_TURNS):
        yield {"type": "error", "message": f"超过最大轮数 {MAX_AGENT_TURNS}"}
        ok = False
    yield {"type": "done", "ok": ok}


def iter_design_domain_graph_plan_draft_events(session_id: str) -> Iterator[dict[str, Any]]:
    """Plan draft via LangChain ChatModel.stream (checkpointed metadata)."""
    try:
        sdir = _get_session_dir(session_id)
    except Exception as e:
        yield {"type": "error", "message": str(e)}
        yield {"type": "done", "ok": False, "phase": "plan_draft"}
        return

    model = _design_domain_agent_model() or get_llm_settings().model
    yield {"type": "meta", "model": model, "protocol": "langgraph_plan_draft"}

    prog = session_progress_flags(sdir)
    settings = get_llm_settings()
    if not settings.api_key:
        rail_emitted: set[int] = set()
        for ev in _yield_fallback_plan_rail_steps(rail_emitted):
            yield ev
        txt = (
            "# Build 执行计划（草稿）\n\n"
            "未配置 `QWEN_API_KEY`：无法调用大模型流式生成。你可直接点击 **Build** 使用内置五步流程。\n"
        )
        yield {"type": "plan_md_delta", "text": txt}
        try:
            (sdir / "build_plan.md").write_text(txt, encoding="utf-8")
        except OSError:
            pass
        yield {"type": "plan_file", "path": "build_plan.md", "chars": len(txt)}
        merge_session_meta(sdir, {"plan_draft_generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        yield {"type": "done", "ok": True, "phase": "plan_draft"}
        return

    system = (
        "你是海洋工程 OC4 设计域助手。请用 **GitHub Markdown** 写一份「Build 执行计划」草稿，语气专业、中文为主。\n"
        "内容包括：1）当前进度简述；2）与四步管线对齐的**编号步骤**（必须严格各占一行，格式为 `1. …` `2. …` `3. …` `4. …`，"
        "对应：设计域 → OBJ 预览 → 体网格 → 载荷 INP）；"
        "3）各步预期产物文件名；4）风险与注意点。\n"
        "不要输出 JSON；不要用 Markdown 代码围栏包住全文。\n"
        f"当前目录进度标记: {json.dumps(prog, ensure_ascii=False)[:2800]}\n"
        f"{LLM_CONTEXT_BLOCK_ZH}"
    )
    yield {"type": "activity", "kind": "plan", "text": "正在流式生成 Build 计划（LangChain）…"}
    buf: list[str] = []
    rail_emitted = set()
    try:
        llm = get_chat_model(model=model, temperature=0.28)
        for chunk in llm.stream(
            messages_to_langchain(
                [{"role": "system", "content": system}, {"role": "user", "content": "请只输出 Markdown 计划正文。"}]
            )
        ):
            piece = getattr(chunk, "content", None) or ""
            if not piece:
                continue
            buf.append(piece)
            yield {"type": "plan_md_delta", "text": piece}
            acc = "".join(buf)
            for ev in _iter_plan_rail_events_from_buffer(acc, rail_emitted, finalize=False):
                yield ev
    except Exception as e:
        yield {"type": "error", "message": f"计划流失败: {e}"}
        yield {"type": "done", "ok": False, "phase": "plan_draft"}
        return

    full = "".join(buf).strip() or "# Build 执行计划\n\n（模型未返回内容）\n"
    for ev in _iter_plan_rail_events_from_buffer(full, rail_emitted, finalize=True):
        yield ev
    for ev in _yield_fallback_plan_rail_steps(rail_emitted):
        yield ev
    try:
        (sdir / "build_plan.md").write_text(full, encoding="utf-8")
    except OSError as e:
        yield {"type": "error", "message": f"无法写入 build_plan.md: {e}"}
        yield {"type": "done", "ok": False, "phase": "plan_draft"}
        return
    merge_session_meta(sdir, {"plan_draft_generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    try:
        graph = _get_graph()
        graph.update_state(
            {"configurable": {"thread_id": f"{session_id}:plan-draft"}},
            {"session_id": session_id, "done": True, "ok": True, "events": [{"type": "plan_file", "path": "build_plan.md"}]},
        )
    except Exception:
        pass
    yield {"type": "plan_file", "path": "build_plan.md", "chars": len(full)}
    yield {"type": "done", "ok": True, "phase": "plan_draft"}


def iter_design_domain_graph_plan_build_events(
    session_id: str,
    *,
    cut_center_column: bool = True,
    include_source_geometry: bool = False,
    mesh_preset: str = "balanced",
    mesh_characteristic_length_max: float | None = None,
    mesh_user_note: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Plan-build: LangChain plan JSON + deterministic tool steps + checkpoint."""
    ws = _workspace_root()
    try:
        sdir = _get_session_dir(session_id)
    except Exception as e:
        yield {"type": "error", "message": str(e)}
        yield {"type": "done", "ok": False, "phase": "plan_build"}
        return

    meta = read_session_meta(sdir)
    if bool(meta.get("design_domain_full_build_done")):
        yield {"type": "error", "message": "已完成全流程 Build。请查看会话目录中的 build_history.md。"}
        yield {"type": "done", "ok": False, "phase": "plan_build"}
        return

    model = _design_domain_agent_model() or get_llm_settings().model
    yield {"type": "meta", "model": model, "protocol": "langgraph_plan_build"}

    mesh_cl = _resolve_mesh_cl_max(sdir, mesh_preset, mesh_characteristic_length_max)
    note = str(mesh_user_note or "").strip()
    mesh_summary = f"preset={mesh_preset}, characteristic_length_max={mesh_cl}"
    if note:
        mesh_summary += f"; note={note[:500]}"

    yield {"type": "activity", "kind": "plan", "text": "正在根据偏好生成执行计划（LangChain）…"}
    # Reuse plan JSON helper but force its QwenClient through LangChain client adapter
    qwen = QwenClient(model=model)
    llm_out = _llm_plan_build_json(
        sdir,
        qwen,
        cut_center_column=cut_center_column,
        include_source_geometry=include_source_geometry,
        mesh_summary=mesh_summary,
    )
    if llm_out:
        rationale, steps_llm = llm_out
        steps = _merge_mesh_into_steps(steps_llm, mesh_cl)
    else:
        steps = _merge_mesh_into_steps(
            _default_plan_build_steps(cut_center_column, include_source_geometry),
            mesh_cl,
        )
        rationale = "内置五步：与四步管线及载荷一致（大模型不可用或未返回合法 JSON 时回退）。"

    yield {"type": "plan", "rationale": rationale, "steps": steps}
    try:
        (sdir / "agent_build_plan.json").write_text(
            json.dumps({"rationale": rationale, "steps": steps}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass

    hdr = f"# Build 执行记录\n\n会话 `{session_id[:12]}…` · {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n\n"
    try:
        (sdir / "build_history.md").write_text(hdr, encoding="utf-8")
    except OSError:
        pass

    config = {"configurable": {"thread_id": f"{session_id}:plan-build"}}
    graph = _get_graph()
    for st in steps:
        idx = int(st.get("id") or 0)
        title = str(st.get("title") or "")
        tname = str(st.get("tool") or "").strip()
        targs = st.get("arguments") if isinstance(st.get("arguments"), dict) else {}
        line = f"\n## 步骤 {idx} · {title} · `{tname}`\n\n"
        _append_build_history(sdir, line)
        start_ev = {"type": "plan_step", "index": idx, "title": title, "tool": tname, "phase": "start"}
        yield start_ev
        yield {"type": "tool", "name": tname, "args": targs}
        ok, summary, extra = _run_tool(tname, targs, sdir=sdir, workspace_root=ws)
        yield _tool_result_payload(tname, ok, targs, summary, extra)
        for fe in _iter_tool_file_touch_events(tname, ok, sdir, None):
            yield fe
        res_line = ("✅ " if ok else "❌ ") + str(summary).strip() + "\n"
        _append_build_history(sdir, res_line)
        done_ev = {"type": "plan_step", "index": idx, "title": title, "tool": tname, "phase": "done", "ok": ok}
        yield done_ev
        try:
            graph.update_state(
                config,
                {"session_id": session_id, "turn": idx, "events": [start_ev, done_ev], "ok": ok},
            )
        except Exception:
            pass
        if not ok:
            yield {"type": "error", "message": f"步骤失败: {tname} · {summary}"}
            yield {"type": "done", "ok": False, "phase": "plan_build"}
            return

    _append_build_history(sdir, "\n---\n\n全流程结束。\n")
    merge_session_meta(sdir, {"design_domain_full_build_done": True})
    yield {"type": "refresh_tree"}
    yield {"type": "done", "ok": True, "phase": "plan_build", "history_path": "build_history.md"}


__all__ = [
    "iter_design_domain_graph_agent_events",
    "iter_design_domain_graph_plan_draft_events",
    "iter_design_domain_graph_plan_build_events",
]
