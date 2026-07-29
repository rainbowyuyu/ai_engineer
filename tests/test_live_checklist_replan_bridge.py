"""Live OC4/BESO path: checklist → BESO θ + version commit helpers."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

from backend.replan.checklist_bridge import (
    beso_theta_defaults_from_checklist,
    maybe_commit_live_replan_version,
    write_job_context,
)
from backend.versions.store import list_commits, list_processes


def test_beso_theta_defaults_without_checklist():
    t = beso_theta_defaults_from_checklist(None)
    assert t["mass_goal_ratio"] == 0.15
    assert t["optimization_base"] == "stiffness"
    assert t["source"] == "chen2026_default"


def test_beso_theta_from_checklist_overrides():
    checklist = SimpleNamespace(
        meta=SimpleNamespace(checklist_id="cl-abc"),
        job_descriptor=SimpleNamespace(
            theta=SimpleNamespace(
                beso=SimpleNamespace(
                    mass_goal_ratio=0.22,
                    filter_radius=3.5,
                    optimization_base="stiffness",
                )
            )
        ),
    )
    t = beso_theta_defaults_from_checklist(checklist)
    assert t["mass_goal_ratio"] == 0.22
    assert t["filter_radius"] == 3.5
    assert t["checklist_id"] == "cl-abc"
    assert "design_checklist" in t["source"]


def test_write_job_context_task_and_checklist(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_job_context(run_dir, design_checklist_id="c1", task_id="t1")
    data = json.loads((run_dir / "job_context.json").read_text(encoding="utf-8"))
    assert data["design_checklist_id"] == "c1"
    assert data["task_id"] == "t1"


def test_maybe_commit_live_replan_version():
    with tempfile.TemporaryDirectory() as td:
        os.environ["WORKSPACE_ROOT"] = td
        Path(td, "runs").mkdir(parents=True, exist_ok=True)
        eid = uuid.uuid4().hex
        ev_dir = Path(td) / "runs" / "_replan" / eid
        ev_dir.mkdir(parents=True)
        (ev_dir / "replan_event.json").write_text(
            json.dumps({"event_id": eid, "case_id": "mesh_live"}),
            encoding="utf-8",
        )
        tid = f"task-{uuid.uuid4().hex[:8]}"
        ver = maybe_commit_live_replan_version(
            tid,
            event_id=eid,
            theta_before={"characteristic_length_max": 4.0},
            theta_after={"characteristic_length_max": 2.8},
            message="mesh live replan test",
            case_id="mesh_live",
        )
        assert ver is not None
        assert ver.get("commit", {}).get("commit_id")
        procs = list_processes(tid)
        assert procs
        commits = list_commits(tid, procs[0]["process_id"])
        assert commits
