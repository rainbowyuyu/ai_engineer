"""Resolve and download workspace artifact files (chat deliverable links)."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.tools.freecad_cad_convert import resolve_workspace_path

router = APIRouter(tags=["workspace"])


def _runs_root() -> Path:
    root = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()
    return root / "runs"


def _workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()


@router.get("/download")
def workspace_download(path: str) -> FileResponse:
    """Download a file under WORKSPACE_ROOT by relative or absolute path."""
    root = _workspace_root()
    try:
        p = resolve_workspace_path(path, root)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    return FileResponse(p, filename=p.name, media_type="application/octet-stream")


@router.get("/resolve-download")
def workspace_resolve_download(
    filename: str,
    job_id: str | None = None,
    scan_dir: str | None = None,
    pack_id: str | None = None,
) -> dict:
    """Resolve bare filename to a fetchable URL for chat markdown links."""
    root = _workspace_root()
    runs = _runs_root()
    fname = Path(str(filename or "").strip()).name
    if not fname or fname in (".", ".."):
        raise HTTPException(status_code=400, detail="filename 无效")

    candidates: list[Path] = []
    if pack_id:
        candidates.append(runs / "_deliverables" / str(pack_id).strip() / fname)
    if job_id:
        candidates.append(runs / str(job_id).strip() / fname)
    if scan_dir:
        try:
            candidates.append(resolve_workspace_path(scan_dir, root) / fname)
        except ValueError:
            pass

    deliverables_root = runs / "_deliverables"
    if deliverables_root.is_dir():
        hits = sorted(
            deliverables_root.glob(f"*/{fname}"),
            key=lambda p: p.stat().st_mtime if p.is_file() else 0,
            reverse=True,
        )
        candidates.extend(hits[:8])

    for p in candidates:
        if not p.is_file():
            continue
        try:
            rel = p.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        url = f"/{rel}" if rel.startswith("runs/") or rel.startswith("examples/") else f"/api/workspace/download?path={rel}"
        return {
            "ok": True,
            "filename": fname,
            "path": rel,
            "url": url,
            "size": int(p.stat().st_size),
        }

    raise HTTPException(status_code=404, detail=f"未找到可下载文件: {fname}")
