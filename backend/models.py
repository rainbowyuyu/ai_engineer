from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="User natural language request")
    # preferred: user uploads file then passes file_id
    file_id: str | None = Field(default=None, description="Uploaded file id returned by /api/files/upload")
    # fallback: absolute path (legacy mode)
    inp_path: str | None = Field(default=None, description="Absolute path to inp file on disk (legacy)")

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

