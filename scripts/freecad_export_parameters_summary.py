# -*- coding: utf-8 -*-
"""FreeCAD CLI: after BESO, fit topology INP → parameters_summary.json (+ measurements).

Usage:
  freecad/bin/python.exe scripts/freecad_export_parameters_summary.py \\
    --run-dir runs/<job_id> [--inp path] [--design-spec path] [--fcstd path] [--out path]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BESO7_ADDITION = REPO / "examples" / "beso" / "beso7" / "addition"
BESO9 = REPO / "examples" / "beso" / "beso9"
if str(BESO7_ADDITION) not in sys.path:
    sys.path.insert(0, str(BESO7_ADDITION))
if str(BESO9) not in sys.path:
    sys.path.insert(0, str(BESO9))

from common.inp_state_mesh import (  # noqa: E402
    build_rebuilt_solid,
    fit_cylinder_pca,
    fit_hub_from_nodes,
    fit_station_radii,
    load_fem_mesh,
    nodes_from_elements,
    segment_legs_and_top,
    write_measurements_json,
)

# Reuse BESO9 builders when available
import export_parameters_summary as _beso9  # noqa: E402

STATION_FRACS = [0.0, 0.333, 0.667, 1.0]


def _latest_state1_inp(out_dir: Path) -> Path | None:
    cands = sorted(out_dir.glob("file*_state1.inp"))
    if not cands:
        return None

    def key(p: Path) -> int:
        m = re.match(r"file(\d+)_state1\.inp$", p.name, re.I)
        return int(m.group(1)) if m else -1

    cands = [p for p in cands if key(p) >= 0]
    cands.sort(key=key)
    return cands[-1] if cands else None


def design_dict_from_spec(spec: dict) -> dict:
    """Map design_spec.json → measure_design_domain-like dict for build_summary."""
    verts = spec.get("sharp_vertices_xy_mm") or _beso9._equilateral_vertices(
        float(spec.get("side_length_mm") or _beso9.SIDE_SPAN_MM)
    )
    corner_r = float(spec.get("corner_cyl_radius_mm") or spec.get("corner_circle_radius_mm") or _beso9.CORNER_CYL_R_MM)
    centers = spec.get("corner_centers_xy_mm") or verts
    load_ctr = spec.get("load_circle_center_xyz_mm") or [
        0.0,
        0.0,
        float(spec.get("z_max_mm") or (_beso9.HEIGHT_ABOVE_MM + _beso9.RING_H_MM)),
    ]
    load_r = float(spec.get("load_circle_radius_mm") or (_beso9.LOAD_DIAMETER_MM / 2.0))
    bb = {
        "x_length": float(spec.get("bbox_x_mm") or spec.get("outer_span_x_mm") or _beso9.SIDE_SPAN_MM),
        "y_length": float(spec.get("bbox_y_mm") or 0.0),
        "z_length": float(spec.get("bbox_z_mm") or float(spec.get("height_total_mm") or 0.0)),
        "x_min": None,
        "x_max": None,
        "y_min": None,
        "y_max": None,
        "z_min": float(spec.get("z_min_mm") or -_beso9.HEIGHT_BELOW_MM),
        "z_max": float(spec.get("z_max_mm") or (_beso9.HEIGHT_ABOVE_MM + _beso9.RING_H_MM)),
    }
    return {
        "volume_mm3": spec.get("volume_mm3"),
        "volume_m3": (float(spec["volume_mm3"]) / 1e9) if spec.get("volume_mm3") is not None else None,
        "bounding_box_mm": {k: (None if v is None else _beso9._r(float(v))) for k, v in bb.items() if v is not None},
        "face_count": spec.get("face_count"),
        "edge_count": spec.get("edge_count"),
        "sharp_vertices_xy_mm": verts,
        "bottom_notch_arcs": None,
        "corner_centers_xy_mm": centers,
        "load_circumference_edge": {
            "edge_index": None,
            "radius_mm": _beso9._r(load_r),
            "length_mm": _beso9._r(2.0 * math.pi * load_r),
            "center_xyz_mm": [float(x) for x in load_ctr],
        },
        "_spec_side_mm": float(spec.get("side_length_mm") or _beso9.SIDE_SPAN_MM),
        "_spec_height_below": float(spec.get("height_below_wl_mm") or _beso9.HEIGHT_BELOW_MM),
        "_spec_height_above": float(spec.get("height_above_wl_mm") or _beso9.HEIGHT_ABOVE_MM),
        "_spec_force_n": float(spec.get("load_force_n") or _beso9.FORCE_N),
        "_spec_corner_r": corner_r,
        "_spec_load_d": float(spec.get("load_circle_diameter_mm") or (2.0 * load_r)),
        "_spec_mass_goal": float(spec.get("mass_goal_ratio") or _beso9.MASS_GOAL_RATIO),
    }


def fit_topology_from_inp(inp: Path):
    fem = load_fem_mesh(inp)
    seg = segment_legs_and_top(fem)
    print(
        f"[INFO] elements legs={[len(x) for x in seg.leg_elements]} top={len(seg.top_elements)}",
        flush=True,
    )
    leg_fits = []
    for i, eids in enumerate(seg.leg_elements):
        pts = nodes_from_elements(fem, eids)
        fit = fit_cylinder_pca(pts)
        fit.station_fracs = tuple(STATION_FRACS)
        fit.station_radii_mm = fit_station_radii(pts, fit)
        leg_fits.append(fit)
        print(
            f"[INFO] leg{i + 1}: R={fit.radius_mm:.1f} L={fit.length_mm:.1f}",
            flush=True,
        )
    top_pts = nodes_from_elements(fem, seg.top_elements)
    hub = fit_hub_from_nodes(top_pts, z_max=seg.z_max)
    counts = [len(x) for x in seg.leg_elements] + [len(seg.top_elements)]
    solid = build_rebuilt_solid(leg_fits, hub)
    return leg_fits, hub, counts, solid


def _patch_summary_constants(summary: dict, design: dict | None) -> dict:
    """If design came from design_spec, overwrite hardcoded BESO9 constants in notes/section."""
    if not design:
        return summary
    dd = summary.get("beso9_design_domain_from_fcstd") or {}
    side = float(design.get("_spec_side_mm") or _beso9.SIDE_SPAN_MM)
    hb = float(design.get("_spec_height_below") or _beso9.HEIGHT_BELOW_MM)
    ha = float(design.get("_spec_height_above") or _beso9.HEIGHT_ABOVE_MM)
    force = float(design.get("_spec_force_n") or _beso9.FORCE_N)
    corner_r = float(design.get("_spec_corner_r") or _beso9.CORNER_CYL_R_MM)
    load_d = float(design.get("_spec_load_d") or _beso9.LOAD_DIAMETER_MM)
    mass_goal = float(design.get("_spec_mass_goal") or _beso9.MASS_GOAL_RATIO)
    height_total = hb + ha
    if dd.get("design_domain_prism"):
        dd["design_domain_prism"]["side_length_mm"] = side
        dd["design_domain_prism"]["side_length_m"] = side / 1000.0
        dd["design_domain_prism"]["height_total_mm"] = height_total
        dd["design_domain_prism"]["height_below_waterline_mm"] = hb
        dd["design_domain_prism"]["height_above_waterline_mm"] = ha
    if dd.get("z_levels_mm"):
        dd["z_levels_mm"]["prism_bottom"] = -hb
        dd["z_levels_mm"]["prism_top"] = ha
        dd["z_levels_mm"]["load_ring_top"] = ha + _beso9.RING_H_MM
    if dd.get("corner_cylinder_digouts"):
        dd["corner_cylinder_digouts"]["radius_mm"] = corner_r
        dd["corner_cylinder_digouts"]["radius_m"] = corner_r / 1000.0
        dd["corner_cylinder_digouts"]["diameter_mm"] = 2.0 * corner_r
    if dd.get("load_ring"):
        dd["load_ring"]["outer_diameter_mm"] = load_d
        dd["load_ring"]["outer_diameter_m"] = load_d / 1000.0
        dd["load_ring"]["outer_radius_mm"] = load_d / 2.0
        dd["load_ring"]["force_n"] = force
        dd["load_ring"]["z_bottom_mm"] = ha
        dd["load_ring"]["z_top_mm"] = ha + _beso9.RING_H_MM
    if dd.get("beso_settings"):
        dd["beso_settings"]["mass_goal_ratio"] = mass_goal
    dd["description"] = (
        f"可设计域：等边三棱柱（边长 {side/1000.0:g} m，高 {height_total/1000.0:g} m，水面 z=0），"
        f"三顶点挖圆柱 R={corner_r/1000.0:g} m；顶面中心 Ø{load_d/1000.0:g} m 圆环施力 {force:.2e} N（−Z）。"
    )
    summary["beso9_design_domain_from_fcstd"] = dd
    # Alias for steel / restruction consumers
    topo = summary.get("beso9_method1_topology_reconstructed")
    if topo and "beso7_method1_topology_reconstructed" not in summary:
        summary["beso7_method1_topology_reconstructed"] = topo
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Export parameters_summary.json after topology optimization")
    ap.add_argument("--run-dir", type=Path, required=True, help="BESO run directory with file*_state1.inp")
    ap.add_argument("--inp", type=Path, default=None, help="Explicit final state1.inp")
    ap.add_argument("--design-spec", type=Path, default=None)
    ap.add_argument("--fcstd", type=Path, default=None, help="Optional design-domain FCStd for measurement")
    ap.add_argument("--out", type=Path, default=None, help="Output parameters_summary.json path")
    ap.add_argument("--skip-rebuild-export", action="store_true")
    ap.add_argument("--title", type=str, default="拓扑优化重建构型 — 几何参数汇总")
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = (args.out or (run_dir / "parameters_summary.json")).resolve()

    inp = args.inp
    if inp is None:
        inp = _latest_state1_inp(run_dir)
    if inp is None or not Path(inp).is_file():
        print("[FAIL] no file*_state1.inp in run-dir", file=sys.stderr)
        return 2
    inp = Path(inp).resolve()

    design = None
    fcstd = args.fcstd
    if fcstd and Path(fcstd).is_file():
        print(f"[INFO] measuring design domain {fcstd}", flush=True)
        design = _beso9.measure_design_domain(Path(fcstd))
    else:
        spec_path = args.design_spec
        if spec_path is None:
            for cand in (
                run_dir / "design_spec.json",
                run_dir.parent / "design_spec.json",
                BESO9 / "design_spec.json",
            ):
                if cand.is_file():
                    spec_path = cand
                    break
        if spec_path and Path(spec_path).is_file():
            spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
            design = design_dict_from_spec(spec)
            print(f"[INFO] design domain from {spec_path}", flush=True)
            # also copy design_spec into run_dir for packaging
            try:
                (run_dir / "design_spec.json").write_text(
                    json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            except Exception:
                pass
        else:
            print("[WARN] no design_spec/fcstd — using BESO9 default design envelope", flush=True)

    print(f"[INFO] fitting topology from {inp.name}", flush=True)
    leg_fits, hub, counts, solid = fit_topology_from_inp(inp)
    write_measurements_json(
        run_dir / "measurements.json",
        legs=leg_fits,
        hub=hub,
        extra={"source_inp": str(inp), "leg_element_counts": counts},
    )
    print(f"[OK] wrote {run_dir / 'measurements.json'}", flush=True)

    if not args.skip_rebuild_export:
        try:
            _beso9._export_rebuilt(solid, run_dir)
        except Exception as ex:
            print(f"[WARN] rebuilt export failed: {ex}", file=sys.stderr)

    summary = _beso9.build_summary(
        root=BESO9,
        inp=inp,
        leg_fits=leg_fits,
        hub=hub,
        counts=counts,
        solid=solid,
        design=design,
    )
    summary["title"] = args.title
    sf = summary.get("source_files") or {}
    sf["beso9_inp"] = str(inp)
    sf["beso9_measurements"] = str(run_dir / "measurements.json")
    sf["run_dir"] = str(run_dir)
    if args.design_spec or (run_dir / "design_spec.json").is_file():
        sf["design_spec"] = str(args.design_spec or (run_dir / "design_spec.json"))
    summary["source_files"] = sf
    summary = _patch_summary_constants(summary, design)

    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    out_path.write_text(text, encoding="utf-8")
    print(f"[OK] wrote {out_path}", flush=True)
    # also write canonical name in run_dir if out elsewhere
    if out_path.parent.resolve() != run_dir.resolve():
        (run_dir / "parameters_summary.json").write_text(text, encoding="utf-8")
    legs = summary["beso9_method1_topology_reconstructed"]["legs"]
    hub_j = summary["beso9_method1_topology_reconstructed"]["hub_top_plate"]
    print(
        f"[OK] legs R={[x['radius_mm'] for x in legs]} hub_D={hub_j['diameter_mm']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
