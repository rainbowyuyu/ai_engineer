from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# 本地开发：从仓库根目录或 WORKSPACE_ROOT 下的 .env 注入 QWEN_*（不覆盖已在环境中的变量）
_backend_dir = Path(__file__).resolve().parent
_repo_root = _backend_dir.parent
for _root in (_repo_root, Path(os.environ.get("WORKSPACE_ROOT", _repo_root)).resolve()):
    _dotenv_file = _root / ".env"
    if _dotenv_file.is_file():
        load_dotenv(_dotenv_file, override=False)

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from backend.agent import decide_params
from backend.generator import scan_input_directory, build_generated_code
from backend.jobs.manager import jobs
from backend.models import AssistantChatRequest, AssistantChatResponse, ChatRequest, ChatResponse
from backend.qwen_client import QwenClient, assistant_chat_http_read_timeout_s
from backend.qwen_runtime_config import get_qwen_config, set_qwen_config
from backend.pydantic_compat import model_to_dict
from backend.tools.files import preview_inp, resolve_file, store_upload, uploads_root
from backend.tools.cad_iges_to_inp import (
    OUTPUT_INP_NAME,
    list_iges_in_dir,
    run_cad_iges_to_inp,
    suggest_char_length_max,
)
from backend.routes.oc4_design_domain_api import router as oc4_design_domain_router

logger = logging.getLogger(__name__)


WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()
RUNS_ROOT = WORKSPACE_ROOT / "runs"
RUNS_ROOT.mkdir(parents=True, exist_ok=True)
TASKS_ROOT = RUNS_ROOT / "_tasks"
TASKS_ROOT.mkdir(parents=True, exist_ok=True)
UI_ROOT = WORKSPACE_ROOT / "frontend_static"
UPLOADS_ROOT = uploads_root(WORKSPACE_ROOT)
UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
CAD_CONVERT_ROOT = RUNS_ROOT / "_cad_convert"
CAD_CONVERT_ROOT.mkdir(parents=True, exist_ok=True)

_cad_convert_registry: dict[str, dict] = {}
_cad_convert_registry_lock = threading.Lock()

app = FastAPI(title="AI Engineering Web")
app.include_router(oc4_design_domain_router, prefix="/api/oc4/design-domain")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/runs", StaticFiles(directory=str(RUNS_ROOT)), name="runs")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_ROOT)), name="uploads")
if UI_ROOT.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_ROOT), html=True), name="ui")


def _path_under_workspace(path: Path) -> bool:
    try:
        path.resolve().relative_to(WORKSPACE_ROOT.resolve())
        return True
    except ValueError:
        return False


def _write_cad_status(task_dir: Path, payload: dict) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    p = task_dir / "status.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _cad_convert_worker(task_id: str, scan_dir: str, iges_name: str | None, mesh: dict) -> None:
    task_dir = CAD_CONVERT_ROOT / task_id
    cancel_ev = threading.Event()
    proc_holder: list = [None]

    def push(progress: int, stage: str, **extra: object) -> None:
        data = {
            "task_id": task_id,
            "progress": progress,
            "stage": stage,
            "done": bool(extra.get("done", False)),
            "error": extra.get("error"),
            "cancelled": bool(extra.get("cancelled", False)),
            "output_inp": extra.get("output_inp"),
            "output_name": OUTPUT_INP_NAME,
        }
        _write_cad_status(task_dir, data)

    with _cad_convert_registry_lock:
        _cad_convert_registry[task_id] = {"cancel": cancel_ev, "proc": proc_holder}
    try:
        push(5, "校验扫描目录…")
        root = Path(scan_dir).resolve()
        if not root.is_dir():
            raise ValueError(f"目录不存在: {scan_dir}")
        if not _path_under_workspace(root):
            raise ValueError("扫描目录必须位于工作区（WORKSPACE_ROOT）内")

        push(15, "查找 IGES 文件…")
        cads = list_iges_in_dir(root)
        if not cads:
            raise ValueError("该目录下没有 .igs / .iges 文件")
        if iges_name:
            pick = (root / iges_name).resolve()
            if not _path_under_workspace(pick) or not pick.is_file():
                raise ValueError(f"找不到指定的 IGES 文件: {iges_name}")
            if pick.suffix.lower() not in {".igs", ".iges"}:
                raise ValueError("iges_name 必须是 .igs 或 .iges")
        elif len(cads) == 1:
            pick = cads[0]
        else:
            raise ValueError("目录中存在多个 IGES，请在请求中指定 iges_name")

        out_inp = (root / OUTPUT_INP_NAME).resolve()
        if not _path_under_workspace(out_inp):
            raise ValueError("输出路径非法")

        cm = float(mesh.get("char_length_max", suggest_char_length_max(pick)))
        push(22, f"IGES→INP（FreeCAD + Gmsh，CharacteristicLengthMax≈{cm:g} mm）…")
        push(28, "正在调用 FreeCAD 生成网格（体网格可能较慢）…")
        done = threading.Event()
        err_box: list[Exception | None] = [None]

        def _cad_runner() -> None:
            try:
                # IGES→INP：cad_iges_to_inp → backend.tools.freecad_iges_to_inp（FreeCAD+Gmsh）
                run_cad_iges_to_inp(
                    pick,
                    out_inp,
                    cancel_event=cancel_ev,
                    proc_box=proc_holder,
                    **mesh,
                )
            except Exception as e:
                err_box[0] = e
            finally:
                done.set()

        th = threading.Thread(target=_cad_runner, name="cad-iges-convert", daemon=True)
        th.start()
        prog = 28
        t0 = time.monotonic()
        while True:
            if cancel_ev.is_set():
                p = proc_holder[0] if proc_holder else None
                if p is not None and p.poll() is None:
                    try:
                        p.kill()
                    except Exception:
                        pass
            if done.wait(timeout=2.5):
                break
            elapsed = int(time.monotonic() - t0)
            prog = min(88, prog + 2)
            push(prog, f"正在转换 IGES…（已等待 {elapsed}s；FreeCAD/Gmsh 体网格可能较慢）")
        th.join(timeout=5.0)
        if err_box[0] is not None:
            err = err_box[0]
            if isinstance(err, RuntimeError) and "转换已取消" in str(err):
                push(100, "已中止", done=True, cancelled=True)
                return
            raise err
        push(100, "已生成 CalculiX INP，可继续流程。", done=True, output_inp=str(out_inp))
    except Exception as e:
        push(100, "转换失败", done=True, error=str(e))
    finally:
        with _cad_convert_registry_lock:
            _cad_convert_registry.pop(task_id, None)


def _suggest_scan_dir_by_filename(filename: str) -> str | None:
    """
    Fallback when browser cannot provide local absolute file path.
    Search workspace for same filename and pick the most likely example/work dir.
    """
    name = Path(filename).name
    candidates = list(WORKSPACE_ROOT.rglob(name))
    if not candidates:
        return None

    def score(p: Path) -> tuple[int, int]:
        s = str(p).lower()
        bonus = 0
        if "examples" in s and "base" in s:
            bonus += 28
        if name.lower() == "beso2-femmeshgmsh.inp" and "examples" in s and "base" in s:
            bonus += 55
        if "wiki_files" in s:
            bonus += 30
        if "example_2" in s or "example_3" in s or "example_1" in s:
            bonus += 20
        if "input_and_results" in s or "analysis_files" in s:
            bonus += 20
        sibling_inps = 0
        try:
            sibling_inps = len(list(p.parent.glob("*.inp")))
        except Exception:
            sibling_inps = 0
        return (bonus, sibling_inps)

    best = max(candidates, key=score)
    return str(best.parent.resolve())


@app.get("/")
def root():
    if UI_ROOT.exists():
        return RedirectResponse(url="/ui/")
    return {"ok": True, "ui": False}


@app.get("/health")
def health():
    return {"ok": True}


def _sanitize_optimization_base(v: str | None) -> str:
    s = (v or "").strip().lower()
    if s in {"failure_index", "stiffness"}:
        return s
    return "failure_index"


def _iges_to_inp_for_job(iges_path: Path) -> str:
    if not _path_under_workspace(iges_path):
        raise HTTPException(status_code=400, detail="IGES 路径必须位于工作区 WORKSPACE_ROOT 内")
    prep = TASKS_ROOT / uuid.uuid4().hex
    prep.mkdir(parents=True, exist_ok=True)
    dest = prep / OUTPUT_INP_NAME
    try:
        run_cad_iges_to_inp(iges_path.resolve(), dest)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"IGES→INP 转换失败: {e}") from e
    return str(dest.resolve())


@app.post("/api/assistant/chat", response_model=AssistantChatResponse)
def assistant_chat(body: AssistantChatRequest):
    """
    通用多轮对话，走 .env / 运行时配置中的 QWEN_*（DashScope 兼容 OpenAI Chat）。
    与下方编排用的 ``POST /api/chat`` 不同。
    """
    qwen = QwenClient(timeout_s=assistant_chat_http_read_timeout_s())
    if not qwen.api_key:
        raise HTTPException(
            status_code=503,
            detail="未配置大模型密钥：请在项目根目录 .env 中设置 QWEN_API_KEY，或在设置页保存 API Key。",
        )
    msgs = _assistant_messages_for_qwen(body)
    try:
        data = qwen.chat(msgs, temperature=float(body.temperature if body.temperature is not None else 0.6))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("assistant_chat failed")
        raise HTTPException(
            status_code=503,
            detail=f"模型请求异常: {e}。请查看本机后端控制台日志；若经反向代理，请确认 QWEN_BASE_URL 与网络可达。",
        ) from e
    try:
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    except Exception:
        content = ""
    if not str(content).strip():
        content = "（模型无有效输出，请重试或缩短上文。）"
    return AssistantChatResponse(reply=str(content), model=qwen.model)


def _assistant_messages_for_qwen(body: AssistantChatRequest) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = [{"role": m.role, "content": m.content} for m in body.messages]
    if not msgs or msgs[0]["role"] != "system":
        msgs = [
            {
                "role": "system",
                "content": (
                    "你是「AI Engineering」的对话助手；角色为 AI 工程与结构仿真方向的专家，熟悉结构/拓扑优化（含 BESO、SIMP）、CalculiX、"
                    "INP 网格与边界条件、以及本产品中设计域—拓扑优化编排—任务流程。"
                    "用简洁中文回答；需要时分点说明，可使用 Markdown；不要编造不存在的文件路径。"
                ),
            },
            *msgs,
        ]
    return msgs


@app.post("/api/assistant/chat/stream")
def assistant_chat_stream(body: AssistantChatRequest):
    """流式对话，直接透传上游 SSE 行（``data:`` JSON 与 ``data: [DONE]``）。"""

    def gen():
        qwen = QwenClient(timeout_s=assistant_chat_http_read_timeout_s())
        if not qwen.api_key:
            yield (
                "data: "
                + json.dumps(
                    {"error": "未配置大模型密钥：请在项目根目录 .env 中设置 QWEN_API_KEY，或在设置页保存 API Key。"},
                    ensure_ascii=False,
                )
                + "\n\n"
            )
            return
        msgs = _assistant_messages_for_qwen(body)
        try:
            for line in qwen.chat_stream(msgs, temperature=float(body.temperature if body.temperature is not None else 0.6)):
                yield line
        except RuntimeError as e:
            yield "data: " + json.dumps({"error": str(e)}, ensure_ascii=False) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"error": f"模型请求失败: {e}"}, ensure_ascii=False) + "\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/assistant/qwen-warmup")
def assistant_qwen_warmup():
    """前端进入页或聚焦输入时调用：预热到 DashScope 的连接，不阻塞主对话路径。"""
    qwen = QwenClient()
    return qwen.warmup()


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Resolve inp path: prefer scan_dir for multi-inp merged mode.
    source_path: str | None = req.inp_path
    bundle = None
    if req.scan_dir:
        try:
            bundle = scan_input_directory(req.scan_dir)
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        source_path = bundle.primary_inp
        if not source_path:
            cads = sorted(
                [x.path for x in bundle.files if x.ext in {".igs", ".iges"}],
                key=lambda p: Path(p).name.lower(),
            )
            if req.iges_name:
                cand = (Path(bundle.scan_dir) / req.iges_name).resolve()
                if (
                    not cand.is_file()
                    or cand.suffix.lower() not in {".igs", ".iges"}
                    or not _path_under_workspace(cand)
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"找不到有效的 IGES 文件（相对于扫描目录）: {req.iges_name}",
                    )
                source_path = str(cand)
            elif len(cads) == 1:
                source_path = cads[0]
            elif len(cads) > 1:
                raise HTTPException(
                    status_code=400,
                    detail="扫描目录中存在多个 IGES，请在请求中设置 iges_name 指定其一",
                )
    elif req.file_id:
        sf = resolve_file(WORKSPACE_ROOT, req.file_id)
        source_path = str(sf.path)

    inp_path = source_path
    cad_source_iges: str | None = None
    if source_path:
        sp = Path(source_path)
        if not sp.exists():
            raise HTTPException(status_code=400, detail=f"输入文件不存在: {source_path}")
        if sp.suffix.lower() in {".igs", ".iges"}:
            cad_source_iges = str(sp.resolve())
            inp_path = _iges_to_inp_for_job(sp)

    primary_inp_override: str | None = None
    if bundle is not None and bundle.primary_inp is None and inp_path:
        primary_inp_override = inp_path

    # LLM parse (only if API key set). User may still override specific fields.
    # example_2 扫描目录不再强制覆盖模型解析结果：配置 QWEN_API_KEY 时由 decide_params 给出参数；
    # 仍需固定值时请在请求体中传入 mass_goal_ratio / filter_radius 等字段。
    eff_inp: str | None = None
    if inp_path and Path(inp_path).suffix.lower() == ".inp":
        try:
            eff_inp = str(Path(inp_path).resolve())
        except OSError:
            eff_inp = inp_path
    parsed = decide_params(req.message, effective_inp_path=eff_inp, scan_dir=req.scan_dir)

    mass_goal_ratio = req.mass_goal_ratio if req.mass_goal_ratio is not None else parsed.mass_goal_ratio
    mass_goal_ratio = max(0.05, min(0.99, float(mass_goal_ratio)))
    filter_radius = req.filter_radius if req.filter_radius is not None else parsed.filter_radius
    optimization_base_raw = req.optimization_base if req.optimization_base is not None else parsed.optimization_base
    optimization_base = _sanitize_optimization_base(optimization_base_raw)
    save_every = req.save_every if req.save_every is not None else parsed.save_every
    save_every = max(1, int(save_every))

    generated_bundle = None
    generated_code_meta: list[dict] = []
    selected_inputs: dict | None = None

    if bundle is not None:
        if not inp_path:
            raise HTTPException(status_code=400, detail="扫描目录中未找到可用的 inp 或 IGES 文件")
    elif not inp_path:
        raise HTTPException(
            status_code=400,
            detail="请提供 inp_path（可为 .inp 或 .igs）、file_id 或 scan_dir（内含 inp 或 IGES）",
        )

    job = jobs.create_job(
        user_message=req.message,
        inp_path=inp_path,
        mass_goal_ratio=mass_goal_ratio,
        filter_radius=filter_radius,
        optimization_base=optimization_base,
        save_every=save_every,
        generated_code_files=[],
        selected_inputs=None,
    )

    if bundle is not None:
        ccx_path = Path(os.environ.get("CCX_PATH", r"D:\freecad\bin\ccx.exe")).resolve()
        generated_bundle = build_generated_code(
            bundle=bundle,
            run_dir=Path(job.run_dir),
            ccx_path=ccx_path,
            mass_goal_ratio=mass_goal_ratio,
            filter_radius=filter_radius,
            optimization_base=optimization_base,
            save_every=save_every,
            primary_inp_override=primary_inp_override,
        )
        for name, content in generated_bundle.files.items():
            p = Path(job.run_dir) / name
            p.write_text(content, encoding="utf-8")
            generated_code_meta.append(
                {
                    "name": name,
                    "url": f"/runs/{job.id}/{name}",
                    "group": "manifest" if name.endswith(".json") else "generated",
                }
            )
        jobs.set_generated_code_files(job.id, list(generated_bundle.files.keys()))
        selected_inputs = generated_bundle.selected_inputs
        jobs.set_selected_inputs(job.id, selected_inputs)

    if req.auto_start:
        jobs.start_job(job.id)
    return ChatResponse(
        job_id=job.id,
        parsed_params={
            "inp_path": inp_path,
            **({"cad_source_iges": cad_source_iges} if cad_source_iges else {}),
            "mass_goal_ratio": mass_goal_ratio,
            "filter_radius": filter_radius,
            "optimization_base": optimization_base,
            "save_every": save_every,
        },
        reasoning_summary=(generated_bundle.reasoning_summary if generated_bundle else parsed.reasoning_summary),
        generated_code=generated_code_meta or None,
        selected_inputs=selected_inputs,
    )


@app.get("/api/scan-directory")
def scan_directory(scan_dir: str):
    try:
        bundle = scan_input_directory(scan_dir)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return bundle.as_dict()


@app.get("/api/scan_directory")
def scan_directory_legacy(scan_dir: str):
    # Backward-compatible alias for clients using underscore style.
    return scan_directory(scan_dir)


class ConvertIgesIn(BaseModel):
    scan_dir: str
    iges_name: str | None = None
    characteristic_length_max: float | None = None
    characteristic_length_min: float | None = None
    element_order: Literal["1st", "2nd"] | None = None
    mesh_size_from_curvature: int | None = None
    compound_part_strategy: Literal["largest_volume", "first"] | None = None
    timeout_minutes: float | None = None


def _mesh_opts_from_convert_body(body: ConvertIgesIn) -> dict:
    """将 API 请求体中的可选网格字段映射为 ``run_cad_iges_to_inp`` 关键字参数。"""
    m: dict = {}
    if body.characteristic_length_max is not None:
        m["char_length_max"] = float(body.characteristic_length_max)
    if body.characteristic_length_min is not None:
        m["char_length_min"] = float(body.characteristic_length_min)
    if body.element_order is not None:
        m["element_order"] = body.element_order
    if body.mesh_size_from_curvature is not None:
        m["mesh_size_from_curvature"] = int(body.mesh_size_from_curvature)
    if body.compound_part_strategy is not None:
        m["compound_part_strategy"] = body.compound_part_strategy
    if body.timeout_minutes is not None:
        m["timeout_s"] = max(60.0, float(body.timeout_minutes) * 60.0)
    return m


@app.post("/api/cad/convert-iges")
def start_convert_iges(body: ConvertIgesIn):
    task_id = uuid.uuid4().hex
    task_dir = CAD_CONVERT_ROOT / task_id
    mesh = _mesh_opts_from_convert_body(body)
    _write_cad_status(
        task_dir,
        {
            "task_id": task_id,
            "progress": 0,
            "stage": "排队中…",
            "done": False,
            "error": None,
            "output_inp": None,
            "output_name": OUTPUT_INP_NAME,
        },
    )
    t = threading.Thread(
        target=_cad_convert_worker,
        args=(task_id, body.scan_dir, body.iges_name, mesh),
        daemon=True,
    )
    t.start()
    return {"task_id": task_id}


@app.post("/api/cad/convert-iges/{task_id}/cancel")
def cancel_convert_iges(task_id: str):
    if not task_id.isalnum() or len(task_id) < 16:
        raise HTTPException(status_code=400, detail="invalid task_id")
    rec = None
    ph = None
    with _cad_convert_registry_lock:
        rec = _cad_convert_registry.get(task_id)
        if rec:
            rec["cancel"].set()
            ph = rec.get("proc")
    if ph:
        p = ph[0] if ph else None
        if p is not None and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass
    return {"ok": True, "cancel_requested": bool(rec)}


@app.get("/api/cad/convert-iges/{task_id}")
def get_convert_iges_status(task_id: str):
    if not task_id.isalnum() or len(task_id) < 16:
        raise HTTPException(status_code=400, detail="invalid task_id")
    p = CAD_CONVERT_ROOT / task_id / "status.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="task not found")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/files/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    try:
        sf = store_upload(WORKSPACE_ROOT, file.filename or "upload", content)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    suggested_scan_dir = _suggest_scan_dir_by_filename(sf.name)
    return {
        "file_id": sf.file_id,
        "name": sf.name,
        "ext": sf.ext,
        "url": f"/uploads/{sf.file_id}/{sf.name}",
        "suggested_scan_dir": suggested_scan_dir,
    }


def _safe_upload_file_id(file_id: str) -> str:
    s = "".join(ch for ch in str(file_id or "").strip().lower() if ch in "0123456789abcdef")
    if len(s) != 32:
        raise HTTPException(status_code=400, detail="invalid file_id")
    return s


@app.delete("/api/files/{file_id}")
def delete_uploaded_file(file_id: str):
    """删除上传目录（用户从对话中移除附件时调用）。"""
    fid = _safe_upload_file_id(file_id)
    base = uploads_root(WORKSPACE_ROOT).resolve()
    root = (base / fid).resolve()
    try:
        root.relative_to(base)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid path") from e
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)
    return {"ok": True, "file_id": fid}


def _task_file(task_id: str) -> Path:
    safe = "".join(ch for ch in str(task_id) if ch.isalnum() or ch in {"-", "_"})
    return TASKS_ROOT / f"{safe}.json"


def _task_index_file() -> Path:
    return TASKS_ROOT / "index.json"


def _read_task_index_ids() -> list[str]:
    idx_file = _task_index_file()
    if not idx_file.exists():
        return []
    try:
        raw = json.loads(idx_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [str(x) for x in raw]
    except Exception:
        pass
    return []


def _load_task(task_id: str) -> dict | None:
    p = _task_file(task_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_task(task_id: str, payload: dict) -> None:
    TASKS_ROOT.mkdir(parents=True, exist_ok=True)
    p = _task_file(task_id)
    payload = dict(payload or {})
    payload["task_id"] = task_id
    payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
    if "created_at" not in payload:
        payload["created_at"] = payload["updated_at"]
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    idx_file = _task_index_file()
    ids = [x for x in _read_task_index_ids() if x != task_id]
    ids.insert(0, task_id)
    idx_file.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_task(task_id: str) -> None:
    p = _task_file(task_id)
    if p.exists():
        p.unlink(missing_ok=True)
    idx_file = _task_index_file()
    ids = [x for x in _read_task_index_ids() if x != task_id]
    idx_file.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")


_TASK_LIST_STRIP_KEYS = ("assistant_thread", "landing_session_digest")


def _task_summary_for_list(task: dict) -> dict:
    """侧栏列表不携带大体量对话字段，避免 /api/tasks 响应过大。"""
    out = {k: v for k, v in task.items() if k not in _TASK_LIST_STRIP_KEYS}
    th = task.get("assistant_thread")
    if isinstance(th, list):
        out["assistant_thread_len"] = len(th)
    dg = task.get("landing_session_digest")
    if isinstance(dg, list):
        out["landing_session_digest_len"] = len(dg)
    return out


@app.get("/api/tasks")
def list_tasks():
    ids = _read_task_index_ids()
    items: list[dict] = []
    for task_id in ids[:200]:
        task = _load_task(task_id)
        if task:
            items.append(_task_summary_for_list(task))
    return {"items": items}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = _load_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


class TaskUpsertIn(BaseModel):
    task_id: str
    title: str | None = None
    progress: int | None = None
    step: int | None = None
    status: str | None = None
    file_name: str | None = None
    """与 /api/files/upload 返回的 file_id 一致，写入任务以便下次打开对话仍关联附件"""
    file_id: str | None = None
    job_id: str | None = None
    scan_dir: str | None = None
    ui_stage: str | None = None
    oc4_design_domain_session_id: str | None = None
    # OC4 设计域：助手 / 用户轨迹（前端为 list[{"ts","role","text"}]，最多由前端裁剪）
    oc4_activity: list | None = None
    # 主页助手多轮对话（与任务同生命周期，删任务即删）
    assistant_thread: list | None = None
    landing_session_digest: list | None = None


def _task_upsert_patch_dict(body: TaskUpsertIn) -> dict[str, object]:
    md = getattr(body, "model_dump", None)
    if callable(md):
        return md(exclude_unset=True)
    d = getattr(body, "dict", None)
    if callable(d):
        return d(exclude_unset=True)
    raise TypeError("expected Pydantic BaseModel")


@app.post("/api/tasks/upsert")
def upsert_task(body: TaskUpsertIn):
    try:
        existing = _load_task(body.task_id) or {}
        payload = dict(existing)
        incoming = _task_upsert_patch_dict(body)
        for k, v in incoming.items():
            if k == "task_id":
                continue
            if k == "file_id" and (v is None or v == ""):
                payload.pop("file_id", None)
            elif k == "oc4_design_domain_session_id" and (v is None or v == ""):
                payload.pop("oc4_design_domain_session_id", None)
            elif v is not None:
                payload[k] = v
        if isinstance(payload.get("assistant_thread"), list):
            payload["assistant_thread"] = payload["assistant_thread"][-200:]
        if isinstance(payload.get("landing_session_digest"), list):
            payload["landing_session_digest"] = payload["landing_session_digest"][-80:]
        _save_task(body.task_id, payload)
        return {"ok": True, "task": payload}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tasks/upsert failed: {e}") from e


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    prev = _load_task(task_id)
    fid = str((prev or {}).get("file_id") or "").strip().lower()
    if len(fid) == 32 and all(c in "0123456789abcdef" for c in fid):
        base = uploads_root(WORKSPACE_ROOT).resolve()
        root = (base / fid).resolve()
        try:
            root.relative_to(base)
            if root.is_dir():
                shutil.rmtree(root, ignore_errors=True)
        except ValueError:
            pass
    _remove_task(task_id)
    run_dir = RUNS_ROOT / task_id
    if run_dir.exists() and run_dir.is_dir():
        # Best-effort cleanup for generated run artifacts.
        for p in sorted(run_dir.rglob("*"), reverse=True):
            try:
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            except Exception:
                pass
        try:
            run_dir.rmdir()
        except Exception:
            pass
    return {"ok": True}


@app.get("/api/files/{file_id}/preview")
def preview(file_id: str):
    sf = resolve_file(WORKSPACE_ROOT, file_id)
    if sf.ext == ".inp":
        p = preview_inp(sf.path)
        return {
            "file_id": sf.file_id,
            "name": sf.name,
            "ext": sf.ext,
            "preview": p,
        }
    return {
        "file_id": sf.file_id,
        "name": sf.name,
        "ext": sf.ext,
        "url": f"/uploads/{sf.file_id}/{sf.name}",
    }


class QwenConfigIn(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


def _qwen_status_payload() -> dict[str, str | bool]:
    """合并进程内配置与 ``QWEN_*`` 环境变量（与 ``QwenClient`` 解析顺序一致，不把密钥回传给前端）。"""
    cfg = get_qwen_config()
    key = (cfg.api_key or "").strip() or (os.environ.get("QWEN_API_KEY") or "").strip()
    base_url = (cfg.base_url or "").strip() or (os.environ.get("QWEN_BASE_URL") or "").strip()
    if not base_url:
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model = (cfg.model or "").strip() or (os.environ.get("QWEN_MODEL") or "").strip()
    if not model:
        model = "qwen-plus"
    return {"configured": bool(key), "base_url": base_url, "model": model}


@app.get("/api/config/qwen")
def get_qwen():
    return _qwen_status_payload()


@app.post("/api/config/qwen")
def set_qwen(body: QwenConfigIn):
    # stored in-memory only
    set_qwen_config(body.api_key, body.base_url, body.model)
    out = _qwen_status_payload()
    return {"ok": True, **out}


@app.post("/api/jobs/{job_id}/start")
def start(job_id: str):
    jobs.start_job(job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str):
    jobs.cancel_job(job_id)
    return {"ok": True}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    try:
        j = jobs.get_job(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}") from e
    return model_to_dict(j)


@app.get("/api/jobs/{job_id}/images")
def job_images(job_id: str):
    run_dir = RUNS_ROOT / job_id
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"run dir not found: {job_id}")
    names = ["Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png"]
    existing = [n for n in names if (run_dir / n).exists()]
    return {"job_id": job_id, "images": existing}


@app.websocket("/ws/jobs/{job_id}")
async def ws_job(websocket: WebSocket, job_id: str):
    await websocket.accept()
    try:
        async for event in jobs.subscribe(job_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    import uvicorn

    reload_enabled = os.environ.get("UVICORN_RELOAD", "").strip().lower() in {"1", "true", "yes"}
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        reload=reload_enabled,
    )
