"""Design requirements API — Phase I NL → design checklist."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend.design_requirements.clarifications import (
    apply_clarification_reply,
    build_pending_clarifications,
    clarification_complete,
)
from backend.design_requirements.markdown import checklist_to_markdown
from backend.design_requirements.nl_parser import parse_design_checklist
from backend.design_requirements.paths import artifact_urls, find_checklist_dir, load_checklist, save_checklist

router = APIRouter(tags=["design-requirements"])


def _enrich_response(checklist, *, markdown: str | None = None) -> dict:
    md = markdown if markdown is not None else checklist_to_markdown(checklist)
    pending = build_pending_clarifications(checklist.meta.source_text, checklist)
    return {
        "checklist_id": checklist.meta.checklist_id,
        "checklist": checklist.model_dump(mode="json"),
        "markdown": md,
        "artifact_urls": artifact_urls(checklist.meta.checklist_id),
        "parser": checklist.meta.parser,
        "pending_clarifications": pending,
        "clarification_complete": clarification_complete(pending),
    }


class ParseDesignRequirementsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=32000)
    persist: bool = True


class ClarifyDesignRequirementsRequest(BaseModel):
    reply: str = Field(..., min_length=1, max_length=8000)


@router.post("/parse")
def parse_design_requirements(body: ParseDesignRequirementsRequest) -> dict:
    try:
        checklist = parse_design_checklist(body.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设计清单解析失败: {e}") from e

    md = checklist_to_markdown(checklist)
    out_dir = None
    if body.persist:
        out_dir = str(save_checklist(checklist, markdown=md))

    payload = _enrich_response(checklist, markdown=md)
    payload["out_dir"] = out_dir
    return payload


@router.post("/{checklist_id}/clarify")
def clarify_design_requirements(checklist_id: str, body: ClarifyDesignRequirementsRequest) -> dict:
    cl = load_checklist(checklist_id)
    if cl is None:
        raise HTTPException(status_code=404, detail="设计清单不存在")
    pending_before = build_pending_clarifications(cl.meta.source_text, cl)
    pending_ids = [p["field_id"] for p in pending_before]
    try:
        updated, _, remaining = apply_clarification_reply(
            cl,
            body.reply,
            pending_field_ids=pending_ids,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"澄清回复解析失败: {e}") from e
    md = checklist_to_markdown(updated)
    save_checklist(updated, markdown=md)
    payload = _enrich_response(updated, markdown=md)
    payload["clarification_reply"] = body.reply
    return payload


@router.get("/{checklist_id}")
def get_design_requirements(checklist_id: str) -> dict:
    cl = load_checklist(checklist_id)
    if cl is None:
        raise HTTPException(status_code=404, detail="设计清单不存在")
    return {
        "checklist_id": checklist_id,
        "checklist": cl.model_dump(mode="json"),
        "artifact_urls": artifact_urls(checklist_id),
    }


@router.get("/{checklist_id}/export/markdown")
def export_design_requirements_markdown(checklist_id: str) -> PlainTextResponse:
    d = find_checklist_dir(checklist_id)
    if d is None:
        raise HTTPException(status_code=404, detail="设计清单不存在")
    md_path = d / "design_checklist.md"
    if not md_path.is_file():
        cl = load_checklist(checklist_id)
        if cl is None:
            raise HTTPException(status_code=404, detail="设计清单不存在")
        md_path.write_text(checklist_to_markdown(cl), encoding="utf-8")
    return PlainTextResponse(
        md_path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="design_checklist_{checklist_id[:8]}.md"'},
    )
