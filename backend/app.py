from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from backend.agent import decide_params
from backend.generator import scan_input_directory, build_generated_code
from backend.jobs.manager import jobs
from backend.models import ChatRequest, ChatResponse
from backend.qwen_runtime_config import get_qwen_config, set_qwen_config
from backend.tools.files import preview_inp, resolve_file, store_upload, uploads_root


WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()
RUNS_ROOT = WORKSPACE_ROOT / "runs"
RUNS_ROOT.mkdir(parents=True, exist_ok=True)
TASKS_ROOT = RUNS_ROOT / "_tasks"
TASKS_ROOT.mkdir(parents=True, exist_ok=True)
UI_ROOT = WORKSPACE_ROOT / "frontend_static"
UPLOADS_ROOT = uploads_root(WORKSPACE_ROOT)
UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="BESO Agent Web")

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


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Resolve inp path: prefer scan_dir for multi-inp merged mode.
    inp_path = req.inp_path
    bundle = None
    if req.scan_dir:
        bundle = scan_input_directory(req.scan_dir)
        inp_path = bundle.primary_inp
    elif req.file_id:
        sf = resolve_file(WORKSPACE_ROOT, req.file_id)
        inp_path = str(sf.path)

    # LLM parse (only if API key set). User may still override specific fields.
    parsed = decide_params(req.message)
    is_example2_mode = bool(req.scan_dir and "example_2" in str(req.scan_dir).lower())

    # For example_2 multi-file workflow, keep deterministic defaults unless user explicitly overrides.
    if is_example2_mode:
        parsed.mass_goal_ratio = 0.4
        parsed.filter_radius = 2.0
        parsed.optimization_base = "failure_index"
        parsed.save_every = 10
        parsed.reasoning_summary = "检测到 example_2 多文件任务，采用与示例一致的稳定参数（可由设置覆盖）。"

    mass_goal_ratio = req.mass_goal_ratio if req.mass_goal_ratio is not None else parsed.mass_goal_ratio
    filter_radius = req.filter_radius if req.filter_radius is not None else parsed.filter_radius
    optimization_base_raw = req.optimization_base if req.optimization_base is not None else parsed.optimization_base
    optimization_base = _sanitize_optimization_base(optimization_base_raw)
    save_every = req.save_every if req.save_every is not None else parsed.save_every

    generated_bundle = None
    generated_code_meta: list[dict] = []
    selected_inputs: dict | None = None

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
        if not inp_path:
            raise HTTPException(status_code=400, detail="扫描目录中未找到可用 inp 文件")
        ccx_path = Path(os.environ.get("CCX_PATH", r"D:\freecad\bin\ccx.exe")).resolve()
        generated_bundle = build_generated_code(
            bundle=bundle,
            run_dir=Path(job.run_dir),
            ccx_path=ccx_path,
            mass_goal_ratio=mass_goal_ratio,
            filter_radius=filter_radius,
            optimization_base=optimization_base,
            save_every=save_every,
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


@app.post("/api/files/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    sf = store_upload(WORKSPACE_ROOT, file.filename or "upload", content)
    suggested_scan_dir = _suggest_scan_dir_by_filename(sf.name)
    return {
        "file_id": sf.file_id,
        "name": sf.name,
        "ext": sf.ext,
        "url": f"/uploads/{sf.file_id}/{sf.name}",
        "suggested_scan_dir": suggested_scan_dir,
    }


def _task_file(task_id: str) -> Path:
    safe = "".join(ch for ch in str(task_id) if ch.isalnum() or ch in {"-", "_"})
    return TASKS_ROOT / f"{safe}.json"


def _task_index_file() -> Path:
    return TASKS_ROOT / "index.json"


def _load_task(task_id: str) -> dict | None:
    p = _task_file(task_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_task(task_id: str, payload: dict) -> None:
    p = _task_file(task_id)
    payload = dict(payload or {})
    payload["task_id"] = task_id
    payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
    if "created_at" not in payload:
        payload["created_at"] = payload["updated_at"]
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    idx_file = _task_index_file()
    ids: list[str] = []
    if idx_file.exists():
        try:
            ids = json.loads(idx_file.read_text(encoding="utf-8"))
        except Exception:
            ids = []
    ids = [x for x in ids if x != task_id]
    ids.insert(0, task_id)
    idx_file.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_task(task_id: str) -> None:
    p = _task_file(task_id)
    if p.exists():
        p.unlink(missing_ok=True)
    idx_file = _task_index_file()
    if idx_file.exists():
        try:
            ids = json.loads(idx_file.read_text(encoding="utf-8"))
        except Exception:
            ids = []
        ids = [x for x in ids if x != task_id]
        idx_file.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/tasks")
def list_tasks():
    idx_file = _task_index_file()
    ids: list[str] = []
    if idx_file.exists():
        try:
            ids = json.loads(idx_file.read_text(encoding="utf-8"))
        except Exception:
            ids = []
    items: list[dict] = []
    for task_id in ids[:200]:
        task = _load_task(task_id)
        if task:
            items.append(task)
    return {"items": items}


class TaskUpsertIn(BaseModel):
    task_id: str
    title: str | None = None
    progress: int | None = None
    step: int | None = None
    status: str | None = None
    file_name: str | None = None
    job_id: str | None = None
    scan_dir: str | None = None


@app.post("/api/tasks/upsert")
def upsert_task(body: TaskUpsertIn):
    existing = _load_task(body.task_id) or {}
    payload = dict(existing)
    for k, v in body.model_dump().items():
        if v is not None:
            payload[k] = v
    _save_task(body.task_id, payload)
    return {"ok": True, "task": payload}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
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


@app.get("/api/config/qwen")
def get_qwen():
    cfg = get_qwen_config()
    return {
        "configured": bool(cfg.api_key),
        "base_url": cfg.base_url,
        "model": cfg.model,
    }


@app.post("/api/config/qwen")
def set_qwen(body: QwenConfigIn):
    # stored in-memory only
    set_qwen_config(body.api_key, body.base_url, body.model)
    cfg = get_qwen_config()
    return {
        "ok": True,
        "configured": bool(cfg.api_key),
        "base_url": cfg.base_url,
        "model": cfg.model,
    }


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
    return j.model_dump()


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
