from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _assistant_multimodal_parts_ok(parts: list) -> bool:
    """OpenAI 兼容：user.content 可为 [{type:text,...},{type:image_url,...}]。"""
    if not isinstance(parts, list) or not parts:
        return False
    has_payload = False
    for p in parts:
        if not isinstance(p, dict):
            return False
        t = str(p.get("type") or "").strip()
        if t == "text":
            tx = str(p.get("text") or "").strip()
            if tx:
                has_payload = True
        elif t == "image_url":
            iu = p.get("image_url")
            if not isinstance(iu, dict):
                return False
            url = str(iu.get("url") or "").strip()
            if url.startswith("data:image/") or url.startswith("http://") or url.startswith("https://"):
                has_payload = True
        else:
            return False
    return has_payload


def _trim_multimodal_parts(parts: list, *, max_text: int = 32000, max_images: int = 6, max_data_url: int = 1_200_000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n_img = 0
    for p in parts:
        if not isinstance(p, dict):
            continue
        t = str(p.get("type") or "").strip()
        if t == "text":
            tx = str(p.get("text") or "").strip()[:max_text]
            if tx:
                out.append({"type": "text", "text": tx})
        elif t == "image_url" and n_img < max_images:
            iu = p.get("image_url") if isinstance(p.get("image_url"), dict) else {}
            url = str(iu.get("url") or "").strip()
            if len(url) > max_data_url:
                url = url[:max_data_url]
            if url:
                out.append({"type": "image_url", "image_url": {"url": url}})
                n_img += 1
    return out


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
    content: str | list[dict[str, Any]] = Field(..., description="纯文本或多模态 parts（仅 user 推荐）")


class AssistantChatRequest(BaseModel):
    """通用对话（OpenAI-compatible Qwen），与编排用的 /api/chat 不同。"""

    messages: list[AssistantChatMessage] = Field(..., min_length=1, max_length=64)
    temperature: float | None = Field(default=0.6, ge=0, le=2)
    attached_file_name: str | None = Field(
        default=None,
        max_length=512,
        description="主页 landing 已绑定上传文件名时由前端传入",
    )
    attached_file_id: str | None = Field(
        default=None,
        max_length=128,
        description="对应 file_id，可选",
    )
    deep_think: bool = Field(default=False, description="深度思考：系统提示强化分步推理，并略降低采样温度")
    web_search: bool = Field(
        default=False,
        description="联网摘要：服务端用 DuckDuckGo Instant Answer 抓取与本轮用户问题相关的短摘要注入上下文",
    )
    tools_enabled: bool = Field(
        default=False,
        description="开启后走服务端 JSON 工具循环（cad_convert / open_results_viewer / list_scan_dir / cad_skill_help / cad_skill_step / open_cad_explorer），响应含 client_actions 与 tool_trace",
    )

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
            if isinstance(raw, list):
                if role != "user":
                    continue
                if not _assistant_multimodal_parts_ok(raw):
                    continue
                trimmed = _trim_multimodal_parts(raw)
                if not trimmed:
                    continue
                out.append({"role": role, "content": trimmed})
            else:
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
    client_actions: list[dict[str, Any]] | None = Field(
        default=None,
        description="前端可执行动作，如 open_results_viewer",
    )
    tool_trace: list[dict[str, Any]] | None = Field(
        default=None,
        description="本轮工具调用摘要（已脱敏），供 UI 折叠展示",
    )


class CadConvertRequest(BaseModel):
    """POST /api/tools/cad-convert：将工作区内 CAD 转为 STEP/IGES/STL/BREP 并写入 runs/_cad_convert/format/<id>/。"""

    input_rel_or_abs: str = Field(..., max_length=4096, description="工作区内绝对路径或相对 WORKSPACE_ROOT 的路径")
    target_format: Literal["step", "iges", "stl", "brep"] = Field(..., description="目标格式")


class CadConvertResponse(BaseModel):
    ok: bool
    output_path: str | None = None
    runs_url: str | None = Field(default=None, description="相对站点根的 /runs/... URL")
    detail: str | None = None

