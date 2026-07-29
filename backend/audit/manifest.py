"""SHA-256 audit manifest for runs."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _add_entry(entries: list[dict[str, Any]], path: Path, role: str, root: Path, **extra: Any) -> None:
    if not path.is_file():
        return
    try:
        rel = str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        rel = str(path)
    entries.append(
        {
            "path": rel,
            "sha256": _sha256_file(path),
            "size": int(path.stat().st_size),
            "role": role,
            **extra,
        }
    )


def build_audit_manifest(
    *,
    task_id: str,
    validation_dir: Path | None = None,
    design_checklist_id: str | None = None,
    oc4_session_id: str | None = None,
    out_path: Path | None = None,
) -> Path:
    root = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()
    entries: list[dict[str, Any]] = []

    if validation_dir and validation_dir.is_dir():
        for pattern in ("*.json", "*.md", "*.png", "*.pdf", "*.docx"):
            for p in validation_dir.glob(pattern):
                _add_entry(entries, p, "validation", root)

    if design_checklist_id:
        cl_dir = root / "runs" / "_design_brief" / design_checklist_id
        for name in ("design_checklist.json", "design_checklist.md"):
            _add_entry(entries, cl_dir / name, "design_checklist", root, checklist_id=design_checklist_id)

    if oc4_session_id:
        sdir = root / "runs" / "_oc4_dd" / str(oc4_session_id)
        for name in (
            "01_design_domain.step",
            "02_mesh_body.inp",
            "03_for_beso.inp",
            "session_meta.json",
        ):
            _add_entry(entries, sdir / name, "oc4_session", root, session_id=oc4_session_id)

    manifest = {
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
        "entry_count": len(entries),
    }
    dest = out_path or (root / "runs" / "_audit" / task_id / "audit_manifest.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest
