#!/usr/bin/env python3
"""Smoke: halt gate + audit manifest + workflow state."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.audit.manifest import build_audit_manifest
from backend.orchestrator.gates import evaluate_transition
from backend.orchestrator.halt import evaluate_halt_gate, halt_and_archive
from backend.orchestrator.models import WorkflowState
from backend.orchestrator.state import load_workflow_state, save_workflow_state
from backend.versions.store import commit_files, list_commits, open_process


def main() -> int:
    print("verify_workflow_module: halt gate …")
    v = evaluate_halt_gate(overall_score=86, ai_review_scores={"x": 62})
    assert v.ok, v.reason

    print("verify_workflow_module: rho gate …")
    st = WorkflowState(task_id="smoke-task", rho_pending=1)
    verdict = evaluate_transition(st, "phase_ii_finalize")
    assert not verdict.ok

    print("verify_workflow_module: audit manifest …")
    with tempfile.TemporaryDirectory() as td:
        vdir = Path(td) / "val"
        vdir.mkdir()
        (vdir / "score.json").write_text(json.dumps({"overall_score": 86}), encoding="utf-8")
        out = build_audit_manifest(task_id="smoke-task", validation_dir=vdir, out_path=vdir / "audit_manifest.json")
        assert out.is_file()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data.get("entries") is not None

    print("verify_workflow_module: halt_and_archive (dry) …")
    with tempfile.TemporaryDirectory() as td2:
        vdir2 = Path(td2) / "val2"
        vdir2.mkdir()
        vid = uuid.uuid4().hex
        (vdir2 / "score.json").write_text(json.dumps({"overall_score": 88}), encoding="utf-8")
        tid = f"smoke-{uuid.uuid4().hex[:8]}"
        save_workflow_state(load_workflow_state(tid))
        res = halt_and_archive(tid, validation_id=vid, validation_dir=vdir2)
        assert res.get("ok") is True
        assert Path(res["archive_path"]).is_dir()

    print("verify_workflow_module: file versions …")
    with tempfile.TemporaryDirectory() as td3:
        os.environ["WORKSPACE_ROOT"] = td3
        Path(td3, "runs").mkdir(parents=True, exist_ok=True)
        tid2 = f"ver-{uuid.uuid4().hex[:8]}"
        open_process(tid2, process_type="replan", process_id="p1", label="smoke")
        c = commit_files(tid2, "p1", message="smoke", inline={"a.txt": "hello"})
        assert c["commit_id"]
        assert list_commits(tid2, "p1")

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
