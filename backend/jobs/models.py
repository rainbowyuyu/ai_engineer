from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel


class JobStatus(str, Enum):
    created = "created"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelling = "cancelling"
    cancelled = "cancelled"


class Job(BaseModel):
    id: str
    created_at: float
    status: JobStatus
    user_message: str

    inp_path: Optional[str]
    mass_goal_ratio: float
    filter_radius: float
    optimization_base: str
    save_every: int

    run_dir: str
    logs: List[str]
    latest_vtk_url: Optional[str]
    artifacts: List[dict[str, Any]]
    generated_code_files: List[str]

