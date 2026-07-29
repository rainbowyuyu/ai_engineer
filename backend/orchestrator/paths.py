"""Paths for workflow state and archives."""
from __future__ import annotations

import os
from pathlib import Path


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()


def workflow_root() -> Path:
    p = workspace_root() / "runs" / "_workflow"
    p.mkdir(parents=True, exist_ok=True)
    return p


def workflow_state_path(task_id: str) -> Path:
    tid = str(task_id or "").strip()
    return workflow_root() / tid / "state.json"


def archive_root() -> Path:
    p = workspace_root() / "runs" / "_archive"
    p.mkdir(parents=True, exist_ok=True)
    return p


def archive_dir(task_id: str) -> Path:
    return archive_root() / str(task_id or "").strip()


def candidates_root() -> Path:
    p = workspace_root() / "runs" / "_candidates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def candidates_registry_path(task_id: str) -> Path:
    return candidates_root() / str(task_id or "").strip() / "registry.json"
