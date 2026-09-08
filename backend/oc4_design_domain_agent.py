"""设计域会话内智能体：严格 JSON 协议 + 白名单工具，NDJSON 事件输出。

.. deprecated::
    默认由 ``backend.agents.design_domain_graph``（LangGraph + checkpoint）接管；
    设置 ``USE_LANGGRAPH_OC4_AGENT=false`` 可回退本模块。
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterator

from backend.oc4_methodology_chen2026 import LLM_CONTEXT_BLOCK_ZH
from backend.oc4_design_domain_service import (
    invalidate_oc4_downstream_from_rail_step,
    merge_session_meta,
    read_session_meta,
    run_build,
    run_export_obj,
    run_export_source_preview_only,
    run_loads,
    run_mesh,
    runs_file_url,
    session_dir,
    session_progress_flags,
)
from backend.qwen_client import QwenClient

MAX_AGENT_TURNS = 14

_PLAN_BUILD_ALLOWED = frozenset(
    {"run_export_source_preview", "run_build", "run_export_obj", "run_mesh", "run_loads"}
)

_PLAN_RAIL_TOPICS = ("design", "preview", "mesh", "loads")
# 匹配「1. xxx」「1、xxx」「**1.** xxx」等常见 Markdown 编号行
_PLAN_RAIL_LINE = re.compile(
    r"^\s*(?:[*#]{0,3}\s*)?(?:\*\*)?([1-4])(?:\*\*)?[\.\、．\:：\]）\)]\s*(.+)$"
)


def _complete_lines_for_rail_scan(text: str, *, finalize: bool) -> list[str]:
    if not text:
        return []
    lines = text.split("\n")
    if finalize:
        return [ln.strip() for ln in lines if ln.strip()]
    if len(lines) <= 1:
        return []
    return [ln.strip() for ln in lines[:-1] if ln.strip()]


def _iter_plan_rail_events_from_buffer(
    text: str,
    emitted: set[int],
    *,
    finalize: bool,
) -> Iterator[dict[str, Any]]:
    """从计划正文中按序解析 1～4 步，首次出现时下发 ``plan_rail_step``。"""
    for line in _complete_lines_for_rail_scan(text, finalize=finalize):
        m = _PLAN_RAIL_LINE.match(line)
        if not m:
            continue
        n = int(m.group(1))
        if n < 1 or n > 4 or n in emitted:
            continue
        emitted.add(n)
        topic = _PLAN_RAIL_TOPICS[n - 1]
        label = str(m.group(2) or "").strip()
        if len(label) > 220:
            label = label[:220] + "…"
        if not label:
            label = f"步骤 {n}"
        yield {"type": "plan_rail_step", "index": n, "topic": topic, "label": label}


def _yield_fallback_plan_rail_steps(emitted: set[int]) -> Iterator[dict[str, Any]]:
    defaults = (
        (
            "design",
            "步骤 1：在会话工作区构建设计域几何（源装配与设计域体），产出 STEP 等中间文件。",
        ),
        (
            "preview",
            "步骤 2：导出三角化 OBJ，用于中栏 3D 预览与几何尺度核对。",
        ),
        (
            "mesh",
            "步骤 3：基于设计域 STEP 生成体网格 INP，作为后续载荷划分的有限元模型。",
        ),
        (
            "loads",
            "步骤 4：写入载荷、约束与 *STEP/*CLOAD，生成面向 BESO 的载荷 INP（如 03_for_beso.inp）。",
        ),
    )
    for i, (topic, lab) in enumerate(defaults, start=1):
        if i in emitted:
            continue
        emitted.add(i)
        yield {"type": "plan_rail_step", "index": i, "topic": topic, "label": lab}


def _read_file_snippet(content: str, max_lines: int = 56, max_chars: int = 14_000) -> str:
    if not isinstance(content, str) or not content.strip():
        return ""
    lines = content.splitlines()
    head = "\n".join(lines[:max_lines])
    if len(head) > max_chars:
        return head[:max_chars] + "\n…(截断)"
    if len(lines) > max_lines:
        return head + f"\n…(共 {len(lines)} 行，仅展示前 {max_lines} 行)"
    return head


def _tool_result_payload(name: str, ok: bool, targs: dict[str, Any], summary: str, extra: dict[str, Any]) -> dict[str, Any]:
    """构造 tool_result 事件公共字段（含 list 预览与 read 片段）。"""
    tr: dict[str, Any] = {"type": "tool_result", "name": name, "ok": ok, "summary": summary}
    if ok and name == "list_files" and isinstance(extra.get("listing"), str):
        lst = str(extra["listing"])
        tr["paths_listed"] = len([x for x in lst.splitlines() if x.strip()])
        tr["listing_preview"] = lst[:8000]
    if ok and name == "read_file":
        rp = str(targs.get("path", "")).strip()
        if rp:
            tr["read_path"] = rp
        cont = extra.get("content")
        if isinstance(cont, str):
            tr["read_chars"] = len(cont)
            tr["content_snippet"] = _read_file_snippet(cont)
    if ok and name == "write_file":
        wp = str(extra.get("path") or targs.get("path", "")).strip()
        if wp:
            tr["write_path"] = wp
        tr["write_bytes"] = int(extra.get("bytes") or 0)
        ws = extra.get("written_snippet")
        if isinstance(ws, str) and ws.strip():
            tr["written_snippet"] = ws[:8000]
    if ok and name == "run_mesh" and isinstance(extra.get("replan_guided"), dict):
        tr["replan_guided"] = extra["replan_guided"]
    return tr


def _sse_line_to_delta_text(line: str) -> str | None:
    s = str(line or "").strip()
    if not s.startswith("data:"):
        return None
    data = s[5:].strip()
    if data == "[DONE]":
        return None
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    ch0 = choices[0] if isinstance(choices[0], dict) else {}
    delta = ch0.get("delta") if isinstance(ch0.get("delta"), dict) else {}
    piece = delta.get("content")
    return piece if isinstance(piece, str) and piece else None


def _iter_tool_file_touch_events(
    tool_name: str, ok: bool, sdir: Path, extra: dict[str, Any] | None = None
) -> Iterator[dict[str, Any]]:
    """根据工具执行结果，补充时间线「文件」卡片（避免漏计 OBJ/STEP 等）。"""
    if not ok:
        return
    t = str(tool_name or "").strip()
    if t == "run_export_source_preview":
        for rel in ("source_preview.obj", "00_source.step"):
            if (sdir / rel).is_file():
                yield {"type": "file", "path": rel, "action": "updated"}
        return
    if t == "run_build":
        for rel in ("01_design_domain.step", "01_design_domain.igs"):
            if (sdir / rel).is_file():
                yield {"type": "file", "path": rel, "action": "updated"}
        cn = str(read_session_meta(sdir).get("design_domain_compound_iges") or "").strip()
        if cn and (sdir / cn).is_file():
            yield {"type": "file", "path": cn, "action": "updated"}
        return
    if t == "run_export_obj":
        if (sdir / "design_preview.obj").is_file():
            yield {"type": "file", "path": "design_preview.obj", "action": "updated"}
        return
    if t == "run_mesh":
        if (sdir / "02_mesh_body.inp").is_file():
            yield {"type": "file", "path": "02_mesh_body.inp", "action": "updated"}
        return
    if t == "run_loads":
        if (sdir / "03_for_beso.inp").is_file():
            yield {"type": "file", "path": "03_for_beso.inp", "action": "updated"}
        return
    if t == "write_file" and isinstance(extra, dict):
        rp = str(extra.get("path") or "").strip().replace("\\", "/").lstrip("/")
        if rp and (sdir / rp).is_file():
            act = str(extra.get("action") or "updated").lower()
            yield {"type": "file", "path": rp, "action": "created" if act == "created" else "updated"}
        return


def _workspace_root() -> Path:
    import os

    return Path(os.environ.get("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[1]))).resolve()


def _path_ok(p: Path) -> bool:
    try:
        p.resolve().relative_to(_workspace_root())
        return True
    except ValueError:
        return False


def _get_session_dir(session_id: str) -> Path:
    if not session_id.isalnum() or len(session_id) < 16:
        raise ValueError("invalid session_id")
    s = session_dir(_workspace_root(), session_id)
    if not s.is_dir():
        raise FileNotFoundError("session not found")
    if not _path_ok(s):
        raise ValueError("invalid session path")
    return s


def _parse_json_object(text: str) -> dict[str, Any] | None:
    t = (text or "").strip().lstrip("\ufeff")
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", t, flags=re.IGNORECASE):
        b = block.strip()
        if b.startswith("{"):
            try:
                o = json.loads(b)
                return o if isinstance(o, dict) else None
            except json.JSONDecodeError:
                continue
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(t[i:])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
        # 尾部夹杂解释文字时，从首 { 起尝试匹配到各候选 } 的闭合 JSON
        for j in range(len(t) - 1, i, -1):
            if t[j] != "}":
                continue
            frag = t[i : j + 1].strip()
            if not frag.startswith("{"):
                continue
            try:
                obj, _ = dec.raw_decode(frag)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _normalize_agent_shape(data: dict[str, Any]) -> dict[str, Any]:
    """兼容模型偶发键名/嵌套，降低「无 tool」误报。"""
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    fr = out.get("final_reply")
    if fr is None:
        for k in ("finalReply", "reply", "answer", "message", "content"):
            v = out.get(k)
            if isinstance(v, str) and v.strip() and k != "thought":
                out["final_reply"] = v
                break
    tl = out.get("tool")
    if not isinstance(tl, dict):
        for k in ("call_tool", "tool_call", "call", "function"):
            v = out.get(k)
            if isinstance(v, dict) and str(v.get("name") or "").strip():
                out["tool"] = v
                break
    if isinstance(out.get("tool"), str) and str(out["tool"]).strip():
        out["tool"] = {
            "name": str(out["tool"]).strip(),
            "arguments": out["arguments"] if isinstance(out.get("arguments"), dict) else {},
        }
    if isinstance(out.get("tool"), dict):
        nm = str(out["tool"].get("name") or "").strip()
        if not nm and isinstance(out["tool"].get("tool"), str):
            out["tool"] = {
                "name": str(out["tool"].get("tool") or "").strip(),
                "arguments": out["tool"].get("arguments")
                if isinstance(out["tool"].get("arguments"), dict)
                else {},
            }
    return out


def _agent_turn_json_valid(data: dict[str, Any]) -> bool:
    fr = data.get("final_reply")
    if isinstance(fr, str) and fr.strip():
        return True
    tl = data.get("tool")
    return isinstance(tl, dict) and bool(str(tl.get("name") or "").strip())


_JSON_REPAIR_USER = (
    "上一条「助手」输出无法按约定解析为单个 JSON 对象（可能多了说明文字、少了引号或键名不一致）。\n"
    "请**只**输出一个合法 JSON（不要 Markdown 围栏、不要前后任何解释），键为：\n"
    '- "thought": string（可简短中文）；\n'
    '- 要么 "tool": {"name": string, "arguments": object}，\n'
    '- 要么 "final_reply": string（直接回答用户）。\n'
    "若用户要新建/修改说明类文件，优先用 write_file，path 为相对会话目录的路径（如 notes/summary.md）。"
)


def _list_files_summary(sdir: Path, max_depth: int = 8, max_lines: int = 120) -> str:
    lines: list[str] = []
    root = sdir.resolve()

    def walk(rel: Path, depth: int) -> None:
        if len(lines) >= max_lines:
            return
        cur = root / rel if rel != Path(".") else root
        try:
            items = sorted(cur.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        for item in items:
            if len(lines) >= max_lines:
                return
            name = item.name
            if name.startswith(".") or name in (".git", "__pycache__"):
                continue
            sub = rel / name if rel != Path(".") else Path(name)
            if item.is_dir():
                if depth < max_depth:
                    lines.append(f"[dir] {sub.as_posix()}/")
                    walk(sub, depth + 1)
            else:
                lines.append(f"{sub.as_posix()}")

    walk(Path("."), 0)
    return "\n".join(lines) if lines else "(空目录)"


def _read_text_file(sdir: Path, rel: str, max_bytes: int = 96 * 1024) -> str:
    raw = (rel or "").strip().replace("\\", "/").lstrip("/")
    if ".." in Path(raw).parts:
        raise ValueError("invalid path")
    target = (sdir / raw).resolve()
    target.relative_to(sdir.resolve())
    if not target.is_file():
        raise FileNotFoundError(rel)
    sz = int(target.stat().st_size)
    if sz > max_bytes:
        return target.read_text(encoding="utf-8", errors="replace")[:max_bytes] + f"\n…(截断，共 {sz} 字节)"
    return target.read_text(encoding="utf-8", errors="replace")


_MAX_SESSION_WRITE_BYTES = 512 * 1024


def _write_text_file(sdir: Path, rel: str, content: str) -> tuple[str, int]:
    """写入会话目录内文本文件。返回 (action created|updated, utf8_bytes)。"""
    raw = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not raw or ".." in Path(raw).parts:
        raise ValueError("invalid path")
    body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    b = body.encode("utf-8", errors="replace")
    if len(b) > _MAX_SESSION_WRITE_BYTES:
        raise ValueError(f"内容超过 {_MAX_SESSION_WRITE_BYTES} 字节")
    target = (sdir / raw).resolve()
    target.relative_to(sdir.resolve())
    existed = target.is_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b)
    return ("updated" if existed else "created"), len(b)


def _run_tool(
    name: str,
    args: dict[str, Any],
    *,
    sdir: Path,
    workspace_root: Path,
) -> tuple[bool, str, dict[str, Any]]:
    args = args if isinstance(args, dict) else {}
    try:
        if name == "list_files":
            depth = int(args.get("max_depth", 8))
            depth = max(1, min(depth, 14))
            text = _list_files_summary(sdir, max_depth=depth)
            return True, f"列出 {depth} 层内文件（摘要）。", {"listing": text[:8000]}
        if name == "read_file":
            rel = str(args.get("path", "")).strip()
            content = _read_text_file(sdir, rel)
            return True, f"已读 {rel}", {"path": rel, "content": content[:120_000]}
        if name == "write_file":
            rel = str(args.get("path", "")).strip()
            if args.get("content") is None and args.get("body") is not None:
                raw_body = args.get("body")
            else:
                raw_body = args.get("content")
            if raw_body is None:
                return False, "write_file 需要 content（或 body）", {}
            if isinstance(raw_body, (dict, list)):
                body = json.dumps(raw_body, ensure_ascii=False, indent=2)
            else:
                body = str(raw_body)
            action, nbytes = _write_text_file(sdir, rel, body)
            snip = body[:4000] + ("…" if len(body) > 4000 else "")
            return True, f"已{('覆盖' if action == 'updated' else '新建')} {rel}（{nbytes} 字节）", {
                "path": rel.replace("\\", "/").lstrip("/"),
                "action": action,
                "bytes": nbytes,
                "written_snippet": snip,
            }
        if name == "run_build":
            from backend.tools.oc4_design_domain_iges import coerce_corner_r_mm, coerce_length_r_mm

            corner = coerce_corner_r_mm(
                args.get("corner_r_mm", args.get("corner_radius_mm", args.get("digout_r_mm")))
            )
            if corner is None:
                # 兼容模型把米写进 corner_r_m
                corner = coerce_corner_r_mm(args.get("corner_r_m"), unit_hint="m")
            center_hole = coerce_length_r_mm(
                args.get(
                    "center_hole_r_mm",
                    args.get("center_r_mm", args.get("center_hole_radius_mm")),
                )
            )
            if center_hole is None:
                center_hole = coerce_length_r_mm(args.get("center_hole_r_m"), unit_hint="m")
            meta_now = read_session_meta(sdir)
            if corner is None:
                corner = coerce_corner_r_mm(meta_now.get("corner_r_mm"))
            if center_hole is None:
                center_hole = coerce_length_r_mm(meta_now.get("center_hole_r_mm"))
            out = run_build(
                sdir,
                cut_center_column=bool(args.get("cut_center_column", True)),
                include_source_geometry=bool(args.get("include_source_geometry", False)),
                domain_envelope=str(args.get("domain_envelope") or meta_now.get("domain_envelope") or "triangle_prism"),
                corner_r_mm=corner,
                center_hole_r_mm=center_hole,
            )
            # 01 已变，旧 02/03 与几何脱节；必须失效，避免预览仍打开过期 03_for_beso.inp
            try:
                inv = invalidate_oc4_downstream_from_rail_step(sdir, rail_step=2)
            except Exception:
                inv = {}
            msg = "run_build 完成"
            bits = []
            if out.get("corner_r_mm") is not None:
                bits.append(f"边立柱挖去 R={float(out['corner_r_mm']) / 1000.0:.3g} m")
            if out.get("center_hole_r_mm") is not None:
                bits.append(f"中心孔 R={float(out['center_hole_r_mm']) / 1000.0:.3g} m")
            if bits:
                msg += "（" + " · ".join(bits) + "）"
            removed = inv.get("removed") if isinstance(inv, dict) else None
            if removed:
                msg += f"；已清除过期 {', '.join(str(x) for x in removed[:6])}"
            return True, msg, {"result": out, "invalidated": inv}
        if name == "run_export_source_preview":
            urls = run_export_source_preview_only(
                sdir,
                workspace_root,
                linear_source=float(args.get("linear_deflection_source", 1200.0)),
            )
            return True, "源几何 OBJ 预览已导出", {"urls": urls}
        if name == "run_export_obj":
            urls = run_export_obj(
                sdir,
                workspace_root,
                linear_source=float(args.get("linear_deflection_source", 1200.0)),
                linear_design=float(args.get("linear_deflection_design", 800.0)),
                design_only=bool(args.get("design_only", False)),
            )
            return True, "OBJ 导出完成", {"urls": urls}
        if name == "run_mesh":
            tout = args.get("timeout_minutes")
            timeout_s = float(tout) * 60.0 if tout is not None and float(tout) > 0 else None
            out = run_mesh(
                sdir,
                char_length_max=args.get("characteristic_length_max"),
                char_length_min=args.get("characteristic_length_min"),
                element_order=args.get("element_order"),
                mesh_size_from_curvature=args.get("mesh_size_from_curvature"),
                compound_part_strategy=args.get("compound_part_strategy"),
                element_dimension=args.get("element_dimension"),
                geometry_tolerance=args.get("geometry_tolerance"),
                optimize_std=args.get("optimize_std"),
                length_unit=args.get("length_unit"),
                timeout_s=timeout_s,
            )
            url = runs_file_url(workspace_root, Path(out["mesh_inp"]))
            return True, "体网格已生成 02_mesh_body.inp", {"mesh_inp_url": url, **out}
        if name == "run_loads":
            meta = read_session_meta(sdir)
            checklist_id = args.get("design_checklist_id") or meta.get("design_checklist_id")
            band_scale = args.get("band_scale")
            z_fix_band = args.get("z_fix_band")
            cload_mag = args.get("cload_mag")
            nl = str(args.get("loads_natural_language")).strip() if args.get("loads_natural_language") else None
            load_case = args.get("load_case") if isinstance(args.get("load_case"), dict) else None
            if not load_case and isinstance(meta.get("preferred_load_case"), dict):
                load_case = dict(meta["preferred_load_case"])
            elif not load_case and meta.get("preferred_force_direction"):
                from backend.tools.oc4_force_direction import merge_force_direction_into_load_case

                load_case = merge_force_direction_into_load_case(
                    None,
                    str(meta.get("preferred_force_direction")),
                    total_force_n=float(cload_mag) if cload_mag is not None else None,
                )
            if checklist_id and not nl:
                from backend.design_requirements.paths import load_checklist

                cl = load_checklist(str(checklist_id))
                if cl is not None:
                    oc4 = cl.job_descriptor.theta.oc4_loads
                    if band_scale is None:
                        band_scale = oc4.band_scale
                    if z_fix_band is None:
                        z_fix_band = oc4.z_fix_band
                    if cload_mag is None and (not load_case or load_case.get("cload_mag") is None):
                        cload_mag = oc4.cload_mag
            if cload_mag is None and isinstance(load_case, dict) and load_case.get("cload_mag") is not None:
                cload_mag = load_case.get("cload_mag")
            out = run_loads(
                sdir,
                band_scale=float(band_scale if band_scale is not None else 1.22),
                z_fix_band=float(z_fix_band if z_fix_band is not None else 800.0),
                cload_mag=float(cload_mag if cload_mag is not None else -5.0e6),
                load_case=load_case,
                loads_natural_language=nl,
                design_checklist_id=str(checklist_id) if checklist_id else None,
            )
            url = runs_file_url(workspace_root, Path(out["final_inp"]))
            return True, "载荷划分完成 03_for_beso.inp", {"final_inp_url": url, **{k: v for k, v in out.items() if k != "stats"}}
        if name == "finalize":
            fin = sdir / "03_for_beso.inp"
            if not fin.is_file():
                return False, "缺少 03_for_beso.inp，无法 finalize", {}
            import os

            ccx = Path(os.environ.get("CCX_PATH", r"D:\freecad\bin\ccx.exe")).resolve()
            from backend.replan.checklist_bridge import beso_theta_defaults_from_checklist, load_checklist_from_session
            from backend.tools.inp_oc4_design_nondesign import write_beso_conf_example3_style

            meta_fin = read_session_meta(sdir)
            task_hint = str(meta_fin.get("task_id") or "").strip()
            if task_hint:
                try:
                    from backend.orchestrator.gates import evaluate_transition
                    from backend.orchestrator.state import load_workflow_state

                    st = load_workflow_state(task_hint, oc4_session_id=session_id)
                    verdict = evaluate_transition(st, "phase_ii_finalize")
                    if not verdict.ok:
                        return False, verdict.reason or "相位闸阻止 finalize（ρₚ≠0）", {}
                except Exception:
                    pass
            checklist = load_checklist_from_session(sdir)
            if checklist is None and meta_fin.get("design_checklist_id"):
                from backend.design_requirements.paths import load_checklist

                checklist = load_checklist(str(meta_fin.get("design_checklist_id")))
            beso_theta = beso_theta_defaults_from_checklist(checklist)
            write_beso_conf_example3_style(
                sdir / "beso_conf.py",
                work_dir=sdir.resolve(),
                ccx_path=ccx,
                inp_name="03_for_beso.inp",
                mass_goal_ratio=float(beso_theta["mass_goal_ratio"]),
                filter_radius=float(beso_theta["filter_radius"]),
                optimization_base=str(beso_theta["optimization_base"]),
            )
            scan_dir = str(sdir.resolve())
            merge_session_meta(
                sdir,
                {
                    "scan_dir": scan_dir,
                    "finalized": True,
                    "beso_defaults_ref": beso_theta.get("source")
                    or "Chen et al. (2026) Ocean Engineering 347: stiffness TO, mass_goal_ratio=0.15",
                    "beso_theta": {
                        "mass_goal_ratio": beso_theta["mass_goal_ratio"],
                        "filter_radius": beso_theta["filter_radius"],
                        "optimization_base": beso_theta["optimization_base"],
                    },
                    "design_checklist_id": beso_theta.get("checklist_id") or meta_fin.get("design_checklist_id"),
                },
            )
            return (
                True,
                f"finalize 完成 scan_dir={scan_dir} · BESO θ from {beso_theta.get('source')}",
                {
                    "scan_dir": scan_dir,
                    "beso_theta": {
                        "mass_goal_ratio": beso_theta["mass_goal_ratio"],
                        "filter_radius": beso_theta["filter_radius"],
                        "optimization_base": beso_theta["optimization_base"],
                        "source": beso_theta.get("source"),
                    },
                    "design_checklist_id": beso_theta.get("checklist_id") or meta_fin.get("design_checklist_id"),
                },
            )
        return False, f"未知工具: {name}", {}
    except Exception as e:
        return False, f"{name} 失败: {e}", {}


def _design_domain_agent_model() -> str | None:
    """进程内 Qwen 配置优先；可用环境变量 QWEN_DESIGN_DOMAIN_MODEL 覆盖（便于与设计域专用模型对齐）。"""
    import os

    env = (os.environ.get("QWEN_DESIGN_DOMAIN_MODEL") or "").strip()
    if env:
        return env
    return None


def _user_wants_more_after_corner(user_message: str) -> bool:
    """改挖角之外是否还点名网格/载荷/约束等后续步骤。"""
    t = str(user_message or "")
    return bool(
        re.search(
            r"网格|mesh|体网格|载荷|荷载|loads?|划荷|约束|固定|boundary|cload|"
            r"finalize|收尾|划分|BESO\s*inp|03_for_beso|方向|幅值",
            t,
            flags=re.IGNORECASE,
        )
    )


def iter_apply_corner_radius_events(
    sdir: Path,
    *,
    workspace_root: Path,
    corner_r_mm: float | None = None,
    center_hole_r_mm: float | None = None,
) -> Iterator[dict[str, Any]]:
    """
    确定性执行：run_build → run_export_obj → run_mesh → run_loads。
    边立柱/中心孔一变，01/02/03 必须同步重生，否则网格预览仍显示旧约束与荷载。
    只改用户点名的参数；未点名的半径沿用会话 meta，互不耦合。
    """
    from backend.tools.oc4_design_domain_iges import coerce_corner_r_mm, coerce_length_r_mm

    patch: dict[str, Any] = {}
    build_args: dict[str, Any] = {}
    notes: list[str] = []
    if corner_r_mm is not None:
        cr = float(corner_r_mm)
        patch.update({"corner_r_mm": cr, "corner_r_m": cr / 1000.0})
        build_args["corner_r_mm"] = cr
        notes.append(f"边立柱挖去半径 {cr / 1000.0:.3g} m（{cr:.0f} mm）")
    if center_hole_r_mm is not None:
        ch = float(center_hole_r_mm)
        patch.update({"center_hole_r_mm": ch, "center_hole_r_m": ch / 1000.0})
        build_args["center_hole_r_mm"] = ch
        notes.append(f"中心孔半径 {ch / 1000.0:.3g} m（{ch:.0f} mm）")
    if not build_args:
        return
    if patch:
        merge_session_meta(sdir, patch)
    yield {
        "type": "activity",
        "kind": "exec",
        "text": (
            f"已解析{' · '.join(notes)}，正在重建设计域，并同步重生体网格与载荷划分"
            "（中心孔与边立柱半径相互独立）…"
        ),
    }
    yield {"type": "tool", "name": "run_build", "args": build_args}
    ok_b, sum_b, extra_b = _run_tool("run_build", build_args, sdir=sdir, workspace_root=workspace_root)
    yield _tool_result_payload("run_build", ok_b, build_args, sum_b, extra_b)
    for fe in _iter_tool_file_touch_events("run_build", ok_b, sdir, extra_b):
        yield fe
    if not ok_b:
        yield {
            "type": "assistant",
            "text": f"重建设计域失败：{sum_b}。请检查源几何后重试。",
        }
        return

    exp_args: dict[str, Any] = {"design_only": True}
    yield {
        "type": "activity",
        "kind": "exec",
        "text": "设计域已重建，正在导出 design_preview.obj…",
    }
    yield {"type": "tool", "name": "run_export_obj", "args": exp_args}
    ok_e, sum_e, extra_e = _run_tool("run_export_obj", exp_args, sdir=sdir, workspace_root=workspace_root)
    yield _tool_result_payload("run_export_obj", ok_e, exp_args, sum_e, extra_e)
    for fe in _iter_tool_file_touch_events("run_export_obj", ok_e, sdir, extra_e):
        yield fe

    mesh_args: dict[str, Any] = {}
    yield {
        "type": "activity",
        "kind": "exec",
        "text": "几何已变，正在重新划分体网格 02_mesh_body.inp…",
    }
    yield {"type": "tool", "name": "run_mesh", "args": mesh_args}
    ok_m, sum_m, extra_m = _run_tool("run_mesh", mesh_args, sdir=sdir, workspace_root=workspace_root)
    yield _tool_result_payload("run_mesh", ok_m, mesh_args, sum_m, extra_m)
    for fe in _iter_tool_file_touch_events("run_mesh", ok_m, sdir, extra_m):
        yield fe
    if not ok_m:
        yield {
            "type": "assistant",
            "text": f"设计域已重建，但体网格失败：{sum_m}。请调整网格参数后重试；03_for_beso.inp 尚未更新。",
        }
        return

    loads_args: dict[str, Any] = {}
    yield {
        "type": "activity",
        "kind": "exec",
        "text": "正在按当前约束/荷载偏好重写 03_for_beso.inp…",
    }
    yield {"type": "tool", "name": "run_loads", "args": loads_args}
    ok_l, sum_l, extra_l = _run_tool("run_loads", loads_args, sdir=sdir, workspace_root=workspace_root)
    yield _tool_result_payload("run_loads", ok_l, loads_args, sum_l, extra_l)
    for fe in _iter_tool_file_touch_events("run_loads", ok_l, sdir, extra_l):
        yield fe

    meta_after = read_session_meta(sdir)
    res = extra_b.get("result") if isinstance(extra_b, dict) else None
    applied_corner = None
    applied_center = None
    if isinstance(res, dict):
        try:
            if res.get("corner_r_mm") is not None:
                applied_corner = float(res["corner_r_mm"])
        except (TypeError, ValueError):
            applied_corner = None
        try:
            if res.get("center_hole_r_mm") is not None:
                applied_center = float(res["center_hole_r_mm"])
        except (TypeError, ValueError):
            applied_center = None
    if applied_corner is None:
        applied_corner = coerce_corner_r_mm(meta_after.get("corner_r_mm"))
    if applied_center is None:
        applied_center = coerce_length_r_mm(meta_after.get("center_hole_r_mm"))

    parts: list[str] = []
    if corner_r_mm is not None and applied_corner is not None:
        note = ""
        if abs(applied_corner - float(corner_r_mm)) > 1.0:
            note = f"（已钳制；请求 {float(corner_r_mm)/1000.0:.3g} m）"
        parts.append(f"边立柱挖去 R={applied_corner/1000.0:.3g} m{note}")
    if center_hole_r_mm is not None and applied_center is not None:
        parts.append(f"中心孔 R={applied_center/1000.0:.3g} m")
    elif corner_r_mm is not None and applied_center is not None:
        parts.append(f"中心孔保持 R={applied_center/1000.0:.3g} m（未改）")

    summary_txt = "、".join(parts) if parts else "几何参数"
    tail_bits: list[str] = []
    if ok_e:
        tail_bits.append("design_preview.obj")
    if ok_m:
        tail_bits.append("02_mesh_body.inp")
    if ok_l:
        tail_bits.append("03_for_beso.inp")
    refreshed = "、".join(tail_bits) if tail_bits else "部分产物"
    if ok_l:
        yield {
            "type": "assistant",
            "text": (
                f"已更新：{summary_txt}，并同步刷新 {refreshed}。"
                "请在左侧重新打开「网格预览 · 03_for_beso.inp」查看约束与荷载。"
            ),
        }
    elif ok_m:
        yield {
            "type": "assistant",
            "text": f"已更新：{summary_txt}，体网格已重生，但载荷划分失败：{sum_l}。",
        }
    elif ok_e:
        yield {
            "type": "assistant",
            "text": f"已更新：{summary_txt}，并刷新 design_preview.obj；网格/载荷未完成。",
        }
    else:
        yield {
            "type": "assistant",
            "text": f"设计域已按 {summary_txt} 重建，但 OBJ 导出失败：{sum_e}。",
        }


def iter_design_domain_agent_events(session_id: str, user_message: str) -> Iterator[dict[str, Any]]:
    ws = _workspace_root()
    try:
        sdir = _get_session_dir(session_id)
    except Exception as e:
        yield {"type": "error", "message": str(e)}
        yield {"type": "done", "ok": False}
        return

    qwen = QwenClient(model=_design_domain_agent_model())
    if not qwen.api_key:
        yield {"type": "error", "message": "未配置 QWEN_API_KEY"}
        yield {"type": "done", "ok": False}
        return

    yield {"type": "meta", "model": qwen.model, "protocol": "json_tool_loop"}

    from backend.tools.oc4_design_domain_iges import (
        coerce_corner_r_mm,
        coerce_length_r_mm,
        parse_center_hole_r_mm_from_text,
        parse_corner_r_mm_from_text,
    )

    parsed_corner_early = parse_corner_r_mm_from_text(user_message)
    parsed_center_early = parse_center_hole_r_mm_from_text(user_message)
    if parsed_corner_early is not None or parsed_center_early is not None:
        apply_ok = True
        for ev in iter_apply_corner_radius_events(
            sdir,
            workspace_root=ws,
            corner_r_mm=float(parsed_corner_early) if parsed_corner_early is not None else None,
            center_hole_r_mm=float(parsed_center_early) if parsed_center_early is not None else None,
        ):
            if ev.get("type") == "tool_result" and ev.get("name") in {
                "run_build",
                "run_mesh",
                "run_loads",
            } and not ev.get("ok"):
                apply_ok = False
            yield ev
        if not _user_wants_more_after_corner(user_message):
            yield {"type": "done", "ok": apply_ok}
            return

    meta = read_session_meta(sdir)
    summ = meta.get("geometry_summary") or {}
    prog = session_progress_flags(sdir)
    files_snip = _list_files_summary(sdir, max_depth=6, max_lines=80)

    system = (
        "你是 OC4 设计域会话内的执行智能体。你必须通过工具完成构建、导出、网格、载荷与收尾；"
        "不要编造文件路径。每次回复必须是**一个** JSON 对象（不要 Markdown 围栏），键如下：\n"
        '- "thought": string，简短中文思考；\n'
        '- 若需调用工具: "tool": {"name": string, "arguments": object}；\n'
        '- 若已可回答用户、无需再调工具: "final_reply": string。\n'
        "允许的工具名：list_files, read_file, write_file, run_build, run_export_source_preview, run_export_obj, "
        "run_mesh, run_loads, finalize。\n"
        "write_file：在会话目录内新建或覆盖说明类/配置类小文件，arguments 含 path（相对路径）、content（字符串）。"
        f"单文件不超过 {_MAX_SESSION_WRITE_BYTES // 1024}KB。\n"
        "规则：先 list_files / read_file 再改；mesh 前需已有 01_design_domain.step；loads 前需 02_mesh_body.inp；"
        "finalize 前需 03_for_beso.inp。管线内部固定使用 01_design_domain.step / 01_design_domain.igs；"
        "run_build 默认按 **beso9 式等边三棱柱**生成设计域（三顶角通高圆柱挖孔 + 可选中心孔），"
        "并另存 `{upload_cad_stem}-Compound.iges`；体网格仍读 01_design_domain.step。\n"
        "**几何参数（必须真正调用工具，禁止只口头答应；两类半径相互独立）：**\n"
        "- corner_r_mm：**边立柱/三顶角边缘挖去**半径（mm）。用户说「边立柱半径 15m」→ 15000。"
        "只改边立柱时**不要**改 center_hole_r_mm。\n"
        "- center_hole_r_mm：**中间/中心圆孔**半径（mm）。用户说「中心孔 5m」→ 5000。"
        "只改中心孔时**不要**改 corner_r_mm。\n"
        "- 改任一半径后：run_build（只带被改参数）→ run_export_obj({\"design_only\":true})"
        "→ run_mesh → run_loads（01 变则 02/03 必须重生，否则预览仍是旧约束/荷载）。\n"
        "- domain_envelope：triangle_prism（默认）或 hull_bbox。\n"
        "用户一句话可能要求多步，请分轮调用工具。\n"
        f"当前进度标记: {json.dumps(prog, ensure_ascii=False)}\n"
        f"会话已存 corner_r_mm: {json.dumps(meta.get('corner_r_mm'), ensure_ascii=False)}；"
        f"center_hole_r_mm: {json.dumps(meta.get('center_hole_r_mm'), ensure_ascii=False)}\n"
        f"几何摘要: {json.dumps(summ, ensure_ascii=False)[:4000]}\n"
        f"文件树摘要:\n{files_snip[:6000]}\n\n{LLM_CONTEXT_BLOCK_ZH}"
    )

    parsed_corner = parsed_corner_early
    if parsed_corner is not None or parsed_center_early is not None:
        bits = []
        if parsed_corner is not None:
            bits.append(f"边立柱挖去={parsed_corner:.0f} mm")
        if parsed_center_early is not None:
            bits.append(f"中心孔={parsed_center_early:.0f} mm")
        system += (
            f"\n【系统已执行】{' · '.join(bits)}，design_preview.obj / 02_mesh_body.inp / 03_for_beso.inp 已按新几何重生。"
            "请勿重复仅改同一半径的 run_build；若用户还要求改约束/荷载，再调用 run_loads。\n"
        )

    history: list[dict[str, str]] = []
    user0 = user_message.strip()
    if not user0:
        yield {"type": "error", "message": "message 为空"}
        yield {"type": "done", "ok": False}
        return

    tools_ran = parsed_corner_early is not None or parsed_center_early is not None
    for turn in range(MAX_AGENT_TURNS):
        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        if turn == 0:
            messages.append({"role": "user", "content": user0})
        else:
            messages.append({"role": "user", "content": "继续：根据工具结果决定下一步（仍只输出一个 JSON）。"})

        yield {"type": "thinking_start"}
        try:
            resp = qwen.chat(messages, temperature=0.15)
            content = resp["choices"][0]["message"]["content"]
        except Exception as e:
            yield {"type": "error", "message": f"模型调用失败: {e}"}
            yield {"type": "done", "ok": False}
            return

        data = _normalize_agent_shape(_parse_json_object(content) or {})
        if not _agent_turn_json_valid(data) and (content or "").strip():
            try:
                repair_messages = [
                    *messages,
                    {"role": "assistant", "content": (content or "")[:12_000]},
                    {"role": "user", "content": _JSON_REPAIR_USER},
                ]
                resp2 = qwen.chat(repair_messages, temperature=0.05)
                content2 = resp2["choices"][0]["message"]["content"]
                data = _normalize_agent_shape(_parse_json_object(content2) or {})
            except Exception:
                pass

        thought = str(data.get("thought") or "").strip()
        if thought:
            yield {"type": "thinking", "text": thought}

        fr = data.get("final_reply")
        if isinstance(fr, str) and fr.strip():
            if parsed_corner is not None and not tools_ran:
                nudge = (
                    f"用户已明确要求改顶角挖去半径为 {parsed_corner/1000:.3g} m。"
                    f"请立即输出 tool.run_build，arguments 含 corner_r_mm={parsed_corner:.0f}，"
                    "然后再 run_export_obj(design_only=true)。不要 final_reply。"
                )
                yield {
                    "type": "activity",
                    "kind": "plan",
                    "text": "检测到几何修改意图但尚未调用工具，已催促模型执行 run_build…",
                }
                history.append({"role": "assistant", "content": (content or "")[:8000]})
                history.append({"role": "user", "content": nudge})
                continue
            yield {"type": "assistant", "text": fr.strip()}
            yield {"type": "done", "ok": True}
            return

        tool = data.get("tool")
        if not isinstance(tool, dict) or not str(tool.get("name") or "").strip():
            yield {"type": "error", "message": "模型未给出 tool 或 final_reply"}
            yield {"type": "done", "ok": False}
            return

        tname = str(tool.get("name") or "").strip()
        targs = tool.get("arguments") if isinstance(tool.get("arguments"), dict) else {}
        if tname == "run_build":
            targs = dict(targs)
            if parsed_corner is not None and coerce_corner_r_mm(targs.get("corner_r_mm", targs.get("corner_r_m"))) is None:
                targs["corner_r_mm"] = float(parsed_corner)
            if parsed_center_early is not None and coerce_length_r_mm(
                targs.get("center_hole_r_mm", targs.get("center_hole_r_m"))
            ) is None:
                targs["center_hole_r_mm"] = float(parsed_center_early)
        yield {
            "type": "activity",
            "kind": "exec",
            "text": f"准备执行工具 · {tname}…",
        }
        yield {"type": "tool", "name": tname, "args": targs}

        ok, summary, extra = _run_tool(tname, targs, sdir=sdir, workspace_root=ws)
        tools_ran = True
        yield _tool_result_payload(tname, ok, targs, summary, extra)

        for fe in _iter_tool_file_touch_events(tname, ok, sdir, extra):
            yield fe

        hist_tool = json.dumps({"name": tname, "arguments": targs}, ensure_ascii=False)
        hist_res = json.dumps({"ok": ok, "summary": summary, **extra}, ensure_ascii=False)[:24_000]
        history.append({"role": "assistant", "content": json.dumps(data, ensure_ascii=False)[:12_000]})
        history.append({"role": "user", "content": f"工具结果:\n{hist_res}"})

    yield {"type": "error", "message": f"超过最大轮数 {MAX_AGENT_TURNS}"}
    yield {"type": "done", "ok": False}


def _default_plan_build_steps(
    cut_center_column: bool,
    include_source_geometry: bool,
    *,
    corner_r_mm: float | None = None,
    load_case: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """与四步管线对齐的全流程：源预览 → 设计域 → 设计 OBJ → 体网格 → 载荷 INP。"""
    build_args: dict[str, Any] = {
        "cut_center_column": cut_center_column,
        "include_source_geometry": include_source_geometry,
        "domain_envelope": "triangle_prism",
    }
    if corner_r_mm is not None and float(corner_r_mm) > 0:
        build_args["corner_r_mm"] = float(corner_r_mm)
    loads_args: dict[str, Any] = {}
    if isinstance(load_case, dict) and load_case:
        loads_args["load_case"] = dict(load_case)
        if load_case.get("cload_mag") is not None:
            loads_args["cload_mag"] = float(load_case["cload_mag"])
    return [
        {
            "id": 1,
            "tool": "run_export_source_preview",
            "title": "1 源几何 OBJ 预览",
            "arguments": {},
        },
        {
            "id": 2,
            "tool": "run_build",
            "title": "2 构建设计域 STEP + Compound IGES",
            "arguments": build_args,
        },
        {
            "id": 3,
            "tool": "run_export_obj",
            "title": "3 导出设计域 OBJ",
            "arguments": {"design_only": True},
        },
        {
            "id": 4,
            "tool": "run_mesh",
            "title": "4 FreeCAD 体网格",
            "arguments": {},
        },
        {
            "id": 5,
            "tool": "run_loads",
            "title": "5 划分载荷 INP",
            "arguments": loads_args,
        },
    ]


def _normalize_plan_steps(
    raw: Any,
    *,
    cut_center_column: bool,
    include_source_geometry: bool,
    corner_r_mm: float | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        return _default_plan_build_steps(
            cut_center_column, include_source_geometry, corner_r_mm=corner_r_mm
        )
    out: list[dict[str, Any]] = []
    for i, it in enumerate(raw):
        if not isinstance(it, dict):
            continue
        tool = str(it.get("tool") or "").strip()
        if tool not in _PLAN_BUILD_ALLOWED:
            continue
        title = str(it.get("title") or tool).strip() or tool
        args = it.get("arguments") if isinstance(it.get("arguments"), dict) else {}
        merged = dict(args)
        if tool == "run_build":
            merged.setdefault("cut_center_column", cut_center_column)
            merged.setdefault("include_source_geometry", include_source_geometry)
            merged.setdefault("domain_envelope", "triangle_prism")
            if corner_r_mm is not None and float(corner_r_mm) > 0:
                merged.setdefault("corner_r_mm", float(corner_r_mm))
        if tool == "run_export_obj":
            merged.setdefault("design_only", True)
        out.append({"id": int(it.get("id") or i + 1), "tool": tool, "title": title, "arguments": merged})
    return out if out else _default_plan_build_steps(
        cut_center_column, include_source_geometry, corner_r_mm=corner_r_mm
    )


def _cad_for_mesh_estimate(sdir: Path) -> Path:
    for name in ("01_design_domain.step", "00_source.step", "00_source.igs", "00_source.iges"):
        p = sdir / name
        if p.is_file():
            return p
    return sdir / "01_design_domain.step"


def _resolve_mesh_cl_max(sdir: Path, mesh_preset: str, mesh_custom: float | None) -> float | None:
    """Gmsh CharacteristicLengthMax（mm）：越大越粗。返回 None 表示不在 JSON 中强制，交给 run_mesh 默认启发式。"""
    mp = (mesh_preset or "balanced").strip().lower()
    cad = _cad_for_mesh_estimate(sdir)
    try:
        from backend.tools.cad_iges_to_inp import default_coarse_char_length_max
    except ImportError:
        from backend.tools.freecad_iges_to_inp import default_coarse_char_length_max

    if cad.is_file():
        base = float(default_coarse_char_length_max(cad))
    else:
        base = 600.0
    if mp == "custom":
        if mesh_custom is None or float(mesh_custom) <= 0:
            return None
        return max(50.0, min(35000.0, float(mesh_custom)))
    mult = {"coarse": 1.45, "balanced": 1.0, "fine": 0.82, "finer": 0.65}.get(mp, 1.0)
    return max(50.0, min(35000.0, base * mult))


def _merge_mesh_into_steps(steps: list[dict[str, Any]], mesh_cl: float | None) -> list[dict[str, Any]]:
    if mesh_cl is None:
        return steps
    out: list[dict[str, Any]] = []
    for st in steps:
        if not isinstance(st, dict):
            continue
        row = dict(st)
        if str(row.get("tool") or "").strip() == "run_mesh":
            args = dict(row.get("arguments") or {})
            args["characteristic_length_max"] = float(mesh_cl)
            row["arguments"] = args
        out.append(row)
    return out


def _extract_chat_message_text(resp: dict[str, Any]) -> str:
    try:
        ch0 = (resp.get("choices") or [{}])[0]
        if not isinstance(ch0, dict):
            return ""
        msg = ch0.get("message") if isinstance(ch0.get("message"), dict) else {}
        c = msg.get("content")
        return str(c or "").strip()
    except Exception:
        return ""


def _plan_build_llm_timeout_s() -> float:
    """Plan-Build 可选 LLM 排期的短读超时（秒），避免阻塞真实工具链。"""
    raw = (os.environ.get("OC4_DD_PLAN_BUILD_LLM_TIMEOUT_S") or "").strip()
    try:
        v = float(raw) if raw else 18.0
    except ValueError:
        v = 18.0
    return max(5.0, min(v, 60.0))


def _llm_plan_build_json(
    sdir: Path,
    qwen: QwenClient,
    *,
    cut_center_column: bool,
    include_source_geometry: bool,
    mesh_summary: str,
) -> tuple[str, list[dict[str, Any]]] | None:
    """调用大模型产出 rationale + steps（JSON）。失败返回 None。"""
    if not qwen.api_key:
        return None
    prog = session_progress_flags(sdir)
    system = (
        "你是海洋工程 OC4 设计域自动化编排助手。用户将执行工具链："
        "run_export_source_preview → run_build → run_export_obj（design_only=true）→ run_mesh → run_loads。\n"
        "只输出 **一行合法 JSON**（禁止 Markdown 代码围栏、禁止前后解释），schema 为：\n"
        '{"rationale":"中文简述排期理由、风险与注意点","steps":['
        '{"id":1,"tool":"run_export_source_preview","title":"中文标题","arguments":{}},'
        '{"id":2,"tool":"run_build","title":"…","arguments":{"cut_center_column":true,"include_source_geometry":false}},'
        '{"id":3,"tool":"run_export_obj","title":"…","arguments":{"design_only":true}},'
        '{"id":4,"tool":"run_mesh","title":"…","arguments":{}},'
        '{"id":5,"tool":"run_loads","title":"…","arguments":{}}'
        "]}\n"
        "tool 名称与顺序必须严格一致；arguments 仅填必要字段，未知则 {}。\n"
        f"用户网格与偏好摘要: {mesh_summary}\n"
        f"run_build 布尔: cut_center_column={json.dumps(bool(cut_center_column))}, "
        f"include_source_geometry={json.dumps(bool(include_source_geometry))}\n"
        f"当前会话进度: {json.dumps(prog, ensure_ascii=False)[:2400]}\n"
        f"{LLM_CONTEXT_BLOCK_ZH}"
    )
    user = "请只输出 JSON。"
    try:
        resp = qwen.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.22,
        )
    except Exception:
        return None
    raw = _extract_chat_message_text(resp)
    if not raw:
        return None
    obj = _parse_json_object(raw) or _parse_json_object(raw.replace("```json", "").replace("```", ""))
    if not isinstance(obj, dict):
        return None
    rationale = str(obj.get("rationale") or "").strip()
    steps_raw = obj.get("steps")
    if not isinstance(steps_raw, list) or not rationale:
        return None
    steps = _normalize_plan_steps(
        steps_raw,
        cut_center_column=cut_center_column,
        include_source_geometry=include_source_geometry,
    )
    if len(steps) < 5:
        return None
    return rationale, steps


def _append_build_history(sdir: Path, chunk: str) -> None:
    p = sdir / "build_history.md"
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(chunk)
    except OSError:
        pass


def iter_design_domain_plan_draft_events(session_id: str) -> Iterator[dict[str, Any]]:
    """流式生成 Markdown 计划，写入 ``build_plan.md``（与 Build 执行分离）。"""
    try:
        sdir = _get_session_dir(session_id)
    except Exception as e:
        yield {"type": "error", "message": str(e)}
        yield {"type": "done", "ok": False, "phase": "plan_draft"}
        return

    qwen = QwenClient(model=_design_domain_agent_model())
    yield {"type": "meta", "model": qwen.model, "protocol": "plan_draft"}

    prog = session_progress_flags(sdir)
    if not qwen.api_key:
        rail_emitted: set[int] = set()
        for ev in _yield_fallback_plan_rail_steps(rail_emitted):
            yield ev
        txt = (
            "# Build 执行计划（草稿）\n\n"
            "未配置 `QWEN_API_KEY`：无法调用大模型流式生成。你可直接点击 **Build** 使用内置五步流程"
            "（源 OBJ → 设计域 STEP → 设计 OBJ → 体网格 → 载荷）。\n"
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
    user = "请只输出 Markdown 计划正文。"
    yield {"type": "activity", "kind": "plan", "text": "正在流式生成 Build 计划（Markdown）…"}
    buf: list[str] = []
    rail_emitted: set[int] = set()
    try:
        for raw in qwen.chat_stream(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.28,
        ):
            piece = _sse_line_to_delta_text(raw)
            if piece:
                buf.append(piece)
                yield {"type": "plan_md_delta", "text": piece}
                acc = "".join(buf)
                for ev in _iter_plan_rail_events_from_buffer(acc, rail_emitted, finalize=False):
                    yield ev
    except Exception as e:
        yield {"type": "error", "message": f"计划流失败: {e}"}
        yield {"type": "done", "ok": False, "phase": "plan_draft"}
        return

    full = "".join(buf).strip()
    if not full:
        full = "# Build 执行计划\n\n（模型未返回内容）\n"
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
    merge_session_meta(
        sdir,
        {
            "plan_draft_generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )
    yield {"type": "plan_file", "path": "build_plan.md", "chars": len(full)}
    yield {"type": "done", "ok": True, "phase": "plan_draft"}


def iter_design_domain_plan_build_events(
    session_id: str,
    *,
    cut_center_column: bool = True,
    include_source_geometry: bool = False,
    mesh_preset: str = "balanced",
    mesh_characteristic_length_max: float | None = None,
    mesh_user_note: str | None = None,
    force_direction: str | None = "-Z",
    cload_mag: float | None = None,
) -> Iterator[dict[str, Any]]:
    """按五步执行全流程 Build；计划可由大模型生成；成功后禁止再次 Build（由 meta 标记）。"""
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

    from backend.tools.oc4_force_direction import (
        force_direction_label_zh,
        merge_force_direction_into_load_case,
        normalize_force_direction,
    )

    fdir = normalize_force_direction(force_direction or meta.get("preferred_force_direction") or "-Z")
    load_case = merge_force_direction_into_load_case(
        None,
        fdir,
        total_force_n=float(cload_mag) if cload_mag is not None else None,
    )
    merge_session_meta(
        sdir,
        {
            "preferred_force_direction": fdir,
            "preferred_load_case": load_case,
        },
    )
    yield {
        "type": "activity",
        "kind": "plan",
        "text": f"载荷方向已确认：{force_direction_label_zh(fdir)}（对齐 BESO9 顶环施力习惯）",
    }

    model = _design_domain_agent_model()
    yield {"type": "meta", "model": model, "protocol": "plan_build"}

    mesh_cl = _resolve_mesh_cl_max(sdir, mesh_preset, mesh_characteristic_length_max)
    note = str(mesh_user_note or "").strip()
    mesh_summary = f"preset={mesh_preset}, characteristic_length_max={mesh_cl}"
    if note:
        mesh_summary += f"; note={note[:500]}"

    # 默认直接用内置五步，避免同步等大模型（读超时可达数分钟）导致界面长时间「卡住」。
    # 需要 LLM 定制标题时设置 OC4_DD_PLAN_BUILD_LLM=1（仍带短超时）。
    from backend.tools.oc4_design_domain_iges import coerce_corner_r_mm

    corner = coerce_corner_r_mm(meta.get("corner_r_mm"))
    steps = _merge_mesh_into_steps(
        _default_plan_build_steps(
            cut_center_column,
            include_source_geometry,
            corner_r_mm=corner,
            load_case=load_case,
        ),
        mesh_cl,
    )
    rationale = (
        f"内置五步：源预览 → 设计域（三棱柱）→ OBJ → 体网格 → 载荷"
        f"（{force_direction_label_zh(fdir)}）。"
    )
    if corner is not None:
        rationale += f" 顶角挖去 R={corner/1000:.3g} m。"
    use_llm = (os.environ.get("OC4_DD_PLAN_BUILD_LLM") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if use_llm:
        yield {"type": "activity", "kind": "plan", "text": "正在用大模型微调执行计划（短超时）…"}
        qwen = QwenClient(model=model, timeout_s=_plan_build_llm_timeout_s())
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
            # 保证载荷步带上用户确认的方向
            for st in steps:
                if str(st.get("tool") or "") == "run_loads":
                    args = dict(st.get("arguments") or {})
                    args["load_case"] = load_case
                    args["cload_mag"] = float(load_case.get("cload_mag"))
                    st["arguments"] = args
        else:
            yield {
                "type": "activity",
                "kind": "plan",
                "text": "大模型计划不可用，继续内置五步。",
            }
    else:
        yield {"type": "activity", "kind": "plan", "text": "使用内置五步计划，开始执行…"}

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

    for st in steps:
        idx = int(st.get("id") or 0)
        title = str(st.get("title") or "")
        tname = str(st.get("tool") or "").strip()
        targs = st.get("arguments") if isinstance(st.get("arguments"), dict) else {}
        line = f"\n## 步骤 {idx} · {title} · `{tname}`\n\n"
        _append_build_history(sdir, line)
        yield {"type": "plan_step", "index": idx, "title": title, "tool": tname, "phase": "start"}
        yield {"type": "tool", "name": tname, "args": targs}
        ok, summary, extra = _run_tool(tname, targs, sdir=sdir, workspace_root=ws)
        yield _tool_result_payload(tname, ok, targs, summary, extra)
        for fe in _iter_tool_file_touch_events(tname, ok, sdir, None):
            yield fe
        res_line = ("✅ " if ok else "❌ ") + str(summary).strip() + "\n"
        _append_build_history(sdir, res_line)
        yield {"type": "plan_step", "index": idx, "title": title, "tool": tname, "phase": "done", "ok": ok}
        if not ok:
            yield {"type": "error", "message": f"步骤失败: {tname} · {summary}"}
            yield {"type": "done", "ok": False, "phase": "plan_build"}
            return

    _append_build_history(sdir, "\n---\n\n全流程结束。\n")
    merge_session_meta(sdir, {"design_domain_full_build_done": True})
    yield {"type": "refresh_tree"}
    yield {
        "type": "done",
        "ok": True,
        "phase": "plan_build",
        "history_path": "build_history.md",
        "force_direction": fdir,
        "open_preview": "03_for_beso.inp",
    }
