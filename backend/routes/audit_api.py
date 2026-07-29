"""Audit manifest API."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.audit.manifest import build_audit_manifest

router = APIRouter(tags=["audit"])


@router.get("/manifest")
def get_audit_manifest(
    task_id: str,
    validation_id: str | None = None,
    design_checklist_id: str | None = None,
    oc4_session_id: str | None = None,
) -> dict:
    root = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()
    validation_dir = None
    if validation_id:
        from backend.validation.paths import find_validation_dir

        validation_dir = find_validation_dir(validation_id)
    out_path = build_audit_manifest(
        task_id=task_id,
        validation_dir=validation_dir,
        design_checklist_id=design_checklist_id,
        oc4_session_id=oc4_session_id,
    )
    rel = out_path.relative_to(root).as_posix()
    return {
        "ok": True,
        "audit_manifest": str(out_path),
        "audit_manifest_url": f"/{rel}",
        "entry_count": len(json.loads(out_path.read_text(encoding="utf-8")).get("entries") or []),
    }


@router.get("/manifest/download")
def download_audit_manifest(task_id: str, validation_id: str | None = None) -> FileResponse:
    out = get_audit_manifest(task_id=task_id, validation_id=validation_id)
    p = Path(out["audit_manifest"])
    if not p.is_file():
        raise HTTPException(status_code=404, detail="manifest not found")
    return FileResponse(p, filename="audit_manifest.json", media_type="application/json")
