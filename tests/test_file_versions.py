"""Process-scoped git-like file versioning."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from backend.versions.store import (
    checkout_commit,
    commit_files,
    diff_commits,
    list_commits,
    list_processes,
    open_process,
    process_handlers_for,
)


@pytest.fixture()
def version_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_replan_process_commit_chain(version_workspace: Path) -> None:
    tid = "task-ver-1"
    proc = open_process(tid, process_type="replan", label="重规划", process_id="replan-1")
    assert proc["process_id"] == "replan-1"
    assert any(h["id"] == "mark_rho" for h in process_handlers_for("replan"))

    c1 = commit_files(
        tid,
        "replan-1",
        message="baseline",
        inline={"theta.json": '{"characteristic_length_max": 2.5}'},
        applied_handlers=["snapshot_theta"],
    )
    c2 = commit_files(
        tid,
        "replan-1",
        message="after refine",
        inline={"theta.json": '{"characteristic_length_max": 1.2}'},
        applied_handlers=["snapshot_theta", "persist_event"],
    )
    log = list_commits(tid, "replan-1")
    assert log[0]["commit_id"] == c2["commit_id"]
    assert log[1]["commit_id"] == c1["commit_id"]

    d = diff_commits(tid, "replan-1", c1["commit_id"], c2["commit_id"])
    assert "theta.json" in d["modified"]

    out = checkout_commit(tid, "replan-1", c2["commit_id"])
    restored = Path(version_workspace) / out["dest_dir"] / "theta.json"
    assert restored.is_file()
    assert json.loads(restored.read_text(encoding="utf-8"))["characteristic_length_max"] == 1.2

    procs = list_processes(tid)
    assert any(p["process_id"] == "replan-1" for p in procs)


def test_candidate_handlers_catalog() -> None:
    ids = {h["id"] for h in process_handlers_for("candidate_select")}
    assert "select_best" in ids
    assert "snapshot_registry" in ids
