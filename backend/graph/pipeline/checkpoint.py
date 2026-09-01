"""LangGraph checkpoint helpers."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from backend.llm.checkpoints import get_sqlite_saver_cached


def pipeline_checkpoint_path() -> Path:
    root = Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()
    p = root / "runs" / "_checkpoints" / "pipeline.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@lru_cache(maxsize=1)
def get_pipeline_checkpointer():
    return get_sqlite_saver_cached(str(pipeline_checkpoint_path()))
