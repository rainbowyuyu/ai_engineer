"""BESO7 GA drawing assembly: original edge columns + optimized smooth braces.

Builds a solid-like triangle mesh for engineering drawings (not topology voxel mesh):
- nondesign edge columns + heave-plate footings (from BESO3 / optimized_geometry.json)
- method-1 reconstructed diagonal braces + hub top plate (FreeCAD STL when available,
  else parametric cylinders from geometry JSON)
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def _cylinder_mesh(
    p0: list[float],
    p1: list[float],
    radius: float,
    *,
    n_circ: int = 48,
    n_len: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    a = [float(p1[i]) - float(p0[i]) for i in range(3)]
    length = math.sqrt(sum(x * x for x in a)) or 1.0
    axis = [x / length for x in a]
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
            offset = [radius * (math.cos(ang) * ux[j] + math.sin(ang) * uy[j]) for j in range(3)]
            verts.append([c[j] + offset[j] for j in range(3)])
    faces: list[list[int]] = []
    for i in range(n_len):
        for k in range(n_circ):
            a0 = i * n_circ + k
            a1 = i * n_circ + (k + 1) % n_circ
            b0 = (i + 1) * n_circ + k
            b1 = (i + 1) * n_circ + (k + 1) % n_circ
            faces.append([a0, a1, b1])
            faces.append([a0, b1, b0])
    # Cap disks
    for end, zsign in ((0, 1), (n_len, -1)):
        center_idx = len(verts)
        c = [float(p0[j]) + (end / n_len) * (float(p1[j]) - float(p0[j])) for j in range(3)]
        verts.append(c)
        base = end * n_circ
        for k in range(n_circ):
            i0 = base + k
            i1 = base + (k + 1) % n_circ
            if zsign > 0:
                faces.append([center_idx, i0, i1])
            else:
                faces.append([center_idx, i1, i0])
    return np.asarray(verts, dtype=float), np.asarray(faces, dtype=int)


def _tapered_leg_mesh(
    p0: list[float],
    p1: list[float],
    radii: list[float],
    fracs: list[float] | None = None,
    *,
    n_circ: int = 36,
) -> tuple[np.ndarray, np.ndarray]:
    """Loft-like tube with station radii along axis."""
    if not radii:
        r = 1500.0
        return _cylinder_mesh(p0, p1, r, n_circ=n_circ, n_len=10)
    n_len = max(len(radii) - 1, 1)
    if fracs is None or len(fracs) != len(radii):
        fracs = [i / n_len for i in range(n_len + 1)]
        while len(fracs) < len(radii):
            fracs.append(1.0)
        fracs = fracs[: len(radii)]
        n_len = len(radii) - 1

    a = [float(p1[i]) - float(p0[i]) for i in range(3)]
    length = math.sqrt(sum(x * x for x in a)) or 1.0
    axis = [x / length for x in a]
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
    for t, r in zip(fracs, radii):
        c = [float(p0[j]) + float(t) * (float(p1[j]) - float(p0[j])) for j in range(3)]
        rr = max(float(r), 1.0)
        for k in range(n_circ):
            ang = 2 * math.pi * k / n_circ
            offset = [rr * (math.cos(ang) * ux[j] + math.sin(ang) * uy[j]) for j in range(3)]
            verts.append([c[j] + offset[j] for j in range(3)])
    faces: list[list[int]] = []
    n_sta = len(radii)
    for i in range(n_sta - 1):
        for k in range(n_circ):
            a0 = i * n_circ + k
            a1 = i * n_circ + (k + 1) % n_circ
            b0 = (i + 1) * n_circ + k
            b1 = (i + 1) * n_circ + (k + 1) % n_circ
            faces.append([a0, a1, b1])
            faces.append([a0, b1, b0])
    return np.asarray(verts, dtype=float), np.asarray(faces, dtype=int)


def _merge_meshes(
    parts: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    if not parts:
        raise ValueError("no mesh parts")
    pts_list: list[np.ndarray] = []
    fac_list: list[np.ndarray] = []
    offset = 0
    for pts, fac in parts:
        pts_list.append(np.asarray(pts, dtype=float))
        fac_list.append(np.asarray(fac, dtype=int) + offset)
        offset += len(pts)
    return np.vstack(pts_list), np.vstack(fac_list)


def _load_tri_mesh(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    if not path.is_file():
        return None
    try:
        import meshio

        mesh = meshio.read(path)
        points = np.asarray(mesh.points, dtype=float)
        tris: list[np.ndarray] = []
        for cell in mesh.cells:
            if "tri" in str(cell.type).lower():
                tris.append(np.asarray(cell.data)[:, :3])
        if not tris:
            return None
        return points, np.vstack(tris)
    except Exception:
        pass
    if path.suffix.lower() == ".obj":
        try:
            from backend.tools.cad_drawing_pack import _parse_obj

            return _parse_obj(path)
        except Exception:
            return None
    return None


def _column_radius_mm(col: dict[str, Any], stats: dict[str, Any] | None = None) -> float:
    r = float(col.get("radius_mm") or 0)
    # Prefer measured shaft stats when JSON radius looks like an envelope
    mean_r = None
    if stats:
        mean_r = (stats.get("shaft_radius_mm") or {}).get("mean")
    if mean_r and r > 1.35 * float(mean_r):
        return float(mean_r)
    if r > 0:
        return r
    return float(mean_r or 6000.0)


def build_platform_ga_assembly(
    workspace_root: Path,
    *,
    job_id: str | None = None,
    geometry_path: Path | None = None,
    out_dir: Path | None = None,
    prefer_reconstructed_stl: bool = False,
) -> dict[str, Any]:
    """
    Write ``drawing_assembly.stl`` (+ ``.obj``) for Phase VI GA drawing.

    Composition: original side columns + heave plates + optimized braces/top plate.

    Default prefers parametric cylinders (smooth outlines) over dense FreeCAD STL
    tessellation — better for engineering drawing silhouette projection.
    """
    root = Path(workspace_root).resolve()
    geom_path = Path(geometry_path) if geometry_path else (root / "rules" / "optimized_geometry.json")
    if not geom_path.is_file():
        raise FileNotFoundError(f"geometry missing: {geom_path}")
    geometry = json.loads(geom_path.read_text(encoding="utf-8"))

    jid = str(job_id or "").strip()
    if out_dir is None:
        out_dir = (root / "runs" / jid) if jid else (root / "runs" / "_ga_assembly")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parts: list[tuple[np.ndarray, np.ndarray]] = []
    mode = "parametric_columns_and_braces"
    recon_used: str | None = None

    # Original columns + footings always from JSON
    ref = geometry.get("beso3_reference_from_fcstd") or {}
    stats = ref.get("edge_columns_statistics") or {}
    for col in ref.get("edge_columns_nondesign") or []:
        cx, cy = float(col["center_xy_mm"][0]), float(col["center_xy_mm"][1])
        z0 = float(col.get("z_bottom_mm") or -14000.0)
        z1 = float(col.get("z_top_mm") or 12000.0)
        r = _column_radius_mm(col, stats)
        parts.append(_cylinder_mesh([cx, cy, z0], [cx, cy, z1], r, n_circ=48, n_len=10))
        foot = col.get("footing") or {}
        if foot:
            fx, fy = float(foot["center_xy_mm"][0]), float(foot["center_xy_mm"][1])
            fz0 = float(foot.get("z_bottom_mm") or -20000.0)
            fz1 = float(foot.get("z_top_mm") or z0)
            fr = float(foot.get("equivalent_radius_mm") or r * 1.15)
            parts.append(_cylinder_mesh([fx, fy, fz0], [fx, fy, fz1], fr, n_circ=48, n_len=4))

    # Optimized smooth structure: prefer FreeCAD reconstructed STL from Phase III
    recon_candidates: list[Path] = []
    if jid:
        run_dir = root / "runs" / jid
        recon_candidates.extend(
            [
                run_dir / "reconstructed.stl",
                run_dir / "method1_parametric" / "preview.stl",
                run_dir / "reconstructed.obj",
            ]
        )
    recon_candidates.append(
        root / "examples" / "beso" / "beso7" / "addition" / "method1_parametric" / "preview.stl"
    )

    loaded_recon = None
    if prefer_reconstructed_stl:
        for cand in recon_candidates:
            loaded_recon = _load_tri_mesh(cand)
            if loaded_recon is not None:
                recon_used = str(cand)
                mode = "columns_plus_reconstructed_stl"
                parts.append(loaded_recon)
                break

    if loaded_recon is None:
        # Fallback: parametric braces + top plate from JSON
        beso7 = geometry.get("beso7_method1_topology_reconstructed") or {}
        for leg in beso7.get("legs") or []:
            base = list(leg.get("base_xyz_mm") or [0, 0, 0])
            top = list(leg.get("top_xyz_mm") or [0, 0, 1000])
            radii = [float(x) for x in (leg.get("station_radii_mm") or [])]
            fracs = [float(x) for x in (leg.get("station_fracs") or [])] or None
            if not radii:
                radii = [float(leg.get("radius_mm") or 3000.0)] * 4
            parts.append(_tapered_leg_mesh(base, top, radii, fracs, n_circ=36))
        plate = beso7.get("hub_top_plate") or {}
        if plate.get("center_xy_mm") and plate.get("radius_mm"):
            cx, cy = float(plate["center_xy_mm"][0]), float(plate["center_xy_mm"][1])
            z0 = float(plate.get("z_bottom_mm") or 7500.0)
            z1 = float(plate.get("z_top_mm") or (z0 + float(plate.get("thickness_mm") or 4000.0)))
            parts.append(
                _cylinder_mesh([cx, cy, z0], [cx, cy, z1], float(plate["radius_mm"]), n_circ=48, n_len=3)
            )
        # short central stub
        top_stub = ref.get("central_extension_column_nondesign") or {}
        if top_stub and plate:
            cx, cy = float(top_stub["center_xy_mm"][0]), float(top_stub["center_xy_mm"][1])
            z0 = float(plate.get("z_top_mm") or 12000.0)
            z1 = z0 + 8000.0
            parts.append(
                _cylinder_mesh(
                    [cx, cy, z0],
                    [cx, cy, z1],
                    float(top_stub.get("radius_mm") or 3250.0),
                    n_circ=36,
                    n_len=4,
                )
            )
        mode = "parametric_columns_and_braces"

    if not parts:
        raise RuntimeError("GA assembly empty — check optimized_geometry.json")

    points, faces = _merge_meshes(parts)
    stl_path = out_dir / "drawing_assembly.stl"
    obj_path = out_dir / "drawing_assembly.obj"

    with obj_path.open("w", encoding="utf-8") as f:
        f.write("# BESO7 GA assembly: original columns + optimized smooth structure\n")
        for v in points:
            f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
        for tri in faces:
            f.write(f"f {int(tri[0]) + 1} {int(tri[1]) + 1} {int(tri[2]) + 1}\n")

    try:
        import meshio

        mesh = meshio.Mesh(points=points, cells=[("triangle", faces)])
        mesh.write(stl_path, file_format="stl")
    except Exception:
        stl_path = obj_path

    if not stl_path.is_file():
        stl_path = obj_path

    manifest = {
        "mode": mode,
        "reconstructed_source": recon_used,
        "n_points": int(len(points)),
        "n_faces": int(len(faces)),
        "parts": "edge_columns+heave_plates+optimized_braces_top_plate",
        "stl": stl_path.name if stl_path.suffix.lower() == ".stl" else None,
        "obj": obj_path.name,
    }
    (out_dir / "drawing_assembly_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    primary = stl_path if stl_path.suffix.lower() == ".stl" and stl_path.is_file() else obj_path
    return {
        "ok": True,
        "path": primary,
        "stl_path": stl_path if stl_path.suffix.lower() == ".stl" and stl_path.is_file() else None,
        "obj_path": obj_path,
        "mode": mode,
        "manifest": manifest,
        "n_points": int(len(points)),
        "n_faces": int(len(faces)),
    }
