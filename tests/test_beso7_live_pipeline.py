"""BESO7 live pipeline demo smoke tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.demo.beso7_live_pipeline import (
    beso7_fcstd,
    bootstrap_beso7_live_demo,
    build_task_version_tree,
    confirm_candidate_selection,
    run_candidate_select_step,
    run_finalize_step,
    run_mesh_replan_step,
    run_orchestrate_job_step,
    run_solver_replan_step,
    seed_beso7_job_artifacts,
)


@pytest.fixture()
def workspace() -> Path:
    root = Path(__file__).resolve().parents[1]
    if not beso7_fcstd(root).is_file():
        pytest.skip("BESO7.FCStd missing")
    return root


def test_beso7_full_chain(workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace))
    boot = bootstrap_beso7_live_demo(workspace)
    assert boot["checklist_id"]
    assert boot["session_id"]
    assert Path(boot["session_dir"], "03_for_beso.inp").is_file()
    assert Path(boot["session_dir"], "design_preview.obj").is_file()
    assert Path(boot["session_dir"], "BESO7.FCStd").is_file()
    assert Path(boot["session_dir"], "file001_state0.inp").is_file()
    assert Path(boot["session_dir"], "Analysis-beso.inp").is_file()
    assert boot["beso_theta"]["mass_goal_ratio"] == 0.15

    mesh = run_mesh_replan_step(boot["task_id"], session_id=boot["session_id"])
    assert mesh.get("rho_pending") == 1
    assert mesh.get("version", {}).get("commit", {}).get("commit_id")

    fin = run_finalize_step(
        workspace,
        session_id=boot["session_id"],
        task_id=boot["task_id"],
        clear_rho=True,
    )
    assert fin["ok"] is True
    assert "design_checklist" in str(fin["beso_theta"].get("source") or "")

    orch = run_orchestrate_job_step(
        scan_dir=fin["scan_dir"],
        task_id=boot["task_id"],
        checklist_id=boot["checklist_id"],
        mass_goal_ratio=float(fin["beso_theta"]["mass_goal_ratio"]),
    )
    assert orch["job_id"]
    seed = orch.get("seed") or {}
    assert seed.get("ok") is True
    assert seed.get("curve_urls")
    assert str(seed.get("latest_mesh_url") or "").endswith(".obj")
    assert (Path(orch["run_dir"]) / "latest.obj").is_file()
    assert (Path(orch["run_dir"]) / "file001_state0.inp").is_file()
    assert (Path(orch["run_dir"]) / "Analysis-beso.inp").is_file()
    evo = seed.get("evolution") or []
    assert len(evo) >= 3, "stepwise evolution must start from file001 and advance"
    assert evo[0]["iter"] in (0, 1)

    solver = run_solver_replan_step(boot["task_id"], job_id=orch["job_id"])
    assert solver.get("rho_pending") == 1

    cands = run_candidate_select_step(boot["task_id"], auto_select=False)
    assert cands.get("awaiting_selection") is True
    assert len(cands.get("candidates") or []) >= 5
    assert all(c.get("preview_url") for c in cands["candidates"])
    rec = cands.get("recommended_id")
    assert rec
    confirmed = confirm_candidate_selection(boot["task_id"], rec)
    assert confirmed["selected"]["candidate_id"] == rec
    assert float(confirmed["selected"]["overall_score"]) >= 85

    tree = build_task_version_tree(boot["task_id"])
    assert tree.get("ok") is True
    assert (tree.get("structure") or {}).get("total_commits", 0) >= 1
    assert len(tree.get("branches") or []) >= 1


def test_seed_beso7_always_writes_obj(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace))
    from backend.jobs.manager import jobs

    job = jobs.create_job(
        user_message="seed test",
        inp_path=str(workspace / "examples" / "beso" / "beso7" / "beso_output" / "Analysis-beso.inp"),
        mass_goal_ratio=0.15,
        filter_radius=2.0,
        optimization_base="stiffness",
        save_every=1,
        generated_code_files=[],
        selected_inputs=None,
    )
    out = seed_beso7_job_artifacts(workspace, job_id=job.id, task_id="seed-test")
    assert out["ok"] is True
    assert (Path(job.run_dir) / "latest.obj").is_file()
    assert (Path(job.run_dir) / "file001_state0.inp").is_file()
    assert str(out["latest_mesh_url"]).endswith(".obj")
    assert len(out.get("evolution") or []) >= 3
