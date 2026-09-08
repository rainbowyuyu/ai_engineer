"""尺寸时域分析 API：拓扑参数汇总 → 静力尺寸优化 + Zwind 时域校核（含图）。"""
from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

router = APIRouter(tags=["sizing-time-analysis"])

AGENT_LABEL_ZH = "尺寸时域分析"


def _workspace_root() -> Path:
    import os

    return Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()


def _runs_dir() -> Path:
    d = _workspace_root() / "runs" / "_restruction"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_dir(session_id: str | None = None) -> tuple[str, Path]:
    sid = (session_id or "").strip() or uuid.uuid4().hex[:16]
    dest = _runs_dir() / sid
    dest.mkdir(parents=True, exist_ok=True)
    return sid, dest


def _rel_url(path: Path) -> str:
    root = _workspace_root() / "runs"
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = path.name
    return f"/runs/{rel}"


def extract_target_mw(payload: dict[str, Any] | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    for path in (
        ("target_power_MW",),
        ("target_power_mw",),
        ("computation", "target_power_MW"),
        ("optimization_info", "target_power_MW"),
        ("project", "target_capacity_mw"),
        ("steel_summary",),  # skip
    ):
        cur: Any = payload
        ok = True
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                ok = False
                break
            cur = cur[k]
        if ok and isinstance(cur, (int, float)) and float(cur) > 0:
            return float(cur)
    # nested geometry wrappers
    for key in ("geometry", "sized_geometry", "result", "parameters"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            mw = extract_target_mw(nested)
            if mw is not None:
                return mw
    return None


def _has_topology_block(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("beso7_method1_topology_reconstructed") or data.get("beso9_method1_topology_reconstructed"):
        return True
    if data.get("beso3_reference_from_fcstd"):
        return True
    for k, v in data.items():
        if isinstance(k, str) and "topology_reconstructed" in k.lower() and isinstance(v, dict) and v.get("legs"):
            return True
    return False


def _looks_like_geometry(data: dict[str, Any]) -> bool:
    if _has_topology_block(data):
        return True
    g = data.get("geometry")
    return isinstance(g, dict) and _has_topology_block(g)


def _as_geometry(data: dict[str, Any]) -> dict[str, Any]:
    if _has_topology_block(data):
        # normalize alias for steel / sizing helpers that expect beso7_* key
        if data.get("beso9_method1_topology_reconstructed") and not data.get(
            "beso7_method1_topology_reconstructed"
        ):
            data = dict(data)
            data["beso7_method1_topology_reconstructed"] = data["beso9_method1_topology_reconstructed"]
        return data
    g = data.get("geometry")
    if isinstance(g, dict) and _has_topology_block(g):
        return _as_geometry(g)
    # sizing_report may embed initial geometry path only — fall back to rules
    return data


def _write_sizing_curve(geometry: dict[str, Any], out_png: Path, *, target_mw: float, x_opt: float) -> bool:
    try:
        import os

        os.environ.setdefault("MPLBACKEND", "Agg")
        import matplotlib

        if matplotlib.get_backend().lower() != "agg":
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        from backend.tools.mixed_platform_steel import compute_for_scale, default_params_from_geometry

        params = default_params_from_geometry(geometry)
        s0 = math.sqrt(target_mw / params["rated_power_MW"])
        xs = np.linspace(0.55, 1.85, 35)
        steels: list[float] = []
        pitches: list[float] = []
        for x in xs:
            props = compute_for_scale(geometry, float(s0 * x), params, target_mw)
            steels.append(float(props["steel_per_MW_t"]))
            pitches.append(float(props["pitch_angle_deg"]))
        fig, ax1 = plt.subplots(figsize=(7.2, 3.8))
        ax1.plot(xs, steels, color="#3C5488", lw=2.0, label="Steel intensity (t/MW)")
        ax1.axvline(x_opt, color="#00A087", ls="--", lw=1.4, label=f"Optimum x={x_opt:.3f}")
        ax1.set_xlabel("Extra scale factor x")
        ax1.set_ylabel("Steel intensity (t/MW)")
        ax2 = ax1.twinx()
        ax2.plot(xs, pitches, color="#E64B35", lw=1.6, alpha=0.85, label="Pitch (deg)")
        ax2.axhline(5.0, color="#E64B35", ls=":", lw=1.0, alpha=0.6)
        ax2.set_ylabel("Pitch angle (deg)")
        ax1.set_title("Sizing–time analysis · static sweep", loc="left", fontweight="bold")
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", frameon=False, fontsize=8)
        fig.tight_layout()
        out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_png, dpi=140)
        plt.close(fig)
        return True
    except Exception:
        return False


def _run_static_bundle(
    *,
    dest: Path,
    target_mw: float,
    pitch_limit: float,
    geometry: dict[str, Any] | None,
) -> dict[str, Any]:
    from backend.tools.platform_restruction import run_platform_restruction

    prest = run_platform_restruction(float(target_mw), pitch_limit_deg=float(pitch_limit))
    (dest / "platform_restruction.json").write_text(
        json.dumps(prest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    steel = prest.get("steel_summary") or {}
    opt = prest.get("scaled_optimized") or {}
    figures: list[dict[str, str]] = []

    shell_report: dict[str, Any] | None = None
    if geometry and _looks_like_geometry(geometry):
        from backend.tools.mixed_platform_steel import attach_steel_to_geometry, compute_steel_report

        geom = _as_geometry(geometry)
        shell_report = compute_steel_report(geom, target_power_mw=float(target_mw), optimize=True)
        sized = attach_steel_to_geometry(geom, shell_report)
        (dest / "sizing_report.json").write_text(
            json.dumps(shell_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (dest / "sized_geometry.json").write_text(
            json.dumps(sized, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        x_opt = float((shell_report.get("computation") or {}).get("extra_scale_factor_x") or 1.0)
        curve = dest / "sizing_curve.png"
        if _write_sizing_curve(geom, curve, target_mw=float(target_mw), x_opt=x_opt):
            figures.append({"label": "钢耗–尺度曲线", "url": _rel_url(curve), "kind": "img"})

    figures.append(
        {
            "label": "平台库静力报告 JSON",
            "url": _rel_url(dest / "platform_restruction.json"),
            "kind": "json",
        }
    )
    if (dest / "sizing_report.json").is_file():
        figures.append(
            {"label": "壳用钢报告 JSON", "url": _rel_url(dest / "sizing_report.json"), "kind": "json"}
        )

    shell_steel = (shell_report or {}).get("steel_summary") or {}
    return {
        "ok": True,
        "mode": "static",
        "target_power_MW": float(target_mw),
        "base_platform": prest.get("base_platform"),
        "extra_scale_x": prest.get("extra_scale_x"),
        "optimizer": prest.get("optimizer"),
        "steel_intensity_t_per_MW": steel.get("steel_intensity_t_per_MW"),
        "struct_mass_t": steel.get("struct_mass_t"),
        "pitch_angle_deg": steel.get("pitch_angle_deg"),
        "shell_steel_intensity_t_per_MW": shell_steel.get("steel_intensity_t_per_MW"),
        "shell_pitch_angle_deg": shell_steel.get("pitch_angle_deg"),
        "geometry": {
            "main_col_dia_m": opt.get("main_col_dia"),
            "offset_col_dia_m": opt.get("offset_col_dia"),
            "heave_plate_dia_m": opt.get("heave_plate_dia"),
            "spacing_m": opt.get("spacing"),
            "draft_m": opt.get("draft"),
            "hub_height_m": opt.get("hub_height"),
            "rotor_dia_m": opt.get("rotor_dia"),
        },
        "figures": figures,
        "report_url": _rel_url(dest / "platform_restruction.json"),
        "process": {
            "title": f"{AGENT_LABEL_ZH} · 静力尺寸",
            "detail": (
                f"基型 {(prest.get('base_platform') or {}).get('name')} → "
                f"min x³ / pitch≤{pitch_limit}° → x={prest.get('extra_scale_x')}"
            ),
        },
    }


def _run_zwind_bundle(*, dest: Path, platform: str) -> dict[str, Any]:
    from backend.tools.zwind_eval import evaluate_zwind_bundle

    result = evaluate_zwind_bundle(run_dir=dest, platform=str(platform or "ai"))
    hl = result.get("highlights") or {}
    checks = result.get("pass_checks") or {}
    panels = result.get("panels") or []
    figures: list[dict[str, str]] = []
    for p in panels:
        if not isinstance(p, dict):
            continue
        name = p.get("name") or ""
        if name:
            figures.append(
                {
                    "label": str(p.get("label") or name),
                    "url": _rel_url(dest / "zwind_fig2" / name),
                    "kind": "img",
                }
            )
    if (dest / "zwind_report.json").is_file():
        figures.append({"label": "Zwind 报告 JSON", "url": _rel_url(dest / "zwind_report.json"), "kind": "json"})
    return {
        "ok": True,
        "mode": "zwind",
        "zwind_mode": result.get("mode"),
        "highlights": hl,
        "pass_checks": checks,
        "figures": figures,
        "panel_urls": [{"label": f["label"], "url": f["url"]} for f in figures if f.get("kind") == "img"],
        "report_url": _rel_url(dest / "zwind_report.json") if (dest / "zwind_report.json").is_file() else None,
        "process": {
            "title": f"{AGENT_LABEL_ZH} · Zwind 时域",
            "detail": (
                f"mode={result.get('mode')} · DLC6.1 pitch={hl.get('extreme_pitch_deg')}° · "
                f"系泊={hl.get('max_mooring_tension_kn')} kN"
            ),
        },
    }


class StaticBody(BaseModel):
    target_power_mw: float = Field(20.0, gt=0, le=50)
    pitch_limit_deg: float = Field(5.0, gt=0, le=30)
    session_id: str | None = None


class ZwindBody(BaseModel):
    target_power_mw: float | None = Field(None, gt=0, le=50)
    platform: str = Field("ai", description="ai | tuqiang")
    session_id: str | None = None
    job_id: str | None = None


class AnalyzeBody(BaseModel):
    """统一分析：可携带拓扑参数汇总 JSON。"""

    modes: list[str] = Field(default_factory=lambda: ["static", "zwind"])
    target_power_mw: float | None = None
    pitch_limit_deg: float = 5.0
    platform: str = "ai"
    session_id: str | None = None
    geometry: dict[str, Any] | None = None
    params_summary: dict[str, Any] | None = None


@router.get("/health")
def restruction_health() -> dict[str, Any]:
    return {
        "ok": True,
        "agent": "sizing_time_analysis",
        "label_zh": AGENT_LABEL_ZH,
        "capabilities": ["static_sizing", "zwind", "upload_params", "figures"],
    }


@router.post("/upload")
async def upload_params_summary(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
) -> dict[str, Any]:
    """上传拓扑优化对应的参数汇总 JSON（如 optimized_geometry / sizing_report / sized_geometry）。"""
    name = str(file.filename or "params.json")
    if not name.lower().endswith((".json", ".txt")):
        raise HTTPException(status_code=400, detail="请上传 JSON 参数汇总文件")
    raw = await file.read()
    if len(raw) > 25_000_000:
        raise HTTPException(status_code=400, detail="文件过大（>25MB）")
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="根节点须为 JSON 对象")

    sid, dest = _session_dir(session_id)
    path = dest / "params_summary.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    mw = extract_target_mw(data)
    return {
        "ok": True,
        "session_id": sid,
        "filename": name,
        "params_url": _rel_url(path),
        "inferred_target_power_MW": mw,
        "has_geometry": _looks_like_geometry(data),
        "title": data.get("title"),
        "label_zh": AGENT_LABEL_ZH,
    }


@router.post("/analyze")
def analyze(body: AnalyzeBody) -> dict[str, Any]:
    """根据参数汇总（或仅功率）运行静力尺寸 / Zwind，返回指标与图。"""
    sid, dest = _session_dir(body.session_id)
    payload = body.params_summary or body.geometry
    if payload is None and (dest / "params_summary.json").is_file():
        try:
            payload = json.loads((dest / "params_summary.json").read_text(encoding="utf-8"))
        except Exception:
            payload = None
    if isinstance(payload, dict):
        (dest / "params_summary.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    mw = body.target_power_mw
    if mw is None:
        mw = extract_target_mw(payload) if isinstance(payload, dict) else None
    if mw is None:
        mw = 20.0

    modes = [str(m).strip().lower() for m in (body.modes or []) if str(m).strip()]
    if not modes:
        modes = ["static", "zwind"]
    # aliases
    norm: list[str] = []
    for m in modes:
        if m in ("static", "sizing", "restruction", "steel", "静力", "尺寸"):
            norm.append("static")
        elif m in ("zwind", "time", "dynamic", "时域"):
            norm.append("zwind")
        else:
            norm.append(m)
    modes = list(dict.fromkeys(norm))

    geometry = payload if isinstance(payload, dict) and _looks_like_geometry(payload) else None
    out: dict[str, Any] = {
        "ok": True,
        "session_id": sid,
        "label_zh": AGENT_LABEL_ZH,
        "target_power_MW": float(mw),
        "results": {},
        "figures": [],
    }
    try:
        if "static" in modes:
            st = _run_static_bundle(
                dest=dest,
                target_mw=float(mw),
                pitch_limit=float(body.pitch_limit_deg),
                geometry=geometry,
            )
            out["results"]["static"] = st
            out["figures"].extend(st.get("figures") or [])
        if "zwind" in modes:
            zw = _run_zwind_bundle(dest=dest, platform=body.platform)
            out["results"]["zwind"] = zw
            out["figures"].extend(zw.get("figures") or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    out["process"] = {
        "title": AGENT_LABEL_ZH,
        "detail": " · ".join(
            filter(
                None,
                [
                    (out.get("results") or {}).get("static", {}).get("process", {}).get("detail"),
                    (out.get("results") or {}).get("zwind", {}).get("process", {}).get("detail"),
                ],
            )
        ),
    }
    return out


@router.post("/static")
def restruction_static(body: StaticBody) -> dict[str, Any]:
    sid, dest = _session_dir(body.session_id)
    geom = None
    p = dest / "params_summary.json"
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and _looks_like_geometry(raw):
                geom = raw
        except Exception:
            pass
    out = _run_static_bundle(
        dest=dest,
        target_mw=float(body.target_power_mw),
        pitch_limit=float(body.pitch_limit_deg),
        geometry=geom,
    )
    out["session_id"] = sid
    out["label_zh"] = AGENT_LABEL_ZH
    return out


@router.post("/zwind")
def restruction_zwind(body: ZwindBody) -> dict[str, Any]:
    root = _workspace_root()
    if body.job_id:
        run_dir = (root / "runs" / str(body.job_id).strip()).resolve()
        if not run_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"job run_dir 不存在: {body.job_id}")
        sid = str(body.job_id).strip()
        dest = run_dir
    else:
        sid, dest = _session_dir(body.session_id)
    try:
        out = _run_zwind_bundle(dest=dest, platform=str(body.platform or "ai"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    out["session_id"] = sid
    out["job_id"] = body.job_id
    out["label_zh"] = AGENT_LABEL_ZH
    return out
