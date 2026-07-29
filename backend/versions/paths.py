"""Paths for per-task process file versioning."""
from __future__ import annotations

import os
from pathlib import Path


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()


def versions_root() -> Path:
    p = workspace_root() / "runs" / "_versions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def task_versions_dir(task_id: str) -> Path:
    tid = str(task_id or "").strip() or "_orphan"
    p = versions_root() / tid
    p.mkdir(parents=True, exist_ok=True)
    return p


def processes_index_path(task_id: str) -> Path:
    return task_versions_dir(task_id) / "processes.json"


def process_dir(task_id: str, process_id: str) -> Path:
    return task_versions_dir(task_id) / str(process_id or "").strip()


def process_meta_path(task_id: str, process_id: str) -> Path:
    return process_dir(task_id, process_id) / "meta.json"


def commit_dir(task_id: str, process_id: str, commit_id: str) -> Path:
    return process_dir(task_id, process_id) / "commits" / str(commit_id or "").strip()


def commit_meta_path(task_id: str, process_id: str, commit_id: str) -> Path:
    return commit_dir(task_id, process_id, commit_id) / "commit.json"


def commit_files_dir(task_id: str, process_id: str, commit_id: str) -> Path:
    p = commit_dir(task_id, process_id, commit_id) / "files"
    p.mkdir(parents=True, exist_ok=True)
    return p
