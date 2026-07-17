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
