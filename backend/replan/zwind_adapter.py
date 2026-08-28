"""Zwind abort adapter (parse + θ patch) + envelope evaluation via zwind_newmodel."""
from __future__ import annotations

from pathlib import Path
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


def run_zwind_subprocess_placeholder(
    *args: Any,
    run_dir: str | Path | None = None,
    platform: str = "ai",
    prefer_live: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Evaluate Zwind envelope from ``third_party/zwind_newmodel`` (paper Fig. 2).

    Replaces the old NotImplemented hook so Case3 resume / demo can import
    metrics without requiring a full OpenSees campaign. Set ``BESO_ZWIND_LIVE=1``
    or ``prefer_live=True`` to attempt ``test0820_hardcode.py``.
    """
    from backend.tools.zwind_eval import evaluate_zwind_bundle

    rd = Path(run_dir) if run_dir else None
    return evaluate_zwind_bundle(run_dir=rd, platform=platform, prefer_live=prefer_live)
