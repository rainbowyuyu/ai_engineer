"""API tests for design-requirements endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_parse_and_get_checklist(monkeypatch):
    class FakeQwen:
        api_key = ""

    monkeypatch.setattr("backend.design_requirements.nl_parser.QwenClient", lambda: FakeQwen())

    r = client.post(
        "/api/design-requirements/parse",
        json={"text": "20MW 半潜，Hs=12，钢耗 300 t/MW，CCS AIP", "persist": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["checklist_id"]
    assert data["checklist"]["project"]["target_capacity_mw"] == 20.0
    assert data["checklist"]["site"]["Hs_m"] == 12.0
    assert data["checklist"]["job_descriptor"]["phase"] == "I"
    assert "markdown" in data and "设计清单" in data["markdown"]
    assert data["parser"] in ("qwen", "rule_fallback")

    cid = data["checklist_id"]
    g = client.get(f"/api/design-requirements/{cid}")
    assert g.status_code == 200
    assert g.json()["checklist"]["meta"]["checklist_id"] == cid

    md = client.get(f"/api/design-requirements/{cid}/export/markdown")
    assert md.status_code == 200
    assert "项目概况" in md.text
