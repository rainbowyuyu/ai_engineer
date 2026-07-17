"""
OC4 设计域前置会话：目录布局、几何摘要、与 ``build_oc4_design_domain_iges`` 的封装。
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from backend.tools.files import resolve_file, StoredFile


def upload_cad_stem_from_upload_name(filename: str) -> str:
    """与 ``examples/beso/BESO3-Compound.iges`` 命名对齐：``{stem}-Compound.iges`` 的 stem 段。"""
    stem = Path(str(filename or "")).stem
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("._-")
    return (stem or "OC4Design")[:48]


def _require_oc4_design_domain_dependencies() -> None:
    """设计域构建依赖 Gmsh 与 networkx；未安装时提示与 ``backend/requirements.txt`` 一致的安装方式。"""
    missing: list[str] = []
    try:
        import gmsh  # noqa: F401
    except ImportError:
        missing.append("gmsh")
    try:
        import networkx  # noqa: F401
    except ImportError:
        missing.append("networkx")
    if not missing:
        return
    pkgs = " ".join(missing)
    raise RuntimeError(
        "缺少 Python 依赖："
        + ", ".join(missing)
        + "。请在启动后端的同一虚拟环境中执行：\n"
        f"  pip install {pkgs}\n"
        "或： pip install -r backend/requirements.txt\n"
        "（Windows 示例： .\\.venv_web\\Scripts\\python -m pip install -r .\\backend\\requirements.txt）"
    )


def design_domain_root(workspace_root: Path) -> Path:
    return (workspace_root / "runs" / "_design_domain").resolve()


def session_dir(workspace_root: Path, session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum())[:64]
    return (design_domain_root(workspace_root) / safe).resolve()


def source_cad_path(session: Path) -> Path:
    for name in ("00_source.igs", "00_source.iges", "00_source.stp", "00_source.step"):
        p = session / name
        if p.is_file():
            return p
    raise FileNotFoundError("会话中未找到 00_source.*")


def write_session_meta(session: Path, data: dict[str, Any]) -> None:
    session.mkdir(parents=True, exist_ok=True)
    (session / "session.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_session_meta(session: Path) -> dict[str, Any]:
    p = session / "session.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def merge_session_meta(session: Path, patch: dict[str, Any]) -> dict[str, Any]:
    cur = read_session_meta(session)
    cur.update(patch)
    write_session_meta(session, cur)
    return cur


def runs_file_url(workspace_root: Path, file_abs: Path) -> str:
    """与 ``app.mount("/runs", RUNS_ROOT)`` 一致：路径为 ``/runs/<相对 RUNS_ROOT 的路径>``，避免 ``/runs/runs/...`` 重复。"""
    rr = (workspace_root / "runs").resolve()
    rel = file_abs.resolve().relative_to(rr)
    return "/runs/" + str(rel).replace("\\", "/")


def session_progress_flags(sdir: Path) -> dict[str, bool]:
    """会话目录内关键产物是否存在（供前端分步引导与按钮禁用）。"""
    meta = read_session_meta(sdir)
    cnm = str(meta.get("design_domain_compound_iges") or "").strip()
    has_compound = bool(cnm) and (sdir / cnm).is_file()
    return {
        "has_source_preview_obj": (sdir / "source_preview.obj").is_file(),
        "has_design_domain_step": (sdir / "01_design_domain.step").is_file(),
        "has_design_domain_compound_iges": has_compound,
        "has_design_preview_obj": (sdir / "design_preview.obj").is_file(),
        "has_mesh_body_inp": (sdir / "02_mesh_body.inp").is_file(),
        "has_for_beso_inp": (sdir / "03_for_beso.inp").is_file(),
        "design_domain_full_build_done": bool(meta.get("design_domain_full_build_done")),
        "has_build_plan_md": (sdir / "build_plan.md").is_file(),
        "has_build_history_md": (sdir / "build_history.md").is_file(),
    }


def _unlink_if_file(p: Path) -> bool:
    try:
        if p.is_file():
            p.unlink()
            return True
    except OSError:
        pass
    return False


def invalidate_oc4_downstream_from_rail_step(sdir: Path, *, rail_step: int) -> dict[str, Any]:
    """
    用户在步骤条上回溯到 rail_step（1～4）时，删除该步**之后**流水线的产物，
    并清理 ``session.json`` 中相关字段，使后续步骤必须重新执行。

    - 点到 1：清除步骤 2～4（设计域 STEP/IGES、OBJ、体网格 INP、BESO INP 等）
    - 点到 2：清除步骤 3～4
    - 点到 3：清除步骤 4
    - 点到 4：不删除文件
    """
    if rail_step < 1 or rail_step > 4:
        raise ValueError("rail_step 必须在 1～4 之间")
    removed: list[str] = []

    def rm(path: Path) -> None:
        if _unlink_if_file(path):
            removed.append(path.name)

    if rail_step <= 3:
        rm(sdir / "03_for_beso.inp")
        rm(sdir / "03_for_beso.log")
        rm(sdir / "beso_conf.py")
        for p in sorted(sdir.glob("03_for_beso.*")):
            rm(p)

    if rail_step <= 2:
        for pat in ("02_mesh_body.inp", "02_mesh_body.log", "_fc.json"):
            rm(sdir / pat)
        for p in sorted(sdir.glob("02_mesh_body.*")):
            rm(p)

    if rail_step <= 1:
        for pat in (
            "01_design_domain.igs",
            "01_design_domain.step",
            "design_preview.obj",
            "01b_design_domain_volume.msh",
            "build_plan.md",
            "build_history.md",
            "agent_build_plan.json",
        ):
            rm(sdir / pat)
        for p in sorted(sdir.glob("01_design_domain.*")):
            rm(p)
        for p in sorted(sdir.glob("*-Compound.iges")):
            rm(p)

    patch: dict[str, Any] = {}
    if rail_step <= 3:
        patch.update(
            {
                "final_inp": None,
                "partition_stats": None,
                "last_load_case": None,
                "last_nl_load_reply": None,
                "scan_dir": None,
                "finalized": False,
                "design_domain_full_build_done": False,
            }
        )
    if rail_step <= 2:
        patch.update(
            {
                "mesh_inp": None,
                "mesh_char_length_max_used": None,
                "mesh_inp_size_bytes": None,
                "mesh_inp_size_warning": None,
            }
        )
    if rail_step <= 1:
        patch.update(
            {
                "build_ok": False,
                "design_domain_iges": None,
                "design_domain_step": None,
                "design_domain_compound_iges": None,
                "design_obj_url": None,
                "design_domain_full_build_done": False,
            }
        )
    if patch:
        merge_session_meta(sdir, patch)
    return {"rail_step": rail_step, "removed": removed, **session_progress_flags(sdir)}


def create_session_from_upload(workspace_root: Path, file_id: str) -> tuple[str, Path, StoredFile]:
    sf = resolve_file(workspace_root, file_id)
    ext = sf.ext.lower()
    if ext not in {".igs", ".iges"}:
        raise ValueError("OC4 设计域前置仅支持上传 .igs / .iges")
    design_domain_root(workspace_root).mkdir(parents=True, exist_ok=True)
    sid = uuid.uuid4().hex
    sdir = session_dir(workspace_root, sid)
    sdir.mkdir(parents=True, exist_ok=False)
    name = "00_source.igs" if ext == ".igs" else "00_source.iges"
    dest = sdir / name
    shutil.copy2(sf.path, dest)
    meta = {
        "session_id": sid,
        "file_id": file_id,
        "source_name": name,
        "upload_cad_stem": upload_cad_stem_from_upload_name(sf.name),
        "workspace_relative": str(sdir.relative_to(workspace_root.resolve())).replace("\\", "/"),
    }
    write_session_meta(sdir, meta)
    return sid, sdir, sf


def _geometry_summary_worker(src_resolved_str: str) -> dict[str, Any]:
    """在 spawn 子进程内执行（Gmsh 信号限制）；参数为 resolve 后的路径字符串。"""
    src = Path(src_resolved_str)
    out: dict[str, Any] = {
        "path": str(src),
        "name": src.name,
        "size_bytes": src.stat().st_size if src.is_file() else 0,
        "beam_segments": None,
        "revolution_cylinders": None,
        "errors": [],
    }
    try:
        from backend.tools.iges_beam_to_inp import _extract_beam_segments_from_iges  # type: ignore

        segs = _extract_beam_segments_from_iges(src)
        out["beam_segments"] = len(segs) if segs is not None else 0
    except Exception as e:
        out["errors"].append(f"beam_segments: {e}")
    try:
        from backend.tools.oc4_design_domain_iges import _extract_revolution_cylinders, _merge_parallel_axis_pairs

        cyls = _extract_revolution_cylinders(src)
        vertical = [c for c in cyls if abs(float(c.direction[2])) > 0.96]
        vertical = _merge_parallel_axis_pairs(vertical)
        out["revolution_cylinders"] = len(vertical)
    except Exception as e:
        out["errors"].append(f"cylinders: {e}")
    return out


def geometry_summary(src: Path) -> dict[str, Any]:
    from backend.gmsh_spawn import run_in_spawn_process

    return run_in_spawn_process(_geometry_summary_worker, str(src.resolve()))


def _run_build_worker(
    sdir_resolved_str: str,
    cut_center_column: bool,
    include_source_geometry: bool,
) -> dict[str, Any]:
    """在 spawn 子进程内执行设计域构建。"""
    sdir = Path(sdir_resolved_str)
    _require_oc4_design_domain_dependencies()
    src = source_cad_path(sdir)
    out_iges = sdir / "01_design_domain.igs"
    out_step = sdir / "01_design_domain.step"
    from backend.tools.oc4_design_domain_iges import build_oc4_design_domain_iges

    build_oc4_design_domain_iges(
        src,
        out_iges,
        out_step=out_step,
        cut_center_column=cut_center_column,
        include_source_geometry=include_source_geometry,
    )
    meta0 = read_session_meta(sdir)
    stem = str(meta0.get("upload_cad_stem") or "OC4Design").strip() or "OC4Design"
    compound_nm = f"{stem}-Compound.iges"
    compound_path = sdir / compound_nm
    try:
        for old in sdir.glob("*-Compound.iges"):
            try:
                if old.resolve() != compound_path.resolve():
                    old.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass
    shutil.copy2(out_iges, compound_path)
    merge_session_meta(
        sdir,
        {
            "design_domain_iges": "01_design_domain.igs",
            "design_domain_step": "01_design_domain.step",
            "design_domain_compound_iges": compound_nm,
            "build_ok": True,
            "cut_center_column": cut_center_column,
            "include_source_geometry": include_source_geometry,
        },
    )
    return {
        "design_domain_iges": str(out_iges),
        "design_domain_step": str(out_step),
        "design_domain_compound_iges": str(compound_path),
    }


def run_build(sdir: Path, *, cut_center_column: bool = True, include_source_geometry: bool = False) -> dict[str, Any]:
    from backend.gmsh_spawn import run_in_spawn_process

    return run_in_spawn_process(
        _run_build_worker,
        str(sdir.resolve()),
        cut_center_column,
        include_source_geometry,
    )


def run_export_source_preview_only(
    sdir: Path,
    workspace_root: Path,
    *,
    linear_source: float = 1200.0,
) -> dict[str, str]:
    """仅源几何：IGES→STEP（若需）→OBJ，不依赖设计域 STEP。"""
    from backend.tools.freecad_export_obj import run_freecad_export_obj
    from backend.tools.freecad_export_step import run_freecad_export_step

    src = source_cad_path(sdir)
    src_step = sdir / "00_source.step"
    try:
        need_step = (not src_step.is_file()) or (src_step.stat().st_mtime < src.stat().st_mtime)
        if need_step:
            run_freecad_export_step(src, src_step)
    except Exception:
        src_step = src
    src_obj = sdir / "source_preview.obj"
    try:
        run_freecad_export_obj(src_step, src_obj, linear_deflection=linear_source)
    except Exception:
        run_freecad_export_obj(src, src_obj, linear_deflection=linear_source)
    u = runs_file_url(workspace_root, src_obj)
    patch: dict[str, Any] = {"source_obj_url": u}
    if (sdir / "00_source.step").is_file():
        patch["source_step"] = "00_source.step"
    merge_session_meta(sdir, patch)
    return {"source_obj": u}


def run_export_design_preview_only(
    sdir: Path,
    workspace_root: Path,
    *,
    linear_design: float = 800.0,
) -> dict[str, str]:
    """仅设计域：由 ``01_design_domain.step`` 导出 OBJ。"""
    from backend.tools.freecad_export_obj import run_freecad_export_obj

    step = sdir / "01_design_domain.step"
    if not step.is_file():
        raise FileNotFoundError("请先执行设计域构建（缺少 01_design_domain.step）")
    design_obj = sdir / "design_preview.obj"
    run_freecad_export_obj(step, design_obj, linear_deflection=linear_design)
    u = runs_file_url(workspace_root, design_obj)
    merge_session_meta(sdir, {"design_obj_url": u})
    return {"design_obj": u}


def run_export_obj(
    sdir: Path,
    workspace_root: Path,
    *,
    linear_source: float = 1200.0,
    linear_design: float = 800.0,
    design_only: bool = False,
) -> dict[str, str]:
    """导出 OBJ 预览。``design_only=True`` 时仅更新设计域 OBJ（左侧源预览保持不变）。"""
    if design_only:
        return run_export_design_preview_only(sdir, workspace_root, linear_design=linear_design)
    src_urls = run_export_source_preview_only(sdir, workspace_root, linear_source=linear_source)
    des_urls = run_export_design_preview_only(sdir, workspace_root, linear_design=linear_design)
    return {**src_urls, **des_urls}


def run_mesh(
    sdir: Path,
    *,
    char_length_max: float | None = None,
    char_length_min: float | None = None,
    element_order: str | None = None,
    mesh_size_from_curvature: int | None = None,
    compound_part_strategy: str | None = None,
    element_dimension: str | None = None,
    geometry_tolerance: float | None = None,
    optimize_std: bool | None = None,
    length_unit: str | None = None,
    timeout_s: float | None = None,
    max_replan_retries: int | None = None,
) -> dict[str, Any]:
    from backend.tools.cad_iges_to_inp import run_cad_iges_to_inp

    try:
        from backend.tools.cad_iges_to_inp import default_coarse_char_length_max
    except ImportError:  # 兼容旧部署未更新门面模块 re-export 的情况
        from backend.tools.freecad_iges_to_inp import default_coarse_char_length_max

    step = sdir / "01_design_domain.step"
    if not step.is_file():
        raise FileNotFoundError("缺少 01_design_domain.step")
    mesh_inp = sdir / "02_mesh_body.inp"
    cl_max = float(char_length_max) if char_length_max is not None else float(default_coarse_char_length_max(step))

    from backend.replan.thresholds import load_thresholds

    retry_cfg = load_thresholds().get("retry") or {}
    retries_left = int(max_replan_retries if max_replan_retries is not None else retry_cfg.get("max_retries", 3))
    replan_events: list[str] = []
    last_err: Exception | None = None

    while True:
        kw: dict[str, Any] = {"char_length_max": cl_max, "timeout_s": timeout_s}
        if char_length_min is not None:
            kw["char_length_min"] = float(char_length_min)
        if element_order is not None:
            kw["element_order"] = str(element_order)
        if mesh_size_from_curvature is not None:
            kw["mesh_size_from_curvature"] = int(mesh_size_from_curvature)
        if compound_part_strategy is not None:
            kw["compound_part_strategy"] = str(compound_part_strategy)
        if element_dimension is not None:
            kw["element_dimension"] = str(element_dimension)
        if geometry_tolerance is not None:
            kw["geometry_tolerance"] = float(geometry_tolerance)
        if optimize_std is not None:
            kw["optimize_std"] = bool(optimize_std)
        if length_unit is not None:
            kw["length_unit"] = str(length_unit)
        try:
            run_cad_iges_to_inp(step, mesh_inp, **kw)
            last_err = None
            break
        except Exception as e:
            last_err = e
            err_text = str(e)
            from backend.replan.engine import evaluate_feedback, replan as replan_theta

            fb = evaluate_feedback(phase="II", step="mesh", logs=err_text)
            if fb.rho_p != 1 or fb.failure_kind != "mesh" or retries_left <= 0:
                raise
            result = replan_theta(
                {"characteristic_length_max": cl_max, "element_size_m": cl_max},
                fb,
                case_id="mesh_live",
                persist=True,
            )
            new_cl = result.theta_after.get("characteristic_length_max")
            if new_cl is None or float(new_cl) >= float(cl_max):
                # Ensure we refine (smaller element size)
                new_cl = max(0.5, float(cl_max) * 0.72)
            cl_max = float(new_cl)
            if result.event:
                replan_events.append(result.event.event_id)
                merge_session_meta(
                    sdir,
                    {
                        "last_replan_event_id": result.event.event_id,
                        "mesh_replan_char_length_max": cl_max,
                    },
                )
            retries_left -= 1

    if last_err is not None:
        raise last_err

    mesh_inp = mesh_inp.resolve()
    size_b = mesh_inp.stat().st_size if mesh_inp.is_file() else 0
    meta_mesh: dict[str, Any] = {
        "mesh_inp": "02_mesh_body.inp",
        "mesh_char_length_max_used": cl_max,
        "mesh_inp_size_bytes": int(size_b),
    }
    if replan_events:
        meta_mesh["mesh_replan_event_ids"] = replan_events
        meta_mesh["last_replan_event_id"] = replan_events[-1]
    ten_mb = 10 * 1024 * 1024
    if size_b > ten_mb:
        meta_mesh["mesh_inp_size_warning"] = (
            f"02_mesh_body.inp 约 {size_b / (1024 * 1024):.1f} MB，超过 10MB 目标；"
            "可在「体网格」步骤 AI 中要求更粗（增大 characteristic_length_max）后重试。"
        )
    else:
        meta_mesh["mesh_inp_size_warning"] = None
    merge_session_meta(sdir, meta_mesh)
    out: dict[str, Any] = {"mesh_inp": str(mesh_inp), "mesh_inp_size_bytes": int(size_b), "mesh_char_length_max_used": cl_max}
    if size_b > ten_mb:
        out["mesh_inp_size_warning"] = meta_mesh["mesh_inp_size_warning"]
    if replan_events:
        out["replan_event_ids"] = replan_events
        out["last_replan_event_id"] = replan_events[-1]
        try:
            from backend.replan.guided import attach_guided
            from backend.replan.paths import load_event

            ev = load_event(replan_events[-1])
            if ev is not None:
                guided = attach_guided(
                    {
                        "case_id": "case1",
                        "title": "体网格失败 · 自治重规划并重试",
                        "feedback_before": {
                            "rho_p": 1,
                            "failure_kind": "mesh",
                            "signals": ev.signals_before.model_dump(mode="json"),
                        },
                        "feedback_after": {"rho_p": 0},
                        "result": {
                            "actions": [a.model_dump(mode="json") for a in ev.actions],
                            "theta_before": ev.theta_before,
                            "theta_after": ev.theta_after,
                            "event": ev.model_dump(mode="json"),
                        },
                        "outcome": {
                            "status": "success",
                            "note": f"已用更新后的特征尺寸 {cl_max} 重新划分网格并成功。",
                            "mesh_char_length_max_used": cl_max,
                        },
                        "ok": True,
                    }
                )
                out["replan_guided"] = guided
        except Exception:
            pass
    return out


def run_loads(
    sdir: Path,
    *,
    band_scale: float = 1.22,
    z_fix_band: float = 800.0,
    cload_mag: float = -5.0e6,
    load_case: dict[str, Any] | None = None,
    loads_natural_language: str | None = None,
    design_checklist_id: str | None = None,
) -> dict[str, Any]:
    from backend.tools.inp_oc4_design_nondesign import partition_oc4_mesh_inp
    from backend.tools.oc4_nl_loads import parse_loads_natural_language

    mesh = sdir / "02_mesh_body.inp"
    src = source_cad_path(sdir)
    out_inp = sdir / "03_for_beso.inp"
    if not mesh.is_file():
        raise FileNotFoundError("缺少 02_mesh_body.inp，请先执行网格")

    # band_scale / z_fix_band / cload_mag 由调用方解析（含 design_checklist 默认）
    merged: dict[str, Any] = {
        "band_scale": float(band_scale),
        "z_fix_band": float(z_fix_band),
        "cload_mag": float(cload_mag),
    }
    merged.update(load_case or {})
    nl_reply: str | None = None
    if (loads_natural_language or "").strip():
        nl_reply, lc_nl = parse_loads_natural_language(
            mesh,
            loads_natural_language.strip(),
            band_scale=float(merged["band_scale"]),
            z_fix_band=float(merged["z_fix_band"]),
            cload_mag=float(merged.get("cload_mag", cload_mag)),
        )
        merged.update(lc_nl)

    stats = partition_oc4_mesh_inp(
        mesh,
        src,
        out_inp,
        band_scale=float(merged["band_scale"]),
        z_fix_band=float(merged["z_fix_band"]),
        cload_mag=float(merged.get("cload_mag", cload_mag)),
        load_case=merged,
    )
    meta_patch: dict[str, Any] = {
        "final_inp": "03_for_beso.inp",
        "partition_stats": stats,
        "last_load_case": merged,
        "last_nl_load_reply": nl_reply,
    }
    if design_checklist_id:
        meta_patch["design_checklist_id"] = design_checklist_id
    merge_session_meta(sdir, meta_patch)
    out: dict[str, Any] = {
        "stats": stats,
        "final_inp": str(out_inp),
        "resolved_load_case": merged,
        "validation_warnings": list(stats.get("validation_warnings") or []),
    }
    if nl_reply:
        out["nl_reply"] = nl_reply
    return out


__all__ = [
    "create_session_from_upload",
    "design_domain_root",
    "geometry_summary",
    "invalidate_oc4_downstream_from_rail_step",
    "merge_session_meta",
    "read_session_meta",
    "run_build",
    "run_export_design_preview_only",
    "run_export_obj",
    "run_export_source_preview_only",
    "run_loads",
    "run_mesh",
    "runs_file_url",
    "session_dir",
    "session_progress_flags",
    "source_cad_path",
    "write_session_meta",
]
