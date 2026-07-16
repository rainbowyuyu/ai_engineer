from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from dotenv import load_dotenv

# 本地开发：从仓库根目录或 WORKSPACE_ROOT 下的 .env 注入 QWEN_*（不覆盖已在环境中的变量）
_backend_dir = Path(__file__).resolve().parent
_repo_root = _backend_dir.parent
for _root in (_repo_root, Path(os.environ.get("WORKSPACE_ROOT", _repo_root)).resolve()):
    _dotenv_file = _root / ".env"
    if _dotenv_file.is_file():
        load_dotenv(_dotenv_file, override=False)

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from backend.agent import decide_params
from backend.generator import scan_input_directory, build_generated_code
from backend.jobs.manager import jobs
from backend.models import (
    AssistantChatRequest,
    AssistantChatResponse,
    CadConvertRequest,
    CadConvertResponse,
    ChatRequest,
    ChatResponse,
)
from backend.qwen_client import QwenClient, assistant_chat_http_read_timeout_s
from backend.qwen_runtime_config import get_qwen_config, set_qwen_config, set_qwen_model_only
from backend.pydantic_compat import model_to_dict
from backend.tools.files import preview_inp, resolve_file, store_upload, uploads_root
from backend.tools.cad_iges_to_inp import (
    OUTPUT_INP_NAME,
    list_iges_in_dir,
    run_cad_iges_to_inp,
    suggest_char_length_max,
)
from backend.oc4_design_domain_service import session_dir as oc4_design_domain_session_dir
from backend.routes.oc4_design_domain_api import router as oc4_design_domain_router
from backend.routes.validation_api import router as validation_router
from backend.routes.design_requirements_api import router as design_requirements_router

logger = logging.getLogger(__name__)


def _ddg_snippet_for_query(query: str, *, timeout_s: float = 6.0) -> str:
    """DuckDuckGo Instant Answer API：无密钥轻量摘要，供「联网搜索」开关注入上下文。"""
    q = str(query or "").strip()
    if len(q) < 2:
        return ""
    if len(q) > 240:
        q = q[:240]
    url = f"https://api.duckduckgo.com/?q={quote_plus(q)}&format=json&no_html=1&skip_disambig=1"
    try:
        req = Request(url, headers={"User-Agent": "AIEngineer/1.0 (assistant; +https://local)"})
        with urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except Exception as e:
        logger.info("ddg instant answer failed: %s", e)
        return ""
    parts: list[str] = []
    abst = str(data.get("AbstractText") or "").strip()
    if abst:
        parts.append(abst)
    for t in data.get("RelatedTopics") or []:
        if isinstance(t, dict) and str(t.get("Text") or "").strip():
            parts.append(str(t["Text"]).strip())
        if len(parts) >= 4:
            break
    out = "\n".join(parts).strip()
    if len(out) > 1800:
        out = out[:1800] + "…"
    return out


def _last_user_text_from_request(body: "AssistantChatRequest") -> str:
    for m in reversed(list(body.messages or [])):
        if m.role != "user":
            continue
        c = m.content
        if isinstance(c, list):
            parts: list[str] = []
            for p in c:
                if isinstance(p, dict) and str(p.get("type") or "").strip() == "text":
                    parts.append(str(p.get("text") or ""))
            return "\n".join(parts).strip()
        return str(c or "").strip()
    return ""


def _effective_assistant_temperature(body: "AssistantChatRequest") -> float:
    t = body.temperature if body.temperature is not None else 0.6
    t = max(0.0, min(2.0, float(t)))
    if body.deep_think:
        t = max(0.12, min(t, 0.42))
    return t


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

app = FastAPI(title="AI Engineer Web")
app.include_router(oc4_design_domain_router, prefix="/api/oc4/design-domain")
app.include_router(validation_router, prefix="/api/validation")
app.include_router(design_requirements_router, prefix="/api/design-requirements")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/runs", StaticFiles(directory=str(RUNS_ROOT)), name="runs")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_ROOT)), name="uploads")


def _mount_workspace_cad_url_prefixes() -> None:
    """
    CAD Explorer 构建产物内资源 URL 为站点根路径 /{仓库相对路径}（如 /third_party/...），
    与 /cad-explorer 静态挂载分离；此处仅挂载常见含 CAD 源文件的顶层目录，避免整盘挂载。
    """
    for name in ("third_party", "examples"):
        d = (WORKSPACE_ROOT / name).resolve()
        if not d.is_dir():
            continue
        try:
            app.mount(f"/{name}", StaticFiles(directory=str(d)), name=f"workspace_cad_{name}")
        except Exception as e:
            logger.info("workspace CAD static mount /%s skipped: %s", name, e)


_mount_workspace_cad_url_prefixes()

_CAD_PRIMARY_EXPLORER_DIST = WORKSPACE_ROOT / "third_party" / "text-to-cad" / "cad_skill" / "explorer" / "dist"
_CAD_EXPORT_CATALOG_SCRIPT = (
    WORKSPACE_ROOT
    / "third_party"
    / "text-to-cad"
    / "cad_skill"
    / "explorer"
    / "scripts"
    / "export-catalog.mjs"
)
_CAD_EXPLORER_FALLBACK_STATIC = UI_ROOT / "cad_explorer_placeholder"


def _resolve_cad_explorer_static_dir() -> Path:
    """优先环境变量 CAD_EXPLORER_DIST，其次仓库内嵌 dist，否则使用占位页（避免 /cad-explorer 整段 404）。"""
    env = (os.environ.get("CAD_EXPLORER_DIST") or "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    if _CAD_PRIMARY_EXPLORER_DIST.is_dir():
        return _CAD_PRIMARY_EXPLORER_DIST.resolve()
    _CAD_EXPLORER_FALLBACK_STATIC.mkdir(parents=True, exist_ok=True)
    return _CAD_EXPLORER_FALLBACK_STATIC.resolve()


_CAD_EXPLORER_STATIC = _resolve_cad_explorer_static_dir()


@app.get("/cad-explorer", include_in_schema=False)
def cad_explorer_redirect_trailing_slash():
    """无尾斜杠时重定向，避免部分浏览器/iframe 落到错误路径。"""
    return RedirectResponse(url="/cad-explorer/")


app.mount(
    "/cad-explorer",
    StaticFiles(directory=str(_CAD_EXPLORER_STATIC), html=True),
    name="cad_explorer",
)
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


@app.get("/api/cad-explorer/status")
def api_cad_explorer_status():
    """排查 CAD Explorer 挂载路径（若 primary_exists=false 则当前为占位页）。"""
    primary = _CAD_PRIMARY_EXPLORER_DIST.resolve()
    return {
        "workspace_root": str(WORKSPACE_ROOT.resolve()),
        "primary_dist": str(primary),
        "primary_exists": primary.is_dir(),
        "serving_static_from": str(_CAD_EXPLORER_STATIC),
        "using_placeholder": not primary.is_dir(),
        "env_CAD_EXPLORER_DIST": (os.environ.get("CAD_EXPLORER_DIST") or "").strip() or None,
        "live_catalog_api": "/api/cad-explorer/catalog",
        "export_catalog_script": str(_CAD_EXPORT_CATALOG_SCRIPT),
        "export_catalog_script_exists": _CAD_EXPORT_CATALOG_SCRIPT.is_file(),
        "node_on_path": bool(shutil.which("node")),
    }


@app.get("/api/cad-explorer/catalog")
def api_cad_explorer_catalog():
    """
    运行时扫描 WORKSPACE_ROOT 下的 CAD 源文件，返回与 CAD Explorer 构建时相同 schema 的 catalog。
    解决 STEP 在 npm build 之后才生成、烘焙清单不含该文件导致「File does not exist」的问题。
    """
    if not _CAD_EXPORT_CATALOG_SCRIPT.is_file():
        raise HTTPException(
            status_code=501,
            detail="缺少 export-catalog.mjs，无法生成动态目录。",
        )
    node = shutil.which("node")
    if not node:
        raise HTTPException(status_code=503, detail="未找到 node 可执行文件，无法扫描 CAD 目录。")
    env = {**os.environ, "EXPLORER_WORKSPACE_ROOT": str(WORKSPACE_ROOT.resolve())}
    try:
        proc = subprocess.run(
            [node, str(_CAD_EXPORT_CATALOG_SCRIPT)],
            cwd=str(_CAD_EXPORT_CATALOG_SCRIPT.parent),
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="CAD 目录扫描超时") from e
    except OSError as e:
        raise HTTPException(status_code=503, detail=f"无法执行 node 扫描: {e}") from e
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()
        if len(tail) > 4000:
            tail = tail[:4000] + "…"
        raise HTTPException(status_code=500, detail=f"catalog 扫描失败（exit {proc.returncode}）: {tail or 'no output'}")
    raw = (proc.stdout or "").strip()
    if not raw:
        raise HTTPException(status_code=500, detail="catalog 扫描无输出")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"catalog JSON 无效: {e}") from e


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
    temp = _effective_assistant_temperature(body)
    if body.tools_enabled:
        from backend.assistant_tool_loop import run_assistant_tool_loop

        try:
            out = run_assistant_tool_loop(
                qwen,
                msgs,
                temperature=temp,
                workspace_root=WORKSPACE_ROOT,
                runs_root=RUNS_ROOT,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except Exception as e:
            logger.exception("assistant_chat tools loop failed")
            raise HTTPException(
                status_code=503,
                detail=f"模型或工具执行异常: {e}。请查看本机后端控制台日志。",
            ) from e
        reply = str(out.reply or "").strip() or "（无回复）"
        return AssistantChatResponse(
            reply=reply,
            model=out.model,
            client_actions=out.client_actions or None,
            tool_trace=out.tool_trace or None,
        )
    try:
        data = qwen.chat(msgs, temperature=temp)
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


@app.post("/api/tools/cad-convert", response_model=CadConvertResponse)
def api_tools_cad_convert(body: CadConvertRequest):
    """工作区内 CAD 格式转换（FreeCAD），与助手工具 cad_convert 共用逻辑。"""
    from backend.tools.freecad_cad_convert import cad_convert_to_runs_subdir, resolve_workspace_path

    try:
        inp = resolve_workspace_path(body.input_rel_or_abs, WORKSPACE_ROOT)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not inp.is_file():
        raise HTTPException(status_code=400, detail="输入路径不是有效文件")
    try:
        out_abs, url = cad_convert_to_runs_subdir(
            inp,
            body.target_format,
            workspace_root=WORKSPACE_ROOT,
            runs_root=RUNS_ROOT,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("cad-convert failed")
        return CadConvertResponse(ok=False, detail=str(e)[:800])
    return CadConvertResponse(ok=True, output_path=str(out_abs), runs_url=url)


def _assistant_messages_for_qwen(body: AssistantChatRequest) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in body.messages]
    fn = str(body.attached_file_name or "").strip()
    fid = str(body.attached_file_id or "").strip()
    file_ctx = ""
    if fn or fid:
        who = f"「{fn}」" if fn else "（已绑定上传）"
        fid_part = f" file_id={fid}" if fid else ""
        file_ctx = (
            "【会话上下文】当前工程任务已在平台关联上传文件："
            f"{who}{fid_part}。"
            "用户尚未进入设计域/构型优化编排子流程时，你也应默认该文件已存在且可被后续流程使用；"
            "不要再说「未看到对方文件」「请先上传」「不知道用户有什么文件」等推脱；"
            "若缺扫描目录、材料参数等需用户补充的信息，再明确追问。"
            "\n"
        )
    base_system = (
        "你是「AI Engineer」的对话助手；角色为 AI 工程与结构仿真方向的专家，熟悉结构/拓扑优化（含 BESO、SIMP）、CalculiX、"
        "INP 网格与边界条件、以及本产品中设计域—拓扑优化编排—任务流程。"
        "用简洁中文回答；需要时分点说明，可使用 Markdown；不要编造不存在的文件路径。"
        "若用户讨论 **OC4 半潜式浮式风机** 概念阶段拓扑优化：回答须与后端定标一致——设计域几何、INP 荷载边界、"
        "`design_space`/`nondesign_space` 划分、BESO 参数以 `backend/oc4_methodology_chen2026.py` 的 `LLM_CONTEXT_BLOCK_ZH` 为唯一基准"
        "（含 `01_…`→`03_for_beso.inp` 会话链与 `examples/beso/Analysis-beso.inp` FCStd 基准）；勿混杂互相矛盾的「自创流程」。"
        "拓扑之后水动力重构用 OpenFAST/AQWA 等另建模型，本工具链交付可算 INP + BESO。"
    )
    if not msgs or msgs[0]["role"] != "system":
        msgs = [{"role": "system", "content": file_ctx + base_system}, *msgs]
    elif file_ctx:
        msgs[0] = {**msgs[0], "content": file_ctx + msgs[0]["content"]}

    mode_parts: list[str] = []
    if body.deep_think:
        mode_parts.append(
            "【深度思考模式·已开启】请采用显式结构：①已知条件与假设 ②分步推理 ③结论与注意事项；"
            "对结构/仿真结论给出可检验依据，避免跳步；不确定处请声明。"
        )
    if body.web_search:
        uq = _last_user_text_from_request(body)
        if uq:
            snippet = _ddg_snippet_for_query(uq)
            if snippet:
                mode_parts.append(
                    "【联网检索摘要·DuckDuckGo Instant Answer】与「用户最后一条消息」相关的公开摘要（可能片面或与工程场景不符），"
                    "请批判性取舍，勿当作正式规范或论文原文引用：\n"
                    + snippet
                )
            else:
                mode_parts.append(
                    "【联网检索】已尝试抓取公开摘要但未获得有效条目；请基于训练知识与用户上下文作答，"
                    "勿虚构网址或声称「实时网页已打开」。"
                )
        else:
            mode_parts.append("【联网检索】对话中缺少用户文本，已跳过外部摘要。")
    if mode_parts:
        extra = "\n\n".join(mode_parts)
        sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
        if sys_i is not None:
            cur = str(msgs[sys_i].get("content") or "")
            msgs[sys_i] = {**msgs[sys_i], "content": (cur + "\n\n" + extra).strip()}
        else:
            msgs = [{"role": "system", "content": extra}, *msgs]
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
            for line in qwen.chat_stream(msgs, temperature=_effective_assistant_temperature(body)):
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


@app.post("/api/assistant/chat/stream-tools")
def assistant_chat_stream_tools(body: AssistantChatRequest):
    """
    工具模式下的 NDJSON/SSE：推送 thought、工具调用、产物路径，并对最终 ``final_reply`` 分块输出。
    请求体与 ``POST /api/assistant/chat`` 相同，且 **必须** ``tools_enabled=true``。
    """
    from backend.assistant_tool_loop import iter_assistant_tool_loop_events

    if not body.tools_enabled:
        raise HTTPException(
            status_code=400,
            detail="stream-tools 仅支持 tools_enabled=true；关闭工具时请用 /api/assistant/chat/stream",
        )

    def gen():
        qwen = QwenClient(timeout_s=assistant_chat_http_read_timeout_s())
        if not qwen.api_key:
            yield (
                "data: "
                + json.dumps(
                    {"type": "error", "message": "未配置大模型密钥：请在 .env 设置 QWEN_API_KEY。"},
                    ensure_ascii=False,
                )
                + "\n\n"
            )
            return
        msgs = _assistant_messages_for_qwen(body)
        temp = _effective_assistant_temperature(body)
        try:
            for ev in iter_assistant_tool_loop_events(
                qwen,
                msgs,
                temperature=temp,
                workspace_root=WORKSPACE_ROOT,
                runs_root=RUNS_ROOT,
            ):
                yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
        except Exception as e:
            logger.exception("assistant_chat_stream_tools failed")
            yield "data: " + json.dumps({"type": "error", "message": str(e)[:1200]}, ensure_ascii=False) + "\n\n"

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

    checklist_beso = None
    if req.design_checklist_id:
        from backend.design_requirements.paths import load_checklist

        cl = load_checklist(req.design_checklist_id)
        if cl is not None:
            checklist_beso = cl.job_descriptor.theta.beso

    mass_goal_ratio = req.mass_goal_ratio
    if mass_goal_ratio is None and checklist_beso is not None:
        mass_goal_ratio = checklist_beso.mass_goal_ratio
    if mass_goal_ratio is None:
        mass_goal_ratio = parsed.mass_goal_ratio
    mass_goal_ratio = max(0.05, min(0.99, float(mass_goal_ratio)))

    filter_radius = req.filter_radius
    if filter_radius is None and checklist_beso is not None:
        filter_radius = checklist_beso.filter_radius
    if filter_radius is None:
        filter_radius = parsed.filter_radius

    optimization_base_raw = req.optimization_base
    if optimization_base_raw is None and checklist_beso is not None:
        optimization_base_raw = checklist_beso.optimization_base
    if optimization_base_raw is None:
        optimization_base_raw = parsed.optimization_base
    optimization_base = _sanitize_optimization_base(optimization_base_raw)

    save_every = req.save_every
    if save_every is None and checklist_beso is not None:
        save_every = checklist_beso.save_every
    if save_every is None:
        save_every = parsed.save_every
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
    payload = bundle.as_dict()
    payload["workspace_root"] = str(WORKSPACE_ROOT.resolve())
    return payload


@app.get("/api/scan_directory")
def scan_directory_legacy(scan_dir: str):
    # Backward-compatible alias for clients using underscore style.
    return scan_directory(scan_dir)


def _resolve_design_domain_explorer_target(session_id: str, rel: str = "") -> Path:
    """解析设计域会话在 runs/_design_domain/<id> 下的目录，用于打开资源管理器。"""
    sid = str(session_id or "").strip()
    if not sid.isalnum() or len(sid) < 16:
        raise HTTPException(status_code=400, detail="invalid design_domain_session_id")
    sdir = oc4_design_domain_session_dir(WORKSPACE_ROOT, sid).resolve()
    if not sdir.is_dir():
        raise HTTPException(status_code=404, detail="设计域会话目录不存在")
    if not _path_under_workspace(sdir):
        raise HTTPException(status_code=400, detail="invalid session path")
    raw = str(rel or "").strip().replace("\\", "/").lstrip("/")
    if not raw:
        return sdir
    if ".." in Path(raw).parts:
        raise HTTPException(status_code=400, detail="invalid design_domain_rel")
    sub = (sdir / raw).resolve()
    try:
        sub.relative_to(sdir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path outside session") from e
    if sub.is_dir():
        return sub
    return sub.parent.resolve()


def _open_explorer_folder_core(raw: str) -> dict:
    """
    在本机打开工作区内的目录（Windows 资源管理器 / macOS Finder / Linux 文件管理器）。
    仅当浏览器访问的后端与桌面在同一台机器上时有效；远程部署会失败属预期。
    """
    raw = str(raw or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="请提供 scan_dir 或 path")
    try:
        p = Path(raw).expanduser().resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"路径无效: {e}") from e
    if not p.exists():
        raise HTTPException(status_code=400, detail="路径不存在或暂不可访问")
    if not _path_under_workspace(p):
        raise HTTPException(status_code=400, detail="仅允许打开 WORKSPACE_ROOT 工作区内的路径")
    target = p if p.is_dir() else p.parent
    try:
        target = target.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"无法解析目录: {e}") from e
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="无法解析为有效目录")
    if not _path_under_workspace(target):
        raise HTTPException(status_code=400, detail="目标目录必须位于工作区内")
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)], start_new_session=True)
        else:
            subprocess.Popen(["xdg-open", str(target)], start_new_session=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"无法打开文件管理器: {e}") from e
    return {"ok": True, "opened": str(target)}


@app.post("/api/open-explorer-folder")
def open_explorer_folder_post(body: dict | None = None):
    b = body if isinstance(body, dict) else {}
    sid = str(b.get("design_domain_session_id") or "").strip()
    if sid:
        rel = str(b.get("design_domain_rel") or b.get("rel") or "").strip()
        target = _resolve_design_domain_explorer_target(sid, rel)
        return _open_explorer_folder_core(str(target))
    raw = str(b.get("scan_dir") or b.get("path") or "").strip()
    return _open_explorer_folder_core(raw)


@app.get("/api/open-explorer-folder")
def open_explorer_folder_get(
    scan_dir: str = "",
    path: str = "",
    design_domain_session_id: str = "",
    design_domain_rel: str = "",
):
    """GET 别名：便于排查或受限环境下与 POST 等价。"""
    sid = str(design_domain_session_id or "").strip()
    if sid:
        target = _resolve_design_domain_explorer_target(sid, str(design_domain_rel or "").strip())
        return _open_explorer_folder_core(str(target))
    raw = str(scan_dir or path or "").strip()
    return _open_explorer_folder_core(raw)


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


@app.post("/api/preview/inp-mesh-vtk")
async def preview_inp_mesh_vtk(file: UploadFile = File(...)):
    """将网格主 INP 转为 VTK Legacy ASCII（FreeCAD Fem），供前端三维预览。"""
    fn = (file.filename or "mesh.inp").lower()
    if not fn.endswith(".inp"):
        raise HTTPException(status_code=400, detail="需要上传 .inp 网格文件")
    content = await file.read()
    max_b = 80 * 1024 * 1024
    if len(content) > max_b:
        raise HTTPException(status_code=413, detail="INP 超过 80MB 上限")

    from backend.tools.freecad_inp_mesh_vtk import convert_inp_to_vtk_file

    with tempfile.NamedTemporaryFile(suffix=".inp", delete=False) as tf_inp:
        tf_inp.write(content)
        inp_path = Path(tf_inp.name)
    out_path = inp_path.with_suffix(".vtk")
    try:
        convert_inp_to_vtk_file(inp_path, out_path, timeout_s=240.0)
        vtk_text = out_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="FreeCAD 转换超时") from e
    finally:
        try:
            inp_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass

    return PlainTextResponse(vtk_text, media_type="text/plain; charset=utf-8")


class Beso7ParametricRebuildRequest(BaseModel):
    measurements_path: str
    out_dir: str | None = None
    params: dict[str, Any] | None = None
    preview_only: bool = True


@app.post("/api/beso7/parametric-rebuild")
def api_beso7_parametric_rebuild(body: Beso7ParametricRebuildRequest):
    """BESO7 方法一：按 measurements.json + 半径缩放参数重建变径柱 preview.stl。"""
    from backend.tools.beso7_parametric_rebuild import run_beso7_parametric_rebuild

    meas = Path(body.measurements_path).resolve()
    if not meas.is_file():
        raise HTTPException(status_code=400, detail=f"measurements.json 不存在: {meas}")
    if not _path_under_workspace(meas):
        raise HTTPException(status_code=400, detail="路径必须位于工作区 WORKSPACE_ROOT 内")

    out_dir = Path(body.out_dir).resolve() if body.out_dir else meas.parent.resolve()
    if not _path_under_workspace(out_dir):
        raise HTTPException(status_code=400, detail="out_dir 必须位于工作区 WORKSPACE_ROOT 内")

    try:
        stl_path = run_beso7_parametric_rebuild(
            measurements_path=meas,
            out_dir=out_dir,
            params=body.params,
            preview_only=bool(body.preview_only),
            timeout_s=240.0,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="FreeCAD 重建超时") from e
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    rel = stl_path.resolve().relative_to(WORKSPACE_ROOT.resolve())
    if rel.parts and rel.parts[0] in {"runs", "examples", "third_party", "uploads"}:
        url = "/" + "/".join(quote_plus(p) for p in rel.parts)
    else:
        url = None

    return {
        "ok": True,
        "preview_path": str(stl_path),
        "preview_url": url,
        "measurements_path": str(meas),
        "out_dir": str(out_dir),
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


def _msg_is_user_turn(msg: object) -> bool:
    if not isinstance(msg, dict):
        return False
    return str(msg.get("role", "")).strip().lower() == "user"


def _user_turn_fingerprint(msg: object) -> tuple[str, str] | None:
    """用于比较用户句是否变化，避免整段 dict 引用/键序导致误判。"""
    if not isinstance(msg, dict) or not _msg_is_user_turn(msg):
        return None
    c = str(msg.get("content", "")).strip()
    att = msg.get("attachment")
    fid = ""
    if isinstance(att, dict):
        fid = str(att.get("file_id", "")).strip()
    return (c, fid)


def _user_input_bumps_task_order(old_th: object, new_th: object) -> bool:
    """仅当线程里出现新的或变更的「用户」消息时把任务顶到侧栏最前；助手回复等不触发，避免列表闪动。"""
    old_l: list = old_th if isinstance(old_th, list) else []
    new_l: list = new_th if isinstance(new_th, list) else []
    old_fps = [fp for m in old_l if (fp := _user_turn_fingerprint(m)) is not None]
    new_fps = [fp for m in new_l if (fp := _user_turn_fingerprint(m)) is not None]
    if len(new_fps) > len(old_fps):
        return True
    if not new_fps:
        return False
    if not old_fps:
        return True
    return new_fps[-1] != old_fps[-1]


def _save_task(task_id: str, payload: dict, *, bump_order: bool = False) -> None:
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
    old_ids = _read_task_index_ids()
    stripped = [x for x in old_ids if x != task_id]
    if task_id in old_ids:
        pos = old_ids.index(task_id)
        if bump_order:
            new_ids = [task_id] + stripped
        else:
            new_ids = stripped[:pos] + [task_id] + stripped[pos:]
    else:
        if bump_order:
            new_ids = [task_id] + stripped
        else:
            new_ids = stripped + [task_id]
    idx_file.write_text(json.dumps(new_ids, ensure_ascii=False, indent=2), encoding="utf-8")


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
    # 为 True 时才允许根据「用户句」变化把任务顶到侧栏最前；同步/切任务等勿传，避免误触置顶
    allow_sidebar_reorder: bool | None = None


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
        allow_reorder = incoming.get("allow_sidebar_reorder") is True
        for k, v in incoming.items():
            if k == "task_id":
                continue
            if k == "allow_sidebar_reorder":
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
        inc_th = incoming.get("assistant_thread")
        if isinstance(inc_th, list):
            inc_th = inc_th[-200:]
        bump_order = bool(allow_reorder and inc_th is not None) and _user_input_bumps_task_order(
            existing.get("assistant_thread"),
            inc_th,
        )
        _save_task(body.task_id, payload, bump_order=bump_order)
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


class QwenModelOnlyIn(BaseModel):
    model: str


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


@app.post("/api/config/qwen/model")
def set_qwen_model(body: QwenModelOnlyIn):
    m = (body.model or "").strip()
    if not m:
        raise HTTPException(status_code=400, detail="model 不能为空")
    set_qwen_model_only(m)
    return {"ok": True, **_qwen_status_payload()}


@app.get("/api/config/editor")
def get_editor_config():
    """VS Code Web / OpenVSCode 侧车：iframe 基址（同源反代路径或绝对 URL）。未配置则前端使用内置 textarea。"""
    base = (os.environ.get("BESO_VSCODE_IFRAME_BASE_URL") or "").strip().rstrip("/")
    return {
        "vscode_iframe_base": base or None,
        "folder_query_param": "folder",
        "hint": "将侧车工作区根目录映射到 WORKSPACE_ROOT；设计域会话路径为 runs/_design_domain/<session_id>。",
    }


@app.get("/api/config/editor/session-open")
def editor_session_open(session_id: str = Query(..., min_length=16)):
    """为设计域会话生成侧车 iframe 打开 URL（folder= 会话目录绝对路径）。"""
    if not session_id.isalnum():
        raise HTTPException(status_code=400, detail="invalid session_id")
    base = (os.environ.get("BESO_VSCODE_IFRAME_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "url": None}
    root = Path(os.environ.get("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[1]))).resolve()
    folder = (root / "runs" / "_design_domain" / session_id).resolve()
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        folder.relative_to(root)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid session path") from e
    from urllib.parse import quote

    u = f"{base}/?folder={quote(str(folder), safe='')}"
    return {"ok": True, "url": u}


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
