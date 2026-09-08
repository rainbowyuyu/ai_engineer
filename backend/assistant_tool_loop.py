"""侧栏助手：多轮 JSON 工具循环（与 OC4 设计域智能体同族协议）。

.. deprecated::
    默认由 ``backend.agents.assistant_graph``（LangGraph）接管；
    设置 ``USE_LANGGRAPH_ASSISTANT=false`` 可回退本模块。
"""
from __future__ import annotations

import json
import logging
import uuid
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
from backend.tools.cad_drawing_pack import build_cad_drawing_pack
from backend.tools.inp_design_deliverables import build_inp_design_deliverables
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
    "7) cad_drawing_pack — arguments: "
    '{"input_path": string | null（工作区内 INP/IGES/STEP/STL/OBJ/VTK）, '
    '"file_id": string | null（上传文件 id，与 input_path 二选一）, '
    '"title": string | null, '
    '"engine": "auto"|"freecad"|"mesh"（默认 auto：STEP/IGES/STL 优先线框）, '
    '"sheet_size": "A3"|"A1"|"A0"（默认 A3 横幅）, '
    '"layout": "ga"|"quad"（默认 ga=总布置式大俯视；quad=四等分）}；'
    "生成「AI Engineer」国标风格总布置式工程图 PNG+PDF（及 SVG 线框）；底层可用 FreeCAD（D:\\\\freecad 或 FREECAD_CMD）或网格引擎；"
    "输出于 runs/_cad_drawings/<id>/。"
    "用户说「画图/工程图/图纸/出图/三视图/总布置」且已上传或给出 CAD/INP 路径时，**必须**调用本工具；"
    "final_reply 说明引擎、比例与非审图免责声明，图面品牌为 AI Engineer。\n"
    "8) export_design_deliverables — arguments: "
    '{"input_path": string（工作区内 .inp，如 BESO 结果 file051_state1.inp）}；'
    "从 INP 的 design_space（或首个 C3D4 块）导出四件套："
    "design_space_preview.png、design_space_nodes.csv、design_space_elements.csv、design_space_surface.stl，"
    "写入 runs/_deliverables/<pack_id>/。"
    "final_reply 中表格链接必须使用工具返回的 files 内完整 URL（以 /runs/ 开头），勿只写裸文件名。\n"
    "9) get_design_checklist — arguments: "
    '{"checklist_id": string | null（省略则用会话绑定的 design_checklist_id）}；'
    "读取 Phase I 设计清单摘要与待确认项。\n"
    "10) update_design_checklist — arguments: "
    '{"reply": string（用户修订原文，如「钢耗改为 280 t/MW，水深 55」）, '
    '"checklist_id": string | null, '
    '"mode": "edit"|"clarify"（默认 edit）}；'
    "按答复写回同一清单；用户要改已锁定参数时**必须**调用本工具，并在 final_reply 复述更新字段。\n"
    "11) probe_execution / set_execution_mode — arguments: "
    '{"mode": "live"|"preview"|null}；探测 FreeCAD/CalculiX/gmsh；live 缺求解器时自动 Preview（须向用户说明 canned）。\n'
    "12) apply_turbine_preset — arguments: "
    '{"preset_id": "5"|"10"|"15"|"20", "checklist_id": string|null, "session_id": string|null}；'
    "应用机型预设（容量/载荷/缩放/验证目标），支持 10MW 等变种。\n"
    "13) start_design_domain_session — arguments: "
    '{"file_id": string|null, "source_path": string|null, "preset_id": string|null, '
    '"checklist_id": string|null, "task_id": string|null}；创建 OC4 设计域会话（IGES）。'
    "用户未上传时也可调用：省略 file_id/source_path 将使用仓库内置 oc4.igs；"
    "10MW 等机型请同时传 preset_id。成功后前端会进入设计域工作台。\n"
    "14) run_design_domain_build — arguments: "
    '{"session_id": string, "pause_before_mesh": bool, "run_mesh": bool, "run_loads": bool, "finalize": bool}；'
    "真构建设计域→网格→载荷；pause_before_mesh=true 时等人审/改几何。\n"
    "15) request_human_edit / apply_geometry_patch / commit_preview_to_session — "
    "人为介入改模型：暂停、替换 STEP/IGES、或提交结果查看器预览写回会话并清下游。\n"
    "16) start_beso_job / get_job_status — 启动真实 CalculiX–BESO 任务并轮询（Preview 模式拒绝冒充成功）。\n"
    "17) run_sizing / run_platform_restruction / run_zwind_eval / run_validation / evaluate_halt — "
    "尺寸优化、平台库静力、Zwind 时域、AI 评审与停机门控；静力/时域会打开「尺寸时域分析」工作台。\n"
    "18) parse_prism_design_brief — arguments: "
    '{"text": string}；解析「三棱柱/beso9/挖角/体积分数」等提示词为棱柱设计域参数。\n'
    "19) start_prism_session / build_prism_design_domain / mesh_prism_design_domain — "
    "分步：建会话 → FreeCAD 建 FCStd → Gmsh 导出 03_for_beso.inp（不做 OC4 载荷分区）。\n"
    "20) run_prism_topology_demo — arguments: "
    '{"text": string（用户原话）, "start_beso": bool（默认 true）, "task_id": string|null}；'
    "一句话闭环：解析→FreeCAD建域→网格→异步启动真实 BESO；返回 session_id/job_id/run_dir。\n"
    "【闭环顺序】确认 MW 预设 → Phase I 清单 → 设计域（可 HITL）→ BESO → 尺寸/评审。"
    "用户未上传文件时：仍须调用 apply_turbine_preset + start_design_domain_session（可省略 file_id，使用内置 oc4.igs）"
    "并依赖 client_hint 进入设计域工作台；网格/载荷完成后 start_beso_job 进入拓扑工作台。"
    "不要只文字描述流程而不调用工具。\n"
    "【棱柱拓扑·一句话闭环】用户提到「三棱柱 / beso9 / 挖角 / 体积分数 / 拓扑优化」且要真跑时："
    "优先 **run_prism_topology_demo**（可在 text 中写边长、水上/水下、挖角 R、载荷 Ø/力、体积分数%、粗网格快演示）；"
    "成功后用 **open_results_viewer**（scan_dir=session_dir 或 run_dir），并用 **get_job_status** 如实报告进度；"
    "勿用 OC4 IGES 路径冒充 beso9 棱柱。OC4/半潜仍用 start_design_domain_session + run_design_domain_build。\n"
    "**禁止**在 live 模式下调用 /api/demo 种子回放冒充成功；教学回放仅当用户明确要求 demo/preview。\n"
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
    "可调用工具名：cad_convert, open_results_viewer, list_scan_dir, cad_skill_help, cad_skill_step, "
    "open_cad_explorer, cad_drawing_pack, export_design_deliverables, get_design_checklist, "
    "update_design_checklist, probe_execution, set_execution_mode, apply_turbine_preset, "
    "start_design_domain_session, run_design_domain_build, request_human_edit, apply_geometry_patch, "
    "commit_preview_to_session, start_beso_job, get_job_status, run_sizing, run_platform_restruction, "
    "run_zwind_eval, run_validation, evaluate_halt, "
    "parse_prism_design_brief, start_prism_session, build_prism_design_domain, mesh_prism_design_domain, "
    "run_prism_topology_demo。"
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
    design_checklist_id: str | None = None,
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

        if name == "cad_drawing_pack":
            raw = str(args.get("input_path") or args.get("path") or "").strip()
            fid = str(args.get("file_id") or "").strip() or None
            if not raw and not fid:
                return False, "须提供 input_path 或 file_id", {}
            title_raw = args.get("title")
            title = str(title_raw).strip() if isinstance(title_raw, str) and title_raw.strip() else None
            eng = str(args.get("engine") or "auto").strip().lower() or "auto"
            if eng not in ("auto", "freecad", "mesh"):
                eng = "auto"
            sheet_size = str(args.get("sheet_size") or "A3").strip().upper() or "A3"
            if sheet_size not in ("A3", "A1", "A0"):
                sheet_size = "A3"
            layout = str(args.get("layout") or "ga").strip().lower() or "ga"
            if layout not in ("ga", "quad"):
                layout = "ga"
            data = build_cad_drawing_pack(
                raw or None,
                file_id=fid,
                workspace_root=workspace_root,
                title=title,
                engine=eng,
                sheet_size=sheet_size,
                layout=layout,
            )
            client_actions.append(
                {
                    "type": "show_cad_drawing",
                    "sheet_url": data.get("sheet_url"),
                    "pdf_url": data.get("pdf_url"),
                    "manifest_url": data.get("manifest_url"),
                    "source_path": data.get("source_path"),
                    "drawing_id": data.get("drawing_id"),
                    "engine": data.get("engine"),
                    "view_svgs": data.get("view_svgs"),
                    "sheet_size": data.get("sheet_size"),
                    "layout": data.get("layout"),
                    "scale": data.get("scale"),
                    "pack": data.get("pack"),
                }
            )
            return (
                True,
                f"已生成工程图（{data.get('engine') or 'mesh'} · {data.get('scale') or ''}）· {data.get('source_path') or raw or fid}",
                {
                    "source_path": data.get("source_path"),
                    "drawing_id": data.get("drawing_id"),
                    "sheet_url": data.get("sheet_url"),
                    "pdf_url": data.get("pdf_url"),
                    "manifest_url": data.get("manifest_url"),
                    "engine": data.get("engine"),
                    "view_svgs": data.get("view_svgs"),
                    "sheet_size": data.get("sheet_size"),
                    "layout": data.get("layout"),
                    "scale": data.get("scale"),
                    "pack": data.get("pack"),
                },
            )

        if name == "export_design_deliverables":
            raw = str(args.get("input_path") or args.get("path") or args.get("inp_path") or "").strip()
            if not raw:
                return False, "input_path 不能为空", {}
            data = build_inp_design_deliverables(
                raw,
                workspace_root=workspace_root,
                runs_root=runs_root,
            )
            files = data.get("files") if isinstance(data.get("files"), dict) else {}
            client_actions.append(
                {
                    "type": "show_deliverables",
                    "pack_id": data.get("pack_id"),
                    "base_url": data.get("base_url"),
                    "files": files,
                    "source_path": data.get("source_path"),
                }
            )
            return True, f"已导出 design_space 交付物 · {data.get('source_path') or raw}", data

        if name == "get_design_checklist":
            from backend.design_requirements.clarifications import (
                build_pending_clarifications,
                checklist_context_block,
            )
            from backend.design_requirements.paths import load_checklist

            cid = str(args.get("checklist_id") or design_checklist_id or "").strip()
            if not cid:
                return False, "须提供 checklist_id 或会话已绑定设计清单", {}
            cl = load_checklist(cid)
            if cl is None:
                return False, f"设计清单不存在: {cid}", {}
            pending = build_pending_clarifications(cl.meta.source_text, cl)
            summary = checklist_context_block(cl)
            return (
                True,
                summary[:800],
                {
                    "checklist_id": cid,
                    "context_summary": summary,
                    "pending_clarifications": pending,
                    "clarification_complete": len(pending) == 0,
                },
            )

        if name == "update_design_checklist":
            from backend.design_requirements.clarifications import (
                apply_clarification_reply,
                build_pending_clarifications,
                checklist_context_block,
            )
            from backend.design_requirements.markdown import checklist_to_markdown
            from backend.design_requirements.paths import load_checklist, save_checklist

            cid = str(args.get("checklist_id") or design_checklist_id or "").strip()
            reply = str(args.get("reply") or args.get("text") or "").strip()
            mode = str(args.get("mode") or "edit").strip().lower() or "edit"
            if mode not in ("edit", "clarify"):
                mode = "edit"
            if not cid:
                return False, "须提供 checklist_id 或会话已绑定设计清单", {}
            if not reply:
                return False, "reply 不能为空", {}
            cl = load_checklist(cid)
            if cl is None:
                return False, f"设计清单不存在: {cid}", {}
            pending_ids = (
                [p["field_id"] for p in build_pending_clarifications(cl.meta.source_text, cl)]
                if mode == "clarify"
                else []
            )
            updated, _, remaining, updated_fields = apply_clarification_reply(
                cl, reply, pending_field_ids=pending_ids, mode=mode
            )
            if mode == "edit" and not updated_fields:
                return False, "未识别到可更新字段；请写明数值如「钢耗 280 t/MW」", {}
            md = checklist_to_markdown(updated)
            save_checklist(updated, markdown=md)
            client_actions.append(
                {
                    "type": "refresh_design_checklist",
                    "checklist_id": cid,
                    "checklist": updated.model_dump(mode="json"),
                    "pending_clarifications": remaining,
                    "clarification_complete": len(remaining) == 0,
                    "updated_fields": updated_fields,
                    "context_summary": checklist_context_block(updated),
                }
            )
            names = ", ".join(u["field_id"] for u in updated_fields) or "—"
            return (
                True,
                f"已更新设计清单字段: {names}",
                {
                    "checklist_id": cid,
                    "updated_fields": updated_fields,
                    "context_summary": checklist_context_block(updated),
                    "clarification_complete": len(remaining) == 0,
                },
            )

        # --- conversation-driven closed-loop pipeline tools ---
        from backend.pipeline import steps as pipe

        def _hint(data: dict[str, Any]) -> None:
            h = data.get("client_hint") if isinstance(data, dict) else None
            if isinstance(h, dict) and h.get("type"):
                client_actions.append(dict(h))

        if name in ("probe_execution", "probe_solvers"):
            data = pipe.step_probe_execution(requested_mode=args.get("mode"))
            return True, f"execution_mode={data.get('execution_mode')}", data

        if name == "set_execution_mode":
            data = pipe.step_set_execution_mode(str(args.get("mode") or "preview"))
            return True, f"execution_mode={data.get('execution_mode')}", data

        if name == "apply_turbine_preset":
            data = pipe.step_apply_turbine_preset(
                preset_id=args.get("preset_id") or args.get("mw") or "10",
                checklist_id=str(args.get("checklist_id") or design_checklist_id or "").strip() or None,
                session_id=str(args.get("session_id") or "").strip() or None,
                source_text=str(args.get("source_text") or "").strip() or None,
            )
            _hint(data)
            if data.get("checklist_id"):
                client_actions.append(
                    {"type": "refresh_design_checklist", "checklist_id": data["checklist_id"]}
                )
            return True, f"已应用 {data.get('preset', {}).get('label')}", data

        if name == "start_design_domain_session":
            data = pipe.step_start_design_domain_session(
                file_id=str(args.get("file_id") or "").strip() or None,
                source_path=str(args.get("source_path") or "").strip() or None,
                task_id=str(args.get("task_id") or "").strip() or None,
                design_checklist_id=str(args.get("checklist_id") or design_checklist_id or "").strip() or None,
                preset_id=str(args.get("preset_id") or "").strip() or None,
            )
            _hint(data)
            return True, f"设计域会话 {data.get('session_id')}", data

        if name == "run_design_domain_build":
            sid = str(args.get("session_id") or "").strip()
            if not sid:
                return False, "session_id 不能为空", {}
            data = pipe.step_run_design_domain_build(
                session_id=sid,
                cut_center_column=bool(args.get("cut_center_column", True)),
                include_source_geometry=bool(args.get("include_source_geometry", False)),
                run_mesh=bool(args.get("run_mesh", True)),
                run_loads=bool(args.get("run_loads", True)),
                finalize=bool(args.get("finalize", True)),
                pause_before_mesh=bool(args.get("pause_before_mesh", False)),
                execution_mode=str(args.get("execution_mode") or "").strip() or None,
            )
            _hint(data)
            ok = bool(data.get("ok", True))
            return ok, ("HITL 暂停于 mesh 前" if data.get("hitl") else "设计域构建完成"), data

        if name == "request_human_edit":
            sid = str(args.get("session_id") or "").strip()
            if not sid:
                return False, "session_id 不能为空", {}
            data = pipe.step_request_human_edit(
                session_id=sid,
                reason=str(args.get("reason") or "review_geometry"),
                message=str(args.get("message") or "").strip() or None,
            )
            _hint(data)
            return True, "已请求人为介入", data

        if name in ("apply_geometry_patch", "replace_geometry"):
            sid = str(args.get("session_id") or "").strip()
            if not sid:
                return False, "session_id 不能为空", {}
            data = pipe.step_replace_geometry(
                session_id=sid,
                source_path=str(args.get("source_path") or args.get("path") or "").strip() or None,
                file_id=str(args.get("file_id") or "").strip() or None,
                as_design_domain=bool(args.get("as_design_domain", True)),
                task_id=str(args.get("task_id") or "").strip() or None,
            )
            _hint(data)
            return True, "已替换几何并清除下游产物", data

        if name == "commit_preview_to_session":
            sid = str(args.get("session_id") or "").strip()
            prev = str(args.get("preview_path") or args.get("path") or "").strip()
            if not sid or not prev:
                return False, "session_id 与 preview_path 不能为空", {}
            data = pipe.step_commit_preview_to_session(
                session_id=sid,
                preview_stl_or_step=prev,
                task_id=str(args.get("task_id") or "").strip() or None,
            )
            _hint(data)
            return True, "已提交预览到设计域会话", data

        if name == "start_beso_job":
            data = pipe.step_start_beso_job(
                session_id=str(args.get("session_id") or "").strip() or None,
                scan_dir=str(args.get("scan_dir") or "").strip() or None,
                inp_path=str(args.get("inp_path") or "").strip() or None,
                design_checklist_id=str(args.get("checklist_id") or design_checklist_id or "").strip() or None,
                task_id=str(args.get("task_id") or "").strip() or None,
                message=str(args.get("message") or "conversation-driven BESO"),
                auto_start=bool(args.get("auto_start", True)),
                execution_mode=str(args.get("execution_mode") or "").strip() or None,
                mass_goal_ratio=(
                    float(args["mass_goal_ratio"]) if args.get("mass_goal_ratio") is not None else None
                ),
            )
            _hint(data)
            ok = bool(data.get("ok", True))
            return ok, ("BESO 已启动" if ok else str(data.get("error") or "BESO 未启动")), data

        if name == "parse_prism_design_brief":
            data = pipe.step_parse_prism_design_brief(text=str(args.get("text") or args.get("reply") or ""))
            return True, data.get("title") or "已解析棱柱参数", data

        if name == "start_prism_session":
            data = pipe.step_start_prism_session(
                text=str(args.get("text") or "").strip() or None,
                spec=args.get("spec") if isinstance(args.get("spec"), dict) else None,
                task_id=str(args.get("task_id") or "").strip() or None,
                design_checklist_id=str(args.get("checklist_id") or design_checklist_id or "").strip() or None,
            )
            _hint(data)
            return True, f"棱柱会话 {data.get('session_id')}", data

        if name == "build_prism_design_domain":
            sid = str(args.get("session_id") or "").strip()
            if not sid:
                return False, "session_id 不能为空", {}
            data = pipe.step_build_prism_design_domain(
                session_id=sid,
                execution_mode=str(args.get("execution_mode") or "").strip() or None,
            )
            ok = bool(data.get("ok", True))
            return ok, ("棱柱设计域已构建" if ok else str(data.get("error") or "构建失败")), data

        if name == "mesh_prism_design_domain":
            sid = str(args.get("session_id") or "").strip()
            if not sid:
                return False, "session_id 不能为空", {}
            data = pipe.step_mesh_prism_design_domain(
                session_id=sid,
                execution_mode=str(args.get("execution_mode") or "").strip() or None,
            )
            ok = bool(data.get("ok", True))
            return ok, ("棱柱网格已导出" if ok else str(data.get("error") or "网格失败")), data

        if name == "run_prism_topology_demo":
            text = str(args.get("text") or args.get("message") or args.get("reply") or "").strip()
            if not text:
                return False, "text 不能为空（用户提示词）", {}
            data = pipe.step_run_prism_topology_demo(
                text=text,
                task_id=str(args.get("task_id") or "").strip() or None,
                design_checklist_id=str(args.get("checklist_id") or design_checklist_id or "").strip() or None,
                start_beso=bool(args.get("start_beso", True)),
                auto_start=bool(args.get("auto_start", True)),
                execution_mode=str(args.get("execution_mode") or "").strip() or None,
            )
            _hint(data)
            ok = bool(data.get("ok", True))
            summary = (
                f"棱柱闭环已启动 job={data.get('job_id')}"
                if ok and data.get("job_id")
                else ("棱柱建域/网格完成" if ok else str(data.get("error") or "棱柱闭环失败"))
            )
            return ok, summary, data

        if name == "get_job_status":
            jid = str(args.get("job_id") or "").strip()
            if not jid:
                return False, "job_id 不能为空", {}
            data = pipe.step_get_job_status(job_id=jid)
            return True, f"status={data.get('status')}", data

        if name == "run_sizing":
            data = pipe.step_run_sizing(
                geometry_path=str(args.get("geometry_path") or "").strip() or None,
                job_id=str(args.get("job_id") or "").strip() or None,
                design_checklist_id=str(args.get("checklist_id") or design_checklist_id or "").strip() or None,
                target_power_mw=float(args["target_power_mw"]) if args.get("target_power_mw") is not None else None,
                out_dir=str(args.get("out_dir") or "").strip() or None,
            )
            return True, f"sizing @ {data.get('target_power_MW')} MW", data

        if name == "run_platform_restruction":
            from backend.tools.platform_restruction import run_platform_restruction

            tw = args.get("target_power_mw")
            if tw is None and design_checklist_id:
                from backend.design_requirements.paths import load_checklist

                cl = load_checklist(str(design_checklist_id))
                if cl is not None:
                    tw = float(cl.project.target_capacity_mw)
            if tw is None:
                tw = 20.0
            pitch = float(args.get("pitch_limit_deg") or 5.0)
            data = run_platform_restruction(float(tw), pitch_limit_deg=pitch)
            steel = data.get("steel_summary") or {}
            client_actions.append(
                {
                    "type": "enter_restruction",
                    "auto": "static" if bool(args.get("open_ui", True)) else None,
                    "target_power_mw": float(tw),
                    "pitch_limit_deg": pitch,
                    "message": "已完成平台库静力；正在打开尺寸时域分析。",
                }
            )
            return (
                True,
                f"尺寸时域·静力 @ {data.get('target_power_MW')} MW · "
                f"x={data.get('extra_scale_x')} · {steel.get('steel_intensity_t_per_MW')} t/MW",
                data,
            )

        if name == "run_zwind_eval":
            from backend.tools.zwind_eval import evaluate_zwind_bundle

            root = workspace_root
            jid = str(args.get("job_id") or "").strip()
            sid = str(args.get("session_id") or "").strip() or uuid.uuid4().hex[:16]
            if jid:
                run_dir = (root / "runs" / jid).resolve()
            else:
                run_dir = (root / "runs" / "_restruction" / sid).resolve()
            run_dir.mkdir(parents=True, exist_ok=True)
            data = evaluate_zwind_bundle(
                run_dir=run_dir,
                platform=str(args.get("platform") or "ai"),
            )
            client_actions.append(
                {
                    "type": "enter_restruction",
                    "auto": "zwind" if bool(args.get("open_ui", True)) else None,
                    "message": "已完成 Zwind 校核；正在打开尺寸时域分析。",
                }
            )
            hl = data.get("highlights") or {}
            return (
                True,
                f"zwind {data.get('mode')} · pitch={hl.get('extreme_pitch_deg')}° · "
                f"mooring={hl.get('max_mooring_tension_kn')} kN",
                data,
            )

        if name == "run_validation":
            data = pipe.step_run_validation(
                geometry_path=str(args.get("geometry_path") or args.get("sized_geometry_path") or "").strip() or None,
                design_checklist_id=str(args.get("checklist_id") or design_checklist_id or "").strip() or None,
                out_dir=str(args.get("out_dir") or "").strip() or None,
                use_llm_rationale=bool(args.get("use_llm_rationale", False)),
            )
            return True, f"validation S={data.get('overall_score')}", data

        if name == "evaluate_halt":
            data = pipe.step_evaluate_halt(
                validation_dir=str(args.get("validation_dir") or args.get("out_dir") or "").strip() or None,
                overall_score=float(args["overall_score"]) if args.get("overall_score") is not None else None,
                ai_review_scores=args.get("ai_review_scores") if isinstance(args.get("ai_review_scores"), dict) else None,
                design_checklist_id=str(args.get("checklist_id") or design_checklist_id or "").strip() or None,
                score=args.get("score") if isinstance(args.get("score"), dict) else None,
            )
            return True, "halt gate evaluated", data

        return False, f"未知工具: {name}", {}
    except Exception as e:
        logger.info("assistant tool %s failed: %s", name, e)
        return False, _sanitize(str(e), workspace_root), {}


def _artifacts_from_tool_extra(extra: dict[str, Any]) -> list[dict[str, Any]]:
    """从工具返回的 extra 中抽取可供前端展示的路径类产物。"""
    out: list[dict[str, Any]] = []
    if not isinstance(extra, dict):
        return out
    for key in (
        "step_path",
        "output_path",
        "runs_url",
        "scan_dir",
        "file",
        "sheet_url",
        "pdf_url",
        "manifest_url",
        "source_path",
        "drawing_id",
    ):
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
    design_checklist_id: str | None = None,
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
            design_checklist_id=design_checklist_id,
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
    design_checklist_id: str | None = None,
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
            design_checklist_id=design_checklist_id,
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
