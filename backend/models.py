from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="User natural language request")
    # preferred: user uploads file then passes file_id
    file_id: str | None = Field(default=None, description="Uploaded file id returned by /api/files/upload")
    # fallback: absolute path (legacy mode)；可为 .inp 或 .igs/.iges（后者在服务端正转为 INP 再优化）
    inp_path: str | None = Field(default=None, description="Absolute path to inp or iges file on disk (legacy)")
    # new mode: scan a directory to auto-discover inputs
    scan_dir: str | None = Field(default=None, description="Absolute directory path for auto scan mode")
    # 当 scan_dir 下存在多个 IGES 时指定文件名（与 /api/cad/convert-iges 一致）
    iges_name: str | None = Field(default=None, description="IGES filename under scan_dir when multiple .igs exist")

    # optional overrides; if omitted, can be filled by LLM
    mass_goal_ratio: float | None = None
    filter_radius: float | None = None
    optimization_base: str | None = None  # failure_index or stiffness
    save_every: int | None = None
    auto_start: bool = True


class ChatResponse(BaseModel):
    job_id: str
    parsed_params: dict | None = None
    reasoning_summary: str | None = None
    generated_code: list[dict] | None = None
    selected_inputs: dict | None = None

