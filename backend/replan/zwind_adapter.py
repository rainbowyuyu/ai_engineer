"""Zwind abort adapter (parse + θ patch); real subprocess left as future hook."""
from __future__ import annotations

from typing import Any

from backend.replan.diagnostics import parse_diagnostics
from backend.replan.models import DiagnosticSignals
from backend.replan.policies import policy_zwind_recover


def parse_zwind_abort(logs: str | list[str] | None, metrics: dict[str, Any] | None = None) -> DiagnosticSignals:
    return parse_diagnostics(logs, metrics)


def apply_zwind_replan(theta: dict[str, Any], sig: DiagnosticSignals | None = None) -> dict[str, Any]:
    sig = sig or DiagnosticSignals()
    actions = policy_zwind_recover(dict(theta), sig)
    out = dict(theta)
    for a in actions:
        out.update(a.theta_patch)
    return out


def run_zwind_subprocess_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Reserved for real Zwind 3.0 integration — not invoked in Phase I replan demos."""
    raise NotImplementedError("Zwind subprocess not wired; use simulate_cases.case3_demo()")
