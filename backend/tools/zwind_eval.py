"""Zwind evaluation step: size-opt → aero-hydro-servo-elastic envelope (paper Fig. 2).

Default path imports ``third_party/zwind_newmodel/paper_fig2_metrics.json`` (fast, demo-safe).
Optional ``BESO_ZWIND_LIVE=1`` launches ``test0820_hardcode.py`` (Windows + DLLs; slow).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
ZWIND_ROOT = _REPO / "third_party" / "zwind_newmodel"
PAPER_METRICS = ZWIND_ROOT / "paper_fig2_metrics.json"
FIGURES_DIR = ZWIND_ROOT / "figures"
GENERATED_FIG2 = _REPO / "submission" / "figures" / "fig2_panels"
CAMPAIGN_SCRIPT = ZWIND_ROOT / "test0820_hardcode.py"

PANEL_FILES = (
    ("fig2b_dynamics.png", "Fig. 2b · Dynamics", "fig_b_unified.png"),
    ("fig2c_operating.png", "Fig. 2c · DLC1.1", "fig_c_unified.png"),
    ("fig2d_extreme.png", "Fig. 2d · DLC 6.1", "fig_d_unified.png"),
    ("fig2e_loads.png", "Fig. 2e · Ultimate loads", "fig_e_unified.png"),
)


def _live_enabled() -> bool:
    return str(os.environ.get("BESO_ZWIND_LIVE", "")).strip().lower() in {"1", "true", "yes", "on"}


def _highlights(metrics: dict[str, Any], platform: str = "ai") -> dict[str, Any]:
    plat = "ai" if platform.lower() in {"ai", "a"} else "tuqiang"
    freq = ((metrics.get("fig2b") or {}).get("tower_frequencies_hz") or {}).get(plat) or {}
    op = metrics.get("fig2c") or {}
    ex = metrics.get("fig2d") or {}
    loads = metrics.get("fig2e") or {}
    return {
        "platform": plat,
        "tower_1st_fa_hz": freq.get("1st_fa"),
        "tower_1st_ss_hz": freq.get("1st_ss"),
        "operating_pitch_deg": (op.get("pitch_deg") or {}).get(plat),
        "operating_surge_m": (op.get("surge_m") or {}).get(plat),
        "extreme_pitch_deg": (ex.get("pitch_deg") or {}).get(plat),
        "extreme_surge_m": (ex.get("surge_m") or {}).get(plat),
        "extreme_tower_top_acc_mps2": (ex.get("tower_top_acc_mps2") or {}).get(plat),
        "max_mooring_tension_kn": (loads.get("max_mooring_tension_kn") or {}).get(plat),
        "tower_base_my_mnm": (loads.get("tower_base_my_mnm") or {}).get(plat),
        "pitch_limit_operating_deg": (op.get("pitch_deg") or {}).get("limit"),
        "pitch_limit_extreme_deg": (ex.get("pitch_deg") or {}).get("limit"),
        "mooring_limit_kn": (loads.get("max_mooring_tension_kn") or {}).get("limit"),
    }


def _resolve_panel_src(generated_name: str, unified_name: str) -> Path | None:
    for base in (GENERATED_FIG2, FIGURES_DIR, ZWIND_ROOT):
        for name in (generated_name, unified_name):
            p = base / name
            if p.is_file():
                return p
    return None


def _copy_panels(run_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    panel_dir = run_dir / "zwind_fig2"
    panel_dir.mkdir(parents=True, exist_ok=True)
    for gen_name, label, unified_name in PANEL_FILES:
        src = _resolve_panel_src(gen_name, unified_name)
        if src is None:
            continue
        dest = panel_dir / gen_name
        shutil.copy2(src, dest)
        out.append(
            {
                "label": label,
                "name": gen_name,
                "path": str(dest),
                "rel": f"zwind_fig2/{gen_name}",
            }
        )
    return out


def _try_live_campaign(timeout_s: float = 120.0) -> dict[str, Any]:
    """Optional live OpenSees campaign; never required for demo."""
    if not CAMPAIGN_SCRIPT.is_file():
        return {"ok": False, "reason": "campaign_script_missing"}
    try:
        proc = subprocess.run(
            [sys.executable, str(CAMPAIGN_SCRIPT)],
            cwd=str(ZWIND_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout", "timeout_s": timeout_s}
    except OSError as e:
        return {"ok": False, "reason": f"os_error: {e}"}


def evaluate_zwind_bundle(
    *,
    run_dir: Path | None = None,
    platform: str = "ai",
    prefer_live: bool | None = None,
) -> dict[str, Any]:
    """Import paper Fig. 2 metrics (+ optional live run) into ``run_dir``."""
    if not PAPER_METRICS.is_file():
        raise FileNotFoundError(
            f"缺少 Zwind 论文指标: {PAPER_METRICS}. 请确认 third_party/zwind_newmodel 已入库。"
        )
    metrics = json.loads(PAPER_METRICS.read_text(encoding="utf-8"))
    from backend.surrogate.zwind_adapter import (
        attach_dynamic_to_prediction,
        envelope_from_paper_fig2,
    )

    envelope = envelope_from_paper_fig2(platform)
    highlights = _highlights(metrics, platform)
    live: dict[str, Any] | None = None
    mode = "paper_fig2_import"
    if prefer_live if prefer_live is not None else _live_enabled():
        live = _try_live_campaign()
        mode = "live_campaign" if live.get("ok") else "paper_fig2_import_after_live_fallback"

    panels: list[dict[str, Any]] = []
    artifacts: dict[str, str] = {}
    if run_dir is not None:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = run_dir / "zwind_fig2_metrics.json"
        env_path = run_dir / "zwind_envelope.json"
        report_path = run_dir / "zwind_report.json"
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        env_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        panels = _copy_panels(run_dir)
        report = {
            "mode": mode,
            "bundle": str(ZWIND_ROOT.relative_to(_REPO)).replace("\\", "/"),
            "platform": platform,
            "highlights": highlights,
            "envelope": envelope,
            "panels": [{"label": p["label"], "rel": p["rel"]} for p in panels],
            "live": live,
            "source_metrics": "third_party/zwind_newmodel/paper_fig2_metrics.json",
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts = {
            "metrics": str(metrics_path),
            "envelope": str(env_path),
            "report": str(report_path),
        }

    ctx = attach_dynamic_to_prediction({}, envelope)
    return {
        "ok": True,
        "mode": mode,
        "bundle_rel": "third_party/zwind_newmodel",
        "platform": platform,
        "metrics": metrics,
        "envelope": envelope,
        "highlights": highlights,
        "panels": panels,
        "artifacts": artifacts,
        "live": live,
        "surrogate_context": ctx,
        "pass_checks": {
            "extreme_pitch_within_limit": (
                highlights.get("extreme_pitch_deg") is not None
                and highlights.get("pitch_limit_extreme_deg") is not None
                and float(highlights["extreme_pitch_deg"])
                <= float(highlights["pitch_limit_extreme_deg"])
            ),
            "mooring_within_limit": (
                highlights.get("max_mooring_tension_kn") is not None
                and highlights.get("mooring_limit_kn") is not None
                and float(highlights["max_mooring_tension_kn"])
                <= float(highlights["mooring_limit_kn"])
            ),
        },
    }
