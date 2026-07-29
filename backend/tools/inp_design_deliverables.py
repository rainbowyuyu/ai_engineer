"""Export design-space deliverables from CalculiX INP (preview PNG, CSV, STL)."""
from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.tools.cad_drawing_pack import _boundary_tris_from_tets, _mesh_from_inp, resolve_workspace_cad_path
from backend.tools.inp_design_120_sectors import _collect_c3d4_block, _parse_nodes

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib as mpl

if mpl.get_backend().lower() != "agg":
    mpl.use("Agg")

import matplotlib.pyplot as plt

DELIVERABLES_SUBDIR = "_deliverables"
FILE_NAMES = (
    "design_space_preview.png",
    "design_space_nodes.csv",
    "design_space_elements.csv",
    "design_space_surface.stl",
)


def _workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()


def _pick_design_elems(lines: list[str]) -> tuple[str, dict[int, tuple[int, int, int, int]]]:
    for name in ("design_space", "Design_Space", "DESIGN_SPACE"):
        elems = _collect_c3d4_block(lines, name)
        if elems:
            return name, elems
    import re

    pat = re.compile(r"^\*Element\s*,", re.I)
    for line in lines:
        u = line.strip()
        if pat.match(u) and "C3D4" in u.upper():
            m = re.search(r"Elset\s*=\s*([^,\n]+)", u, re.I)
            elset_name = (m.group(1).strip() if m else "C3D4") or "C3D4"
            elems = _collect_c3d4_block(lines, elset_name)
            if elems:
                return elset_name, elems
    raise RuntimeError("INP 中未找到 C3D4 单元块（design_space）")


def _meshio_fallback(src: Path) -> tuple[str, dict[int, tuple[float, float, float]], dict[int, tuple[int, ...]], np.ndarray]:
    """Shell / 混合网格：用 meshio 表面三角化。"""
    points, faces = _mesh_from_inp(src)
    nodes = {i + 1: tuple(float(x) for x in points[i]) for i in range(len(points))}
    elems = {i + 1: (int(f[0]) + 1, int(f[1]) + 1, int(f[2]) + 1) for i, f in enumerate(faces)}
    return "surface_mesh", nodes, elems, np.asarray(faces, dtype=int)


def _write_stl_ascii(path: Path, points: np.ndarray, tris: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("solid design_space_surface\n")
        for tri in tris:
            a, b, c = (int(tri[0]), int(tri[1]), int(tri[2]))
            p0, p1, p2 = points[a], points[b], points[c]
            v1 = p1 - p0
            v2 = p2 - p0
            n = np.cross(v1, v2)
            norm = float(np.linalg.norm(n))
            if norm > 1e-12:
                n = n / norm
            else:
                n = np.array([0.0, 0.0, 1.0])
            f.write(f"  facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}\n")
            f.write("    outer loop\n")
            for idx in (a, b, c):
                p = points[idx]
                f.write(f"      vertex {p[0]:.6e} {p[1]:.6e} {p[2]:.6e}\n")
            f.write("    endloop\n  endfacet\n")
        f.write("endsolid design_space_surface\n")


def _render_preview_png(
    path: Path,
    points: np.ndarray,
    tris: np.ndarray,
    *,
    title: str,
    subtitle: str,
) -> None:
    fig = plt.figure(figsize=(8, 6), dpi=120)
    ax = fig.add_subplot(111, projection="3d")
    verts = points[tris]
    coll = ax.plot_trisurf(
        points[:, 0],
        points[:, 1],
        points[:, 2],
        triangles=tris,
        color="#3b82f6",
        alpha=0.82,
        linewidth=0.08,
        edgecolor="#1e3a8a",
    )
    coll.set_edgecolor("#1e3a8a")
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    fig.text(0.02, 0.02, subtitle, fontsize=8, color="#64748b")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)


def build_inp_design_deliverables(
    path_str: str,
    *,
    workspace_root: Path | None = None,
    runs_root: Path | None = None,
) -> dict[str, Any]:
    root = workspace_root or _workspace_root()
    runs = runs_root or (root / "runs")
    src = resolve_workspace_cad_path(path_str, root)
    if src.suffix.lower() != ".inp":
        raise ValueError("仅支持 .inp 文件")

    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        elset_name, elems = _pick_design_elems(lines)
        nodes = _parse_nodes(lines)
        if not nodes:
            raise RuntimeError("INP 无 *NODE 数据")
        node_ids = sorted({nid for nn in elems.values() for nid in nn})
        points = np.array([nodes[nid] for nid in node_ids], dtype=float)
        node_index = {nid: i for i, nid in enumerate(node_ids)}
        tets = np.array(
            [[node_index[a], node_index[b], node_index[c], node_index[d]] for a, b, c, d in elems.values()]
        )
        tris = _boundary_tris_from_tets(tets)
        elem_rows = elems
    except RuntimeError:
        elset_name, nodes, elem_rows, tris = _meshio_fallback(src)
        node_ids = sorted(nodes.keys())
        points = np.array([nodes[nid] for nid in node_ids], dtype=float)
        tris = np.asarray(tris, dtype=int)

    if tris.size == 0:
        raise RuntimeError("无法提取外表面三角网格")

    pack_id = uuid.uuid4().hex
    out_dir = runs / DELIVERABLES_SUBDIR / pack_id
    out_dir.mkdir(parents=True, exist_ok=True)

    rel_src = str(src.relative_to(root)).replace("\\", "/")
    nodes_csv = out_dir / FILE_NAMES[1]
    elems_csv = out_dir / FILE_NAMES[2]
    stl_path = out_dir / FILE_NAMES[3]
    png_path = out_dir / FILE_NAMES[0]

    with nodes_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["NodeID", "X", "Y", "Z"])
        for nid in node_ids:
            x, y, z = nodes[nid]
            w.writerow([nid, x, y, z])

    with elems_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ElementID", "Type", "Node1", "Node2", "Node3", "Node4", "Node5", "Node6", "Node7", "Node8"])
        for eid, nn in sorted(elem_rows.items()):
            row = [eid, "C3D4" if len(nn) == 4 else f"S{len(nn)}", *list(nn)]
            while len(row) < 11:
                row.append("")
            w.writerow(row[:11])

    _write_stl_ascii(stl_path, points, tris)
    _render_preview_png(
        png_path,
        points,
        tris,
        title=f"Design space preview · {src.name}",
        subtitle=f"Elset={elset_name} · {rel_src} · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    )

    files: dict[str, str] = {}
    for name in FILE_NAMES:
        rel = (out_dir / name).relative_to(root).as_posix()
        files[name] = f"/{rel}"

    manifest = {
        "pack_id": pack_id,
        "source_path": rel_src,
        "elset": elset_name,
        "node_count": len(node_ids),
        "element_count": len(elem_rows),
        "triangle_count": int(len(tris)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    (out_dir / "manifest.json").write_text(
        __import__("json").dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "pack_id": pack_id,
        "source_path": rel_src,
        "elset": elset_name,
        "base_url": f"/runs/{DELIVERABLES_SUBDIR}/{pack_id}",
        "files": files,
        "manifest_url": f"/runs/{DELIVERABLES_SUBDIR}/{pack_id}/manifest.json",
    }


__all__ = ["build_inp_design_deliverables", "FILE_NAMES", "DELIVERABLES_SUBDIR"]
