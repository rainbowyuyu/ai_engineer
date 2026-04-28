from __future__ import annotations

import os
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


@app.get("/")
def root():
    if UI_ROOT.exists():
        return RedirectResponse(url="/ui/")
    return {"ok": True, "ui": False}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Resolve inp path: prefer uploaded file_id
    inp_path = req.inp_path
    bundle = None
    if req.file_id:
        sf = resolve_file(WORKSPACE_ROOT, req.file_id)
        inp_path = str(sf.path)
    elif req.scan_dir:
        bundle = scan_input_directory(req.scan_dir)
        inp_path = bundle.primary_inp

    # LLM parse (only if API key set). User may still override specific fields.
    parsed = decide_params(req.message)
    mass_goal_ratio = req.mass_goal_ratio if req.mass_goal_ratio is not None else parsed.mass_goal_ratio
    filter_radius = req.filter_radius if req.filter_radius is not None else parsed.filter_radius
    optimization_base = req.optimization_base if req.optimization_base is not None else parsed.optimization_base
    save_every = req.save_every if req.save_every is not None else parsed.save_every

    generated_bundle = None
    generated_code_meta: list[dict] = []

    job = jobs.create_job(
        user_message=req.message,
        inp_path=inp_path,
        mass_goal_ratio=mass_goal_ratio,
        filter_radius=filter_radius,
        optimization_base=optimization_base,
        save_every=save_every,
        generated_code_files=[],
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
            generated_code_meta.append({"name": name, "url": f"/runs/{job.id}/{name}"})
        jobs.set_generated_code_files(job.id, list(generated_bundle.files.keys()))

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
    return {
        "file_id": sf.file_id,
        "name": sf.name,
        "ext": sf.ext,
        "url": f"/uploads/{sf.file_id}/{sf.name}",
    }


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
    j = jobs.get_job(job_id)
    return j.model_dump()


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

    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
    )
