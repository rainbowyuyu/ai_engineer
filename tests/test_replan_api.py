"""API tests for /api/replan."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_evaluate_and_apply_mesh():
    r = client.post(
        "/api/replan/evaluate",
        json={
            "phase": "II",
            "logs": "inverted elements quality < 0.15; mesh_quality_min = 0.12; mesh_error_code = -5",
            "metrics": {"mesh_quality_min": 0.12, "mesh_error_code": -5},
        },
    )
    assert r.status_code == 200, r.text
    fb = r.json()["feedback"]
    assert fb["rho_p"] == 1
    assert fb["failure_kind"] == "mesh"

    a = client.post(
        "/api/replan/apply",
        json={
            "theta": {"characteristic_length_max": 2.5},
            "feedback": fb,
        },
    )
    assert a.status_code == 200, a.text
    data = a.json()
    assert abs(float(data["theta_after"]["characteristic_length_max"]) - 1.8) < 0.05
    assert data["event_id"]


def test_case_demos():
    for cid in ("case1", "case2", "case3"):
        r = client.post(f"/api/replan/cases/{cid}/demo")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True


def test_replan_resume_mesh_and_beso():
    r = client.post(
        "/api/replan/resume",
        json={
            "target": "mesh",
            "theta_after": {"characteristic_length_max": 1.8},
            "session_id": "sess-demo",
            "design_checklist_id": None,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target"] == "mesh"
    assert data["mesh_body"]["characteristic_length_max"] == 1.8

    b = client.post(
        "/api/replan/resume",
        json={
            "target": "beso",
            "theta_after": {"mass_goal_ratio": 0.4, "filter_radius": 2.0},
            "scan_dir": "runs/demo",
            "mass_goal_ratio": 0.4,
        },
    )
    assert b.status_code == 200, b.text
    chat = b.json()["chat_body"]
    assert chat["auto_start"] is True
    assert chat["mass_goal_ratio"] == 0.4


def test_workflow_can_advance_empty_task():
    r = client.get("/api/workflow/can-advance", params={"task_id": "task-test-1", "transition": "phase_ii_finalize"})
    assert r.status_code == 200, r.text
    assert "verdict" in r.json()

