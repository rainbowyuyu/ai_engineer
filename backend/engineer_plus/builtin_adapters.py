"""Built-in adapters that bridge existing real CAD/BESO implementations."""
from __future__ import annotations

import json
import hashlib
import time
import shutil
from pathlib import Path
from typing import Any, Callable

from .engine import DesignRequest
from .registry import ConstructionAdapter, ConstructionRegistry
from .revision import PrismRevisionPolicy, prism_spec


def _workspace(request: DesignRequest) -> Path:
    default_root = Path(__file__).resolve().parents[2]
    root = Path(str(request.requirements.get("workspace_root") or default_root)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_prism(request: DesignRequest, *, candidate_index: int) -> dict[str, Any]:
    from backend.tools.prism_design_domain import (
        PrismDesignSpec, run_prism_build_fcstd, run_prism_mesh_inp, design_spec_json_from_prism,
    )
    root = _workspace(request) / "_plus" / request.task_id / (request.attempt_id or f"candidate_{candidate_index + 1}")
    root.mkdir(parents=True, exist_ok=True)
    spec = PrismDesignSpec.from_dict(prism_spec(request))
    if request.requirements.get("_topology_continuation"):
        previous = request.requirements["_fixed_domain"]
        if json.loads(Path(previous["spec_path"]).read_text(encoding="utf-8")) != spec.to_dict():
            raise ValueError("fixed-domain continuation specification changed")
        preserved = {**previous}
        for key in ("artifact_path", "fcstd_path", "spec_path", "design_spec_path"):
            if key not in previous:
                continue
            source = Path(previous[key]).resolve()
            source.relative_to(_workspace(request))
            destination = root / source.name
            if destination.exists():
                raise ValueError("continuation attempt directory already contains artifacts")
            shutil.copy2(source, destination)
            if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
                raise ValueError("copied fixed-domain artifact changed")
            preserved[key] = str(destination)
        if "design_spec_path" not in preserved:
            design_spec_path = root / "design_spec.json"
            design_spec_path.write_text(json.dumps(design_spec_json_from_prism(spec), ensure_ascii=False, indent=2), encoding="utf-8")
            preserved["design_spec_path"] = str(design_spec_path)
        preserved["continuation"] = request.requirements["_topology_continuation"]
        preserved["geometry"] = {"source": "unchanged_prism_domain", "spec_path": preserved["spec_path"]}
        return preserved
    spec_path = root / "prism_spec.json"
    spec_path.write_text(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    design_spec_path = root / "design_spec.json"
    design_spec_path.write_text(json.dumps(design_spec_json_from_prism(spec), ensure_ascii=False, indent=2), encoding="utf-8")
    fcstd = run_prism_build_fcstd(spec=spec, out_fcstd=root / "design_domain.FCStd")
    inp = run_prism_mesh_inp(fcstd=fcstd, out_inp=root / "03_for_beso.inp", spec=spec)
    return {"artifact_path": str(inp), "fcstd_path": str(fcstd), "spec_path": str(spec_path),
            "design_spec_path": str(design_spec_path),
            "mass_goal_ratio": spec.mass_goal_ratio,
            "geometry": {"source": "prism_design_domain", "spec_path": str(spec_path)}}


def _run_beso_and_size(domain: dict[str, Any], *, candidate_index: int,
                       on_job_started: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    from backend.pipeline.steps import step_get_job_status, step_run_sizing, step_start_beso_job
    inp = str(domain["artifact_path"])
    started = step_start_beso_job(inp_path=inp, scan_dir=str(Path(inp).parent),
                                  message="AI Engineer Plus candidate", auto_start=True,
                                  execution_mode="live", mass_goal_ratio=domain.get("mass_goal_ratio"),
                                  continuation=domain.get("continuation"))
    job_id = started.get("job_id")
    if not job_id:
        raise RuntimeError("BESO did not return a job id")
    if on_job_started:
        on_job_started({"job_id": job_id, "run_dir": started.get("run_dir")})
    timeout = float(domain.get("timeout_s") or 86_400)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = step_get_job_status(job_id=job_id)
        if status.get("failed"):
            raise RuntimeError(f"BESO job failed: {job_id}")
        if status.get("complete"):
            run_dir = Path(str(status.get("run_dir") or ""))
            # The sizing stage must consume the topology reconstructed from
            # this exact BESO run.  Passing no geometry_path makes the legacy
            # pipeline silently fall back to rules/optimized_geometry.json.
            topology_geometry = run_dir / "parameters_summary.json"
            if not topology_geometry.is_file():
                raise RuntimeError(
                    f"BESO completed without topology reconstruction: {topology_geometry}"
                )
            try:
                topo_data = json.loads(topology_geometry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"invalid topology reconstruction: {topology_geometry}") from exc
            topo_sections = [v for k, v in topo_data.items()
                             if "topology_reconstructed" in str(k) and isinstance(v, dict)]
            legs = sum(len(v.get("legs") or []) for v in topo_sections)
            if not topo_sections or legs == 0:
                raise RuntimeError("topology reconstruction contains no elements")
            source_inp = max(run_dir.glob("file*_state1.inp"),
                             key=lambda p: int(p.stem[4:].split("_")[0])) if list(run_dir.glob("file*_state1.inp")) else None
            if source_inp is None:
                raise RuntimeError("BESO completed without a state1 input deck")
            provenance = {
                "job_id": job_id,
                "source_state1_inp": str(source_inp),
                "source_state1_sha256": hashlib.sha256(source_inp.read_bytes()).hexdigest(),
                "parameters_summary_sha256": hashlib.sha256(topology_geometry.read_bytes()).hexdigest(),
                "reconstructed_elements": legs,
            }
            (run_dir / "topology_provenance.json").write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            sized = step_run_sizing(
                job_id=job_id,
                geometry_path=str(topology_geometry),
            )
            return {"artifact_path": sized["sized_geometry_path"], "job_id": job_id,
                    "source_run": str(run_dir), "source_input_path": str(run_dir / Path(inp).name),
                    "source_state1_path": str(source_inp),
                    "continuation_provenance_path": str(run_dir / "continuation_provenance.json") if domain.get("continuation") else None,
                    "sizing": sized, "topology_geometry_path": str(topology_geometry),
                    "topology_provenance": str(run_dir / "topology_provenance.json"),
                    "topology_provenance_data": provenance}
        time.sleep(min(2.0, max(0.1, deadline - time.monotonic())))
    raise TimeoutError(f"BESO job timed out: {job_id}")


def _build_oc4(request: DesignRequest, *, candidate_index: int) -> dict[str, Any]:
    """Use the existing OC4 session builder, including mesh and load partition."""
    from backend.pipeline.steps import step_run_design_domain_build, step_start_design_domain_session
    source = request.requirements.get("source_path")
    started = step_start_design_domain_session(source_path=str(source) if source else None,
                                               task_id=request.task_id)
    sid = started["session_id"]
    built = step_run_design_domain_build(session_id=sid, execution_mode="live")
    inp = Path(started["session_dir"]) / "03_for_beso.inp"
    if not inp.is_file():
        raise RuntimeError(f"OC4 design-domain build did not produce {inp.name}")
    return {"artifact_path": str(inp), "session_id": sid,
            "build": built, "geometry": {"source": "oc4_design_domain_service", "session_id": sid}}


def _build_generic_cad(request: DesignRequest, *, candidate_index: int) -> dict[str, Any]:
    """Convert a user-supplied IGES/STEP solid to a load-free FEM domain."""
    from backend.tools.cad_iges_to_inp import run_cad_iges_to_inp
    source = Path(str(request.requirements.get("source_path") or "")).resolve()
    root = _workspace(request).resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise ValueError("source_path must be inside workspace") from exc
    if not source.is_file() or source.suffix.lower() not in {".igs", ".iges", ".step", ".stp"}:
        raise ValueError("source_path must be an existing IGES or STEP file")
    out = root / "_plus" / request.task_id / (request.attempt_id or f"candidate_{candidate_index + 1}") / "03_for_beso.inp"
    out.parent.mkdir(parents=True, exist_ok=True)
    params = request.requirements
    run_cad_iges_to_inp(source, out,
                        char_length_max=params.get("char_length_max"),
                        char_length_min=params.get("char_length_min"),
                        element_order=params.get("element_order"),
                        timeout_s=params.get("timeout_s"))
    if not out.is_file() or out.stat().st_size < 10_000:
        raise RuntimeError("CAD conversion produced no usable FEM input")
    physics = params.get("generic_physics")
    physics_evidence = None
    if physics is not None:
        from .generic_physics import apply_explicit_physics
        # FreeCAD FEM writes mesh coordinates in millimetres; Pa must become N/mm².
        requested_physics = dict(physics)
        if requested_physics.get("mesh_length_unit", "mm") != "mm":
            raise ValueError("FreeCAD CAD mesh coordinates use mm")
        requested_physics["mesh_length_unit"] = "mm"
        physics_evidence = apply_explicit_physics(out, out.with_name("03_for_beso_physical.inp"), requested_physics)
        out = Path(physics_evidence["output_inp"])
    from .physical_evidence import audit_calculix_deck
    deck_audit = audit_calculix_deck(out)
    if not deck_audit["solvable_structural_model"]:
        raise RuntimeError("CAD mesh is not a solvable structural model; missing "
                           + ", ".join(deck_audit["missing"])
                           + ". Supply material, constraints and loads before BESO.")
    return {"artifact_path": str(out), "source_path": str(source),
            "geometry": {"source": "freecad_gmsh_cad_to_inp", "cad_path": str(source)},
            "physical_evidence": deck_audit, "physics_evidence": physics_evidence}


def register_builtin_adapters(registry: ConstructionRegistry) -> None:
    """Register only adapters backed by repository implementations."""
    registry.register(ConstructionAdapter(
        name="prism", description="FreeCAD equilateral prism with BESO topology and sizing",
        build_domain=_build_prism, run_topology=_run_beso_and_size,
        capabilities=("freecad", "gmsh", "calculix", "beso", "sizing"),
        input_formats=("natural-language prism brief",),
        required_inputs=("geometry dimensions", "material", "loads", "supports", "optimization target"),
        produced_artifacts=("design_domain.FCStd", "03_for_beso.inp", "BESO state1 input", "topology_provenance.json", "sized geometry"),
        limitations=("requires the prism-specific builder; does not represent arbitrary solids",),
        revision_policy=PrismRevisionPolicy(),
    ))
    registry.register(ConstructionAdapter(
        name="oc4", description="OC4 CAD design domain with mesh, loads, BESO and sizing",
        build_domain=_build_oc4, run_topology=_run_beso_and_size,
        capabilities=("iges", "design-domain", "gmsh", "calculix", "beso", "sizing"),
        input_formats=("OC4 source geometry", "workspace-local IGES/STEP source"),
        required_inputs=("source geometry", "load partition", "material", "supports", "optimization target"),
        produced_artifacts=("03_for_beso.inp", "BESO state1 input", "topology_provenance.json", "sized geometry"),
        limitations=("uses the OC4-specific geometry and load-partition workflow",),
    ))
    registry.register(ConstructionAdapter(
        name="cad", description="Generic IGES/STEP solid converted to FEM design domain",
        build_domain=_build_generic_cad, run_topology=_run_beso_and_size,
        capabilities=("iges", "step", "freecad", "gmsh", "calculix", "beso", "sizing"),
        input_formats=("workspace-local IGES", "workspace-local STEP"),
        required_inputs=("source_path", "youngs_modulus_pa", "poissons_ratio", "load_n", "support/load assumptions"),
        produced_artifacts=("03_for_beso_physical.inp", "BESO state1 input", "topology_provenance.json", "sized geometry"),
        limitations=("generic physics uses explicit min-z support and max-z distributed load; contacts, nonlinear materials and complex load paths require a dedicated adapter",),
    ))


__all__ = ["register_builtin_adapters"]
