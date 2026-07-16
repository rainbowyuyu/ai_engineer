"""Persist and resolve design checklist artifacts."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from backend.design_requirements.models import DesignChecklist

_REPO_ROOT = Path(__file__).resolve().parents[2]


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", str(_REPO_ROOT))).resolve()


def design_brief_root() -> Path:
    root = workspace_root() / "runs" / "_design_brief"
    root.mkdir(parents=True, exist_ok=True)
    return root


def find_checklist_dir(checklist_id: str) -> Path | None:
    cid = str(checklist_id or "").strip()
    if not cid or not re.fullmatch(r"[a-f0-9]{32}", cid):
        return None
    d = design_brief_root() / cid
    if d.is_dir() and (d / "design_checklist.json").is_file():
        return d.resolve()
    return None


def save_checklist(checklist: DesignChecklist, *, markdown: str) -> Path:
    cid = checklist.meta.checklist_id
    out_dir = design_brief_root() / cid
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "design_checklist.json").write_text(
        json.dumps(checklist.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "design_checklist.md").write_text(markdown, encoding="utf-8")
    return out_dir.resolve()


def load_checklist(checklist_id: str) -> DesignChecklist | None:
    d = find_checklist_dir(checklist_id)
    if d is None:
        return None
    data = json.loads((d / "design_checklist.json").read_text(encoding="utf-8"))
    return DesignChecklist.model_validate(data)


def artifact_urls(checklist_id: str) -> dict[str, str]:
    base = f"/api/design-requirements/{checklist_id}"
    return {
        "checklist_json": f"{base}",
        "markdown": f"{base}/export/markdown",
    }
