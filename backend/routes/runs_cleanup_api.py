"""API for previewing and manually triggering stale-runs cleanup."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.runs_cleanup import (
    RunsCleanupConfig,
    RunsCleaner,
    default_runs_root,
    scheduler_for,
)

router = APIRouter(tags=["runs-cleanup"])


def _runs_root() -> Path:
    if os.environ.get("WORKSPACE_ROOT"):
        return Path(os.environ["WORKSPACE_ROOT"]).expanduser().resolve() / "runs"
    return default_runs_root()


class CleanupRunIn(BaseModel):
    retention_days: float | None = Field(default=None, gt=0, le=3650)
    include_archives: bool | None = None
    max_items: int | None = Field(default=None, ge=1, le=100_000)
    dry_run: bool = False


def _config(body: CleanupRunIn) -> RunsCleanupConfig:
    return RunsCleanupConfig.from_env().with_overrides(
        retention_days=body.retention_days,
        include_archives=body.include_archives,
        max_items=body.max_items,
    )


@router.get("/status")
def cleanup_status() -> dict[str, Any]:
    scheduler = scheduler_for(_runs_root())
    return {
        "ok": True,
        "runs_root": str(_runs_root()),
        "config": RunsCleanupConfig.from_env().to_dict(),
        "scheduler": {
            "running": scheduler.running,
            "last_report": scheduler.last_report,
        },
    }


@router.post("/preview")
def cleanup_preview(body: CleanupRunIn | None = None) -> dict[str, Any]:
    body = body or CleanupRunIn()
    report = RunsCleaner(_runs_root()).cleanup(config=_config(body), dry_run=True)
    return report


@router.post("/run")
def cleanup_run(body: CleanupRunIn | None = None) -> dict[str, Any]:
    body = body or CleanupRunIn()
    report = RunsCleaner(_runs_root()).cleanup(config=_config(body), dry_run=body.dry_run)
    if not report.get("ok"):
        raise HTTPException(status_code=409, detail=report)
    return report


__all__ = ["router"]
