"""Validation API: score geometry JSON against DNV rules and fleet benchmarks."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.tools.freecad_cad_convert import resolve_workspace_path
from backend.validation.paths import (
    artifact_urls,
    find_validation_dir,
    safe_artifact_name,
    validation_runs_root,
    workspace_root,
)
from backend.validation.pipeline import run_validation
from backend.validation.rules_engine import load_rules

router = APIRouter(tags=["validation"])

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GEOMETRY = _REPO_ROOT / "rules" / "optimized_geometry.json"

_MEDIA_TYPES = {
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ValidationOptions(BaseModel):
    use_llm_rationale: bool = False
    candidate_label: str = "Candidate"


class ValidationRunRequest(BaseModel):
    geometry_path: str | None = Field(
        default=None,
        description="Path to geometry JSON under WORKSPACE_ROOT",
    )
    geometry: dict[str, Any] | None = Field(default=None, description="Inline geometry JSON")
    options: ValidationOptions = Field(default_factory=ValidationOptions)


@router.post("/run")
def validation_run(body: ValidationRunRequest) -> dict[str, Any]:
    root = workspace_root()
    if body.geometry is not None:
        geometry = body.geometry
        src = "inline"
    else:
        path_str = body.geometry_path or str(DEFAULT_GEOMETRY.relative_to(root))
        try:
            geom_path = resolve_workspace_path(path_str, root)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not geom_path.is_file():
            raise HTTPException(status_code=404, detail=f"Geometry JSON not found: {geom_path}")
        geometry = json.loads(geom_path.read_text(encoding="utf-8"))
        src = str(geom_path.relative_to(root)).replace("\\", "/")

    out_dir = validation_runs_root() / uuid.uuid4().hex
    try:
        result = run_validation(
            geometry,
            out_dir=out_dir,
            use_llm_rationale=body.options.use_llm_rationale,
            candidate_label=body.options.candidate_label,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}") from e

    vid = result["validation_id"]
    urls = artifact_urls(vid, out_dir)
    return {
        **result,
        "geometry_source": src,
        "artifact_urls": urls,
    }


@router.get("/rules/summary")
def validation_rules_summary() -> dict[str, Any]:
    rules_path = _REPO_ROOT / "rules" / "validation_rules.yaml"
    if not rules_path.is_file():
        raise HTTPException(status_code=404, detail="validation_rules.yaml not found")
    rules, cat_weights, scoring_config = load_rules(rules_path)
    from backend.validation.ai_review import load_ai_review_config

    ai_review_cfg = load_ai_review_config(rules_path)
    category_labels = {
        "benchmark": "基准对标",
        "stability_watertight": "稳性 / 水密",
        "structural_layout": "结构布局",
        "detailing_fatigue_proxy": "疲劳 / 细节",
    }
    ai_labels = ai_review_cfg.get("dimension_labels_zh") or {}
    return {
        "category_weights": cat_weights,
        "category_labels": category_labels,
        "ai_review_weights": ai_review_cfg.get("dimension_weights") or {},
        "ai_review_labels": ai_labels,
        "ai_review_primary": ai_review_cfg.get("primary", True),
        "scoring_config": scoring_config,
        "rule_count": len(rules),
        "rules": [
            {
                "id": r.id,
                "category": r.category,
                "category_label": category_labels.get(r.category, r.category),
                "metric": r.metric,
                "operator": r.operator,
                "weight": r.weight,
                "limits": r.limits,
                "reference": r.reference,
                "scoring": r.scoring,
                "description_zh": r.description_zh,
                "source": r.source,
                "regulation_ref": r.regulation_ref,
                "clause_ref": r.clause_ref,
                "unit": r.unit,
            }
            for r in rules
        ],
    }


@router.get("/{validation_id}/export/word")
def validation_export_word(validation_id: str) -> FileResponse:
    """Download full validation report as Word; generates docx on demand if missing."""
    out_dir = find_validation_dir(validation_id)
    if out_dir is None:
        raise HTTPException(status_code=404, detail="Validation run not found")
    docx = out_dir / "validation_report.docx"
    if not docx.is_file():
        try:
            from backend.validation.word_export import build_validation_docx

            build_validation_docx(out_dir, validation_id=validation_id)
        except ImportError as e:
            raise HTTPException(
                status_code=503,
                detail="Word export requires python-docx (pip install -r backend/requirements-validation.txt)",
            ) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Word export failed: {e}") from e
    filename = f"validation_report_{validation_id[:8]}.docx"
    return FileResponse(
        docx,
        media_type=_MEDIA_TYPES[".docx"],
        filename=filename,
    )


@router.get("/{validation_id}/files/{filename}")
def validation_file(validation_id: str, filename: str) -> FileResponse:
    safe = safe_artifact_name(filename)
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid artifact filename")
    out_dir = find_validation_dir(validation_id)
    if out_dir is None:
        raise HTTPException(status_code=404, detail="Validation run not found")
    path = (out_dir / safe).resolve()
    if not path.is_file() or path.parent != out_dir:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {safe}")
    media = _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=safe)


@router.get("/{validation_id}/report")
def validation_report(validation_id: str) -> dict[str, str]:
    out_dir = find_validation_dir(validation_id)
    if out_dir is None:
        raise HTTPException(status_code=404, detail="Report not found")
    md = out_dir / "validation_report.md"
    if not md.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return {"markdown": md.read_text(encoding="utf-8")}


@router.get("/{validation_id}")
def validation_get(validation_id: str) -> dict[str, Any]:
    out_dir = find_validation_dir(validation_id)
    if out_dir is None:
        raise HTTPException(status_code=404, detail="Validation run not found")
    score_path = out_dir / "validation_score.json"
    data = json.loads(score_path.read_text(encoding="utf-8"))
    data["artifact_urls"] = artifact_urls(validation_id, out_dir)
    return data
