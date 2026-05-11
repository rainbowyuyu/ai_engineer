"""侧栏助手：多轮 JSON 工具循环（与 OC4 设计域智能体同族协议）。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.generator import scan_input_directory
from backend.oc4_design_domain_agent import (
    _agent_turn_json_valid,
    _normalize_agent_shape,
    _parse_json_object,
)
from backend.qwen_client import QwenClient
from backend.tools.cad_skill_runner import cad_skill_help_text, run_step_on_generator
from backend.tools.freecad_cad_convert import (
    cad_convert_to_runs_subdir,
    path_under_workspace,
    resolve_workspace_path,
)

logger = logging.getLogger(__name__)

MAX_ASSISTANT_TOOL_TURNS = 10

_ASSISTANT_TOOLS_BLOCK = (
    "\n\n【工具模式·已开启】除正常中文回答外，你也可以通过**工具**完成格式转换或打开结果查看器。"
    "每次回复必须是**一个** JSON 对象（不要 Markdown 代码围栏），键如下：\n"
    '- "thought": string，简短中文；\n'
    '- 若需调用工具: "tool": {"name": string, "arguments": object}；\n'
    '- 若已可回答用户、无需再调工具: "final_reply": string（面向用户的最终说明）。\n'
    "允许的工具：\n"
    "1) cad_convert — arguments: "
    '{"input_path": string（WORKSPACE_ROOT 内绝对路径或相对路径）, '
    '"target_format": "step"|"iges"|"stl"|"brep"}；'
    "将 .igs/.iges/.stp/.step/.stl/.brep 转为目标格式，输出在 runs/_cad_convert/format/<id>/converted.* 。\n"
    "2) open_results_viewer — arguments: "
    '{"scan_dir": string}；'
    "在工作区内打开「拓扑优化结果查看器」并加载该目录（须为已存在目录，常用为 runs 下某任务目录或刚转换输出目录的父级）。\n"
    "3) list_scan_dir — arguments: "
    '{"scan_dir": string}；'
    "列出该目录下由平台扫描到的输入文件摘要（路径、扩展名），便于确认再 cad_convert。\n"
    "4) cad_skill_help — arguments: {}；"
    "返回内嵌 text-to-cad「cad」技能说明（SKILL.md 摘要 + STEP 示例脚本列表），"
    "用于文本转 CAD、build123d、STEP 生成流程。\n"
    "5) cad_skill_step — arguments: "
    '{"generator_py": string（工作区内 .py，须含 gen_step()，常用 third_party/text-to-cad/STEP/demo_mounting_plate.py）, '
    '"output_step": string | null（可选，写出 STEP；路径须用 POSIX 正斜杠 /，勿用反斜杠 \\）}；'
    "调用内嵌 cad_skill 的 scripts/step 生成 STEP/附属产物；"
    "需 build123d：可在项目 .venv 执行 pip install -r backend/requirements-text-to-cad.txt，"
    "或设 TEXT_TO_CAD_PYTHON；否则自动尝试仓库 .venv、同级 text-to-cad/.venv、运行后端的 Python。\n"
    "6) open_cad_explorer — arguments: "
    '{"file": string | null（可选，工作区相对路径的 .step/.stp，如 third_party/text-to-cad/STEP/demo_mounting_plate.step）}；'
    "登记由浏览器打开内嵌 **CAD Explorer** 新标签页（本站点 /cad-explorer/）。\n"
    "路径必须真实且位于工作区内；不要编造路径。若用户仅咨询概念、不需要操作文件，直接用 final_reply。"
)

_CAD_ONE_SHOT_PIPELINE = (
    "\n\n【CAD 设计台·一句话闭环】用户常用**一句自然语言**完成修改（可含 @cad[path/to.step#fN] 指向面 fN）。"
    "你的目标是在**尽量少轮工具调用**内产出可用几何，而不是让用户反复手动确认：\n"
    "· **thought**（1～3 句）：写清解析到的 STEP 路径、下一步工具名、若用户未给孔径/深度等则采用**明确默认工程值**（并在 final_reply 中告知）。\n"
    "· 典型最短路径：必要时 **cad_skill_help**（一次）→ **cad_skill_step**（generator_py 须为仓库内真实 .py；"
    "**output_step** 一律 POSIX `/`）→ **open_cad_explorer**（**最多一次**，打开刚生成或刚修改的 .step）。"
    "避免连续多轮只 open_cad_explorer 却不执行 cad_skill_step。\n"
    "· 若现有 `third_party/text-to-cad/STEP/*.py` 不足以表达用户特征，可在 final_reply 中说明限制并给出可复制的 build123d 修改建议；"
    "能脚本化则优先 cad_skill_step。\n"
    "· **final_reply** 面向用户：必须使用 **Markdown**（如 `###` 小节、`-` 列表、`**粗体**`、行内 `代码`），"
    "总结已执行步骤与产物路径；本 JSON 对象本身不要用 Markdown 代码围栏包裹。"
)

_ASSISTANT_TOOLS_FULL = (_ASSISTANT_TOOLS_BLOCK.strip() + _CAD_ONE_SHOT_PIPELINE).strip()

_JSON_REPAIR = (
    "上一条「助手」输出无法按约定解析为单个 JSON 对象。"
    "请**只**输出一个合法 JSON（不要 Markdown 围栏、不要前后任何解释），键为：\n"
    '- "thought": string（可简短中文）；\n'
    '- 要么 "tool": {"name": string, "arguments": object}，\n'
    '- 要么 "final_reply": string（直接回答用户）。\n'
    "可调用工具名：cad_convert, open_results_viewer, list_scan_dir, cad_skill_help, cad_skill_step, open_cad_explorer。"
)


@dataclass
class AssistantToolLoopResult:
    reply: str
    client_actions: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    model: str | None


def append_tools_system_block(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """在首条 system 消息末尾追加工具说明；若无 system 则插入一条。"""
    out = [dict(m) for m in messages]
    if not out:
        return [{"role": "system", "content": _ASSISTANT_TOOLS_FULL}]
    sys_i = next((i for i, m in enumerate(out) if m.get("role") == "system"), None)
    if sys_i is None:
        return [{"role": "system", "content": _ASSISTANT_TOOLS_FULL}, *out]
    cur = str(out[sys_i].get("content") or "")
    out[sys_i] = {**out[sys_i], "content": (cur + "\n\n" + _ASSISTANT_TOOLS_FULL).strip()}
    return out


def _sanitize(s: str, workspace_root: Path) -> str:
    t = str(s or "")[:500]
    try:
        root = str(workspace_root.resolve())
        if len(root) > 2 and root in t:
            t = t.replace(root, "<workspace>")
    except OSError:
        pass
    return t


def _run_assistant_tool(
    name: str,
    args: dict[str, Any],
    *,
    workspace_root: Path,
    runs_root: Path,
    client_actions: list[dict[str, Any]],
) -> tuple[bool, str, dict[str, Any]]:
    args = args if isinstance(args, dict) else {}
    try:
        if name == "cad_convert":
            raw_in = str(args.get("input_path", "")).strip()
            tfm = str(args.get("target_format", "")).strip().lower()
            inp = resolve_workspace_path(raw_in, workspace_root)
            if not inp.is_file():
                return False, "输入路径不是文件", {}
            if tfm not in ("step", "iges", "stl", "brep"):
                return False, "target_format 须为 step / iges / stl / brep", {}
            out_abs, url = cad_convert_to_runs_subdir(
                inp,
                tfm,  # type: ignore[arg-type]
                workspace_root=workspace_root,
                runs_root=runs_root,
            )
            return True, f"已转换 -> {out_abs.name}", {"output_path": str(out_abs), "runs_url": url}

        if name == "open_results_viewer":
            raw = str(args.get("scan_dir", "")).strip()
            sdir = resolve_workspace_path(raw, workspace_root)
            if not sdir.is_dir():
                return False, "scan_dir 不是有效目录", {}
            scan_abs = str(sdir.resolve())
            client_actions.append({"type": "open_results_viewer", "scan_dir": scan_abs})
            return True, f"已登记打开结果查看器: {scan_abs}", {"scan_dir": scan_abs}

        if name == "list_scan_dir":
            raw = str(args.get("scan_dir", "")).strip()
            sdir = resolve_workspace_path(raw, workspace_root)
            if not sdir.is_dir():
                return False, "scan_dir 不是有效目录", {}
            bundle = scan_input_directory(str(sdir.resolve()))
            d = bundle.as_dict()
            snippet = json.dumps(d, ensure_ascii=False)[:14_000]
            return True, f"已扫描 {len(bundle.files)} 个输入文件", {"bundle_json": snippet}

        if name == "cad_skill_help":
            txt = cad_skill_help_text(workspace_root)
            return True, "已加载 cad 技能说明摘要", {"skill_markdown": txt[:20_000]}

        if name == "cad_skill_step":
            raw_py = str(args.get("generator_py", "")).strip()
            gen = resolve_workspace_path(raw_py, workspace_root)
            out_raw = args.get("output_step")
            out_path: Path | None = None
            if isinstance(out_raw, str) and out_raw.strip():
                out_path = resolve_workspace_path(out_raw.strip(), workspace_root)
            ok, summary, extra = run_step_on_generator(
                workspace_root,
                gen,
                output_step=out_path,
            )
            return ok, summary, extra

        if name == "open_cad_explorer":
            rel = str(args.get("file", "") or "").strip().replace("\\", "/")
            if rel:
                p = (workspace_root / Path(rel)).resolve()
                if not path_under_workspace(p, workspace_root):
                    return False, "file 必须位于工作区 workspace_root 内", {}
            client_actions.append({"type": "open_cad_explorer", "file": rel})
            return True, "已登记打开 CAD Explorer（前端将打开新标签页）", {"file": rel or None}

        return False, f"未知工具: {name}", {}
    except Exception as e:
        logger.info("assistant tool %s failed: %s", name, e)
        return False, _sanitize(str(e), workspace_root), {}


def _artifacts_from_tool_extra(extra: dict[str, Any]) -> list[dict[str, Any]]:
    """从工具返回的 extra 中抽取可供前端展示的路径类产物。"""
    out: list[dict[str, Any]] = []
    if not isinstance(extra, dict):
        return out
    for key in ("step_path", "output_path", "runs_url", "scan_dir", "file"):
        v = extra.get(key)
        if isinstance(v, str) and v.strip():
            out.append({"kind": key, "path": v.strip()[:4000]})
    return out


def iter_assistant_tool_loop_events(
    qwen: QwenClient,
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    workspace_root: Path,
    runs_root: Path,
):
    """
    以 dict 事件序列驱动 SSE：思考（thought）、工具起止、最终正文分块（delta）、结束（done）。
    与 ``run_assistant_tool_loop`` 逻辑一致，供 CAD 设计台等需要流式与过程可视化的前端使用。
    """
    client_actions: list[dict[str, Any]] = []
    tool_trace: list[dict[str, Any]] = []
    msgs = append_tools_system_block(messages)
    history: list[dict[str, Any]] = []

    yield {"type": "session", "model": qwen.model}

    for turn in range(MAX_ASSISTANT_TOOL_TURNS):
        yield {"type": "turn", "turn": turn + 1, "max": MAX_ASSISTANT_TOOL_TURNS}
        round_msgs = [*msgs, *history]
        try:
            resp = qwen.chat(round_msgs, temperature=temperature)
            content = (resp.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        except Exception as e:
            err = _sanitize(str(e), workspace_root)
            yield {"type": "error", "message": err}
            yield {
                "type": "done",
                "reply": f"模型调用失败: {err}",
                "client_actions": client_actions,
                "tool_trace": tool_trace
                + [{"name": "chat", "ok": False, "summary": err, "artifacts": []}],
                "model": qwen.model,
            }
            return

        data = _normalize_agent_shape(_parse_json_object(content) or {})
        if not _agent_turn_json_valid(data) and (content or "").strip():
            try:
                repair = [
                    *round_msgs,
                    {"role": "assistant", "content": (content or "")[:12_000]},
                    {"role": "user", "content": _JSON_REPAIR},
                ]
                resp2 = qwen.chat(repair, temperature=min(0.12, temperature))
                content2 = (resp2.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                data = _normalize_agent_shape(_parse_json_object(content2) or {})
            except Exception:
                pass

        thought = str(data.get("thought") or "").strip()
        if thought:
            yield {"type": "thinking", "text": thought}

        fr = data.get("final_reply")
        if isinstance(fr, str) and fr.strip():
            text = fr.strip()
            yield {"type": "reply_start", "length": len(text)}
            chunk_size = 44
            for i in range(0, len(text), chunk_size):
                yield {"type": "delta", "text": text[i : i + chunk_size]}
            yield {
                "type": "done",
                "reply": text,
                "client_actions": client_actions,
                "tool_trace": tool_trace,
                "model": qwen.model,
            }
            return

        tool = data.get("tool")
        if not isinstance(tool, dict) or not str(tool.get("name") or "").strip():
            msg = "（模型未给出有效的 tool 或 final_reply，请重试或缩短上文。）"
            yield {"type": "reply_start", "length": len(msg)}
            yield {"type": "delta", "text": msg}
            yield {
                "type": "done",
                "reply": msg,
                "client_actions": client_actions,
                "tool_trace": tool_trace,
                "model": qwen.model,
            }
            return

        tname = str(tool.get("name") or "").strip()
        targs = tool.get("arguments") if isinstance(tool.get("arguments"), dict) else {}
        yield {
            "type": "tool_start",
            "name": tname,
            "arguments_preview": json.dumps(targs, ensure_ascii=False)[:800],
        }
        ok, summary, extra = _run_assistant_tool(
            tname,
            targs,
            workspace_root=workspace_root,
            runs_root=runs_root,
            client_actions=client_actions,
        )
        arg_snip = json.dumps(targs, ensure_ascii=False)[:800]
        ex = extra if isinstance(extra, dict) else {}
        artifacts = _artifacts_from_tool_extra(ex)
        tool_trace.append(
            {
                "name": tname,
                "ok": ok,
                "summary": _sanitize(summary, workspace_root),
                "arguments_preview": arg_snip,
                "artifacts": artifacts,
            }
        )
        yield {
            "type": "tool_done",
            "name": tname,
            "ok": ok,
            "summary": _sanitize(summary, workspace_root),
            "artifacts": artifacts,
        }
        hist_tool = json.dumps(data, ensure_ascii=False)[:12_000]
        hist_res = json.dumps({"ok": ok, "summary": summary, **ex}, ensure_ascii=False)[:24_000]
        history.append({"role": "assistant", "content": hist_tool})
        history.append({"role": "user", "content": f"工具结果:\n{hist_res}"})

    over = f"（超过最大工具轮数 {MAX_ASSISTANT_TOOL_TURNS}，请分步说明需求。）"
    yield {"type": "reply_start", "length": len(over)}
    yield {"type": "delta", "text": over}
    yield {
        "type": "done",
        "reply": over,
        "client_actions": client_actions,
        "tool_trace": tool_trace,
        "model": qwen.model,
    }


def run_assistant_tool_loop(
    qwen: QwenClient,
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    workspace_root: Path,
    runs_root: Path,
) -> AssistantToolLoopResult:
    client_actions: list[dict[str, Any]] = []
    tool_trace: list[dict[str, Any]] = []
    msgs = append_tools_system_block(messages)
    history: list[dict[str, Any]] = []

    for turn in range(MAX_ASSISTANT_TOOL_TURNS):
        round_msgs = [*msgs, *history]
        try:
            resp = qwen.chat(round_msgs, temperature=temperature)
            content = (resp.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        except Exception as e:
            return AssistantToolLoopResult(
                reply=f"模型调用失败: {_sanitize(str(e), workspace_root)}",
                client_actions=client_actions,
                tool_trace=tool_trace + [{"name": "chat", "ok": False, "summary": _sanitize(str(e), workspace_root)}],
                model=qwen.model,
            )

        data = _normalize_agent_shape(_parse_json_object(content) or {})
        if not _agent_turn_json_valid(data) and (content or "").strip():
            try:
                repair = [
                    *round_msgs,
                    {"role": "assistant", "content": (content or "")[:12_000]},
                    {"role": "user", "content": _JSON_REPAIR},
                ]
                resp2 = qwen.chat(repair, temperature=min(0.12, temperature))
                content2 = (resp2.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                data = _normalize_agent_shape(_parse_json_object(content2) or {})
            except Exception:
                pass

        fr = data.get("final_reply")
        if isinstance(fr, str) and fr.strip():
            return AssistantToolLoopResult(
                reply=fr.strip(),
                client_actions=client_actions,
                tool_trace=tool_trace,
                model=qwen.model,
            )

        tool = data.get("tool")
        if not isinstance(tool, dict) or not str(tool.get("name") or "").strip():
            return AssistantToolLoopResult(
                reply="（模型未给出有效的 tool 或 final_reply，请重试或缩短上文。）",
                client_actions=client_actions,
                tool_trace=tool_trace,
                model=qwen.model,
            )

        tname = str(tool.get("name") or "").strip()
        targs = tool.get("arguments") if isinstance(tool.get("arguments"), dict) else {}
        ok, summary, extra = _run_assistant_tool(
            tname,
            targs,
            workspace_root=workspace_root,
            runs_root=runs_root,
            client_actions=client_actions,
        )
        arg_snip = json.dumps(targs, ensure_ascii=False)[:800]
        ex_loop = extra if isinstance(extra, dict) else {}
        tool_trace.append(
            {
                "name": tname,
                "ok": ok,
                "summary": _sanitize(summary, workspace_root),
                "arguments_preview": arg_snip,
                "artifacts": _artifacts_from_tool_extra(ex_loop),
            }
        )
        hist_tool = json.dumps(data, ensure_ascii=False)[:12_000]
        hist_res = json.dumps({"ok": ok, "summary": summary, **ex_loop}, ensure_ascii=False)[:24_000]
        history.append({"role": "assistant", "content": hist_tool})
        history.append({"role": "user", "content": f"工具结果:\n{hist_res}"})

    return AssistantToolLoopResult(
        reply=f"（超过最大工具轮数 {MAX_ASSISTANT_TOOL_TURNS}，请分步说明需求。）",
        client_actions=client_actions,
        tool_trace=tool_trace,
        model=qwen.model,
    )


__all__ = [
    "AssistantToolLoopResult",
    "append_tools_system_block",
    "iter_assistant_tool_loop_events",
    "run_assistant_tool_loop",
]
