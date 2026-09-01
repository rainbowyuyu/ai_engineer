"""MasterGraph gate wiring tests (no LLM)."""
from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from backend.graph.pipeline.master_graph import _gate_halt, _gate_rho
from backend.graph.pipeline.state import PipelineState


def test_gate_rho_routes_to_replan_when_pending():
    state: PipelineState = {"rho_pending": 1, "workflow_phase": "II"}
    assert _gate_rho(state) == "replan"


def test_gate_rho_continues_when_clear():
    state: PipelineState = {"rho_pending": 0, "workflow_phase": "II"}
    assert _gate_rho(state) == "continue"


def test_gate_halt_passes():
    state: PipelineState = {"halt_ok": True, "rho_pending": 0}
    assert _gate_halt(state) == "halt"


def test_gate_halt_replan_on_rho():
    state: PipelineState = {"halt_ok": False, "rho_pending": 1}
    assert _gate_halt(state) == "replan"
