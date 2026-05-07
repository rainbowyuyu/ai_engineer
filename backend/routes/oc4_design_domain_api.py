"""OC4 设计域前置：会话、构建、OBJ 预览、FreeCAD 网格、载荷划分与 Qwen 对话 API。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.oc4_design_domain_service import (
    create_session_from_upload,
    geometry_summary,
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

router = APIRouter(tags=["oc4-design-domain"])


def _workspace_root() -> Path:
    # parents[2] = 仓库根（backend/routes/..）
    return Path(os.environ.get("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()


def _path_ok(p: Path) -> bool:
    try:
        p.resolve().relative_to(_workspace_root())
        return True
    except ValueError:
        return False


def _get_session(session_id: str) -> Path:
    if not session_id.isalnum() or len(session_id) < 16:
        raise HTTPException(status_code=400, detail="invalid session_id")
    s = session_dir(_workspace_root(), session_id)
    if not s.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    if not _path_ok(s):
        raise HTTPException(status_code=400, detail="invalid session path")
    return s


def _parse_json_object(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
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
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(t[i:])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                break
    return None


class SessionCreateIn(BaseModel):
    file_id: str


class BuildIn(BaseModel):
    session_id: str
    cut_center_column: bool = True
    include_source_geometry: bool = False


class ExportObjIn(BaseModel):
    session_id: str
    linear_deflection_source: float = Field(default=1200.0, ge=1.0)
    linear_deflection_design: float = Field(default=800.0, ge=1.0)
    design_only: bool = False


class ExportSourcePreviewIn(BaseModel):
    session_id: str
    linear_deflection_source: float = Field(default=1200.0, ge=1.0)


class MeshIn(BaseModel):
    """与主页「IGES→INP」相同的 FreeCAD+Gmsh 管线（``run_cad_iges_to_inp`` / ``freecad_iges_to_inp_runner.py``）。"""

    session_id: str
    characteristic_length_max: float | None = Field(
        default=None,
        description="Gmsh CharacteristicLengthMax（mm），越大网格越粗；省略时使用设计域默认最粗启发式。",
    )
    characteristic_length_min: float | None = Field(default=None, ge=0.0)
    element_order: str | None = Field(default=None, description="1st 或 2nd")
    mesh_size_from_curvature: int | None = Field(default=None, ge=0, le=64)
    compound_part_strategy: str | None = None
    element_dimension: str | None = None
    geometry_tolerance: float | None = Field(default=None, ge=0.0)
    optimize_std: bool | None = None
    length_unit: str | None = None
    timeout_minutes: float | None = Field(default=None, ge=5.0, le=720.0)


class LoadsIn(BaseModel):
    session_id: str
    band_scale: float = Field(default=1.22, ge=1.0, le=3.0)
    z_fix_band: float = Field(default=800.0, ge=10.0)
    cload_mag: float = Field(default=-5.0e6)
    load_case: dict[str, Any] | None = Field(
        default=None,
        description="可选：结构化载荷参数（cload_mode、top_node_count 等），与数值字段合并后写入 INP。",
    )
    loads_natural_language: str | None = Field(
        default=None,
        max_length=4000,
        description="可选：自然语言描述载荷与边界意图；若填写则调用 Qwen 解析为 load_case 后写入 INP。",
    )


class ChatIn(BaseModel):
    session_id: str
    message: str
    topic: Literal["general", "design", "preview", "mesh", "loads"] = "general"


@router.post("/session")
def oc4_dd_create_session(body: SessionCreateIn):
    try:
        sid, sdir, sf = create_session_from_upload(_workspace_root(), body.file_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    src = sdir / (read_session_meta(sdir).get("source_name") or "00_source.igs")
    summ = geometry_summary(src)
    merge_session_meta(sdir, {"geometry_summary": summ})
    return {
        "session_id": sid,
        "geometry_summary": summ,
        "source_filename": sf.name,
    }


@router.get("/session/{session_id}")
def oc4_dd_get_session(session_id: str):
    sdir = _get_session(session_id)
    meta = read_session_meta(sdir)
    return {"session_id": session_id, **meta, **session_progress_flags(sdir)}


class InvalidateFromStepIn(BaseModel):
    session_id: str
    rail_step: int = Field(..., ge=1, le=4, description="用户点击的步骤条序号（1～4）；将清除该步之后的产物。")


@router.post("/invalidate-from-step")
def oc4_dd_invalidate_from_step(body: InvalidateFromStepIn):
    """步骤条回溯到较早步骤时，删除后续步骤生成的文件并清理 session meta。"""
    sdir = _get_session(body.session_id)
    try:
        out = invalidate_oc4_downstream_from_rail_step(sdir, rail_step=body.rail_step)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **out}


@router.post("/build")
def oc4_dd_build(body: BuildIn):
    sdir = _get_session(body.session_id)
    try:
        out = run_build(
            sdir,
            cut_center_column=body.cut_center_column,
            include_source_geometry=body.include_source_geometry,
        )
    except Exception as e:
        meta = read_session_meta(sdir)
        summ = meta.get("geometry_summary") or {}
        hint = ""
        if summ:
            hint = (
                f" [几何摘要: beam_segments={summ.get('beam_segments')!r}, "
                f"revolution_cylinders={summ.get('revolution_cylinders')!r}"
            )
            errs = summ.get("errors")
            if errs:
                hint += f", errors={errs!r}"
            hint += "]"
        if "主立柱不足" in str(e) or "未识别到" in str(e):
            hint += (
                " 提示：本流程仅针对 OC4 类导管架 IGES（Gmsh 能解析出足够 revolution 圆柱或梁段）。"
                "请换用示例 `examples/oc4/oc4_design_domain.igs` 或同类模型验证环境。"
            )
        raise HTTPException(status_code=400, detail=f"设计域构建失败: {e}{hint}") from e
    return {"ok": True, **out}


@router.post("/export-source-preview")
def oc4_dd_export_source_preview(body: ExportSourcePreviewIn):
    """仅源几何 STEP→OBJ 预览（无需已构建设计域）。"""
    sdir = _get_session(body.session_id)
    try:
        urls = run_export_source_preview_only(
            sdir,
            _workspace_root(),
            linear_source=body.linear_deflection_source,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"源几何预览导出失败: {e}") from e
    return {"ok": True, **urls}


@router.post("/export-obj")
def oc4_dd_export_obj(body: ExportObjIn):
    sdir = _get_session(body.session_id)
    try:
        urls = run_export_obj(
            sdir,
            _workspace_root(),
            linear_source=body.linear_deflection_source,
            linear_design=body.linear_deflection_design,
            design_only=body.design_only,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OBJ 导出失败: {e}") from e
    return {"ok": True, **urls}


@router.post("/mesh")
def oc4_dd_mesh(body: MeshIn):
    sdir = _get_session(body.session_id)
    timeout_s = None
    if body.timeout_minutes is not None:
        timeout_s = float(body.timeout_minutes) * 60.0
    try:
        out = run_mesh(
            sdir,
            char_length_max=body.characteristic_length_max,
            char_length_min=body.characteristic_length_min,
            element_order=body.element_order,
            mesh_size_from_curvature=body.mesh_size_from_curvature,
            compound_part_strategy=body.compound_part_strategy,
            element_dimension=body.element_dimension,
            geometry_tolerance=body.geometry_tolerance,
            optimize_std=body.optimize_std,
            length_unit=body.length_unit,
            timeout_s=timeout_s,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"体网格失败: {e}") from e
    url = runs_file_url(_workspace_root(), Path(out["mesh_inp"]))
    payload: dict[str, Any] = {
        "ok": True,
        "mesh_inp": out["mesh_inp"],
        "mesh_inp_url": url,
        "mesh_inp_size_bytes": out.get("mesh_inp_size_bytes"),
        "mesh_char_length_max_used": out.get("mesh_char_length_max_used"),
    }
    if out.get("mesh_inp_size_warning"):
        payload["mesh_inp_size_warning"] = out["mesh_inp_size_warning"]
    return payload


@router.post("/loads")
def oc4_dd_loads(body: LoadsIn):
    sdir = _get_session(body.session_id)
    try:
        out = run_loads(
            sdir,
            band_scale=body.band_scale,
            z_fix_band=body.z_fix_band,
            cload_mag=body.cload_mag,
            load_case=body.load_case,
            loads_natural_language=body.loads_natural_language,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"载荷/分区失败: {e}") from e
    url = runs_file_url(_workspace_root(), Path(out["final_inp"]))
    payload: dict[str, Any] = {
        "ok": True,
        "stats": out["stats"],
        "final_inp": out["final_inp"],
        "final_inp_url": url,
        "resolved_load_case": out.get("resolved_load_case"),
    }
    if out.get("nl_reply"):
        payload["nl_reply"] = out["nl_reply"]
    if out.get("validation_warnings"):
        payload["validation_warnings"] = out["validation_warnings"]
    return payload


def _oc4_dd_chat_no_key(topic: str) -> dict[str, Any]:
    return {
        "reply": "未配置 QWEN_API_KEY，无法调用大模型。请先在设置中填写 API Key。",
        "topic": topic,
        "suggested_build": None,
        "suggested_loads": None,
        "suggested_mesh": None,
        "suggested_export": None,
    }


@router.post("/chat")
def oc4_dd_chat(body: ChatIn):
    sdir = _get_session(body.session_id)
    meta = read_session_meta(sdir)
    summ = meta.get("geometry_summary") or {}
    topic = body.topic
    qwen = QwenClient()
    if not qwen.api_key:
        return _oc4_dd_chat_no_key(topic)

    step = sdir / "01_design_domain.step"
    step_note = ""
    if step.is_file():
        try:
            mb = step.stat().st_size / (1024 * 1024)
            step_note = f"当前设计域 STEP 约 {mb:.2f} MB。\n"
        except OSError:
            step_note = ""

    if topic == "general":
        system = (
            "你是海洋工程/结构 CAD 助手，帮助用户理解 OC4 导管架 IGES 与设计域构建流程。"
            "根据几何摘要（非完整模型）与用户问题作答。"
            "你必须只输出**一个** JSON 对象，不要 Markdown 围栏，不要其它多余文字。键：\n"
            '- "reply": string，中文自然语言回答；\n'
            '- "suggested_build": object 或 null，仅含 cut_center_column、include_source_geometry（布尔）；\n'
            '- "suggested_loads": object 或 null，可含 band_scale（1~3）、z_fix_band、cload_mag、'
            "cload_mode、cload_each、top_node_count、top_fraction、explicit_cloads。\n"
            "若用户未要求改参数，对应键用 null。"
        )
        user = f"几何摘要:\n{json.dumps(summ, ensure_ascii=False)}\n\n用户问题:\n{body.message.strip()}"
    elif topic == "design":
        system = (
            "你是 OC4 设计域构建助手（步骤 1：源装配 + 设计域几何选项）。"
            "只根据几何摘要与用户意图，建议是否挖除中心柱、是否合并源几何作对照。"
            "只输出**一个** JSON：{\"reply\":string,\"suggested_build\":object|null}；"
            "suggested_build 仅含 cut_center_column、include_source_geometry（布尔），未提及则 null。"
        )
        user = f"几何摘要:\n{json.dumps(summ, ensure_ascii=False)}\n\n用户:\n{body.message.strip()}"
    elif topic == "preview":
        system = (
            "你是三角化预览助手（步骤 2：OBJ 导出）。说明与主页 CAD 流程无关，仅影响预览三角化疏密："
            "linear_deflection_source / linear_deflection_design（正数，越大越粗、越快）。"
            "只输出**一个** JSON：{\"reply\":string,\"suggested_export\":object|null}；"
            "suggested_export 可含 linear_deflection_source、linear_deflection_design（典型 400~3000），未改则 null。"
        )
        user = f"几何摘要:\n{json.dumps(summ, ensure_ascii=False)}\n\n用户:\n{body.message.strip()}"
    elif topic == "mesh":
        system = (
            "你是 FreeCAD+Gmsh 体网格助手（步骤 3）。本步与主页「IGES→INP」使用同一管线："
            "backend/tools/cad_iges_to_inp.py → scripts/freecad_iges_to_inp_runner.py；"
            "Gmsh 中 **characteristic_length_max 越大网格越粗**，单元越少，INP 越小。"
            "默认设计域会话在未指定时使用服务端「最粗启发式」以尽量让 02_mesh_body.inp 落在约 10MB 内（不保证）。"
            "只输出**一个** JSON：{\"reply\":string,\"suggested_mesh\":object|null}。\n"
            "suggested_mesh 可含字段（未改填 null）：\n"
            "- characteristic_length_max（mm，正数；想更小文件则建议更大值）\n"
            "- characteristic_length_min（>=0）\n"
            "- element_order: \"1st\"|\"2nd\"\n"
            "- mesh_size_from_curvature: 整数，0 表示关闭曲率加密（更粗）\n"
            "- compound_part_strategy: 如 largest_volume\n"
            "- optimize_std: 布尔，false 常略减网格量\n"
            "- timeout_minutes: 5~720\n"
            "若用户只说「默认最粗」「冒烟网格」等，应给出明显偏大的 characteristic_length_max 与 mesh_size_from_curvature=0。"
        )
        user = (
            f"{step_note}几何摘要:\n{json.dumps(summ, ensure_ascii=False)}\n\n用户:\n{body.message.strip()}"
        )
    elif topic == "loads":
        system = (
            "你是 OC4 载荷与分区助手（步骤 4：写入 03_for_beso.inp 的 *STEP/*CLOAD）。"
            "只输出**一个** JSON：{\"reply\":string,\"suggested_loads\":object|null}；\n"
            "suggested_loads 可含 band_scale（1~3）、z_fix_band、cload_mag、"
            "cload_mode（single_top|top_count|top_fraction|explicit）、cload_each、top_node_count、"
            "top_fraction、explicit_cloads；未改则 null。"
        )
        user = f"几何摘要:\n{json.dumps(summ, ensure_ascii=False)}\n\n用户:\n{body.message.strip()}"
    else:
        raise HTTPException(status_code=400, detail=f"unknown topic: {topic}")

    try:
        resp = qwen.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        content = resp["choices"][0]["message"]["content"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Qwen 调用失败: {e}") from e
    data = _parse_json_object(content) or {}
    reply = str(data.get("reply") or content.strip())
    sb = data.get("suggested_build") if isinstance(data.get("suggested_build"), dict) else None
    sl = data.get("suggested_loads") if isinstance(data.get("suggested_loads"), dict) else None
    sm = data.get("suggested_mesh") if isinstance(data.get("suggested_mesh"), dict) else None
    se = data.get("suggested_export") if isinstance(data.get("suggested_export"), dict) else None
    patch: dict[str, Any] = {
        "last_chat_topic": topic,
        "last_chat_suggested_build": sb,
        "last_chat_suggested_loads": sl,
        "last_chat_suggested_mesh": sm,
        "last_chat_suggested_export": se,
    }
    merge_session_meta(sdir, patch)
    out: dict[str, Any] = {
        "reply": reply,
        "topic": topic,
        "suggested_build": sb,
        "suggested_loads": sl,
        "suggested_mesh": sm,
        "suggested_export": se,
    }
    return out


class FinalizeIn(BaseModel):
    session_id: str


@router.post("/finalize")
def oc4_dd_finalize(body: FinalizeIn):
    """写入最小 beso_conf.py，返回扫描目录供后续智能体流程使用。"""
    sdir = _get_session(body.session_id)
    fin = sdir / "03_for_beso.inp"
    if not fin.is_file():
        raise HTTPException(
            status_code=400,
            detail="尚未生成 03_for_beso.inp：请在本页依次完成「3 FreeCAD 体网格」与「4 划分载荷」后再点收尾。",
        )
    ccx = Path(os.environ.get("CCX_PATH", r"D:\freecad\bin\ccx.exe")).resolve()
    from backend.tools.inp_oc4_design_nondesign import write_beso_conf_example3_style

    write_beso_conf_example3_style(
        sdir / "beso_conf.py",
        work_dir=sdir.resolve(),
        ccx_path=ccx,
        inp_name="03_for_beso.inp",
        mass_goal_ratio=0.4,
        filter_radius=2.0,
        optimization_base="failure_index",
    )
    scan_dir = str(sdir.resolve())
    merge_session_meta(sdir, {"scan_dir": scan_dir, "finalized": True})
    return {"ok": True, "scan_dir": scan_dir}
