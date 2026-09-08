# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from backend.tools.parameters_summary_export import (
    latest_state1_inp,
    resolve_design_spec_path,
)


def test_latest_state1_inp_picks_highest_index(tmp_path: Path):
    (tmp_path / "file003_state1.inp").write_text("*NODE\n", encoding="utf-8")
    (tmp_path / "file051_state1.inp").write_text("*NODE\n", encoding="utf-8")
    (tmp_path / "file012_state1.inp").write_text("*NODE\n", encoding="utf-8")
    (tmp_path / "file051_state0.inp").write_text("*NODE\n", encoding="utf-8")
    got = latest_state1_inp(tmp_path)
    assert got is not None
    assert got.name == "file051_state1.inp"


def test_resolve_design_spec_prefers_run_dir(tmp_path: Path):
    run = tmp_path / "job"
    run.mkdir()
    (run / "design_spec.json").write_text(json.dumps({"side_length_mm": 95000.0}), encoding="utf-8")
    got = resolve_design_spec_path(run, workspace_root=tmp_path)
    assert got == (run / "design_spec.json").resolve()


def test_resolve_design_spec_from_job_context_session(tmp_path: Path):
    root = tmp_path
    run = root / "runs" / "abc"
    run.mkdir(parents=True)
    sess = root / "runs" / "_design_domain" / "sess1"
    sess.mkdir(parents=True)
    (sess / "design_spec.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (run / "job_context.json").write_text(
        json.dumps({"oc4_session_id": "sess1"}),
        encoding="utf-8",
    )
    got = resolve_design_spec_path(run, workspace_root=root)
    assert got is not None
    assert got.resolve() == (sess / "design_spec.json").resolve()


def test_ensure_parameters_summary_reuses_existing(tmp_path: Path):
    from backend.tools.parameters_summary_export import ensure_parameters_summary

    run = tmp_path / "job"
    run.mkdir()
    payload = {
        "title": "t",
        "beso9_method1_topology_reconstructed": {"legs": [{"id": 1}, {"id": 2}, {"id": 3}]},
    }
    out = run / "parameters_summary.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    r = ensure_parameters_summary(run, workspace_root=tmp_path)
    assert r["ok"] is True
    assert r["reused"] is True
    assert r["legs"] == 3
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "beso7_method1_topology_reconstructed" in data


def test_backend_wrapper_imports_without_freecad():
    from backend.tools import parameters_summary_export as mod

    assert callable(mod.export_parameters_summary)
    assert callable(mod.maybe_export_after_beso)
    assert callable(mod.ensure_parameters_summary)
