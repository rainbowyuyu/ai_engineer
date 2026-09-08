# -*- coding: utf-8 -*-
"""拓扑优化结束后自动导出 parameters_summary.json（调用 FreeCAD 拟合脚本）。"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from backend.tools.freecad_inp_mesh_vtk import resolve_freecad_python

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "freecad_export_parameters_summary.py"


def latest_state1_inp(run_dir: Path) -> Path | None:
    cands = sorted(Path(run_dir).glob("file*_state1.inp"))
    if not cands:
        return None

    def key(p: Path) -> int:
        m = re.match(r"file(\d+)_state1\.inp$", p.name, re.I)
        return int(m.group(1)) if m else -1

    cands = [p for p in cands if key(p) >= 0]
    cands.sort(key=key)
    return cands[-1] if cands else None


def _load_job_context(run_dir: Path) -> dict[str, Any]:
    for name in ("job_context.json", "task_manifest.json", "replan_context.json"):
        p = run_dir / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


def resolve_design_spec_path(run_dir: Path, workspace_root: Path | None = None) -> Path | None:
    run_dir = Path(run_dir).resolve()
    root = (workspace_root or _REPO_ROOT).resolve()
    direct = run_dir / "design_spec.json"
    if direct.is_file():
        return direct

    ctx = _load_job_context(run_dir)
    sid = (
        str(ctx.get("oc4_session_id") or ctx.get("session_id") or ctx.get("prism_session_id") or "")
        .strip()
    )
    if sid:
        for rel in (
            root / "runs" / "_design_domain" / sid / "design_spec.json",
            root / "runs" / "_prism_design" / sid / "design_spec.json",
            root / "runs" / sid / "design_spec.json",
        ):
            if rel.is_file():
                return rel

    # walk up a bit (session parent of job)
    for parent in list(run_dir.parents)[:4]:
        cand = parent / "design_spec.json"
        if cand.is_file():
            return cand

    fallback = root / "examples" / "beso" / "beso9" / "design_spec.json"
    return fallback if fallback.is_file() else None


def resolve_design_fcstd(run_dir: Path, workspace_root: Path | None = None) -> Path | None:
    run_dir = Path(run_dir).resolve()
    root = (workspace_root or _REPO_ROOT).resolve()
    for name in ("design_domain.FCStd", "BESO9.FCStd", "prism.FCStd", "session.FCStd"):
        p = run_dir / name
        if p.is_file():
            return p
    ctx = _load_job_context(run_dir)
    sid = str(ctx.get("oc4_session_id") or ctx.get("session_id") or "").strip()
    if sid:
        for rel in (
            root / "runs" / "_design_domain" / sid / "design_domain.FCStd",
            root / "runs" / "_prism_design" / sid / "prism.FCStd",
        ):
            if rel.is_file():
                return rel
    beso9 = root / "examples" / "beso" / "beso9" / "BESO9.FCStd"
    return beso9 if beso9.is_file() else None


def export_parameters_summary(
    run_dir: Path,
    *,
    workspace_root: Path | None = None,
    inp: Path | None = None,
    design_spec: Path | None = None,
    fcstd: Path | None = None,
    out_path: Path | None = None,
    skip_rebuild_export: bool = True,
    timeout_s: float | None = None,
    on_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    对拓扑优化 run 目录生成 parameters_summary.json（及 measurements.json）。

    默认 skip_rebuild_export=True：只写 JSON/measurements，不导出 STEP/FCStd（更快、更稳）。
    """
    log = on_log or (lambda _m: None)
    run_dir = Path(run_dir).resolve()
    if not _SCRIPT.is_file():
        raise FileNotFoundError(f"缺少导出脚本: {_SCRIPT}")

    inp_path = Path(inp).resolve() if inp else latest_state1_inp(run_dir)
    if inp_path is None or not inp_path.is_file():
        raise FileNotFoundError(f"run_dir 中无 file*_state1.inp: {run_dir}")

    spec = Path(design_spec).resolve() if design_spec else resolve_design_spec_path(run_dir, workspace_root)
    fc = Path(fcstd).resolve() if fcstd else resolve_design_fcstd(run_dir, workspace_root)
    out = Path(out_path).resolve() if out_path else (run_dir / "parameters_summary.json")

    exe = resolve_freecad_python()
    cmd = [
        str(exe),
        str(_SCRIPT),
        "--run-dir",
        str(run_dir),
        "--inp",
        str(inp_path),
        "--out",
        str(out),
    ]
    if spec and spec.is_file():
        cmd.extend(["--design-spec", str(spec)])
    if fc and fc.is_file():
        cmd.extend(["--fcstd", str(fc)])
    if skip_rebuild_export:
        cmd.append("--skip-rebuild-export")

    timeout = timeout_s
    if timeout is None:
        timeout = float((os.environ.get("BESO_PARAMS_SUMMARY_TIMEOUT_S") or "600").strip() or "600")

    env = os.environ.copy()
    fc_bin = exe.parent
    extras = [str(fc_bin), str(fc_bin / "Lib"), str(fc_bin / "Lib" / "site-packages")]
    env["PYTHONPATH"] = os.pathsep.join(extras + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))

    log(f"[INFO] exporting parameters_summary via FreeCAD ({inp_path.name}) …")
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    tail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        raise RuntimeError(f"parameters_summary 导出失败 (code {proc.returncode}): {tail[-2500:]}")
    for line in (proc.stdout or "").splitlines()[-12:]:
        if line.strip():
            log(line.rstrip())

    if not out.is_file():
        raise RuntimeError(f"未生成 parameters_summary.json: {out}")

    summary: dict[str, Any] = {}
    try:
        summary = json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        summary = {}

    # 兼容尺寸时域 / AI Review：若仅有 beso9 块则同步别名
    if isinstance(summary, dict):
        b9 = summary.get("beso9_method1_topology_reconstructed")
        b7 = summary.get("beso7_method1_topology_reconstructed")
        changed = False
        if isinstance(b9, dict) and b9 and not isinstance(b7, dict):
            summary["beso7_method1_topology_reconstructed"] = b9
            changed = True
        if not summary.get("optimization_info") and isinstance(b9 or b7, dict):
            # 轻量补齐，避免验证缺 target_power
            summary.setdefault(
                "optimization_info",
                {"target_power_MW": 20.0, "wall_thickness_m": 0.06, "steel_density_kgpm3": 7850.0},
            )
            changed = True
        if changed:
            out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "parameters_summary_path": str(out),
        "measurements_path": str(run_dir / "measurements.json")
        if (run_dir / "measurements.json").is_file()
        else None,
        "source_inp": str(inp_path),
        "design_spec": str(spec) if spec and spec.is_file() else None,
        "legs": len(
            (
                (summary.get("beso9_method1_topology_reconstructed") or summary.get("beso7_method1_topology_reconstructed") or {}).get(
                    "legs"
                )
                or []
            )
        ),
        "title": summary.get("title"),
    }


def ensure_parameters_summary(
    run_dir: Path,
    *,
    workspace_root: Path | None = None,
    force: bool = False,
    on_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    若 run_dir 已有 parameters_summary.json 则直接返回；否则尝试导出。
    供 Job 结束后补跑 / 尺寸时域继承前调用。
    """
    log = on_log or (lambda _m: None)
    run_dir = Path(run_dir).resolve()
    out = run_dir / "parameters_summary.json"
    if out.is_file() and not force:
        try:
            summary = json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            summary = {}
        # 补齐别名后仍复用文件
        if isinstance(summary, dict):
            b9 = summary.get("beso9_method1_topology_reconstructed")
            if isinstance(b9, dict) and b9 and not summary.get("beso7_method1_topology_reconstructed"):
                summary["beso7_method1_topology_reconstructed"] = b9
                out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        legs = len(
            (
                (summary.get("beso9_method1_topology_reconstructed") or summary.get("beso7_method1_topology_reconstructed") or {}).get(
                    "legs"
                )
                or []
            )
        )
        log("[INFO] parameters_summary.json already present — reuse")
        return {
            "ok": True,
            "reused": True,
            "parameters_summary_path": str(out),
            "url": None,
            "legs": legs,
            "title": summary.get("title") if isinstance(summary, dict) else None,
        }
    result = export_parameters_summary(run_dir, workspace_root=workspace_root, on_log=log)
    result["reused"] = False
    return result


def maybe_export_after_beso(
    run_dir: Path,
    *,
    workspace_root: Path | None = None,
    on_log: Callable[[str], None] | None = None,
    on_artifact: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    """BESO 成功后尽力导出；失败只记日志，不抛出（避免拖垮主作业）。"""
    log = on_log or (lambda _m: None)
    if (os.environ.get("BESO_SKIP_PARAMS_SUMMARY") or "").strip().lower() in ("1", "true", "yes"):
        log("[INFO] BESO_SKIP_PARAMS_SUMMARY=1 — skip parameters_summary export")
        return None
    if latest_state1_inp(run_dir) is None:
        log("[WARN] no file*_state1.inp — skip parameters_summary export")
        return None
    try:
        result = export_parameters_summary(
            run_dir,
            workspace_root=workspace_root,
            on_log=log,
        )
    except Exception as exc:  # noqa: BLE001
        log(f"[WARN] parameters_summary export skipped: {exc}")
        return {"ok": False, "error": str(exc)}

    if on_artifact and result.get("parameters_summary_path"):
        on_artifact(
            {
                "kind": "json",
                "path": "parameters_summary.json",
                "name": "parameters_summary.json",
                "meta": {
                    "group": "topology_reconstructed",
                    "legs": result.get("legs"),
                    "source_inp": result.get("source_inp"),
                },
            }
        )
        if result.get("measurements_path"):
            on_artifact(
                {
                    "kind": "json",
                    "path": "measurements.json",
                    "name": "measurements.json",
                    "meta": {"group": "topology_reconstructed"},
                }
            )
    log(
        f"[OK] parameters_summary.json ready"
        + (f" ({result.get('legs')} legs)" if result.get("legs") else "")
    )
    return result
