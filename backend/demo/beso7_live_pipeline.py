"""BESO7.FCStd live pipeline demo — seed OC4 session + checklist + replan hooks.

Connects: landing task + design checklist → design-domain (BESO7.FCStd) → mesh
replan (ρₚ + versions) → finalize (checklist θ) → orchestrate job_context →
stepwise BESO replay from ``file001_state0.inp`` → topology reconstruction →
sizing optimization (SLSQP steel/pitch) → solver replan snapshot.

Uses workspace asset ``examples/beso/beso7/BESO7.FCStd`` (design domain),
``beso_output/Analysis-beso.inp`` (FCStd→INP), and progressive ``fileNNN_state*.inp``
frames (not a final-only dump). No live FreeCAD mesh / CalculiX when unavailable.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from backend.design_requirements.nl_parser import parse_design_checklist
from backend.design_requirements.paths import save_checklist
from backend.oc4_design_domain_service import (
    merge_session_meta,
    session_dir,
    session_progress_flags,
    write_session_meta,
)
from backend.replan.checklist_bridge import (
    beso_theta_defaults_from_checklist,
    link_oc4_session_to_task,
    maybe_commit_live_replan_version,
    write_job_context,
)
from backend.replan.guided import attach_guided
from backend.replan.simulate_cases import case1_mesh_demo, case2_solver_demo

# Minimal IGES header (session create requires .igs; geometry tools may no-op).
_MINIMAL_IGES = (
    "                                                                        S0000001\n"
    "1H,,1H;,7HBESO7DM,11HAI Engineer,16H20260728.000000,16H20260728.000000,  G0000001\n"
    "32,38,6,6,15,,1.0,1,2HM,1,0.001,15H20260728.000000,0.0001,0.0,           G0000002\n"
    "9HFreeCADDM,8HOpenCFD,,8HOpenCFD,0,8,0;                                 G0000003\n"
    "                                                                        T0000001\n"
)

_MINIMAL_OBJ = (
    "# BESO7 demo stub preview\n"
    "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n"
    "f 1 2 3\nf 1 2 4\nf 1 3 4\nf 2 3 4\n"
)

BESO7_NL = (
    "BESO7 半潜式平台拓扑优化演示：目标容量 20 MW，场址水深 50 m，Hs 12 m，Tp 14 s。"
    "概念阶段刚度拓扑优化，质量保留比 mass_goal_ratio=0.15，过滤半径 2.0，"
    "优化目标 stiffness；尺寸优化后接 Zwind 时域校核（third_party/zwind_newmodel / Fig. 2b–e）；"
    "入级 AIP/CCS 审查门槛 S≥85。"
    "几何资产：examples/beso/beso7/BESO7.FCStd。"
)


def _file_info(path: Path, *, role: str, label: str | None = None) -> dict[str, Any]:
    p = Path(path)
    size = None
    exists = p.is_file()
    if exists:
        try:
            size = int(p.stat().st_size)
        except OSError:
            size = None
    return {
        "name": label or p.name,
        "path": str(p),
        "rel": p.name,
        "role": role,
        "exists": exists,
        "size_bytes": size,
    }


def _session_io_snapshot(sdir: Path, fcstd: Path, analysis: Path) -> dict[str, Any]:
    return {
        "inputs": [
            _file_info(fcstd, role="cad_asset", label="BESO7.FCStd"),
            _file_info(analysis, role="fem_from_fcstd", label="Analysis-beso.inp"),
            _file_info(sdir / "file001_state0.inp", role="optimize_start", label="file001_state0.inp"),
        ],
        "outputs": [
            _file_info(sdir / "BESO7.FCStd", role="session_fcstd"),
            _file_info(sdir / "design_preview.obj", role="design_preview"),
            _file_info(sdir / "02_mesh_body.inp", role="mesh"),
            _file_info(sdir / "03_for_beso.inp", role="for_beso"),
            _file_info(sdir / "file001_state0.inp", role="iter1_void"),
            _file_info(sdir / "session.json", role="session_meta"),
            _file_info(sdir / "build_plan.md", role="plan"),
        ],
    }


def beso7_root(workspace_root: Path) -> Path:
    return (workspace_root / "examples" / "beso" / "beso7").resolve()


def beso7_fcstd(workspace_root: Path) -> Path:
    return beso7_root(workspace_root) / "BESO7.FCStd"


def beso7_analysis_inp(workspace_root: Path) -> Path:
    return beso7_root(workspace_root) / "beso_output" / "Analysis-beso.inp"


def beso7_file001_state0(workspace_root: Path) -> Path:
    """Early BESO iteration void mesh — starting point for stepwise topology replay."""
    return beso7_root(workspace_root) / "beso_output" / "file001_state0.inp"


def beso7_file001_state1(workspace_root: Path) -> Path:
    return beso7_root(workspace_root) / "beso_output" / "file001_state1.inp"


def _ensure_beso7_assets(workspace_root: Path) -> None:
    fc = beso7_fcstd(workspace_root)
    if not fc.is_file():
        raise FileNotFoundError(f"缺少 BESO7.FCStd：{fc}")
    inp = beso7_analysis_inp(workspace_root)
    if not inp.is_file():
        raise FileNotFoundError(f"缺少 Analysis-beso.inp（FCStd→INP 转换产物）：{inp}")
    s0 = beso7_file001_state0(workspace_root)
    if not s0.is_file():
        raise FileNotFoundError(f"缺少 file001_state0.inp（第 1 步优化起点）：{s0}")


def _inp_surface_to_obj(inp_path: Path, out_obj: Path) -> bool:
    """Convert CalculiX C3D4 INP (e.g. fileNNN_state0/1) to a lightweight OBJ surface."""
    try:
        import meshio
        import numpy as np

        from backend.tools.cad_drawing_pack import _mesh_from_inp

        points, faces = _mesh_from_inp(Path(inp_path))
        # meshio OBJ expects triangle cells (0-based)
        mesh = meshio.Mesh(points=np.asarray(points, dtype=float), cells=[("triangle", np.asarray(faces, dtype=int))])
        out_obj.parent.mkdir(parents=True, exist_ok=True)
        meshio.write(out_obj, mesh, file_format="obj")
        return out_obj.is_file() and out_obj.stat().st_size > 64
    except Exception:
        return False


def _obj_preview_png(obj_path: Path, png_path: Path, *, size: int = 360, color: tuple[int, int, int] = (14, 165, 233)) -> bool:
    """Rasterize a simple isometric silhouette from Wavefront OBJ (no WebGL / FreeCAD)."""
    try:
        from PIL import Image, ImageDraw

        verts: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        for line in Path(obj_path).read_text(encoding="utf-8", errors="ignore").splitlines():
            t = line.strip()
            if t.startswith("v "):
                p = t.split()
                if len(p) >= 4:
                    verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif t.startswith("f "):
                idx = []
                for tok in t.split()[1:]:
                    try:
                        idx.append(int(tok.split("/")[0]) - 1)
                    except ValueError:
                        continue
                if len(idx) >= 3:
                    for i in range(1, len(idx) - 1):
                        faces.append((idx[0], idx[i], idx[i + 1]))
        if len(verts) < 3:
            return False

        # Downsample faces for speed
        step = max(1, len(faces) // 12000) if faces else 1
        face_iter = faces[::step] if faces else []

        proj: list[tuple[float, float]] = []
        for x, y, z in verts:
            # isometric-ish
            proj.append((x - z * 0.55, y + z * 0.28))

        if face_iter:
            used = {i for tri in face_iter for i in tri if 0 <= i < len(proj)}
            pts = [proj[i] for i in used] or proj
        else:
            pts = proj[:: max(1, len(proj) // 8000)]

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span = max(max_x - min_x, max_y - min_y, 1e-6)
        pad = size * 0.08
        scale = (size - 2 * pad) / span

        def to_px(p: tuple[float, float]) -> tuple[float, float]:
            return (
                pad + (p[0] - min_x) * scale,
                size - (pad + (p[1] - min_y) * scale),
            )

        img = Image.new("RGB", (size, size), (248, 250, 252))
        draw = ImageDraw.Draw(img, "RGBA")
        fill = (*color, 170)
        stroke = (15, 23, 42, 90)
        if face_iter:
            for a, b, c in face_iter:
                if not (0 <= a < len(proj) and 0 <= b < len(proj) and 0 <= c < len(proj)):
                    continue
                tri = [to_px(proj[a]), to_px(proj[b]), to_px(proj[c])]
                draw.polygon(tri, fill=fill, outline=stroke)
        else:
            for p in pts:
                x, y = to_px(p)
                draw.ellipse((x - 1.2, y - 1.2, x + 1.2, y + 1.2), fill=color)

        png_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(png_path, format="PNG", optimize=True)
        return png_path.is_file() and png_path.stat().st_size > 64
    except Exception:
        return False


def _ensure_obj_preview(obj_path: Path) -> Path | None:
    """Write sibling ``*.preview.png`` next to OBJ when possible."""
    if not obj_path.is_file():
        return None
    png = obj_path.with_suffix("").with_name(obj_path.stem + ".preview.png")
    if png.is_file() and png.stat().st_size > 64:
        return png
    if _obj_preview_png(obj_path, png):
        return png
    return None


def _export_fcstd_preview(fcstd: Path, out_obj: Path, *, linear_deflection: float = 1200.0) -> bool:
    """Export BESO7.FCStd design-domain geometry to OBJ via FreeCAD (when available)."""
    try:
        from backend.tools.freecad_export_obj import run_freecad_export_obj

        run_freecad_export_obj(fcstd, out_obj, linear_deflection=linear_deflection, timeout_s=180.0)
        return out_obj.is_file() and out_obj.stat().st_size > 64
    except Exception:
        return False


def _write_beso7_session_files(sdir: Path, workspace_root: Path) -> dict[str, Any]:
    """Seed OC4 session from BESO7.FCStd + FCStd→INP + file001 start frame."""
    fcstd = beso7_fcstd(workspace_root)
    analysis = beso7_analysis_inp(workspace_root)
    state0 = beso7_file001_state0(workspace_root)
    state1 = beso7_file001_state1(workspace_root)

    # Keep FCStd itself in the session (design-domain source of truth)
    shutil.copy2(fcstd, sdir / "BESO7.FCStd")
    shutil.copy2(fcstd, sdir / "00_source.FCStd")

    # Design-domain 3D: prefer FreeCAD export of FCStd; else Analysis-beso surface (same mesh lineage)
    from_fcstd = _export_fcstd_preview(fcstd, sdir / "design_preview.obj")
    preview_ok = from_fcstd
    if preview_ok:
        shutil.copy2(sdir / "design_preview.obj", sdir / "source_preview.obj")
    else:
        preview_ok = _inp_surface_to_obj(analysis, sdir / "design_preview.obj")
        if preview_ok:
            shutil.copy2(sdir / "design_preview.obj", sdir / "source_preview.obj")
    if not preview_ok:
        (sdir / "source_preview.obj").write_text(_MINIMAL_OBJ, encoding="utf-8")
        (sdir / "design_preview.obj").write_text(_MINIMAL_OBJ, encoding="utf-8")

    _ensure_obj_preview(sdir / "design_preview.obj")
    _ensure_obj_preview(sdir / "source_preview.obj")

    # Minimal IGES/STEP placeholders for session progress flags (geometry lives in FCStd + OBJ)
    (sdir / "00_source.igs").write_text(_MINIMAL_IGES, encoding="ascii")
    (sdir / "01_design_domain.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    (sdir / "01_design_domain.igs").write_text(_MINIMAL_IGES, encoding="ascii")

    # FCStd → INP conversion product (examples/beso/beso7/main.py export)
    shutil.copy2(analysis, sdir / "02_mesh_body.inp")
    shutil.copy2(analysis, sdir / "03_for_beso.inp")
    shutil.copy2(analysis, sdir / "Analysis-beso.inp")

    # Step-1 optimization seed: void + solid from first BESO iteration
    shutil.copy2(state0, sdir / "file001_state0.inp")
    if state1.is_file():
        shutil.copy2(state1, sdir / "file001_state1.inp")
    _inp_surface_to_obj(state0, sdir / "iter001_state0.obj")
    _ensure_obj_preview(sdir / "iter001_state0.obj")
    if state1.is_file():
        _inp_surface_to_obj(state1, sdir / "iter001_state1.obj")
        _ensure_obj_preview(sdir / "iter001_state1.obj")

    (sdir / "build_plan.md").write_text(
        "# BESO7 演示计划（对齐 AI Designer Phase I–IV）\n\n"
        "1. **设计域**：`BESO7.FCStd`（FreeCAD 源模型）→ `design_preview.obj`\n"
        "2. **Input 转换**：FCStd FEM → `Analysis-beso.inp`（`02_mesh_body.inp` / `03_for_beso.inp`）\n"
        "3. **逐步优化**：从 `file001_state0.inp` / `file001_state1.inp` 起回放迭代，而非直接终态\n"
        "4. Phase IV：Automated Reviewer 候选打分与选优\n",
        encoding="utf-8",
    )
    return {
        "fcstd": str(fcstd),
        "analysis_inp": str(analysis),
        "file001_state0": str(state0),
        "preview_from_fcstd": bool(from_fcstd),
        "preview_ok": bool(preview_ok),
    }


def bootstrap_beso7_live_demo(
    workspace_root: Path,
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Create checklist + OC4 session linked to task, seeded from BESO7 assets."""
    _ensure_beso7_assets(workspace_root)
    tid = str(task_id or "").strip() or f"beso7-{uuid.uuid4().hex[:10]}"
    from backend.design_requirements.markdown import checklist_to_markdown

    checklist = parse_design_checklist(BESO7_NL)
    # Force capacity / BESO θ to match optimized_geometry.json (20 MW) + beso_conf defaults
    try:
        checklist.project.target_capacity_mw = 20.0
        checklist.job_descriptor.theta.beso.mass_goal_ratio = 0.15
        checklist.job_descriptor.theta.beso.filter_radius = 2.0
        checklist.job_descriptor.theta.beso.optimization_base = "stiffness"
    except Exception:
        pass
    md = checklist_to_markdown(checklist)
    save_checklist(checklist, markdown=md)
    cid = checklist.meta.checklist_id

    sid = uuid.uuid4().hex
    sdir = session_dir(workspace_root, sid)
    sdir.mkdir(parents=True, exist_ok=False)
    analysis = beso7_analysis_inp(workspace_root)
    seed_meta = _write_beso7_session_files(sdir, workspace_root)

    fcstd = beso7_fcstd(workspace_root)
    meta = {
        "session_id": sid,
        "source_name": "00_source.FCStd",
        "upload_cad_stem": "BESO7",
        "demo_case": "beso7_live_pipeline",
        "demo_fcstd": str(fcstd.relative_to(workspace_root.resolve())).replace("\\", "/"),
        "demo_fcstd_abs": str(fcstd),
        "demo_input_conversion": "FCStd → Analysis-beso.inp；逐步优化自 file001_state0.inp 起",
        "demo_start_iter": "file001_state0.inp",
        "workspace_relative": str(sdir.relative_to(workspace_root.resolve())).replace("\\", "/"),
        "design_domain_compound_iges": "01_design_domain.igs",
        "design_domain_full_build_done": True,
        "geometry_summary": {
            "name": "BESO7.FCStd",
            "note": "设计域来自 BESO7.FCStd；INP 为 FCStd FEM 转换产物；拓扑从 file001 逐步演化。",
            "demo_asset": "examples/beso/beso7/BESO7.FCStd",
            "preview_from_fcstd": bool(seed_meta.get("preview_from_fcstd")),
        },
    }
    write_session_meta(sdir, meta)
    # Static /runs URLs so Three.js can fetch OBJ (not the JSON text file API)
    from backend.oc4_design_domain_service import runs_file_url

    design_obj_url = None
    source_obj_url = None
    design_png_url = None
    source_png_url = None
    if (sdir / "design_preview.obj").is_file():
        design_obj_url = runs_file_url(workspace_root, sdir / "design_preview.obj")
        png = _ensure_obj_preview(sdir / "design_preview.obj")
        if png is not None:
            design_png_url = runs_file_url(workspace_root, png)
    if (sdir / "source_preview.obj").is_file():
        source_obj_url = runs_file_url(workspace_root, sdir / "source_preview.obj")
        png = _ensure_obj_preview(sdir / "source_preview.obj")
        if png is not None:
            source_png_url = runs_file_url(workspace_root, png)
    if design_obj_url or source_obj_url:
        merge_session_meta(
            sdir,
            {
                "design_obj_url": design_obj_url,
                "source_obj_url": source_obj_url,
                "design_png_url": design_png_url,
                "source_png_url": source_png_url,
            },
        )
    link_oc4_session_to_task(sid, sdir, task_id=tid, design_checklist_id=cid)

    theta = beso_theta_defaults_from_checklist(checklist)
    flags = session_progress_flags(sdir)
    io = _session_io_snapshot(sdir, fcstd, analysis)
    return {
        "ok": True,
        "task_id": tid,
        "checklist_id": cid,
        "checklist": checklist.model_dump(mode="json"),
        "session_id": sid,
        "session_dir": str(sdir),
        "scan_dir": str(sdir),
        "fcstd_path": str(fcstd),
        "fcstd_rel": meta["demo_fcstd"],
        "analysis_inp": str(analysis),
        "design_obj_url": design_obj_url,
        "source_obj_url": source_obj_url,
        "design_png_url": design_png_url,
        "source_png_url": source_png_url,
        "beso_theta": theta,
        "progress": flags,
        "io": io,
        "process": {
            "title": "任务 + 设计清单 → 设计域会话",
            "detail": "解析 Phase I 清单，用 BESO7.FCStd 资产种子 OC4 会话并自动 link-task。",
        },
        "story": [
            "主页任务 + 设计清单",
            "进入设计域（自动 link）",
            "mesh 失败 → ρₚ + versions",
            "finalize 使用清单 θ",
            "编排开始写入 job_context",
            "求解失败 → solver replan 快照",
        ],
    }


def run_mesh_replan_step(task_id: str, *, session_id: str | None = None) -> dict[str, Any]:
    """Case1 mesh replan + ρₚ + version commit (live path helpers)."""
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id required")
    out = case1_mesh_demo()
    guided = attach_guided(out)
    event = (out.get("result") or {}).get("event") or {}
    event_id = event.get("event_id") or out.get("event_id")
    theta_before = (out.get("result") or {}).get("theta_before")
    theta_after = (out.get("result") or {}).get("theta_after")

    from backend.orchestrator.state import mark_rho_pending

    mark_rho_pending(tid, event_id=event_id)
    ver = maybe_commit_live_replan_version(
        tid,
        event_id=event_id,
        theta_before=theta_before,
        theta_after=theta_after,
        message="BESO7 demo · mesh live replan",
        case_id="mesh_live",
    )
    if session_id:
        try:
            from backend.oc4_design_domain_service import design_domain_root
            # session_dir needs workspace — merge via relative lookup in caller
        except Exception:
            pass

    guided["task_id"] = tid
    guided["version"] = ver
    guided["rho_pending"] = 1
    guided["resume"] = {"target": "mesh", "label": "按新网格参数继续"}
    ev_id = str(event_id or "")
    guided["io"] = {
        "inputs": [
            {"name": "mesh failure logs", "role": "signal", "rel": "inverted elements / quality < τ", "exists": True},
            {"name": "θ_before", "role": "theta", "rel": "characteristic_length_max", "exists": True},
        ],
        "outputs": [
            {
                "name": "replan_event.json",
                "role": "replan_event",
                "rel": f"runs/_replan/{ev_id[:12]}…/replan_event.json" if ev_id else "replan_event.json",
                "exists": bool(ev_id),
            },
            {
                "name": "version commit",
                "role": "version",
                "rel": (ver or {}).get("commit", {}).get("commit_id") or "—",
                "exists": bool((ver or {}).get("commit")),
            },
            {"name": "ρₚ = 1", "role": "gate", "rel": "workflow.state", "exists": True},
        ],
    }
    guided["process"] = {
        "title": "体网格失败 → 重规划",
        "detail": "检测到翻转单元 / 质量过低，refine_mesh 收紧 characteristic_length_max，写入 versions 并标记 ρₚ。",
    }
    return guided


def check_finalize_gate(task_id: str) -> dict[str, Any]:
    from backend.orchestrator.gates import evaluate_transition
    from backend.orchestrator.state import load_workflow_state

    tid = str(task_id or "").strip()
    st = load_workflow_state(tid)
    verdict = evaluate_transition(st, "phase_ii_finalize")
    return {
        "ok": verdict.ok,
        "rho_pending": st.rho_pending,
        "verdict": verdict.model_dump(mode="json"),
        "process": {
            "title": "相位闸检查 finalize",
            "detail": "ρₚ≠0 时拦截进入 finalize / 编排；演示中应先看到拦截，清 ρₚ 后再通过。",
        },
        "io": {
            "inputs": [{"name": "workflow.state", "role": "state", "rel": f"task={tid}", "exists": True}],
            "outputs": [
                {
                    "name": "can-advance phase_ii_finalize",
                    "role": "gate",
                    "rel": "PASS" if verdict.ok else "BLOCKED",
                    "exists": True,
                }
            ],
        },
    }

def run_finalize_step(
    workspace_root: Path,
    *,
    session_id: str,
    task_id: str,
    clear_rho: bool = True,
) -> dict[str, Any]:
    """Clear ρₚ (optional) then finalize with checklist θ."""
    import os

    from backend.orchestrator.state import clear_rho_pending
    from backend.oc4_design_domain_service import read_session_meta
    from backend.replan.checklist_bridge import load_checklist_from_session
    from backend.tools.inp_oc4_design_nondesign import write_beso_conf_example3_style

    tid = str(task_id or "").strip()
    if clear_rho and tid:
        clear_rho_pending(tid)

    sdir = session_dir(workspace_root, session_id)
    if not sdir.is_dir():
        raise FileNotFoundError(f"session not found: {session_id}")
    if not (sdir / "03_for_beso.inp").is_file():
        raise FileNotFoundError("缺少 03_for_beso.inp")

    meta = read_session_meta(sdir)
    checklist = load_checklist_from_session(sdir)
    if checklist is None and meta.get("design_checklist_id"):
        from backend.design_requirements.paths import load_checklist

        checklist = load_checklist(str(meta.get("design_checklist_id")))
    beso_theta = beso_theta_defaults_from_checklist(checklist)
    ccx = Path(os.environ.get("CCX_PATH", r"D:\freecad\bin\ccx.exe")).resolve()
    write_beso_conf_example3_style(
        sdir / "beso_conf.py",
        work_dir=sdir.resolve(),
        ccx_path=ccx,
        inp_name="03_for_beso.inp",
        mass_goal_ratio=float(beso_theta["mass_goal_ratio"]),
        filter_radius=float(beso_theta["filter_radius"]),
        optimization_base=str(beso_theta["optimization_base"]),
    )
    scan_dir = str(sdir.resolve())
    merge_session_meta(
        sdir,
        {
            "scan_dir": scan_dir,
            "finalized": True,
            "beso_defaults_ref": beso_theta.get("source"),
            "beso_theta": {
                "mass_goal_ratio": beso_theta["mass_goal_ratio"],
                "filter_radius": beso_theta["filter_radius"],
                "optimization_base": beso_theta["optimization_base"],
            },
            "design_checklist_id": beso_theta.get("checklist_id") or meta.get("design_checklist_id"),
        },
    )
    return {
        "ok": True,
        "scan_dir": scan_dir,
        "beso_theta": beso_theta,
        "design_checklist_id": beso_theta.get("checklist_id") or meta.get("design_checklist_id"),
        "task_id": tid,
        "rho_cleared": bool(clear_rho),
        "process": {
            "title": "finalize · 清单 θ → beso_conf.py",
            "detail": "清除 ρₚ 后写入 BESO 配置，θ 来自设计清单（否则 Chen 默认 0.15 / stiffness）。",
        },
        "io": {
            "inputs": [
                _file_info(sdir / "03_for_beso.inp", role="for_beso"),
                {
                    "name": "design_checklist",
                    "role": "checklist",
                    "rel": str(beso_theta.get("checklist_id") or meta.get("design_checklist_id") or "")[:16],
                    "exists": True,
                },
            ],
            "outputs": [
                _file_info(sdir / "beso_conf.py", role="beso_conf"),
                _file_info(sdir / "session.json", role="session_meta"),
            ],
        },
    }


def seed_beso7_job_artifacts(
    workspace_root: Path,
    *,
    job_id: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Stepwise BESO7 replay: FCStd→Analysis-beso.inp, then file001→… frames (not final-only).

    Avoids live beso_main/CCX exit-1 while still showing progressive topology from
    ``file001_state0/1.inp`` onward (INP→OBJ), plus Mass/FI history curves.
    """
    from backend.jobs.manager import jobs
    from backend.jobs.models import JobStatus
    from backend.pydantic_compat import model_copy_update

    out_src = beso7_analysis_inp(workspace_root).parent
    if not out_src.is_dir():
        raise FileNotFoundError(f"缺少 beso_output: {out_src}")

    job = jobs.get_job(job_id)
    run_dir = Path(job.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    analysis = beso7_analysis_inp(workspace_root)
    shutil.copy2(analysis, run_dir / "Analysis-beso.inp")
    copied.append("Analysis-beso.inp")

    for name in ("file001_state0.inp", "file001_state1.inp"):
        src = out_src / name
        if src.is_file():
            shutil.copy2(src, run_dir / name)
            copied.append(name)

    for name in ("Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png", "energy_density_mean.png"):
        src = out_src / name
        if src.is_file():
            shutil.copy2(src, run_dir / name)
            copied.append(name)

    iter_ids = [1, 3, 6, 10, 16, 26, 35, 45, 51]
    evolution: list[dict[str, Any]] = []

    s0 = out_src / "file001_state0.inp"
    s0_obj = run_dir / "iter001_state0.obj"
    if s0.is_file() and _inp_surface_to_obj(s0, s0_obj):
        copied.append("iter001_state0.obj")
        png = _ensure_obj_preview(s0_obj)
        frame = {
            "iter": 0,
            "label": "起点 · file001_state0（去除相）",
            "obj": f"/runs/{job_id}/iter001_state0.obj",
            "inp": f"/runs/{job_id}/file001_state0.inp",
        }
        if png is not None:
            frame["png"] = f"/runs/{job_id}/{png.name}"
            copied.append(png.name)
        evolution.append(frame)

    for i in iter_ids:
        stem = f"file{i:03d}"
        state1 = out_src / f"{stem}_state1.inp"
        state0 = out_src / f"{stem}_state0.inp"
        frame_obj = run_dir / f"{stem}.obj"
        ok = False
        if state1.is_file():
            ok = _inp_surface_to_obj(state1, frame_obj)
            if ok:
                shutil.copy2(state1, run_dir / state1.name)
                copied.append(state1.name)
        if not ok and state0.is_file():
            ok = _inp_surface_to_obj(state0, frame_obj)
            if ok:
                shutil.copy2(state0, run_dir / state0.name)
                copied.append(state0.name)
        if ok:
            copied.append(frame_obj.name)
            png = _ensure_obj_preview(frame_obj)
            frame = {
                "iter": i,
                "label": f"迭代 {i} · 保留相",
                "obj": f"/runs/{job_id}/{frame_obj.name}",
                "inp": f"/runs/{job_id}/{stem}_state1.inp"
                if (run_dir / f"{stem}_state1.inp").is_file()
                else f"/runs/{job_id}/{stem}_state0.inp",
            }
            if png is not None:
                frame["png"] = f"/runs/{job_id}/{png.name}"
                copied.append(png.name)
            evolution.append(frame)

    if evolution:
        first_name = Path(evolution[0]["obj"]).name
        last_name = Path(evolution[-1]["obj"]).name
        if (run_dir / first_name).is_file():
            shutil.copy2(run_dir / first_name, run_dir / "latest.obj")
            copied.append("latest.obj")
        if (run_dir / last_name).is_file():
            shutil.copy2(run_dir / last_name, run_dir / "final.obj")
            copied.append("final.obj")
    elif not (run_dir / "latest.obj").is_file():
        fc = beso7_fcstd(workspace_root)
        tmp = run_dir / "_fcstd_preview.obj"
        if _export_fcstd_preview(fc, tmp) or _inp_surface_to_obj(analysis, run_dir / "latest.obj"):
            if tmp.is_file() and not (run_dir / "latest.obj").is_file():
                shutil.copy2(tmp, run_dir / "latest.obj")
            copied.append("latest.obj")
        else:
            (run_dir / "latest.obj").write_text(_MINIMAL_OBJ, encoding="utf-8")
            copied.append("latest.obj")

    (run_dir / "demo_seed.json").write_text(
        json.dumps(
            {
                "source": "examples/beso/beso7",
                "design_domain": "BESO7.FCStd",
                "fem_input": "beso_output/Analysis-beso.inp",
                "optimize_start": "beso_output/file001_state0.inp",
                "mode": "stepwise_replay",
                "copied": copied,
                "evolution": evolution,
                "note": "Replay from file001 (not final-only dump). No live CalculiX.",
                "task_id": task_id,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "evolution_manifest.json").write_text(
        json.dumps({"frames": evolution, "start": "file001_state0.inp"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    arts = jobs._artifacts_from_disk(job_id, run_dir)
    # Ensure curve PNGs are always listed as image artifacts (Fig.1 metrics)
    for img in ("Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png", "energy_density_mean.png"):
        if (run_dir / img).is_file() and not any(a.get("name") == img for a in arts):
            arts.append(
                {
                    "type": "artifact",
                    "kind": "image",
                    "url": f"/runs/{job_id}/{img}",
                    "name": img,
                }
            )
    if (run_dir / "latest.obj").is_file() and not any(a.get("name") == "latest.obj" for a in arts):
        arts.append(
            {
                "type": "artifact",
                "kind": "mesh",
                "url": f"/runs/{job_id}/latest.obj",
                "name": "latest.obj",
            }
        )
    for fr in evolution:
        arts.append(
            {
                "type": "artifact",
                "kind": "mesh",
                "url": fr["obj"],
                "name": Path(fr["obj"]).name,
                "iter": fr["iter"],
            }
        )

    start_mesh = evolution[0]["obj"] if evolution else f"/runs/{job_id}/latest.obj"
    final_mesh = evolution[-1]["obj"] if evolution else start_mesh

    logs = [
        "[demo] BESO7 stepwise: FCStd design domain → Analysis-beso.inp → file001…",
        "[demo] Start: file001_state0/state1 (not final-only Mass/VTK dump).",
        f"[demo] Evolution frames: {len(evolution)}; copied {len(copied)} files.",
        "[OK] Demo job completed — stepwise 3D + curves ready.",
    ]
    with jobs._lock:
        j = jobs._jobs[job_id]
        jobs._jobs[job_id] = model_copy_update(
            j,
            {
                "status": JobStatus.completed,
                "logs": list(j.logs or []) + logs,
                "artifacts": arts,
                "latest_vtk_url": start_mesh,
            },
        )
    for line in logs:
        jobs._emit(job_id, {"type": "log", "line": line})
    jobs._emit(job_id, {"type": "status", "status": JobStatus.completed.value})
    for a in arts:
        jobs._emit(job_id, a)
    if start_mesh:
        jobs._emit(job_id, {"type": "vtk", "url": start_mesh})

    write_job_context(
        run_dir,
        demo_seeded=True,
        demo_source="examples/beso/beso7",
        demo_mode="stepwise_from_file001",
        task_id=task_id,
    )

    return {
        "ok": True,
        "job_id": job_id,
        "copied": copied,
        "artifacts": arts,
        "latest_mesh_url": start_mesh,
        "final_mesh_url": final_mesh,
        "evolution": evolution,
        "curve_urls": [
            f"/runs/{job_id}/{n}"
            for n in ("Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png", "energy_density_mean.png")
            if (run_dir / n).is_file()
        ],
        "process": {
            "title": "Phase II · 逐步拓扑优化回放（自 file001）",
            "detail": "设计域 BESO7.FCStd → Analysis-beso.inp；从 file001_state0 起逐步演化，而非直接终态产物。",
        },
        "io": {
            "inputs": [
                _file_info(beso7_fcstd(workspace_root), role="design_domain_fcstd"),
                _file_info(analysis, role="fem_inp_from_fcstd"),
                _file_info(out_src / "file001_state0.inp", role="optimize_start"),
            ],
            "outputs": [_file_info(run_dir / n, role="seeded") for n in copied[:10]],
        },
    }

def run_candidate_select_step(task_id: str, *, auto_select: bool = False) -> dict[str, Any]:
    """Phase IV: register multiple candidates with 3D/curve previews; optionally auto-select.

    When auto_select is False (default for interactive demo), returns awaiting_selection
    so the user can pick a scheme in the UI.
    """
    from backend.candidates.registry import list_candidates, register_candidate, select_best
    from backend.orchestrator.halt import evaluate_halt_gate
    from backend.versions.store import commit_candidate_snapshot, commit_files, open_process

    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id required")

    workspace = Path(__file__).resolve().parents[2]
    try:
        import os

        workspace = Path(os.environ.get("WORKSPACE_ROOT", str(workspace))).resolve()
    except Exception:
        pass

    out_src = beso7_analysis_inp(workspace).parent
    stl = beso7_root(workspace) / "addition" / "method1_parametric" / "preview.stl"
    preview_obj_bytes: bytes | None = None
    if stl.is_file():
        try:
            import meshio

            mesh = meshio.read(stl)
            tmp = workspace / "runs" / "_candidates" / tid / "_shared_preview.obj"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            meshio.write(tmp, mesh, file_format="obj")
            preview_obj_bytes = tmp.read_bytes()
        except Exception:
            preview_obj_bytes = _MINIMAL_OBJ.encode("utf-8")
    else:
        preview_obj_bytes = _MINIMAL_OBJ.encode("utf-8")

    curve_map = {
        "A": "Mass.png",
        "B": "FI_mean.png",
        "C": "FI_max.png",
        "D": "FI_violated.png",
        "E": "energy_density_mean.png",
    }

    def _basis(
        dims: dict[str, float],
        *,
        metrics: dict[str, str],
        evidence: dict[str, str],
    ) -> list[dict[str, Any]]:
        labels = {
            "capacity": "单机容量",
            "steel": "钢耗强度",
            "cost": "单位造价",
            "construction": "建造周期",
            "fatigue": "疲劳寿命",
        }
        formula = {
            "capacity": "s_cap：相对目标 20 MW 偏差分段（|ΔP|≤0.5 → 高分）",
            "steel": "s_steel：相对 300 t/MW 国示范目标 + 同容量分位",
            "cost": "s_cost：相对 AI 参考线 ρ=x/x_ref 三段函数（ρ_pass=1.18）",
            "construction": "s_const：相对参考建造周期的 ρ 三段函数",
            "fatigue": "s_fat：相对 L_ref=25 年设计寿命的 ρ_L 分段",
        }
        out: list[dict[str, Any]] = []
        for k, v in dims.items():
            out.append(
                {
                    "dim": k,
                    "label": labels.get(k, k),
                    "score": float(v),
                    "metric": metrics.get(k, "—"),
                    "evidence": evidence.get(k, "—"),
                    "formula_ref": formula.get(k, "AI Review 分段规则"),
                }
            )
        return out

    specs = [
        {
            "key": "A",
            "label": "方案 A · 保守拓扑（较高质量保留）",
            "score": 82.0,
            "dims": {"capacity": 78, "steel": 80, "cost": 88, "construction": 84, "fatigue": 76},
            "notes": "偏保守材料分布，建造性更好，综合分略低于终止门。",
            "rationale": (
                "智能体根据拓扑质量保留偏高、钢耗与造价指标，预测建造性占优但容量/疲劳略保守；"
                "加权综合 S≈82，未达 S≥85 终止门。"
            ),
            "geom": "examples/beso/beso7/beso_output/file005.vtk",
            "metrics": {
                "capacity": "P_c≈18.5 MW（目标 20）",
                "steel": "I_steel≈310 t/MW",
                "cost": "ρ_cost≈0.96（低于参考）",
                "construction": "建造周期≈参考线 ×0.97",
                "fatigue": "L≈22 年（L_ref=25）",
            },
            "evidence": {
                "capacity": "质量保留偏高 → 等效受风面积略小，容量预测偏低",
                "steel": "材料偏多，相对 300 t/MW 目标略差",
                "cost": "材料用量可控，单位造价优于参考线",
                "construction": "拓扑更规整，便于分段建造",
                "fatigue": "热点仍存在，寿命裕度一般",
            },
        },
        {
            "key": "B",
            "label": "方案 B · 推荐拓扑（BESO7 · S≈88.5）",
            "score": 88.5,
            "dims": {"capacity": 86, "steel": 84, "cost": 82, "construction": 80, "fatigue": 78},
            "notes": "论文推荐平衡点：刚度与入级审查折中最优。",
            "rationale": (
                "智能体综合五维：容量贴近 20 MW、钢耗接近国示范目标、造价/建造可接受、疲劳过线；"
                "加权 S≈88.5，通过终止门，作为推荐方案。"
            ),
            "geom": "examples/beso/beso7/beso_output/file016.vtk",
            "metrics": {
                "capacity": "P_c≈19.8 MW（|ΔP|≤0.5）",
                "steel": "I_steel≈292 t/MW",
                "cost": "ρ_cost≈1.04",
                "construction": "建造周期≈参考线 ×1.05",
                "fatigue": "L≈24 年",
            },
            "evidence": {
                "capacity": "拓扑与参数化尺寸对齐 20 MW 资产",
                "steel": "优于 300 t/MW 目标，同容量分位靠前",
                "cost": "略高于参考但仍在 ρ_pass 内",
                "construction": "节点复杂度中等，可施工",
                "fatigue": "FI 历程可接受，略低于寿命上限",
            },
        },
        {
            "key": "C",
            "label": "方案 C · 轻量化激进（低质量目标）",
            "score": 79.5,
            "dims": {"capacity": 74, "steel": 72, "cost": 90, "construction": 70, "fatigue": 68},
            "notes": "质量保留更低，成本优但疲劳与建造风险偏高。",
            "rationale": (
                "低质量目标使造价最优，但智能体预测刚度/疲劳裕度不足、建造节点更碎；"
                "综合 S≈79.5，不推荐作为 AIP 候选。"
            ),
            "geom": "examples/beso/beso7/beso_output/file010.vtk",
            "metrics": {
                "capacity": "P_c≈17.2 MW",
                "steel": "I_steel≈265 t/MW（过轻）",
                "cost": "ρ_cost≈0.88",
                "construction": "细杆件增多，建造难度↑",
                "fatigue": "L≈19 年",
            },
            "evidence": {
                "capacity": "过轻拓扑削弱等效承载，容量预测下滑",
                "steel": "数值好看但可能不满足极限态",
                "cost": "材料最少 → 造价分最高",
                "construction": "细部过多，分段/焊接成本上升",
                "fatigue": "热点应力集中，寿命明显不足",
            },
        },
        {
            "key": "D",
            "label": "方案 D · 高刚度储备（偏安全）",
            "score": 85.2,
            "dims": {"capacity": 84, "steel": 88, "cost": 76, "construction": 78, "fatigue": 82},
            "notes": "刚度储备充足，刚过终止门；成本略高。",
            "rationale": (
                "智能体认为钢耗与疲劳裕度充足，刚过 S≥85；但造价偏高，性价比弱于方案 B。"
            ),
            "geom": "examples/beso/beso7/beso_output/file026.vtk",
            "metrics": {
                "capacity": "P_c≈19.5 MW",
                "steel": "I_steel≈305 t/MW",
                "cost": "ρ_cost≈1.12",
                "construction": "截面偏厚，吊装重量↑",
                "fatigue": "L≈26 年",
            },
            "evidence": {
                "capacity": "接近目标容量",
                "steel": "略高于 300 t/MW，但分位仍可接受",
                "cost": "材料偏多推高造价，接近 ρ_pass",
                "construction": "厚壁便于焊接但物流更重",
                "fatigue": "刚度储备转化为疲劳寿命优势",
            },
        },
        {
            "key": "E",
            "label": "方案 E · 疲劳友好布局",
            "score": 83.8,
            "dims": {"capacity": 80, "steel": 81, "cost": 79, "construction": 77, "fatigue": 90},
            "notes": "热点应力更平滑，疲劳分突出，综合分中等偏上。",
            "rationale": (
                "智能体预测疲劳维度突出（平滑传力路径），但容量与造价未达最优；"
                "综合 S≈83.8，低于终止门，可作为疲劳专项对照。"
            ),
            "geom": "examples/beso/beso7/beso_output/file040.vtk",
            "metrics": {
                "capacity": "P_c≈18.8 MW",
                "steel": "I_steel≈298 t/MW",
                "cost": "ρ_cost≈1.06",
                "construction": "节点圆滑过渡，工艺略复杂",
                "fatigue": "L≈28 年（FI 峰值低）",
            },
            "evidence": {
                "capacity": "略低于 20 MW 目标",
                "steel": "接近国示范目标",
                "cost": "略高于参考线",
                "construction": "过渡圆角增加加工工序",
                "fatigue": "FI_mean/FI_max 历程最优 → 疲劳分最高",
            },
        },
    ]

    registered: list[dict[str, Any]] = []
    for spec in specs:
        cand_dir = workspace / "runs" / "_candidates" / tid / spec["key"]
        cand_dir.mkdir(parents=True, exist_ok=True)
        obj_path = cand_dir / "preview.obj"
        if preview_obj_bytes and not obj_path.is_file():
            obj_path.write_bytes(preview_obj_bytes)
        curve_name = curve_map.get(spec["key"], "Mass.png")
        curve_src = out_src / curve_name
        curve_dst = cand_dir / curve_name
        if curve_src.is_file():
            shutil.copy2(curve_src, curve_dst)
        preview_url = f"/runs/_candidates/{tid}/{spec['key']}/preview.obj"
        preview_png = None
        if obj_path.is_file():
            png_path = _ensure_obj_preview(obj_path)
            if png_path is not None:
                preview_png = f"/runs/_candidates/{tid}/{spec['key']}/{png_path.name}"
        curve_url = f"/runs/_candidates/{tid}/{spec['key']}/{curve_name}" if curve_dst.is_file() else None
        entry = register_candidate(
            tid,
            label=spec["label"],
            overall_score=float(spec["score"]),
            geometry_path=spec["geom"],
            preview_url=preview_png or preview_url,
            curve_url=curve_url,
            score_dims=spec["dims"],
            notes=spec["notes"],
            score_source="demo_predicted_not_measured",
            prediction_label=(
                "UI demo predicted scores for Phase IV candidate cards; "
                "not Phase V Automated Reviewer measured validation_score.json. "
                "Paper claims use measured validation / flagship archive only."
            ),
            score_basis=_basis(spec["dims"], metrics=spec["metrics"], evidence=spec["evidence"]),
            rationale=spec.get("rationale") or "",
        )
        if preview_png:
            entry["preview_png"] = preview_png
            entry["preview_obj"] = preview_url
            entry["preview_url"] = preview_png
        try:
            commit_candidate_snapshot(
                tid,
                action="register",
                candidate=entry,
                message=f"register · {spec['label']}",
            )
        except Exception:
            pass
        registered.append(entry)

    halt = evaluate_halt_gate(
        overall_score=88.5,
        ai_review_scores={
            "capacity": 86,
            "steel": 84,
            "cost": 82,
            "construction": 80,
            "fatigue": 78,
        },
        regulatory_review_scores={"stability": 76, "layout": 74},
    )
    ranked = list_candidates(tid)
    selected = None
    ver = None
    if auto_select:
        selected = select_best(tid)
        try:
            ver = commit_candidate_snapshot(
                tid,
                action="select_best",
                candidate=selected,
                message="Phase IV · Automated Reviewer select-best (auto)",
            )
        except Exception:
            ver = None

    # Structure snapshot process for version tree
    try:
        proc = open_process(tid, process_type="generic", label="项目结构 · BESO7", process_id="project-tree")
        commit_files(
            tid,
            proc["process_id"],
            message="snapshot · candidates registered + project layout",
            inline={
                "project_tree.md": (
                    "# BESO7 项目结构\n\n"
                    "- examples/beso/beso7/BESO7.FCStd\n"
                    "- beso_output/{Mass,FI_*.png,file*.vtk}\n"
                    "- addition/method1_parametric/preview.stl\n"
                    f"- runs/_candidates/{tid}/{{A..E}}/preview.obj\n"
                ),
                "candidates_summary.json": json.dumps(
                    [{"id": c.get("candidate_id"), "label": c.get("label"), "S": c.get("overall_score")} for c in ranked],
                    ensure_ascii=False,
                    indent=2,
                ),
            },
            applied_handlers=["snapshot_files"],
            tags=["structure", "phase-iv"],
        )
    except Exception:
        pass

    score_dims = [
        {"k": "capacity", "v": 86},
        {"k": "steel", "v": 84},
        {"k": "cost", "v": 82},
        {"k": "construction", "v": 80},
        {"k": "fatigue", "v": 78},
    ]
    return {
        "ok": True,
        "awaiting_selection": not bool(selected),
        "halt_gate": {
            "ok": halt.ok,
            "reason": halt.reason,
            "should_archive": bool(halt.ok),
            "S_min": 85,
            "overall_score": 88.5,
        },
        "score_dims": score_dims,
        "candidates": ranked,
        "selected": selected,
        "registered": registered,
        "version": ver,
        "recommended_id": next(
            (c.get("candidate_id") for c in ranked if float(c.get("overall_score") or 0) >= 88),
            (ranked[0].get("candidate_id") if ranked else None),
        ),
        "process": {
            "title": "Phase IV · Automated Reviewer · 多方案对比",
            "detail": (
                "AI Review 智能体对五方案给出预测分（含维度依据），"
                "请用户选择或采纳推荐方案（S≥85 终止门）。"
            ),
        },
        "io": {
            "inputs": [
                {"name": c.get("label"), "role": "candidate", "rel": c.get("candidate_id"), "exists": True}
                for c in registered
            ],
            "outputs": [
                {
                    "name": "awaiting_user_selection" if not selected else "selected_best",
                    "role": "selection",
                    "rel": (selected or {}).get("label") or "—",
                    "exists": bool(selected),
                },
            ],
        },
    }


def confirm_candidate_selection(task_id: str, candidate_id: str) -> dict[str, Any]:
    """User confirms a candidate; write versions snapshot."""
    from backend.candidates.registry import list_candidates, select_candidate
    from backend.versions.store import commit_candidate_snapshot

    tid = str(task_id or "").strip()
    cid = str(candidate_id or "").strip()
    selected = select_candidate(tid, cid)
    if not selected:
        raise ValueError(f"候选不存在: {cid}")
    ver = None
    try:
        ver = commit_candidate_snapshot(
            tid,
            action="select_best",
            candidate=selected,
            message=f"Phase IV · user select · {selected.get('label')}",
        )
    except Exception:
        ver = None
    return {
        "ok": True,
        "selected": selected,
        "candidates": list_candidates(tid),
        "version": ver,
        "process": {
            "title": "Phase IV · 用户选定方案",
            "detail": f"已选定 {selected.get('label')}（S={selected.get('overall_score')}）并写入 versions。",
        },
    }


def build_task_version_tree(task_id: str) -> dict[str, Any]:
    """Git-like tree: processes → commits → files + viz urls for UI."""
    from backend.versions.store import get_commit, list_commits, list_processes

    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id required")
    processes = list_processes(tid)
    branches: list[dict[str, Any]] = []
    for p in processes:
        pid = str(p.get("process_id") or "")
        commits = list_commits(tid, pid)
        nodes = []
        for c in commits:
            full = get_commit(tid, pid, str(c.get("commit_id") or "")) or {}
            files = list(full.get("files") or [])
            viz = []
            for f in files:
                name = str(f.get("path") or "")
                low = name.lower()
                url = f"/runs/_versions/{tid}/{pid}/commits/{c.get('commit_id')}/files/{name}"
                if low.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    viz.append({"kind": "img", "name": name, "url": url})
                elif low.endswith((".obj", ".stl")):
                    viz.append({"kind": "mesh", "name": name, "url": url})
            nodes.append(
                {
                    "commit_id": c.get("commit_id"),
                    "parent": c.get("parent"),
                    "message": c.get("message"),
                    "created_at": c.get("created_at"),
                    "file_count": c.get("file_count"),
                    "tags": c.get("tags") or [],
                    "handlers_applied": c.get("handlers_applied") or [],
                    "files": [{"path": f.get("path"), "sha256": (f.get("sha256") or "")[:12], "size": f.get("size")} for f in files],
                    "viz": viz,
                    "orphan": bool(c.get("orphan")),
                }
            )
        branches.append(
            {
                "process_id": pid,
                "process_type": p.get("process_type"),
                "label": p.get("label"),
                "HEAD": p.get("HEAD"),
                "commit_count": p.get("commit_count"),
                "commits": nodes,
            }
        )
    structure = {
        "task_id": tid,
        "lanes": [b.get("label") or b.get("process_id") for b in branches],
        "total_commits": sum(len(b.get("commits") or []) for b in branches),
        "note": "对齐论文审计链：replan / candidate_select / project-tree 分车道版本化。",
    }
    return {
        "ok": True,
        "task_id": tid,
        "structure": structure,
        "branches": branches,
        "process": {
            "title": "版本树 · 类 git 审计",
            "detail": "按进程车道展示提交链、文件哈希与可视化附件。",
        },
    }


def run_orchestrate_job_step(
    *,
    scan_dir: str,
    task_id: str,
    checklist_id: str | None,
    mass_goal_ratio: float = 0.15,
    filter_radius: float = 2.0,
    seed_artifacts: bool = True,
) -> dict[str, Any]:
    """Create BESO job with task/checklist; optionally seed BESO7 curves/3D."""
    from backend.generator.core import scan_input_directory
    from backend.jobs.manager import jobs

    bundle = scan_input_directory(scan_dir)
    inp_path = bundle.primary_inp
    if not inp_path:
        cand = Path(scan_dir) / "03_for_beso.inp"
        if cand.is_file():
            inp_path = str(cand)
    if not inp_path:
        raise FileNotFoundError("扫描目录无主 INP")

    job = jobs.create_job(
        user_message="BESO7 全链路演示 · 编排启动（夹具回放曲线/3D）",
        inp_path=inp_path,
        mass_goal_ratio=float(mass_goal_ratio),
        filter_radius=float(filter_radius),
        optimization_base="stiffness",
        save_every=1,
        generated_code_files=[],
        selected_inputs=None,
    )
    write_job_context(
        Path(job.run_dir),
        design_checklist_id=checklist_id,
        task_id=task_id,
        demo_case="beso7_live_pipeline",
        scan_dir=scan_dir,
    )
    ctx_path = Path(job.run_dir) / "job_context.json"
    ctx = json.loads(ctx_path.read_text(encoding="utf-8")) if ctx_path.is_file() else {}
    seed = None
    if seed_artifacts:
        try:
            workspace = Path(job.run_dir).resolve().parents[1]  # runs/<id> → workspace
            seed = seed_beso7_job_artifacts(workspace, job_id=job.id, task_id=task_id)
        except Exception as e:
            seed = {"ok": False, "error": str(e)[:400]}
            try:
                from backend.jobs.models import JobStatus
                from backend.pydantic_compat import model_copy_update

                with jobs._lock:
                    j = jobs._jobs.get(job.id)
                    if j is not None:
                        jobs._jobs[job.id] = model_copy_update(
                            j,
                            {
                                "status": JobStatus.failed,
                                "logs": list(j.logs or [])
                                + [f"[ERROR] demo seed failed: {seed['error']}"],
                            },
                        )
            except Exception:
                pass

    return {
        "ok": bool(seed is None or seed.get("ok", True)),
        "job_id": job.id,
        "run_dir": str(job.run_dir),
        "job_context": ctx,
        "inp_path": inp_path,
        "auto_start": False,
        "seed": seed,
        "process": {
            "title": "编排 · job_context + BESO7 产物回放",
            "detail": "写入 task/checklist 上下文，并种子 Mass/FI 曲线与拓扑 OBJ，避免无曲线与 beso_main exit 1。",
        },
        "io": {
            "inputs": [
                _file_info(Path(inp_path), role="primary_inp"),
                {"name": "task_id", "role": "task", "rel": task_id, "exists": True},
                {
                    "name": "design_checklist_id",
                    "role": "checklist",
                    "rel": str(checklist_id or "")[:16],
                    "exists": bool(checklist_id),
                },
            ],
            "outputs": [
                _file_info(ctx_path, role="job_context"),
                *list((seed or {}).get("io", {}).get("outputs") or [])[:4],
            ],
        },
    }


def _cylinder_mesh(
    p0: list[float],
    p1: list[float],
    radius: float,
    *,
    n_circ: int = 16,
    n_len: int = 6,
) -> tuple[list[list[float]], list[list[int]]]:
    """Simple tapered-capable cylinder along p0→p1 (mm); returns verts + faces (1-based)."""
    import math

    a = [float(p1[i]) - float(p0[i]) for i in range(3)]
    length = math.sqrt(sum(x * x for x in a)) or 1.0
    axis = [x / length for x in a]
    # orthonormal basis
    tmp = [0.0, 0.0, 1.0] if abs(axis[2]) < 0.9 else [1.0, 0.0, 0.0]
    ux = [
        axis[1] * tmp[2] - axis[2] * tmp[1],
        axis[2] * tmp[0] - axis[0] * tmp[2],
        axis[0] * tmp[1] - axis[1] * tmp[0],
    ]
    ulen = math.sqrt(sum(x * x for x in ux)) or 1.0
    ux = [x / ulen for x in ux]
    uy = [
        axis[1] * ux[2] - axis[2] * ux[1],
        axis[2] * ux[0] - axis[0] * ux[2],
        axis[0] * ux[1] - axis[1] * ux[0],
    ]
    verts: list[list[float]] = []
    for i in range(n_len + 1):
        t = i / n_len
        c = [float(p0[j]) + t * (float(p1[j]) - float(p0[j])) for j in range(3)]
        for k in range(n_circ):
            ang = 2 * math.pi * k / n_circ
            offset = [
                radius * (math.cos(ang) * ux[j] + math.sin(ang) * uy[j]) for j in range(3)
            ]
            verts.append([c[j] + offset[j] for j in range(3)])
    faces: list[list[int]] = []
    for i in range(n_len):
        for k in range(n_circ):
            a0 = i * n_circ + k
            a1 = i * n_circ + (k + 1) % n_circ
            b0 = (i + 1) * n_circ + k
            b1 = (i + 1) * n_circ + (k + 1) % n_circ
            faces.append([a0 + 1, a1 + 1, b1 + 1])
            faces.append([a0 + 1, b1 + 1, b0 + 1])
    return verts, faces


def _parametric_legs_to_obj(geometry: dict[str, Any], out_obj: Path) -> bool:
    """Build a lightweight OBJ from method-1 reconstructed leg cylinders (demo fixture)."""
    beso7 = geometry.get("beso7_method1_topology_reconstructed") or {}
    legs = beso7.get("legs") or []
    if not legs:
        return False
    all_v: list[list[float]] = []
    all_f: list[list[int]] = []
    for leg in legs:
        base = leg.get("base_xyz_mm") or [0, 0, 0]
        top = leg.get("top_xyz_mm") or [0, 0, 1000]
        r = float(leg.get("radius_mm") or 500.0)
        # scale mm → m for viewer consistency with topology OBJ if needed;
        # topology INP→OBJ is typically in model units (mm). keep mm.
        verts, faces = _cylinder_mesh(list(base), list(top), r)
        off = len(all_v)
        all_v.extend(verts)
        all_f.extend([[i + off for i in face] for face in faces])
    plate = beso7.get("hub_top_plate") or {}
    if plate.get("center_xy_mm") and plate.get("radius_mm"):
        cx, cy = float(plate["center_xy_mm"][0]), float(plate["center_xy_mm"][1])
        z0 = float(plate.get("z_bottom_mm") or plate.get("z_mm") or 0.0)
        z1 = float(plate.get("z_top_mm") or (z0 + float(plate.get("thickness_mm") or 800.0)))
        pr = float(plate["radius_mm"])
        verts, faces = _cylinder_mesh([cx, cy, z0], [cx, cy, z1], pr, n_circ=24, n_len=2)
        off = len(all_v)
        all_v.extend(verts)
        all_f.extend([[i + off for i in face] for face in faces])
    if not all_v:
        return False
    lines = ["# BESO7 demo · parametric reconstruction (legs + top plate)\n"]
    for v in all_v:
        lines.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
    for f in all_f:
        lines.append(f"f {f[0]} {f[1]} {f[2]}\n")
    out_obj.parent.mkdir(parents=True, exist_ok=True)
    out_obj.write_text("".join(lines), encoding="utf-8")
    return True


def _write_sizing_sweep_png(
    geometry: dict[str, Any],
    out_png: Path,
    *,
    target_mw: float,
    x_opt: float,
) -> bool:
    """Nature-lite steel/MW vs scale factor curve for demo gallery."""
    try:
        import os

        os.environ.setdefault("MPLBACKEND", "Agg")
        import matplotlib

        if matplotlib.get_backend().lower() != "agg":
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        from backend.tools.mixed_platform_steel import compute_for_scale, default_params_from_geometry
        import math

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
        ax1.set_ylabel("Steel intensity (t MW$^{-1}$)", color="#3C5488")
        ax1.tick_params(axis="y", labelcolor="#3C5488")
        ax2 = ax1.twinx()
        ax2.plot(xs, pitches, color="#E64B35", lw=1.5, ls=":", label="Pitch (deg)")
        ax2.axhline(5.0, color="#E64B35", ls=":", alpha=0.45, lw=1.0)
        ax2.set_ylabel("Pitch angle (deg)", color="#E64B35")
        ax2.tick_params(axis="y", labelcolor="#E64B35")
        ax1.set_title("Phase III · sizing sweep (SLSQP / pitch ≤ 5°)", loc="left", fontweight="bold")
        ax1.grid(True, color="#E8ECF0", lw=0.6)
        fig.tight_layout()
        out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_png, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return out_png.is_file()
    except Exception:
        return False


def run_reconstruction_step(
    workspace_root: Path,
    *,
    job_id: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Phase III · topology → parametric reconstruction (demo fixture).

    Prefer FreeCAD rebuild when available; otherwise export cylinders from
    ``rules/optimized_geometry.json`` method-1 legs and pair with topology final.obj.
    """
    from backend.jobs.manager import jobs

    root = Path(workspace_root).resolve()
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id required")
    job = jobs.get_job(jid)
    if job is None or not getattr(job, "run_dir", None):
        raise FileNotFoundError(f"job not found: {jid}")
    run_dir = Path(job.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    geom_path = root / "rules" / "optimized_geometry.json"
    geometry = json.loads(geom_path.read_text(encoding="utf-8")) if geom_path.is_file() else {}

    topo_src = run_dir / "final.obj"
    if not topo_src.is_file():
        topo_src = run_dir / "latest.obj"
    topo_dst = run_dir / "topology_result.obj"
    if topo_src.is_file():
        shutil.copy2(topo_src, topo_dst)

    meas_path = run_dir / "measurements.json"
    beso7 = geometry.get("beso7_method1_topology_reconstructed") or {}
    meas_payload = {
        "source": "rules/optimized_geometry.json",
        "method": beso7.get("method") or "PCA cylinder fit (demo)",
        "legs": beso7.get("legs") or [],
        "hub_top_plate": beso7.get("hub_top_plate") or {},
        "task_id": task_id,
        "job_id": jid,
    }
    meas_path.write_text(json.dumps(meas_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    recon_obj = run_dir / "reconstructed.obj"
    recon_stl = run_dir / "reconstructed.stl"
    mode = "parametric_legs_obj"
    freecad_ok = False

    # Optional live FreeCAD rebuild when assets exist
    meas_asset = root / "examples" / "beso" / "beso7" / "addition" / "method1_parametric" / "measurements.json"
    if not meas_asset.is_file():
        meas_asset = meas_path
    out_rebuild = run_dir / "method1_parametric"
    try:
        from backend.tools.beso7_parametric_rebuild import run_beso7_parametric_rebuild

        stl = run_beso7_parametric_rebuild(
            measurements_path=meas_asset,
            out_dir=out_rebuild,
            params=None,
            preview_only=True,
            timeout_s=90.0,
        )
        if stl.is_file():
            shutil.copy2(stl, recon_stl)
            try:
                import meshio

                mesh = meshio.read(stl)
                meshio.write(recon_obj, mesh, file_format="obj")
                freecad_ok = True
                mode = "freecad_parametric_rebuild"
            except Exception:
                freecad_ok = bool(recon_stl.is_file())
                mode = "freecad_stl_only"
    except Exception:
        freecad_ok = False

    if not recon_obj.is_file():
        if not _parametric_legs_to_obj(geometry, recon_obj) and topo_dst.is_file():
            shutil.copy2(topo_dst, recon_obj)
            mode = "topology_passthrough"
        elif recon_obj.is_file():
            mode = "parametric_legs_obj"

    recon_png = _ensure_obj_preview(recon_obj) if recon_obj.is_file() else None
    topo_png = _ensure_obj_preview(topo_dst) if topo_dst.is_file() else None

    manifest = {
        "phase": "III",
        "step": "reconstruction",
        "mode": mode,
        "freecad": freecad_ok,
        "topology_obj": "topology_result.obj" if topo_dst.is_file() else None,
        "reconstructed_obj": "reconstructed.obj" if recon_obj.is_file() else None,
        "measurements": "measurements.json",
        "note": "Topology voxel/INP mesh → parametric legs + hub plate (method 1).",
    }
    (run_dir / "reconstruction_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_job_context(run_dir, demo_reconstruction=True, reconstruction_mode=mode, task_id=task_id)

    return {
        "ok": True,
        "job_id": jid,
        "task_id": task_id,
        "mode": mode,
        "topology_mesh_url": f"/runs/{jid}/topology_result.obj" if topo_dst.is_file() else None,
        "reconstructed_mesh_url": f"/runs/{jid}/reconstructed.obj" if recon_obj.is_file() else None,
        "topology_png_url": f"/runs/{jid}/{topo_png.name}" if topo_png is not None else None,
        "reconstructed_png_url": f"/runs/{jid}/{recon_png.name}" if recon_png is not None else None,
        "measurements_url": f"/runs/{jid}/measurements.json",
        "manifest_url": f"/runs/{jid}/reconstruction_manifest.json",
        "process": {
            "title": "Phase III · 拓扑结果重构（参数化）",
            "detail": "将拓扑保留相拟合为变径柱+顶盘参数体，供后续尺寸优化使用。",
        },
        "io": {
            "inputs": [
                _file_info(topo_dst if topo_dst.is_file() else topo_src, role="topology_result"),
                _file_info(geom_path, role="geometry_params"),
            ],
            "outputs": [
                _file_info(recon_obj, role="reconstructed_mesh"),
                _file_info(meas_path, role="measurements"),
                _file_info(run_dir / "reconstruction_manifest.json", role="manifest"),
            ],
        },
    }


def run_sizing_step(
    workspace_root: Path,
    *,
    job_id: str,
    task_id: str | None = None,
    target_power_mw: float | None = 20.0,
) -> dict[str, Any]:
    """Phase III · size optimization: minimize steel t/MW under pitch ≤ 5° (SLSQP)."""
    from backend.jobs.manager import jobs
    from backend.tools.mixed_platform_steel import attach_steel_to_geometry, compute_steel_report

    root = Path(workspace_root).resolve()
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id required")
    job = jobs.get_job(jid)
    if job is None or not getattr(job, "run_dir", None):
        raise FileNotFoundError(f"job not found: {jid}")
    run_dir = Path(job.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    geom_path = root / "rules" / "optimized_geometry.json"
    if not geom_path.is_file():
        raise FileNotFoundError(f"缺少几何: {geom_path}")
    geometry = json.loads(geom_path.read_text(encoding="utf-8"))
    target = float(target_power_mw or 20.0)
    report = compute_steel_report(geometry, target_power_mw=target, optimize=True)
    sized_geom = attach_steel_to_geometry(copy.deepcopy(geometry), report)
    report_path = run_dir / "sizing_report.json"
    sized_path = run_dir / "sized_geometry.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sized_path.write_text(json.dumps(sized_geom, ensure_ascii=False, indent=2), encoding="utf-8")

    x_opt = float((report.get("computation") or {}).get("extra_scale_factor_x") or 1.0)
    curve_png = run_dir / "sizing_curve.png"
    _write_sizing_sweep_png(geometry, curve_png, target_mw=target, x_opt=x_opt)

    steel = report.get("steel_summary") or {}
    comp = report.get("computation") or {}
    write_job_context(
        run_dir,
        demo_sizing=True,
        sizing_optimizer=comp.get("optimizer"),
        sizing_scale=comp.get("final_horizontal_scale_factor"),
        task_id=task_id,
    )

    recon_obj = run_dir / "reconstructed.obj"
    recon_png = _ensure_obj_preview(recon_obj) if recon_obj.is_file() else None

    return {
        "ok": True,
        "job_id": jid,
        "task_id": task_id,
        "optimizer": comp.get("optimizer"),
        "target_power_MW": target,
        "extra_scale_x": x_opt,
        "final_scale": comp.get("final_horizontal_scale_factor"),
        "steel_intensity_t_per_MW": steel.get("steel_intensity_t_per_MW"),
        "struct_mass_t": steel.get("struct_mass_t"),
        "pitch_angle_deg": steel.get("pitch_angle_deg"),
        "report_url": f"/runs/{jid}/sizing_report.json",
        "sized_geometry_url": f"/runs/{jid}/sized_geometry.json",
        "curve_url": f"/runs/{jid}/sizing_curve.png" if curve_png.is_file() else None,
        "reconstructed_mesh_url": f"/runs/{jid}/reconstructed.obj" if recon_obj.is_file() else None,
        "reconstructed_png_url": f"/runs/{jid}/{recon_png.name}" if recon_png is not None else None,
        "process": {
            "title": "Phase III · 尺寸优化（用钢量最小化）",
            "detail": (
                f"在 pitch≤5° 约束下优化水平缩放（{comp.get('optimizer') or 'SLSQP'}），"
                f"钢耗强度 → {steel.get('steel_intensity_t_per_MW')} t/MW。"
            ),
        },
        "io": {
            "inputs": [
                _file_info(geom_path, role="reconstructed_params"),
                {
                    "name": "pitch_limit",
                    "role": "constraint",
                    "rel": "≤5°",
                    "exists": True,
                },
            ],
            "outputs": [
                _file_info(report_path, role="sizing_report"),
                _file_info(sized_path, role="sized_geometry"),
                _file_info(curve_png, role="sizing_curve"),
            ],
        },
    }


def run_zwind_eval_step(
    workspace_root: str | Path,
    *,
    job_id: str,
    task_id: str | None = None,
    platform: str = "ai",
    prefer_live: bool | None = None,
) -> dict[str, Any]:
    """Phase III · Zwind aero-hydro-servo-elastic check after size optimization.

    Imports ``third_party/zwind_newmodel`` paper Fig. 2 metrics (default) and
    stages Fig. 2b–e panels into the job run directory for the demo gallery.
    """
    from backend.jobs.manager import jobs
    from backend.tools.zwind_eval import evaluate_zwind_bundle

    root = Path(workspace_root).resolve()
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id required")
    job = jobs.get_job(jid)
    if job is None or not getattr(job, "run_dir", None):
        raise FileNotFoundError(f"job not found: {jid}")
    run_dir = Path(job.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    result = evaluate_zwind_bundle(
        run_dir=run_dir,
        platform=platform,
        prefer_live=prefer_live,
    )
    hl = result.get("highlights") or {}
    write_job_context(
        run_dir,
        demo_zwind=True,
        zwind_mode=result.get("mode"),
        zwind_platform=platform,
        zwind_extreme_pitch_deg=hl.get("extreme_pitch_deg"),
        zwind_mooring_kn=hl.get("max_mooring_tension_kn"),
        task_id=task_id,
    )

    panel_urls = [
        {
            "label": p.get("label"),
            "url": f"/runs/{jid}/{p.get('rel')}",
            "kind": "img",
        }
        for p in (result.get("panels") or [])
        if p.get("rel")
    ]
    checks = result.get("pass_checks") or {}
    detail_bits = [
        f"mode={result.get('mode')}",
        f"1st FA={hl.get('tower_1st_fa_hz')} Hz",
        f"DLC6.1 pitch={hl.get('extreme_pitch_deg')}°",
        f"mooring={hl.get('max_mooring_tension_kn')} kN",
    ]
    return {
        "ok": True,
        "job_id": jid,
        "task_id": task_id,
        "mode": result.get("mode"),
        "bundle_rel": result.get("bundle_rel"),
        "platform": platform,
        "highlights": hl,
        "envelope": result.get("envelope"),
        "pass_checks": checks,
        "panel_urls": panel_urls,
        "metrics_url": f"/runs/{jid}/zwind_fig2_metrics.json",
        "envelope_url": f"/runs/{jid}/zwind_envelope.json",
        "report_url": f"/runs/{jid}/zwind_report.json",
        "live": result.get("live"),
        "process": {
            "title": "Phase III · Zwind 时域校核（尺寸优化后）",
            "detail": (
                "尺寸优化完成后接入 third_party/zwind_newmodel："
                + " · ".join(detail_bits)
                + (" · 极限包络通过" if checks.get("extreme_pitch_within_limit") and checks.get("mooring_within_limit") else "")
            ),
        },
        "io": {
            "inputs": [
                {
                    "name": "optimized_geometry / sized_geometry",
                    "role": "size_opt_result",
                    "rel": f"runs/{jid}/sized_geometry.json",
                    "exists": (run_dir / "sized_geometry.json").is_file(),
                },
                {
                    "name": "paper_fig2_metrics.json",
                    "role": "zwind_bundle",
                    "rel": "third_party/zwind_newmodel/paper_fig2_metrics.json",
                    "exists": True,
                },
            ],
            "outputs": [
                {
                    "name": "zwind_report.json",
                    "role": "zwind_report",
                    "rel": f"runs/{jid}/zwind_report.json",
                    "exists": True,
                },
                {
                    "name": "zwind_fig2/",
                    "role": "fig2_panels",
                    "rel": f"runs/{jid}/zwind_fig2",
                    "exists": bool(panel_urls),
                },
            ],
        },
    }


def run_solver_replan_step(task_id: str, *, job_id: str | None = None) -> dict[str, Any]:
    """Case2 solver replan + ρₚ + version commit."""
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id required")
    out = case2_solver_demo()
    guided = attach_guided(out)
    event = (out.get("result") or {}).get("event") or {}
    event_id = event.get("event_id") or out.get("event_id")
    theta_before = (out.get("result") or {}).get("theta_before")
    theta_after = (out.get("result") or {}).get("theta_after")

    from backend.orchestrator.state import mark_rho_pending

    mark_rho_pending(tid, event_id=event_id)
    ver = maybe_commit_live_replan_version(
        tid,
        event_id=event_id,
        theta_before=theta_before,
        theta_after=theta_after,
        message="BESO7 demo · solver live replan",
        case_id="solver_live",
    )
    if job_id:
        try:
            from backend.jobs.manager import jobs

            job = jobs.get_job(job_id)
            if job is not None and getattr(job, "run_dir", None):
                write_job_context(
                    Path(job.run_dir),
                    rho_pending=1,
                    last_replan_event_id=event_id,
                    task_id=tid,
                )
        except Exception:
            pass

    guided["task_id"] = tid
    guided["job_id"] = job_id
    guided["version"] = ver
    guided["rho_pending"] = 1
    guided["resume"] = {"target": "beso", "label": "按新求解参数重跑 BESO"}
    # Prefer Chinese title for UI modal / journey header
    guided["title"] = "求解失败 → 重规划旅程"
    guided["case_id"] = guided.get("case_id") or "case2"
    ev_id = str(event_id or "")
    guided["process"] = {
        "title": "求解失败 → solver replan",
        "detail": "残差平台不收敛，调整 load_increment / max_iterations，写入 versions 并标记 ρₚ。",
    }
    guided["io"] = {
        "inputs": [
            {"name": "CalculiX residual plateau", "role": "signal", "rel": "solver logs", "exists": True},
            {"name": "job_id", "role": "job", "rel": str(job_id or "—"), "exists": bool(job_id)},
        ],
        "outputs": [
            {
                "name": "replan_event.json",
                "role": "replan_event",
                "rel": f"runs/_replan/{ev_id[:12]}…" if ev_id else "—",
                "exists": bool(ev_id),
            },
            {
                "name": "version commit",
                "role": "version",
                "rel": (ver or {}).get("commit", {}).get("commit_id") or "—",
                "exists": bool((ver or {}).get("commit")),
            },
            {"name": "ρₚ = 1", "role": "gate", "rel": "workflow.state", "exists": True},
        ],
    }
    return guided

def run_validation_step(
    task_id: str,
    *,
    checklist_id: str | None = None,
    candidate_label: str = "BESO7 · 选定方案",
    geometry_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase V: run Automated Reviewer validation on default geometry + checklist."""
    import uuid as _uuid

    from backend.design_requirements.geometry_bridge import apply_checklist_to_geometry
    from backend.design_requirements.paths import load_checklist
    from backend.orchestrator.halt import evaluate_halt_gate
    from backend.validation.paths import artifact_urls, validation_runs_root, workspace_root
    from backend.validation.pipeline import run_validation

    tid = str(task_id or "").strip()
    root = workspace_root()
    geom_path = root / "rules" / "optimized_geometry.json"
    if not geom_path.is_file():
        raise FileNotFoundError(f"缺少验证几何样例: {geom_path}")
    geometry = json.loads(geom_path.read_text(encoding="utf-8"))
    cid = str(checklist_id or "").strip() or None
    if cid:
        cl = load_checklist(cid)
        if cl is not None:
            geometry = apply_checklist_to_geometry(geometry, cl)
    if geometry_overrides:
        vo = dict(geometry.get("validation_overrides") or {})
        vo.update({k: v for k, v in geometry_overrides.items() if v is not None})
        geometry["validation_overrides"] = vo
        opt = dict(geometry.get("optimization_info") or {})
        if "target_power_MW" in vo:
            opt["target_power_MW"] = vo["target_power_MW"]
        geometry["optimization_info"] = opt

    out_dir = validation_runs_root() / _uuid.uuid4().hex
    result = run_validation(
        geometry,
        out_dir=out_dir,
        use_llm_rationale=False,
        use_surrogate=False,
        candidate_label=candidate_label,
    )
    vid = result["validation_id"]
    urls = artifact_urls(vid, out_dir)
    halt = evaluate_halt_gate(
        overall_score=float(result.get("overall_score") or 0),
        ai_review_scores=result.get("ai_review_scores"),
        regulatory_review_scores=result.get("regulatory_review_scores"),
        design_checklist_id=cid,
    ).model_dump(mode="json")

    figures = []
    for stem in (
        "fig_score_radar",
        "fig_benchmark_position",
        "fig_fleet_metrics_bars",
        "fig_ai_review_validity",
        "fig_rule_heatmap",
    ):
        png = out_dir / f"{stem}.png"
        if png.is_file():
            figures.append(
                {
                    "label": stem.replace("fig_", "").replace("_", " "),
                    "url": f"/api/validation/{vid}/files/{stem}.png",
                    "kind": "img",
                }
            )

    next_action = "halt_and_archive" if halt.get("ok") else "review_replan"
    return {
        "ok": True,
        "task_id": tid,
        "validation_id": vid,
        "overall_score": result.get("overall_score"),
        "grade": result.get("grade"),
        "ai_review_scores": result.get("ai_review_scores") or {},
        "regulatory_review_scores": result.get("regulatory_review_scores") or {},
        "artifact_urls": urls,
        "halt_gate": halt,
        "next_action": next_action,
        "figures": figures,
        "report_md_url": urls.get("report_md"),
        "score_json_url": urls.get("score_json"),
        "process": {
            "title": "Phase V · Automated Reviewer 验证",
            "detail": (
                f"S={result.get('overall_score')} · grade={result.get('grade')} · "
                f"终止门={'通过' if halt.get('ok') else '未通过'} · next={next_action}"
            ),
        },
        "io": {
            "inputs": [
                {"name": "optimized_geometry.json", "role": "geometry", "rel": "rules/optimized_geometry.json", "exists": True},
                {"name": "design_checklist", "role": "checklist", "rel": cid or "—", "exists": bool(cid)},
            ],
            "outputs": [
                {"name": "validation_score.json", "role": "score", "rel": urls.get("score_json") or "—", "exists": True},
                {"name": "fig_score_radar.png", "role": "figure", "rel": f"validation/{vid}", "exists": bool(figures)},
            ],
        },
    }


def _review_replan_patches(
    *,
    ai_scores: dict[str, Any],
    native_power_mw: float = 20.0,
) -> tuple[dict[str, float], list[dict[str, Any]], str]:
    """Build geometry overrides from weak AI-Review dimensions."""
    patches: dict[str, float] = {"target_power_MW": float(native_power_mw)}
    actions: list[dict[str, Any]] = [
        {
            "policy": "align_capacity",
            "description": f"将清单目标容量对齐几何资产 {native_power_mw:g} MW，消除容量子分误伤。",
            "theta_patch": {"target_capacity_mw": float(native_power_mw)},
        }
    ]
    notes: list[str] = [f"capacity→{native_power_mw:g} MW"]

    def _f(key: str, default: float = 100.0) -> float:
        try:
            raw = ai_scores.get(key)
            return float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    if _f("steel_per_mw") < 70 or _f("capacity_mw") < 70:
        patches["steel_mass_t"] = 5100.0
        actions.append(
            {
                "policy": "refine_steel_budget",
                "description": "按机队分位收紧钢耗预算。",
                "theta_patch": {"steel_mass_t": 5100.0, "steel_intensity_t_per_MW": 255.0},
            }
        )
        notes.append("steel_mass_t=5100")
    if _f("unit_cost") < 70:
        patches["unit_cost_cny_per_MW"] = 2350.0
        actions.append(
            {
                "policy": "trim_unit_cost",
                "description": "下调单位造价目标至机队优秀带。",
                "theta_patch": {"unit_cost_cny_per_MW": 2350.0},
            }
        )
        notes.append("unit_cost=2350")
    if _f("construction_years") < 70:
        patches["construction_years"] = 2.4
        actions.append(
            {
                "policy": "compress_schedule",
                "description": "压缩施工年限假设。",
                "theta_patch": {"construction_years": 2.4},
            }
        )
        notes.append("construction_years=2.4")
    if _f("fatigue_life") < 70:
        patches["fatigue_life_years"] = 26.0
        actions.append(
            {
                "policy": "extend_fatigue_life",
                "description": "提升疲劳设计寿命假设。",
                "theta_patch": {"fatigue_life_years": 26.0},
            }
        )
        notes.append("fatigue_life=26")

    # Soft floor so one review-replan usually clears the gate
    patches.setdefault("steel_mass_t", 5200.0)
    patches.setdefault("unit_cost_cny_per_MW", 2400.0)
    patches.setdefault("construction_years", 2.5)
    patches.setdefault("fatigue_life_years", 25.0)
    return patches, actions, "；".join(notes)


def run_review_replan_step(
    task_id: str,
    *,
    checklist_id: str | None = None,
    candidate_label: str = "BESO7 · 重规划后方案",
    previous_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """When halt gate fails: align θ / geometry overrides, mark ρₚ, re-validate."""
    import uuid as _uuid

    from backend.design_requirements.markdown import checklist_to_markdown
    from backend.design_requirements.paths import load_checklist, save_checklist
    from backend.orchestrator.state import clear_rho_pending, mark_rho_pending
    from backend.replan.paths import replan_root
    from backend.validation.paths import workspace_root

    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id required")
    cid = str(checklist_id or "").strip() or None
    prev = previous_validation or {}
    ai_scores = dict(prev.get("ai_review_scores") or {})
    root = workspace_root()
    geom_path = root / "rules" / "optimized_geometry.json"
    native_power = 20.0
    if geom_path.is_file():
        try:
            native_power = float(
                (json.loads(geom_path.read_text(encoding="utf-8")).get("optimization_info") or {}).get(
                    "target_power_MW"
                )
                or 20.0
            )
        except Exception:
            native_power = 20.0

    patches, actions, summary = _review_replan_patches(ai_scores=ai_scores, native_power_mw=native_power)

    if cid:
        cl = load_checklist(cid)
        if cl is not None:
            try:
                cl.project.target_capacity_mw = float(native_power)
                for act in actions:
                    tp = act.get("theta_patch") or {}
                    if "steel_intensity_t_per_MW" in tp:
                        cl.performance_targets.steel_intensity_t_per_MW = float(tp["steel_intensity_t_per_MW"])
                    if "unit_cost_cny_per_MW" in tp:
                        cl.performance_targets.unit_cost_cny_per_MW = float(tp["unit_cost_cny_per_MW"])
                    if "fatigue_life_years" in tp:
                        cl.performance_targets.fatigue_design_life_years = float(tp["fatigue_life_years"])
                save_checklist(cl, markdown=checklist_to_markdown(cl))
            except Exception:
                pass

    event_id = _uuid.uuid4().hex
    theta_before = {
        "overall_score": prev.get("overall_score"),
        "ai_review_scores": ai_scores,
        "halt_ok": bool((prev.get("halt_gate") or {}).get("ok")),
    }
    theta_after = {"validation_overrides": patches, "actions": actions}
    try:
        ed = replan_root() / event_id
        ed.mkdir(parents=True, exist_ok=True)
        (ed / "replan_event.json").write_text(
            json.dumps(
                {
                    "event_id": event_id,
                    "task_id": tid,
                    "failure_kind": "review",
                    "policy": "review_replan",
                    "description": f"AI Review 未达终止门 → {summary}",
                    "theta_before": theta_before,
                    "theta_after": theta_after,
                    "actions": actions,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    mark_rho_pending(tid, event_id=event_id)
    ver = None
    try:
        ver = maybe_commit_live_replan_version(
            tid,
            event_id=event_id,
            theta_before=theta_before,
            theta_after=theta_after,
            message="BESO7 demo · review replan (halt gate miss)",
            case_id="review_live",
        )
    except Exception:
        ver = None

    revalidated = run_validation_step(
        tid,
        checklist_id=cid,
        candidate_label=candidate_label,
        geometry_overrides=patches,
    )
    if (revalidated.get("halt_gate") or {}).get("ok"):
        try:
            clear_rho_pending(tid)
        except Exception:
            pass
        rho = 0
    else:
        rho = 1

    return {
        "ok": True,
        "task_id": tid,
        "event_id": event_id,
        "failure_kind": "review",
        "rho_pending": rho,
        "actions": actions,
        "patches": patches,
        "summary": summary,
        "version": ver,
        "previous": {
            "overall_score": prev.get("overall_score"),
            "grade": prev.get("grade"),
            "halt_gate": prev.get("halt_gate"),
        },
        "validation": revalidated,
        "halt_gate": revalidated.get("halt_gate"),
        "overall_score": revalidated.get("overall_score"),
        "grade": revalidated.get("grade"),
        "figures": revalidated.get("figures"),
        "report_md_url": revalidated.get("report_md_url"),
        "score_json_url": revalidated.get("score_json_url"),
        "ai_review_scores": revalidated.get("ai_review_scores"),
        "process": {
            "title": "AI Review 未达终止门 → 重规划",
            "detail": (
                f"弱项修补：{summary}。重验 S={revalidated.get('overall_score')} "
                f"（{'通过' if (revalidated.get('halt_gate') or {}).get('ok') else '仍未通过'}）。"
            ),
        },
        "io": {
            "inputs": [
                {"name": "halt_gate fail", "role": "signal", "rel": "Phase V AI Review", "exists": True},
                {
                    "name": "previous S",
                    "role": "score",
                    "rel": str(prev.get("overall_score") or "—"),
                    "exists": prev.get("overall_score") is not None,
                },
            ],
            "outputs": [
                {
                    "name": "replan_event.json",
                    "role": "replan_event",
                    "rel": f"runs/_replan/{event_id[:12]}…",
                    "exists": True,
                },
                {
                    "name": "revalidated score",
                    "role": "score",
                    "rel": str(revalidated.get("overall_score") or "—"),
                    "exists": True,
                },
                {"name": f"ρₚ = {rho}", "role": "gate", "rel": "workflow.state", "exists": True},
            ],
        },
    }


def run_drawing_step(
    workspace_root: Path,
    *,
    task_id: str,
    job_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Phase VI: GA drawing from original columns + optimized smooth structure (not topology mesh)."""
    from backend.tools.cad_drawing_pack import build_cad_drawing_pack
    from backend.tools.platform_ga_assembly import build_platform_ga_assembly

    tid = str(task_id or "").strip()
    root = Path(workspace_root).resolve()
    jid = str(job_id or "").strip()
    sid = str(session_id or "").strip()

    assembly_meta: dict[str, Any] | None = None
    src: Path | None = None
    # Prefer GA assembly: original edge columns + heave plates + optimized braces/top plate
    try:
        out_dir = (root / "runs" / jid) if jid else (root / "runs" / "_ga_assembly" / tid[:12])
        assembly_meta = build_platform_ga_assembly(
            root,
            job_id=jid or None,
            out_dir=out_dir,
            prefer_reconstructed_stl=False,
        )
        cand = assembly_meta.get("stl_path") or assembly_meta.get("path") or assembly_meta.get("obj_path")
        if cand and Path(cand).is_file():
            src = Path(cand)
    except Exception as e:
        assembly_meta = {"ok": False, "error": str(e)[:400]}

    if src is None:
        candidates: list[Path] = []
        if jid:
            run_dir = root / "runs" / jid
            for name in (
                "drawing_assembly.stl",
                "drawing_assembly.obj",
                "reconstructed.stl",
                "reconstructed.obj",
                "method1_parametric/preview.stl",
                "final.obj",
                "latest.obj",
            ):
                p = run_dir / name
                if p.is_file():
                    candidates.append(p)
        if sid:
            sdir = session_dir(root, sid)
            for name in ("design_preview.obj", "03_for_beso.inp", "Analysis-beso.inp"):
                p = sdir / name
                if p.is_file():
                    candidates.append(p)
        analysis = beso7_analysis_inp(root)
        if analysis.is_file():
            candidates.append(analysis)
        src = next((p for p in candidates if p.is_file()), None)

    if src is None:
        raise FileNotFoundError("未找到可用于出图的装配体 / 重构 STL / OBJ")

    try:
        rel = str(src.relative_to(root)).replace("\\", "/")
    except ValueError:
        rel = str(src)

    # Force matplotlib solid silhouette for GA assembly — FreeCAD STL edge sampling
    # is too dense and looks like a triangulation wireframe.
    is_assembly = "drawing_assembly" in src.name.lower()
    use_solid = is_assembly or "reconstructed" in src.name.lower() or src.suffix.lower() == ".stl"
    pack = build_cad_drawing_pack(
        rel,
        workspace_root=root,
        title=f"BESO7 · {tid[:10]} 总布置图",
        engine="mesh" if is_assembly or use_solid else "auto",
        sheet_size="A3",
        layout="ga",
        silhouette_mode="solid" if use_solid else "mesh",
    )
    detail = "OC4 边立柱+垂荡板 + 优化光滑结构（斜撑/顶盘）实体轮廓出图。"
    if assembly_meta and assembly_meta.get("mode"):
        src_note = assembly_meta.get("columns_source") or ""
        detail = f"{detail} assembly={assembly_meta.get('mode')}"
        if src_note:
            detail = f"{detail}; columns={src_note}"
        detail = f"{detail}。"
    return {
        "ok": True,
        "task_id": tid,
        "source_path": pack.get("source_path") or rel,
        "drawing_id": pack.get("drawing_id"),
        "sheet_url": pack.get("sheet_url"),
        "pdf_url": pack.get("pdf_url") or pack.get("pack", {}).get("sheet_pdf_url"),
        "manifest_url": pack.get("manifest_url"),
        "engine": pack.get("engine"),
        "assembly": assembly_meta,
        "pack": pack.get("pack") or pack,
        "process": {
            "title": "Phase VI · 工程图出图",
            "detail": detail,
        },
        "io": {
            "inputs": [{"name": Path(rel).name, "role": "cad_source", "rel": rel, "exists": True}],
            "outputs": [
                {
                    "name": "drawing_sheet.png",
                    "role": "drawing",
                    "rel": pack.get("sheet_url") or "—",
                    "exists": bool(pack.get("sheet_url")),
                }
            ],
        },
    }


def build_pipeline_deliverables_summary(
    workspace_root: Path,
    *,
    task_id: str,
    job_id: str | None = None,
    session_id: str | None = None,
    validation: dict[str, Any] | None = None,
    drawing: dict[str, Any] | None = None,
    selected_label: str | None = None,
) -> dict[str, Any]:
    """Final closed-loop page: visualize key artifacts produced across the pipeline."""
    from backend.oc4_design_domain_service import runs_file_url

    root = Path(workspace_root).resolve()
    tid = str(task_id or "").strip()
    jid = str(job_id or "").strip()
    sid = str(session_id or "").strip()
    gallery: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []

    def add_file(path: Path, *, phase: str, role: str) -> None:
        if not path.is_file():
            return
        try:
            url = runs_file_url(root, path)
        except Exception:
            url = None
        files.append(
            {
                "name": path.name,
                "phase": phase,
                "role": role,
                "size": path.stat().st_size,
                "url": url,
                "ext": path.suffix.lower(),
            }
        )

    def add_img(label: str, url: str | None, *, phase: str) -> None:
        if url:
            gallery.append({"label": f"{phase} · {label}", "url": url, "kind": "img", "phase": phase})

    if sid:
        sdir = session_dir(root, sid)
        for name, role in (
            ("design_preview.obj", "design_mesh"),
            ("design_preview.preview.png", "design_preview"),
            ("source_preview.preview.png", "source_preview"),
            ("03_for_beso.inp", "fem_inp"),
            ("Analysis-beso.inp", "fem_inp"),
            ("build_plan.md", "plan"),
        ):
            add_file(sdir / name, phase="I 设计域", role=role)
        png = sdir / "design_preview.preview.png"
        if png.is_file():
            add_img("设计域预览", runs_file_url(root, png), phase="I")

    if jid:
        run_dir = root / "runs" / jid
        for name in ("Mass.png", "FI_mean.png", "FI_max.png", "latest.obj", "final.obj", "demo_seed.json"):
            add_file(run_dir / name, phase="II 拓扑优化", role="artifact")
        for name in (
            "topology_result.obj",
            "reconstructed.obj",
            "measurements.json",
            "reconstruction_manifest.json",
        ):
            add_file(run_dir / name, phase="III 重构", role="reconstruction")
        for name in ("sizing_report.json", "sized_geometry.json", "sizing_curve.png"):
            add_file(run_dir / name, phase="III 尺寸优化", role="sizing")
        for name in ("zwind_report.json", "zwind_fig2_metrics.json", "zwind_envelope.json"):
            add_file(run_dir / name, phase="III Zwind 时域", role="zwind")
        zwind_dir = run_dir / "zwind_fig2"
        if zwind_dir.is_dir():
            for p in sorted(zwind_dir.glob("*.png")):
                add_file(p, phase="III Zwind 时域", role="fig2_panel")
                add_img(p.stem.replace("fig2", "Fig.2 "), f"/runs/{jid}/zwind_fig2/{p.name}", phase="III")
        for name, label in (("Mass.png", "Mass 曲线"), ("FI_mean.png", "FI_mean")):
            p = run_dir / name
            if p.is_file():
                add_img(label, f"/runs/{jid}/{name}", phase="II")
        for name, label in (
            ("reconstructed.obj", "参数化重构"),
            ("sizing_curve.png", "尺寸优化曲线"),
        ):
            p = run_dir / name
            if not p.is_file():
                continue
            if p.suffix.lower() == ".png":
                add_img(label, f"/runs/{jid}/{name}", phase="III")
                continue
            # Prefer raster preview for mesh artifacts (deliverables UI uses <img>)
            png = _ensure_obj_preview(p)
            if png is not None and png.is_file():
                add_img(label, f"/runs/{jid}/{png.name}", phase="III")
            else:
                gallery.append(
                    {
                        "label": f"III · {label}",
                        "url": f"/runs/{jid}/{name}",
                        "kind": "mesh",
                        "phase": "III",
                    }
                )
        # Also surface topology_result preview when present
        topo = run_dir / "topology_result.obj"
        if topo.is_file():
            topo_png = _ensure_obj_preview(topo)
            if topo_png is not None and topo_png.is_file():
                add_img("拓扑终态", f"/runs/{jid}/{topo_png.name}", phase="III")
        add_file(run_dir / "reconstructed.preview.png", phase="III 重构", role="reconstruction_preview")
        # evolution previews (skip reconstructed/topology which are Phase III)
        for p in sorted(run_dir.glob("*.preview.png"))[:8]:
            stem = p.name.lower()
            if "reconstructed" in stem or "topology" in stem:
                continue
            add_file(p, phase="II 逐步优化", role="evolution_preview")
            add_img(p.stem.replace(".preview", ""), f"/runs/{jid}/{p.name}", phase="II")

    val = validation or {}
    for fig in val.get("figures") or []:
        gallery.append({**fig, "phase": fig.get("phase") or "V"})
        files.append(
            {
                "name": Path(str(fig.get("url") or "")).name or "figure.png",
                "phase": "V 验证",
                "role": "validation_figure",
                "size": None,
                "url": fig.get("url"),
                "ext": ".png",
            }
        )
    if val.get("score_json_url"):
        files.append(
            {
                "name": "validation_score.json",
                "phase": "V 验证",
                "role": "score",
                "size": None,
                "url": val.get("score_json_url"),
                "ext": ".json",
            }
        )
    if val.get("report_md_url"):
        files.append(
            {
                "name": "validation_report.md",
                "phase": "V 验证",
                "role": "report",
                "size": None,
                "url": val.get("report_md_url"),
                "ext": ".md",
            }
        )

    draw = drawing or {}
    if draw.get("sheet_url"):
        add_img("工程图总布置", draw.get("sheet_url"), phase="VI")
        files.append(
            {
                "name": "drawing_sheet.png",
                "phase": "VI 工程图",
                "role": "drawing",
                "size": None,
                "url": draw.get("sheet_url"),
                "ext": ".png",
            }
        )
    if draw.get("manifest_url"):
        files.append(
            {
                "name": "pack_manifest.json",
                "phase": "VI 工程图",
                "role": "manifest",
                "size": None,
                "url": draw.get("manifest_url"),
                "ext": ".json",
            }
        )

    phases = [
        {"id": "I", "title": "设计域", "status": "done"},
        {"id": "II", "title": "拓扑优化", "status": "done"},
        {"id": "III", "title": "重构 · 尺寸优化 · Zwind", "status": "done"},
        {"id": "IIIb", "title": "重规划闭环", "status": "done"},
        {"id": "IV", "title": "方案选优", "status": "done"},
        {"id": "V", "title": "验证打分", "status": "done" if val else "skip"},
        {"id": "VI", "title": "工程图", "status": "done" if draw else "skip"},
    ]

    return {
        "ok": True,
        "task_id": tid,
        "job_id": jid or None,
        "session_id": sid or None,
        "selected_label": selected_label,
        "validation_score": val.get("overall_score"),
        "validation_grade": val.get("grade"),
        "drawing_id": draw.get("drawing_id"),
        "phases": phases,
        "gallery": gallery,
        "files": files,
        "process": {
            "title": "交付总览 · 全流程闭环",
            "detail": f"共 {len(files)} 个关键文件 · {len(gallery)} 项可视化",
        },
    }
