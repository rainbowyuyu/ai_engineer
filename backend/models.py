from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


class AssistantChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., max_length=32000)


class AssistantChatRequest(BaseModel):
    """通用对话（OpenAI-compatible Qwen），与编排用的 /api/chat 不同。"""

    messages: list[AssistantChatMessage] = Field(..., min_length=1, max_length=64)
    temperature: float | None = Field(default=0.6, ge=0, le=2)

    @field_validator("messages", mode="before")
    @classmethod
    def _drop_non_chat_roles(cls, v):
        """前端 localStorage 线程可能含 role=card 等 UI 结构；仅保留 Qwen 允许的三种 role。"""
        if not isinstance(v, list):
            return v
        allowed = frozenset({"system", "user", "assistant"})
        out: list[dict] = []
        for item in v:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            if role not in allowed:
                continue
            raw = item.get("content")
            if raw is None and item.get("text") is not None:
                raw = item.get("text")
            text = str(raw or "").strip()
            if not text:
                continue
            out.append({"role": role, "content": text[:32000]})
        if not out:
            raise ValueError("messages 需至少包含一条有效对话（role 为 system/user/assistant 且 content 非空）")
        return out[:64]


class AssistantChatResponse(BaseModel):
    reply: str
    model: str | None = None

