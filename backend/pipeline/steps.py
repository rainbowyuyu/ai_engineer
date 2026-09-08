"""Shared live pipeline steps used by assistant tools and MasterGraph."""
from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from backend.pipeline.execution_mode import (
    assert_live_or_raise,
    probe_solvers,
    resolve_execution_mode,
)
from backend.presets.turbine_presets import (
    apply_preset_to_checklist,
    get_preset,
    list_presets,
    nearest_preset_id,
    preset_session_meta_patch,
)

logger = logging.getLogger(__name__)


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()


def step_probe_execution(*, requested_mode: str | None = None) -> dict[str, Any]:
    mode, probe = resolve_execution_mode(requested_mode)
    return {
        "ok": True,
        "execution_mode": mode,
        "preview": mode == "preview",
        "solvers": probe.to_dict(),
        "presets": [p.to_dict() for p in list_presets()],
    }


def step_set_execution_mode(mode: str) -> dict[str, Any]:
    m = str(mode or "").strip().lower()
    if m not in ("live", "preview"):
        raise ValueError("mode must be live|preview")
    os.environ["BESO_EXECUTION_MODE"] = m
    return step_probe_execution(requested_mode=m)


def step_apply_turbine_preset(
    *,
    preset_id: str | float | int,
    checklist_id: str | None = None,
    session_id: str | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    """Apply 5/10/15/20 MW preset to checklist (+ optional OC4 session meta)."""
    from backend.design_requirements.models import DesignChecklist
    from backend.design_requirements.nl_parser import parse_design_checklist
    from backend.design_requirements.paths import load_checklist, save_checklist
    from backend.oc4_design_domain_service import merge_session_meta, session_dir

    preset = get_preset(preset_id)
    root = workspace_root()
    cl: DesignChecklist | None = None
    cid = str(checklist_id or "").strip()
    if cid:
        cl = load_checklist(cid)
    if cl is None and source_text:
        cl = parse_design_checklist(source_text)
        cid = cl.meta.checklist_id
    if cl is None:
        # minimal checklist seeded from preset
        text = (
            source_text
            or f"设计一台 {preset.target_power_mw:g} MW 半潜式漂浮风机基础，OC4 族平台，目标钢耗约 {preset.steel_intensity_t_per_mw:g} t/MW。"
        )
        cl = parse_design_checklist(text)
        cid = cl.meta.checklist_id
    apply_preset_to_checklist(cl, preset)
    from backend.design_requirements.markdown import checklist_to_markdown

    save_checklist(cl, markdown=checklist_to_markdown(cl))

    sid = str(session_id or "").strip()
    session_patch: dict[str, Any] = {}
    if sid:
        sdir = session_dir(root, sid)
        if sdir.is_dir():
            session_patch = merge_session_meta(sdir, preset_session_meta_patch(preset))
            merge_session_meta(sdir, {"design_checklist_id": cid})

    return {
        "ok": True,
        "checklist_id": cid,
        "preset": preset.to_dict(),
        "session_id": sid or None,
        "session_meta": session_patch or None,
        "client_hint": {"type": "refresh_design_checklist", "checklist_id": cid},
    }


def _default_oc4_iges(root: Path) -> Path | None:
    """仓库内置 OC4 参考几何（用户未上传时用于 10MW 等对话真跑）。"""
    for rel in (
        "beso/wiki_files/nake_oc4/oc4.igs",
        "beso/wiki_files/nake_oc4/oc4.iges",
        "examples/oc4/oc4.igs",
        "examples/oc4/oc4.iges",
    ):
        p = (root / rel).resolve()
        if p.is_file():
            return p
    return None


def step_start_design_domain_session(
    *,
    file_id: str | None = None,
    source_path: str | None = None,
    task_id: str | None = None,
    design_checklist_id: str | None = None,
    preset_id: str | None = None,
) -> dict[str, Any]:
    from backend.oc4_design_domain_service import (
        create_session_from_upload,
        merge_session_meta,
        session_dir,
        write_session_meta,
    )
    from backend.tools.files import resolve_file, store_upload

    root = workspace_root()
    fid = str(file_id or "").strip()
    file_name = ""
    if fid:
        try:
            file_name = resolve_file(root, fid).name
        except Exception:
            file_name = ""
    if not fid:
        src: Path | None = None
        raw_src = str(source_path or "").strip()
        if raw_src:
            cand = Path(raw_src)
            if not cand.is_file():
                cand = (root / raw_src).resolve()
            if cand.is_file():
                src = cand
        if src is None:
            src = _default_oc4_iges(root)
        if src is None or not src.is_file():
            raise FileNotFoundError(
                "需要 file_id、source_path，或仓库内 beso/wiki_files/nake_oc4/oc4.igs（OC4 参考几何）"
            )
        stored = store_upload(root, src.name, src.read_bytes())
        fid = stored.file_id
        file_name = stored.name or src.name

    sid, sdir, _sf = create_session_from_upload(root, fid)
    patch: dict[str, Any] = {"domain_envelope": "triangle_prism"}
    if task_id:
        patch["task_id"] = task_id
    if design_checklist_id:
        patch["design_checklist_id"] = design_checklist_id
    if preset_id:
        preset = get_preset(preset_id)
        patch.update(preset_session_meta_patch(preset))
        if design_checklist_id:
            from backend.design_requirements.paths import load_checklist, save_checklist

            cl = load_checklist(design_checklist_id)
            if cl is not None:
                apply_preset_to_checklist(cl, preset)
                from backend.design_requirements.markdown import checklist_to_markdown

                save_checklist(cl, markdown=checklist_to_markdown(cl))
        else:
            applied = step_apply_turbine_preset(preset_id=preset_id, session_id=sid)
            patch["design_checklist_id"] = applied["checklist_id"]
    if patch:
        merge_session_meta(sdir, patch)
    return {
        "ok": True,
        "session_id": sid,
        "session_dir": str(sdir),
        "file_id": fid,
        "file_name": file_name or "oc4.igs",
        "meta": patch,
        "client_hint": {
            "type": "enter_design_domain",
            "session_id": sid,
            "file_id": fid,
            "file_name": file_name or "oc4.igs",
        },
    }


def step_run_design_domain_build(
    *,
    session_id: str,
    cut_center_column: bool = True,
    include_source_geometry: bool = False,
    run_mesh: bool = True,
    run_loads: bool = True,
    finalize: bool = True,
    pause_before_mesh: bool = False,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    from backend.oc4_design_domain_service import (
        merge_session_meta,
        read_session_meta,
        run_build,
        run_loads as dd_run_loads,
        run_mesh as dd_run_mesh,
        session_dir,
        session_progress_flags,
    )

    mode, probe = resolve_execution_mode(execution_mode)
    if mode == "live":
        assert_live_or_raise(mode)
    elif not probe.gmsh_ok:
        return {
            "ok": False,
            "execution_mode": "preview",
            "preview": True,
            "error": "Preview: gmsh missing; cannot build design domain. Install gmsh or use teaching demo bypass.",
            "solvers": probe.to_dict(),
        }

    root = workspace_root()
    sdir = session_dir(root, session_id)
    if not sdir.is_dir():
        raise FileNotFoundError(f"session not found: {session_id}")

    build_info = run_build(
        sdir,
        cut_center_column=cut_center_column,
        include_source_geometry=include_source_geometry,
        domain_envelope=str(read_session_meta(sdir).get("domain_envelope") or "triangle_prism"),
    )
    out: dict[str, Any] = {
        "ok": True,
        "execution_mode": mode,
        "preview": mode == "preview",
        "session_id": session_id,
        "build": build_info if isinstance(build_info, dict) else {"ok": True},
        "progress": session_progress_flags(sdir),
    }
    if pause_before_mesh:
        merge_session_meta(
            sdir,
            {
                "hitl_pause": "before_mesh",
                "hitl_pause_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            },
        )
        out["hitl"] = {
            "paused": True,
            "reason": "before_mesh",
            "message": "Design domain built. Review / edit geometry, then continue with run_mesh or apply_geometry_patch.",
        }
        out["client_hint"] = {
            "type": "await_user_confirm",
            "session_id": session_id,
            "reason": "before_mesh",
            "open_parametric_editor": True,
        }
        return out

    meta = read_session_meta(sdir)
    cload = meta.get("cload_mag")
    if run_mesh:
        out["mesh"] = dd_run_mesh(sdir)
    if run_loads:
        kwargs: dict[str, Any] = {}
        if cload is not None:
            try:
                kwargs["cload_mag"] = float(cload)
            except (TypeError, ValueError):
                pass
        out["loads"] = dd_run_loads(sdir, **kwargs)
    if finalize:
        out["finalize"] = step_finalize_design_domain(session_id=session_id)
    out["progress"] = session_progress_flags(sdir)
    return out


def step_finalize_design_domain(*, session_id: str) -> dict[str, Any]:
    """Write beso_conf / mark ready — mirrors OC4 finalize without starting BESO."""
    from backend.oc4_design_domain_service import merge_session_meta, read_session_meta, session_dir

    root = workspace_root()
    sdir = session_dir(root, session_id)
    meta = read_session_meta(sdir)
    for_beso = sdir / "03_for_beso.inp"
    if not for_beso.is_file():
        raise FileNotFoundError(
            f"设计域会话缺少 03_for_beso.inp（带 *CLOAD/*BOUNDARY 的载荷 INP）。"
            f"禁止回退到无约束的 02_mesh_body.inp。请先在设计域完成载荷划分。session={session_id}"
        )
    merge_session_meta(
        sdir,
        {
            "design_domain_full_build_done": True,
            "for_beso_inp": for_beso.name,
            "hitl_pause": None,
        },
    )
    return {"ok": True, "session_id": session_id, "for_beso": str(for_beso), "meta": read_session_meta(sdir)}


def step_replace_geometry(
    *,
    session_id: str,
    source_path: str | None = None,
    file_id: str | None = None,
    as_design_domain: bool = True,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Replace session CAD, invalidate downstream, snapshot user_edit version."""
    from backend.oc4_design_domain_service import (
        invalidate_oc4_downstream_from_rail_step,
        merge_session_meta,
        session_dir,
        source_cad_path,
    )
    from backend.tools.files import resolve_file
    from backend.versions.store import commit_files, open_process

    root = workspace_root()
    sdir = session_dir(root, session_id)
    if not sdir.is_dir():
        raise FileNotFoundError(f"session not found: {session_id}")

    src: Path | None = None
    if file_id:
        sf = resolve_file(root, file_id)
        src = Path(sf.path)
    elif source_path:
        p = Path(source_path)
        if not p.is_file():
            p = (root / source_path).resolve()
        if p.is_file():
            src = p
    if src is None or not src.is_file():
        raise FileNotFoundError("replace geometry requires valid source_path or file_id")

    from backend.oc4_design_domain_service import read_session_meta

    tid = str(task_id or read_session_meta(sdir).get("task_id") or session_id)
    files_to_snap = [
        str(sdir / name)
        for name in ("01_design_domain.step", "01_design_domain.igs", "00_source.igs", "00_source.iges", "00_source.step")
        if (sdir / name).is_file()
    ]
    try:
        proc = open_process(tid, process_type="user_edit", label="geometry replace")
        pid = str(proc.get("process_id") or proc.get("id") or "")
        if pid and files_to_snap:
            commit_files(
                tid,
                pid,
                message=f"user_edit before replace · {src.name}",
                file_paths=files_to_snap,
                applied_handlers=["snapshot_files"],
            )
    except Exception as e:
        logger.info("user_edit snapshot skipped: %s", e)

    invalidate_oc4_downstream_from_rail_step(sdir, rail_step=1 if as_design_domain else 1)
    suf = src.suffix.lower()
    if as_design_domain and suf in {".step", ".stp", ".iges", ".igs"}:
        # write as design domain primary + keep as source
        if suf in {".step", ".stp"}:
            dest = sdir / "01_design_domain.step"
            shutil.copy2(src, dest)
            # also refresh source if missing
            if not any((sdir / n).is_file() for n in ("00_source.igs", "00_source.iges", "00_source.stp", "00_source.step")):
                shutil.copy2(src, sdir / f"00_source{suf}")
        else:
            dest = sdir / ("00_source.igs" if suf == ".igs" else "00_source.iges")
            shutil.copy2(src, dest)
            # clear old design domain so rebuild is required
            for n in ("01_design_domain.step", "01_design_domain.igs"):
                try:
                    (sdir / n).unlink(missing_ok=True)
                except OSError:
                    pass
    else:
        # replace source only
        for n in ("00_source.igs", "00_source.iges", "00_source.stp", "00_source.step"):
            try:
                (sdir / n).unlink(missing_ok=True)
            except OSError:
                pass
        dest = sdir / f"00_source{suf if suf else '.igs'}"
        shutil.copy2(src, dest)

    merge_session_meta(
        sdir,
        {
            "design_domain_full_build_done": False,
            "hitl_pause": None,
            "geometry_replaced_from": str(src),
            "user_edit": True,
        },
    )
    return {
        "ok": True,
        "session_id": session_id,
        "replaced_from": str(src),
        "as_design_domain": as_design_domain,
        "next": "run_design_domain_build or run_mesh after rebuild",
        "client_hint": {"type": "enter_design_domain", "session_id": session_id},
    }


def step_commit_preview_to_session(
    *,
    session_id: str,
    preview_stl_or_step: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Commit results-viewer parametric preview into the design-domain session."""
    return step_replace_geometry(
        session_id=session_id,
        source_path=preview_stl_or_step,
        as_design_domain=True,
        task_id=task_id,
    )


def step_request_human_edit(
    *,
    session_id: str,
    reason: str = "review_geometry",
    message: str | None = None,
) -> dict[str, Any]:
    from backend.oc4_design_domain_service import merge_session_meta, session_dir

    root = workspace_root()
    sdir = session_dir(root, session_id)
    merge_session_meta(sdir, {"hitl_pause": reason, "hitl_message": message or reason})
    return {
        "ok": True,
        "paused": True,
        "session_id": session_id,
        "reason": reason,
        "client_hint": {
            "type": "await_user_confirm",
            "session_id": session_id,
            "reason": reason,
            "open_parametric_editor": True,
        },
    }


def step_start_beso_job(
    *,
    session_id: str | None = None,
    scan_dir: str | None = None,
    inp_path: str | None = None,
    design_checklist_id: str | None = None,
    task_id: str | None = None,
    message: str = "conversation-driven BESO",
    auto_start: bool = True,
    execution_mode: str | None = None,
    mass_goal_ratio: float | None = None,
) -> dict[str, Any]:
    mode, probe = resolve_execution_mode(execution_mode)
    if mode == "preview":
        return {
            "ok": False,
            "execution_mode": "preview",
            "preview": True,
            "error": "Preview mode: refusing to start live BESO. Set live solvers or use teaching demo (?demo=beso7-pipeline).",
            "solvers": probe.to_dict(),
        }
    assert_live_or_raise(mode)

    from backend.design_requirements.paths import load_checklist
    from backend.jobs.manager import jobs
    from backend.oc4_design_domain_service import read_session_meta, session_dir
    from backend.replan.checklist_bridge import write_job_context
    from backend.tools.prism_design_domain import prism_session_dir, read_prism_session_meta

    root = workspace_root()
    mass = 0.15
    filt = 2.0
    opt_base = "stiffness"
    save_every = 1
    cid = str(design_checklist_id or "").strip() or None
    resolved_inp = inp_path
    resolved_scan = scan_dir
    prism_meta: dict[str, Any] = {}

    if session_id:
        # Prefer OC4 session; fall back to prism session layout
        sdir = session_dir(root, session_id)
        if sdir.is_dir():
            meta = read_session_meta(sdir)
            cid = cid or str(meta.get("design_checklist_id") or "").strip() or None
            for_beso = sdir / "03_for_beso.inp"
            if not for_beso.is_file():
                raise FileNotFoundError(
                    f"设计域会话缺少 03_for_beso.inp。请先完成载荷划分；"
                    f"不能用无 *CLOAD/*BOUNDARY 的 02_mesh_body.inp 启动拓扑。session={session_id}"
                )
            resolved_inp = str(for_beso)
            resolved_scan = str(sdir)
            # OC4 平台柔度目标：忽略 checklist 里易碎裂的 failure_index
            if mass_goal_ratio is None and meta.get("mass_goal_ratio") is not None:
                try:
                    mass_goal_ratio = float(meta["mass_goal_ratio"])
                except Exception:
                    pass
        else:
            pdir = prism_session_dir(root, session_id)
            if pdir.is_dir():
                prism_meta = read_prism_session_meta(pdir)
                cid = cid or str(prism_meta.get("design_checklist_id") or "").strip() or None
                for_beso = pdir / "03_for_beso.inp"
                if for_beso.is_file():
                    resolved_inp = str(for_beso)
                    resolved_scan = str(pdir)
                if mass_goal_ratio is None and prism_meta.get("mass_goal_ratio") is not None:
                    mass_goal_ratio = float(prism_meta["mass_goal_ratio"])

    if cid:
        cl = load_checklist(cid)
        if cl is not None:
            mass = float(cl.job_descriptor.theta.beso.mass_goal_ratio)
            filt = float(cl.job_descriptor.theta.beso.filter_radius)
            opt_base = str(cl.job_descriptor.theta.beso.optimization_base or "stiffness")
            save_every = int(cl.job_descriptor.theta.beso.save_every or 1)

    if mass_goal_ratio is not None:
        mass = float(mass_goal_ratio)

    # OC4 带载荷主 INP：强制 stiffness，避免 failure_index 在低应力下碎裂
    try:
        if resolved_inp and Path(resolved_inp).name.lower() == "03_for_beso.inp":
            opt_base = "stiffness"
    except Exception:
        pass

    if not resolved_inp:
        raise ValueError("inp_path, scan_dir, or finalized design-domain session required")

    job = jobs.create_job(
        user_message=message,
        inp_path=resolved_inp,
        mass_goal_ratio=mass,
        filter_radius=filt,
        optimization_base=opt_base,
        save_every=save_every,
    )
    write_job_context(
        Path(job.run_dir),
        design_checklist_id=cid,
        task_id=task_id,
        oc4_session_id=session_id if not prism_meta else None,
        execution_mode=mode,
    )
    # 把会话 design_spec 拷入 run_dir，供拓扑结束后自动生成 parameters_summary.json
    try:
        from pathlib import Path as _P
        import shutil as _shutil

        jdir = _P(job.run_dir)
        src_spec = None
        if resolved_scan:
            cand = _P(resolved_scan) / "design_spec.json"
            if cand.is_file():
                src_spec = cand
        if src_spec is None and session_id:
            for base in (
                session_dir(root, session_id) / "design_spec.json",
                prism_session_dir(root, session_id) / "design_spec.json",
            ):
                if base.is_file():
                    src_spec = base
                    break
        if src_spec is not None and src_spec.is_file():
            _shutil.copy2(src_spec, jdir / "design_spec.json")
    except Exception:
        pass
    if auto_start:
        jobs.start_job(job.id)
    return {
        "ok": True,
        "execution_mode": mode,
        "job_id": job.id,
        "run_dir": job.run_dir,
        "inp_path": resolved_inp,
        "scan_dir": resolved_scan,
        "checklist_id": cid,
        "session_id": session_id,
        "mass_goal_ratio": mass,
        "status": "started" if auto_start else "created",
        "client_hint": {
            "type": "enter_topology_flow",
            "job_id": job.id,
            "scan_dir": resolved_scan or job.run_dir,
            "run_dir": job.run_dir,
            "session_id": session_id,
        },
    }


def step_get_job_status(*, job_id: str) -> dict[str, Any]:
    from backend.jobs.manager import jobs

    job = jobs.get_job(job_id)
    if job is None:
        raise FileNotFoundError(f"job not found: {job_id}")
    status = getattr(job.status, "value", None) or str(job.status)
    return {
        "ok": True,
        "job_id": job_id,
        "status": status,
        "run_dir": getattr(job, "run_dir", None),
        "latest_vtk_url": getattr(job, "latest_vtk_url", None),
        "complete": str(status).lower() in {"completed", "complete", "succeeded", "success", "done"},
        "failed": str(status).lower() in {"failed", "error", "cancelled", "canceled"},
    }


def step_run_sizing(
    *,
    geometry_path: str | None = None,
    job_id: str | None = None,
    design_checklist_id: str | None = None,
    target_power_mw: float | None = None,
    out_dir: str | None = None,
) -> dict[str, Any]:
    from backend.design_requirements.geometry_bridge import apply_checklist_to_geometry
    from backend.design_requirements.paths import load_checklist
    from backend.tools.mixed_platform_steel import attach_steel_to_geometry, compute_steel_report

    root = workspace_root()
    geom_path = Path(geometry_path) if geometry_path else (root / "rules" / "optimized_geometry.json")
    if not geom_path.is_file():
        geom_path = root / "rules" / "optimized_geometry.json"
    if not geom_path.is_file():
        raise FileNotFoundError(f"geometry json not found: {geom_path}")
    geometry = json.loads(geom_path.read_text(encoding="utf-8"))

    target = target_power_mw
    cid = str(design_checklist_id or "").strip() or None
    if cid:
        cl = load_checklist(cid)
        if cl is not None:
            geometry = apply_checklist_to_geometry(geometry, cl, capacity_policy="checklist")
            if target is None:
                target = float(cl.project.target_capacity_mw)
    if target is None:
        target = float((geometry.get("optimization_info") or {}).get("target_power_MW") or 20.0)
        # snap to nearest preset for consistency
        target = get_preset(nearest_preset_id(target)).target_power_mw

    report = compute_steel_report(geometry, target_power_mw=float(target), optimize=True)
    sized = attach_steel_to_geometry(geometry, report)

    dest = Path(out_dir) if out_dir else None
    if dest is None and job_id:
        from backend.jobs.manager import jobs

        job = jobs.get_job(job_id)
        if job and job.run_dir:
            dest = Path(job.run_dir)
    if dest is None:
        dest = root / "runs" / "_sizing" / uuid.uuid4().hex
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "sizing_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest / "sized_geometry.json").write_text(json.dumps(sized, ensure_ascii=False, indent=2), encoding="utf-8")
    prest = report.get("platform_restruction") or {}
    if isinstance(prest, dict) and prest.get("ok"):
        (dest / "platform_restruction.json").write_text(
            json.dumps(prest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    steel = report.get("steel_summary") or {}
    prest_steel = (prest.get("steel_summary") or {}) if isinstance(prest, dict) else {}
    return {
        "ok": True,
        "target_power_MW": float(target),
        "steel_intensity_t_per_MW": steel.get("steel_intensity_t_per_MW"),
        "pitch_angle_deg": steel.get("pitch_angle_deg"),
        "platform_restruction": {
            "base_name": (prest.get("base_platform") or {}).get("name") if isinstance(prest, dict) else None,
            "extra_scale_x": prest.get("extra_scale_x") if isinstance(prest, dict) else None,
            "steel_intensity_t_per_MW": prest_steel.get("steel_intensity_t_per_MW"),
            "pitch_angle_deg": prest_steel.get("pitch_angle_deg"),
            "optimizer": prest.get("optimizer") if isinstance(prest, dict) else None,
        },
        "out_dir": str(dest),
        "report_path": str(dest / "sizing_report.json"),
        "sized_geometry_path": str(dest / "sized_geometry.json"),
        "preset_id": nearest_preset_id(float(target)),
    }


def step_run_validation(
    *,
    geometry_path: str | None = None,
    design_checklist_id: str | None = None,
    out_dir: str | None = None,
    use_llm_rationale: bool = False,
) -> dict[str, Any]:
    from backend.design_requirements.geometry_bridge import apply_checklist_to_geometry
    from backend.design_requirements.paths import load_checklist
    from backend.validation.pipeline import run_validation

    root = workspace_root()
    geom_path = Path(geometry_path) if geometry_path else None
    if geom_path is None or not geom_path.is_file():
        # prefer sized geometry beside rules
        for cand in (
            geometry_path,
            str(root / "rules" / "optimized_geometry.json"),
        ):
            if cand and Path(cand).is_file():
                geom_path = Path(cand)
                break
    if geom_path is None or not geom_path.is_file():
        raise FileNotFoundError("geometry_path required for validation")
    geometry = json.loads(geom_path.read_text(encoding="utf-8"))
    cid = str(design_checklist_id or "").strip() or None
    if cid:
        cl = load_checklist(cid)
        if cl is not None:
            geometry = apply_checklist_to_geometry(geometry, cl, capacity_policy="checklist")

    dest = Path(out_dir) if out_dir else (root / "runs" / "_validation" / uuid.uuid4().hex)
    result = run_validation(
        geometry,
        out_dir=dest,
        use_llm_rationale=use_llm_rationale,
    )
    return {"ok": True, "out_dir": str(dest), **(result if isinstance(result, dict) else {"result": result})}


def step_evaluate_halt(
    *,
    validation_dir: str | None = None,
    overall_score: float | None = None,
    ai_review_scores: dict[str, float] | None = None,
    design_checklist_id: str | None = None,
    score: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from backend.orchestrator.halt import evaluate_halt_gate

    payload = dict(score or {})
    if validation_dir:
        p = Path(validation_dir)
        for name in ("score.json", "validation_score.json", "ai_review_score.json", "report.json"):
            q = p / name
            if q.is_file():
                try:
                    payload.update(json.loads(q.read_text(encoding="utf-8")))
                except Exception:
                    pass
                break
    ov = overall_score
    if ov is None:
        ov = payload.get("overall_score")
    if ov is None:
        raise ValueError("overall_score or validation_dir with score required")
    ai = ai_review_scores or payload.get("ai_review_scores")
    if isinstance(ai, dict):
        ai_f = {str(k): float(v) for k, v in ai.items() if v is not None}
    else:
        ai_f = None
    gate = evaluate_halt_gate(
        overall_score=float(ov),
        ai_review_scores=ai_f,
        design_checklist_id=design_checklist_id or payload.get("design_checklist_id"),
    )
    if hasattr(gate, "model_dump"):
        data = gate.model_dump(mode="json")
    elif isinstance(gate, dict):
        data = gate
    else:
        data = {"passed": getattr(gate, "passed", None), "raw": str(gate)}
    return {"ok": True, "halt": data}


def step_ensure_session_for_pipeline(
    *,
    design_checklist_id: str | None,
    oc4_session_id: str | None,
    preset_id: str | None = None,
) -> dict[str, Any]:
    """MasterGraph helper: ensure checklist + optional session."""
    out: dict[str, Any] = {"ok": True}
    if preset_id:
        out["preset"] = step_apply_turbine_preset(
            preset_id=preset_id,
            checklist_id=design_checklist_id,
            session_id=oc4_session_id,
        )
        design_checklist_id = out["preset"].get("checklist_id") or design_checklist_id
    if oc4_session_id:
        out["session_id"] = oc4_session_id
    out["design_checklist_id"] = design_checklist_id
    return out


# ---------------------------------------------------------------------------
# Prism / beso9-style design domain (prompt-driven)
# ---------------------------------------------------------------------------


def step_parse_prism_design_brief(*, text: str) -> dict[str, Any]:
    from backend.tools.prism_design_domain import parse_prism_design_brief

    spec = parse_prism_design_brief(text)
    return {"ok": True, "spec": spec.to_dict(), "title": spec.title}


def step_start_prism_session(
    *,
    text: str | None = None,
    spec: dict[str, Any] | None = None,
    task_id: str | None = None,
    design_checklist_id: str | None = None,
) -> dict[str, Any]:
    from backend.tools.prism_design_domain import (
        PrismDesignSpec,
        new_prism_session_id,
        parse_prism_design_brief,
        prism_session_dir,
        write_prism_design_files,
        write_prism_session_meta,
    )

    root = workspace_root()
    if spec:
        ps = PrismDesignSpec.from_dict(spec)
    else:
        ps = parse_prism_design_brief(str(text or ""))
    sid = new_prism_session_id()
    sdir = prism_session_dir(root, sid)
    write_prism_design_files(sdir, ps)
    meta = write_prism_session_meta(
        sdir,
        {
            "session_id": sid,
            "domain_kind": "prism_beso9",
            "task_id": task_id,
            "design_checklist_id": design_checklist_id,
            "mass_goal_ratio": ps.mass_goal_ratio,
            "title": ps.title,
            "status": "created",
        },
    )
    return {
        "ok": True,
        "session_id": sid,
        "session_dir": str(sdir),
        "spec": ps.to_dict(),
        "meta": meta,
        "client_hint": {"type": "open_results_viewer", "scan_dir": str(sdir)},
    }


def step_build_prism_design_domain(
    *,
    session_id: str,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    from backend.tools.prism_design_domain import (
        PrismDesignSpec,
        prism_session_dir,
        read_prism_session_meta,
        run_prism_build_fcstd,
        write_prism_session_meta,
    )

    mode, probe = resolve_execution_mode(execution_mode)
    if mode == "preview":
        return {
            "ok": False,
            "execution_mode": "preview",
            "preview": True,
            "error": "Preview mode: FreeCAD prism build requires live solvers (FREECAD_PYTHON).",
            "solvers": probe.to_dict(),
        }
    assert_live_or_raise(mode)

    root = workspace_root()
    sid = str(session_id or "").strip()
    sdir = prism_session_dir(root, sid)
    if not sdir.is_dir():
        raise FileNotFoundError(f"prism session not found: {sid}")
    spec_path = sdir / "prism_spec.json"
    if not spec_path.is_file():
        raise FileNotFoundError(f"missing prism_spec.json in {sdir}")
    spec = PrismDesignSpec.from_dict(json.loads(spec_path.read_text(encoding="utf-8")))
    fcstd = sdir / "BESO_PRISM.FCStd"
    run_prism_build_fcstd(spec=spec, out_fcstd=fcstd)
    write_prism_session_meta(
        sdir,
        {
            "status": "built",
            "fcstd": str(fcstd),
            "step": str(fcstd.with_suffix(".step")) if fcstd.with_suffix(".step").is_file() else None,
        },
    )
    return {
        "ok": True,
        "execution_mode": mode,
        "session_id": sid,
        "session_dir": str(sdir),
        "fcstd": str(fcstd),
        "step": str(fcstd.with_suffix(".step")) if fcstd.with_suffix(".step").is_file() else None,
        "meta": read_prism_session_meta(sdir),
    }


def step_mesh_prism_design_domain(
    *,
    session_id: str,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    from backend.tools.prism_design_domain import (
        PrismDesignSpec,
        prism_session_dir,
        read_prism_session_meta,
        run_prism_mesh_inp,
        write_prism_session_meta,
    )

    mode, probe = resolve_execution_mode(execution_mode)
    if mode == "preview":
        return {
            "ok": False,
            "execution_mode": "preview",
            "preview": True,
            "error": "Preview mode: FreeCAD prism mesh requires live solvers.",
            "solvers": probe.to_dict(),
        }
    assert_live_or_raise(mode)

    root = workspace_root()
    sid = str(session_id or "").strip()
    sdir = prism_session_dir(root, sid)
    fcstd = sdir / "BESO_PRISM.FCStd"
    if not fcstd.is_file():
        raise FileNotFoundError(f"FCStd missing — run build first: {fcstd}")
    spec = PrismDesignSpec.from_dict(
        json.loads((sdir / "prism_spec.json").read_text(encoding="utf-8"))
        if (sdir / "prism_spec.json").is_file()
        else {}
    )
    out_inp = sdir / "03_for_beso.inp"
    run_prism_mesh_inp(fcstd=fcstd, out_inp=out_inp, spec=spec)
    # also copy as Analysis-beso.inp for BESO runners that expect that name
    analysis = sdir / "Analysis-beso.inp"
    try:
        shutil.copy2(out_inp, analysis)
    except Exception:
        analysis = out_inp
    write_prism_session_meta(
        sdir,
        {"status": "meshed", "inp": str(out_inp), "analysis_inp": str(analysis)},
    )
    return {
        "ok": True,
        "execution_mode": mode,
        "session_id": sid,
        "session_dir": str(sdir),
        "inp_path": str(out_inp),
        "meta": read_prism_session_meta(sdir),
    }


def step_run_prism_topology_demo(
    *,
    text: str,
    task_id: str | None = None,
    design_checklist_id: str | None = None,
    start_beso: bool = True,
    auto_start: bool = True,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    """One-shot: parse → session → FreeCAD build → mesh → async BESO."""
    parsed = step_parse_prism_design_brief(text=text)
    sess = step_start_prism_session(
        text=text,
        spec=parsed.get("spec"),
        task_id=task_id,
        design_checklist_id=design_checklist_id,
    )
    sid = str(sess["session_id"])
    built = step_build_prism_design_domain(session_id=sid, execution_mode=execution_mode)
    if not built.get("ok"):
        return {**built, "session_id": sid, "phase": "build"}
    meshed = step_mesh_prism_design_domain(session_id=sid, execution_mode=execution_mode)
    if not meshed.get("ok"):
        return {**meshed, "session_id": sid, "phase": "mesh", "build": built}

    beso: dict[str, Any] | None = None
    if start_beso:
        mass = float((parsed.get("spec") or {}).get("mass_goal_ratio") or 0.15)
        beso = step_start_beso_job(
            session_id=sid,
            inp_path=meshed.get("inp_path"),
            scan_dir=str(sess.get("session_dir")),
            design_checklist_id=design_checklist_id,
            task_id=task_id,
            message=f"prism topology demo: {text[:200]}",
            auto_start=auto_start,
            execution_mode=execution_mode,
            mass_goal_ratio=mass,
        )

    scan = beso.get("run_dir") if beso and beso.get("ok") else sess.get("session_dir")
    hint: dict[str, Any]
    if beso and beso.get("ok") and beso.get("job_id"):
        hint = {
            "type": "enter_topology_flow",
            "job_id": beso.get("job_id"),
            "scan_dir": scan,
            "run_dir": beso.get("run_dir"),
            "session_id": sid,
        }
    else:
        hint = {"type": "open_results_viewer", "scan_dir": scan}
    return {
        "ok": True if (beso is None or beso.get("ok")) else False,
        "session_id": sid,
        "session_dir": sess.get("session_dir"),
        "spec": parsed.get("spec"),
        "build": built,
        "mesh": meshed,
        "beso": beso,
        "job_id": (beso or {}).get("job_id"),
        "run_dir": (beso or {}).get("run_dir"),
        "client_hint": hint,
        "error": None if (beso is None or beso.get("ok")) else (beso or {}).get("error"),
    }
