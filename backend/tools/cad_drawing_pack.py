"""Generate preview-grade multi-view CAD drawing sheets from workspace paths (INP / IGES / STEP / OBJ)."""
from __future__ import annotations

import io
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib as mpl

if mpl.get_backend().lower() != "agg":
    mpl.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager as _fm
CAD_EXTS = {".inp", ".iges", ".igs", ".step", ".stp", ".obj", ".vtk", ".stl"}
DRAWING_SUBDIR = "_cad_drawings"

# Windows / common CJK fonts so title block & brand render (not tofu boxes).
_CJK_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Arial Unicode MS",
)
_cjk_font_ready = False

# ISO A-series landscape (mm) — screen-friendly default A3
_PAPER_MM: dict[str, tuple[float, float]] = {
    "A3": (420.0, 297.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
}


def _configure_cjk_font() -> str | None:
    """Prefer a system CJK font for matplotlib sheet chrome."""
    global _cjk_font_ready
    if _cjk_font_ready:
        family = mpl.rcParams.get("font.family")
        if isinstance(family, list) and family:
            return str(family[0])
        return str(family) if family else None

    available = {f.name for f in _fm.fontManager.ttflist}
    chosen: str | None = None
    for name in _CJK_FONT_CANDIDATES:
        if name in available:
            chosen = name
            break
    if chosen is None:
        for path in (
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
        ):
            p = Path(path)
            if not p.is_file():
                continue
            try:
                _fm.fontManager.addfont(str(p))
                chosen = _fm.FontProperties(fname=str(p)).get_name()
                break
            except Exception:
                continue

    if chosen:
        mpl.rcParams["font.family"] = chosen
        mpl.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
        mpl.rcParams["axes.unicode_minus"] = False
    _cjk_font_ready = True
    return chosen


def _workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve()


def resolve_workspace_cad_path(path_str: str, workspace_root: Path | None = None) -> Path:
    root = workspace_root or _workspace_root()
    raw = str(path_str or "").strip().lstrip("@").replace("\\", "/")
    if not raw:
        raise FileNotFoundError("路径为空")
    p = Path(raw)
    if not p.is_absolute():
        p = root / raw
    p = p.resolve()
    if not str(p).startswith(str(root.resolve())):
        raise PermissionError("路径必须位于工作区内")
    if not p.is_file():
        raise FileNotFoundError(f"文件不存在: {p}")
    if p.suffix.lower() not in CAD_EXTS:
        raise ValueError(f"不支持的格式: {p.suffix}")
    return p


def _boundary_tris_from_tets(tets: np.ndarray) -> np.ndarray:
    face_count: dict[tuple[int, ...], int] = defaultdict(int)
    face_nodes: dict[tuple[int, ...], tuple[int, int, int]] = {}
    for tet in tets:
        n = [int(tet[i]) for i in range(4)]
        for a, b, c in ((n[0], n[1], n[2]), (n[0], n[1], n[3]), (n[0], n[2], n[3]), (n[1], n[2], n[3])):
            key = tuple(sorted((a, b, c)))
            face_count[key] += 1
            face_nodes[key] = (a, b, c)
    tris = [face_nodes[k] for k, c in face_count.items() if c == 1]
    if not tris:
        return np.zeros((0, 3), dtype=int)
    return np.asarray(tris, dtype=int)


def _mesh_from_inp(inp_path: Path) -> tuple[np.ndarray, np.ndarray]:
    import meshio
    from meshio.abaqus._abaqus import read_buffer

    text = inp_path.read_text(encoding="utf-8", errors="replace")
    mesh = read_buffer(io.StringIO(text))
    points = np.asarray(mesh.points, dtype=float)
    if points.size == 0:
        raise RuntimeError("INP 无节点")
    tris: list[np.ndarray] = []
    for cell in mesh.cells:
        typ = str(cell.type).lower()
        data = np.asarray(cell.data)
        if typ in ("triangle", "tri") and data.size:
            tris.append(data[:, :3])
        elif typ in ("tetra", "tetra10") and data.size:
            tris.append(_boundary_tris_from_tets(data))
        elif "quad" in typ and data.size:
            for q in data:
                a, b, c, d = int(q[0]), int(q[1]), int(q[2]), int(q[3])
                tris.append(np.array([[a, b, c], [a, c, d]], dtype=int))
    if not tris:
        raise RuntimeError("INP 中未找到可绘制的三角/四面体单元")
    faces = np.vstack(tris)
    if len(faces) > 12000:
        step = max(1, len(faces) // 12000)
        faces = faces[::step]
    return points, faces


def _parse_obj(obj_path: Path) -> tuple[np.ndarray, np.ndarray]:
    verts: list[list[float]] = []
    faces: list[list[int]] = []
    for line in obj_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            idx = []
            for part in line.split()[1:]:
                idx.append(int(part.split("/")[0]) - 1)
            if len(idx) >= 3:
                for i in range(1, len(idx) - 1):
                    faces.append([idx[0], idx[i], idx[i + 1]])
    if not verts or not faces:
        raise RuntimeError("OBJ 无有效几何")
    return np.asarray(verts, dtype=float), np.asarray(faces, dtype=int)


def _cad_to_obj(cad_path: Path, out_obj: Path) -> Path:
    from backend.tools.freecad_export_obj import run_freecad_export_obj

    run_freecad_export_obj(cad_path, out_obj, linear_deflection=1200.0, timeout_s=300.0)
    return out_obj


def _load_mesh(path: Path, work_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    ext = path.suffix.lower()
    if ext == ".inp":
        return _mesh_from_inp(path)
    if ext == ".obj":
        return _parse_obj(path)
    if ext == ".vtk":
        import meshio

        mesh = meshio.read(path)
        points = np.asarray(mesh.points, dtype=float)
        tris = []
        for cell in mesh.cells:
            if "tri" in str(cell.type).lower():
                tris.append(np.asarray(cell.data)[:, :3])
        if not tris:
            raise RuntimeError("VTK 无三角面片")
        return points, np.vstack(tris)
    if ext in (".iges", ".igs", ".step", ".stp"):
        obj = work_dir / f"{path.stem}_preview.obj"
        _cad_to_obj(path, obj)
        return _parse_obj(obj)
    if ext == ".stl":
        import meshio

        mesh = meshio.read(path)
        points = np.asarray(mesh.points, dtype=float)
        tris = []
        for cell in mesh.cells:
            if "tri" in str(cell.type).lower():
                tris.append(np.asarray(cell.data)[:, :3])
        if not tris:
            raise RuntimeError("STL 无三角面片")
        return points, np.vstack(tris)
    raise ValueError(f"unsupported: {ext}")


def _view_angles(name: str) -> tuple[float, float]:
    views = {
        "iso": (28, -48),
        "top": (90, -90),
        "front": (0, -90),
        "right": (0, 0),
    }
    return views.get(name, (25, -60))


BRAND_NAME = "AI Engineer"
LOGO_REL_CANDIDATES = (
    "frontend_static/assets/beso-agent-mark.png",
    "frontend_static/assets/beso-agent-mark.svg",
)
VIEW_LABELS = {
    "iso": "A  轴测图",
    "top": "B  俯视图（总布置）",
    "front": "C  正视图",
    "right": "D  侧视图",
}
_logo_cache: Any = None


def _normalize_sheet_size(sheet_size: str | None) -> str:
    key = str(sheet_size or "A3").strip().upper()
    return key if key in _PAPER_MM else "A3"


def _normalize_layout(layout: str | None) -> str:
    key = str(layout or "ga").strip().lower()
    return key if key in ("ga", "quad") else "ga"


def _paper_spec(sheet_size: str | None = "A3") -> dict[str, Any]:
    """GB/T 14689-inspired paper geometry in mm + matplotlib figure inches."""
    size = _normalize_sheet_size(sheet_size)
    w_mm, h_mm = _PAPER_MM[size]
    # ~150 dpi equivalent in inches for screen; PDF uses vector paths
    dpi = 160 if size == "A3" else 130
    figsize = (w_mm / 25.4, h_mm / 25.4)
    # Extra margin for zone grid letters/numbers (图一风格区格)
    return {
        "sheet_size": size,
        "w_mm": w_mm,
        "h_mm": h_mm,
        "figsize": figsize,
        "dpi": dpi,
        "margin_left": 0.042,
        "margin_right": 0.028,
        "margin_bottom": 0.028,
        "margin_top": 0.028,
        "title_block_h": 0.118,
        "title_block_w": 0.38,
        "rev_h": 0.024,
        "param_h": 0.055,
        "zone_cols": 12 if size != "A3" else 10,
        "zone_rows": 8 if size == "A3" else 12,
    }


def _guess_to_mm_factor(span: float) -> float:
    """Heuristic: large coords → already mm; small → meters."""
    a = abs(float(span))
    if a <= 0:
        return 1.0
    if a >= 500:  # likely mm
        return 1.0
    if a >= 50:  # ambiguous; treat as mm
        return 1.0
    return 1000.0  # likely m


def _model_span_mm(bbox: dict[str, float]) -> float:
    dx = float(bbox.get("dx") or 0)
    dy = float(bbox.get("dy") or 0)
    dz = float(bbox.get("dz") or 0)
    span = max(dx, dy, dz, 0.0)
    return span * _guess_to_mm_factor(span)


def _compute_drawing_scale(model_span_mm: float, drawable_mm: float) -> tuple[str, int]:
    """Pick a standard engineering scale 1:N so the model fits drawable width."""
    if model_span_mm <= 0 or drawable_mm <= 0:
        return "1:1", 1
    raw = model_span_mm / max(drawable_mm * 0.85, 1.0)
    candidates = (
        1,
        2,
        5,
        10,
        20,
        25,
        50,
        100,
        200,
        250,
        500,
        1000,
        2000,
        5000,
        10000,
    )
    n = candidates[-1]
    for c in candidates:
        if c >= raw:
            n = c
            break
    return f"1:{n}", int(n)


def _resolve_logo_path() -> Path | None:
    root = _workspace_root()
    for rel in LOGO_REL_CANDIDATES:
        p = root / rel
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return p
    return None


def _load_logo_array():
    """Load brand mark as RGBA ndarray for matplotlib OffsetImage."""
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache
    path = _resolve_logo_path()
    if path is None:
        _logo_cache = False
        return None
    try:
        from PIL import Image

        img = Image.open(path).convert("RGBA")
        _logo_cache = np.asarray(img)
        return _logo_cache
    except Exception:
        _logo_cache = False
        return None


def _fmt_len(v: float) -> str:
    a = abs(float(v))
    if a >= 1e4:
        return f"{v / 1000.0:.2f} m"
    if a >= 1:
        return f"{v:.1f}"
    if a >= 1e-3:
        return f"{v:.3f}"
    return f"{v:.3e}"


def _fmt_dim(v: float, *, unit_to_mm: float = 1.0) -> str:
    """Dimension text in model units scaled by ``unit_to_mm`` (never infer from a single edge)."""
    mm = float(v) * float(unit_to_mm)
    a = abs(mm)
    if a < 1e-6:
        return "0"
    if a >= 1000:
        return f"{mm / 1000.0:.2f} m"
    if a >= 10:
        return f"{mm:.0f}"
    if a >= 1:
        return f"{mm:.1f}"
    return f"{mm:.2f}"


def _bbox_from_points(points: np.ndarray) -> dict[str, float]:
    if points is None or len(points) == 0:
        return {"dx": 0.0, "dy": 0.0, "dz": 0.0, "xmin": 0, "xmax": 0, "ymin": 0, "ymax": 0, "zmin": 0, "zmax": 0}
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    return {
        "xmin": float(mins[0]),
        "xmax": float(maxs[0]),
        "ymin": float(mins[1]),
        "ymax": float(maxs[1]),
        "zmin": float(mins[2]) if points.shape[1] > 2 else 0.0,
        "zmax": float(maxs[2]) if points.shape[1] > 2 else 0.0,
        "dx": float(maxs[0] - mins[0]),
        "dy": float(maxs[1] - mins[1]),
        "dz": float((maxs[2] - mins[2]) if points.shape[1] > 2 else 0.0),
    }


def _bbox_from_line_views(views: dict[str, Any]) -> dict[str, float]:
    """Estimate envelope from plan + front projections (model units)."""
    plan = (views.get("top") or {}).get("polylines") or []
    front = (views.get("front") or {}).get("polylines") or []
    xs: list[float] = []
    ys: list[float] = []
    for poly in plan:
        for p in poly:
            xs.append(float(p[0]))
            ys.append(float(p[1]))
    zs: list[float] = []
    for poly in front:
        for p in poly:
            if len(xs) == 0:
                xs.append(float(p[0]))
            zs.append(float(p[1]))
    if not xs or not ys:
        return {"dx": 0.0, "dy": 0.0, "dz": 0.0}
    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = (max(zs) - min(zs)) if zs else 0.0
    return {"dx": float(dx), "dy": float(dy), "dz": float(dz)}


def _view_basis(view_key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (u, v, view_dir) orthonormal basis for orthographic / iso projection."""
    key = str(view_key or "top").lower()
    if key == "top":
        u = np.array([1.0, 0.0, 0.0])
        v = np.array([0.0, 1.0, 0.0])
        d = np.array([0.0, 0.0, 1.0])
    elif key == "front":
        u = np.array([1.0, 0.0, 0.0])
        v = np.array([0.0, 0.0, 1.0])
        d = np.array([0.0, -1.0, 0.0])
    elif key == "right":
        u = np.array([0.0, 1.0, 0.0])
        v = np.array([0.0, 0.0, 1.0])
        d = np.array([1.0, 0.0, 0.0])
    else:  # iso
        d = np.array([1.0, 1.0, 1.0], dtype=float)
        d /= np.linalg.norm(d)
        arb = np.array([0.0, 0.0, 1.0])
        u = np.cross(d, arb)
        if np.linalg.norm(u) < 1e-9:
            u = np.cross(d, np.array([1.0, 0.0, 0.0]))
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        v /= np.linalg.norm(v)
    return u, v, d


def _mesh_face_normals(points: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tris = points[faces]
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lens = np.linalg.norm(n, axis=1)
    lens[lens < 1e-15] = 1.0
    return n / lens[:, None]


def _collect_mesh_edges(faces: np.ndarray) -> tuple[list[tuple[int, int]], dict[tuple[int, int], list[int]]]:
    """Unique undirected edges + face adjacency."""
    adj: dict[tuple[int, int], list[int]] = defaultdict(list)
    for fi, face in enumerate(faces):
        a, b, c = int(face[0]), int(face[1]), int(face[2])
        for i, j in ((a, b), (b, c), (c, a)):
            key = (i, j) if i < j else (j, i)
            adj[key].append(fi)
    edges = list(adj.keys())
    return edges, adj


def _project_xy(points: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.column_stack((points @ u, points @ v))


def _hull_ring(xy: np.ndarray) -> list[list[float]]:
    """Convex hull ring in 2D (closed)."""
    if len(xy) < 3:
        return [[float(p[0]), float(p[1])] for p in xy]
    try:
        from scipy.spatial import ConvexHull

        hull = ConvexHull(xy)
        ring = [[float(xy[i, 0]), float(xy[i, 1])] for i in hull.vertices]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        return ring
    except Exception:
        return [[float(p[0]), float(p[1])] for p in xy]


def project_mesh_to_view_polylines(
    points: np.ndarray,
    faces: np.ndarray,
    view_key: str,
    *,
    max_edges: int = 8000,
    silhouette_mode: str = "mesh",
) -> list[list[list[float]]]:
    """
    Professional 2D outline from a triangle mesh: boundary + silhouette edges only
    (no internal triangulation wireframe).

    ``silhouette_mode``:
    - ``mesh``: boundary + facing flip + sharp creases (topology / FEM surfaces)
    - ``solid``: boundary + facing flip only — smooth cylinders/CAD solids look clean
    """
    pts = np.asarray(points, dtype=float)
    fac = np.asarray(faces, dtype=int)
    if len(pts) == 0 or len(fac) == 0:
        return []
    # Cap faces for huge INP surfaces
    if len(fac) > 40000:
        step = max(1, len(fac) // 40000)
        fac = fac[::step]
    u, v, view_dir = _view_basis(view_key)
    normals = _mesh_face_normals(pts, fac)
    facing = normals @ view_dir
    edges, adj = _collect_mesh_edges(fac)
    boundary: list[tuple[int, int]] = []
    silhouette: list[tuple[int, int]] = []
    solid = str(silhouette_mode or "mesh").strip().lower() == "solid"
    crease_cos = -1.0 if solid else 0.35
    for e, fis in adj.items():
        if len(fis) == 1:
            boundary.append(e)
            continue
        if len(fis) >= 2:
            f0, f1 = facing[fis[0]], facing[fis[1]]
            n0, n1 = normals[fis[0]], normals[fis[1]]
            # silhouette / sharp crease only — never draw coplanar internal triangulation
            if f0 * f1 <= 0.0 or (crease_cos >= 0 and float(n0 @ n1) < crease_cos):
                silhouette.append(e)

    def elen(e: tuple[int, int]) -> float:
        dlt = pts[e[1]] - pts[e[0]]
        return float(np.dot(dlt, dlt))

    # Prefer all boundary; cap silhouette so dense INP stays clean
    silhouette_cap = max(400, max_edges - len(boundary))
    if len(silhouette) > silhouette_cap:
        silhouette = sorted(silhouette, key=elen, reverse=True)[:silhouette_cap]
    keep = boundary + silhouette
    if len(keep) > max_edges:
        keep = sorted(keep, key=elen, reverse=True)[:max_edges]
    xy = _project_xy(pts, u, v)
    polys: list[list[list[float]]] = []
    for a, b in keep:
        polys.append([[float(xy[a, 0]), float(xy[a, 1])], [float(xy[b, 0]), float(xy[b, 1])]])
    # Outer envelope as thick contour ring
    hull = _hull_ring(xy)
    if len(hull) >= 3:
        polys.append(hull)
    return polys


def mesh_to_view_dict(
    points: np.ndarray,
    faces: np.ndarray,
    *,
    silhouette_mode: str = "mesh",
) -> dict[str, Any]:
    """Build freecad-like views dict from mesh for unified sheet renderer."""
    views: dict[str, Any] = {}
    for key in ("iso", "top", "front", "right"):
        polys = project_mesh_to_view_polylines(
            points, faces, key, silhouette_mode=silhouette_mode
        )
        views[key] = {"polylines": polys, "polyline_count": len(polys)}
    return views


def _poly_length(poly: list) -> float:
    if len(poly) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(poly)):
        dx = float(poly[i][0]) - float(poly[i - 1][0])
        dy = float(poly[i][1]) - float(poly[i - 1][1])
        total += (dx * dx + dy * dy) ** 0.5
    return total


def _draw_scale_bar(
    ax,
    span: float,
    *,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
) -> None:
    """CAD-style scale bar in a reserved margin below the geometry."""
    if span <= 0:
        return
    raw = span / 5.0
    exp = 10 ** int(np.floor(np.log10(raw))) if raw > 0 else 1.0
    nice = exp
    for m in (1, 2, 5, 10):
        if m * exp <= raw * 1.2:
            nice = m * exp

    pad_side = 0.08 * span
    pad_top = 0.06 * span
    pad_bottom = 0.22 * span
    ax.set_xlim(xmin - pad_side, xmax + pad_side)
    ax.set_ylim(ymin - pad_bottom, ymax + pad_top)

    tick = 0.012 * span
    x0 = xmin
    y0 = ymin - 0.10 * span
    ax.fill_between([x0, x0 + nice / 2], y0 - tick * 0.35, y0 + tick * 0.35, color="#111827", zorder=5, clip_on=False)
    ax.plot([x0, x0 + nice], [y0, y0], color="#111827", linewidth=1.2, solid_capstyle="butt", clip_on=False, zorder=6)
    ax.plot([x0, x0], [y0 - tick, y0 + tick], color="#111827", linewidth=0.9, clip_on=False, zorder=6)
    ax.plot([x0 + nice, x0 + nice], [y0 - tick, y0 + tick], color="#111827", linewidth=0.9, clip_on=False, zorder=6)
    ax.text(
        x0 + nice / 2,
        y0 - 0.028 * span,
        _fmt_len(nice),
        ha="center",
        va="top",
        fontsize=6.5,
        color="#111827",
        clip_on=False,
        zorder=6,
    )


def _draw_centerlines(ax, xmin: float, xmax: float, ymin: float, ymax: float) -> None:
    """Dash-dot centerlines through view envelope (CAD convention)."""
    cx = 0.5 * (xmin + xmax)
    cy = 0.5 * (ymin + ymax)
    span = max(xmax - xmin, ymax - ymin, 1e-9)
    pad = 0.04 * span
    kw = {"color": "#6b7280", "linewidth": 0.45, "linestyle": (0, (8, 3, 1.5, 3)), "zorder": 2, "clip_on": False}
    ax.plot([xmin - pad, xmax + pad], [cy, cy], **kw)
    ax.plot([cx, cx], [ymin - pad, ymax + pad], **kw)


def _draw_overall_dimensions(
    ax,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    *,
    unit_to_mm: float = 1.0,
) -> None:
    """Extension lines + bidirectional arrows for overall W × H."""
    w = xmax - xmin
    h = ymax - ymin
    span = max(w, h, 1e-9)
    # Skip degenerate axes (flat plate → H≈0)
    draw_w = abs(w) > span * 1e-4
    draw_h = abs(h) > span * 1e-4
    if not draw_w and not draw_h:
        return
    gap = 0.07 * span
    ext = 0.02 * span
    color = "#111827"
    lw = 0.5

    if draw_w:
        y_dim = ymin - gap
        ax.plot([xmin, xmin], [ymin, y_dim - ext * 0.25], color=color, linewidth=lw, clip_on=False, zorder=7)
        ax.plot([xmax, xmax], [ymin, y_dim - ext * 0.25], color=color, linewidth=lw, clip_on=False, zorder=7)
        ax.annotate(
            "",
            xy=(xmax, y_dim),
            xytext=(xmin, y_dim),
            arrowprops={"arrowstyle": "<|-|>", "color": color, "lw": 0.65, "mutation_scale": 8, "shrinkA": 0, "shrinkB": 0},
            annotation_clip=False,
            zorder=8,
        )
        ax.text(
            0.5 * (xmin + xmax),
            y_dim - 0.028 * span,
            _fmt_dim(w, unit_to_mm=unit_to_mm),
            ha="center",
            va="top",
            fontsize=7.5,
            fontweight="600",
            color=color,
            clip_on=False,
            zorder=8,
            bbox={"facecolor": "#ffffff", "edgecolor": "none", "pad": 0.5},
        )

    if draw_h:
        x_dim = xmax + gap
        ax.plot([xmax, x_dim + ext * 0.25], [ymin, ymin], color=color, linewidth=lw, clip_on=False, zorder=7)
        ax.plot([xmax, x_dim + ext * 0.25], [ymax, ymax], color=color, linewidth=lw, clip_on=False, zorder=7)
        ax.annotate(
            "",
            xy=(x_dim, ymax),
            xytext=(x_dim, ymin),
            arrowprops={"arrowstyle": "<|-|>", "color": color, "lw": 0.65, "mutation_scale": 8, "shrinkA": 0, "shrinkB": 0},
            annotation_clip=False,
            zorder=8,
        )
        ax.text(
            x_dim + 0.025 * span,
            0.5 * (ymin + ymax),
            _fmt_dim(h, unit_to_mm=unit_to_mm),
            ha="left",
            va="center",
            fontsize=7.5,
            fontweight="600",
            color=color,
            clip_on=False,
            zorder=8,
            rotation=90,
            bbox={"facecolor": "#ffffff", "edgecolor": "none", "pad": 0.5},
        )


def _style_view_frame(ax, label: str) -> None:
    """Viewport border + CAD view callout."""
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#111827")
        spine.set_linewidth(0.85)
    ax.set_title("")
    text_fn = getattr(ax, "text2D", None) or ax.text
    text_fn(
        0.012,
        0.985,
        label,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=7.5,
        fontweight="700",
        color="#111827",
        bbox={"facecolor": "#ffffff", "edgecolor": "#111827", "linewidth": 0.65, "pad": 2.0},
        zorder=10,
    )


def _apply_gb_sheet_chrome(
    fig,
    *,
    title: str,
    source_path: str,
    drawing_id: str,
    generated_at: str,
    engine_label: str,
    paper: dict[str, Any],
    bbox: dict[str, float] | None = None,
    scale_label: str = "1:1",
    unit_hint: str = "尺寸单位：按模型坐标推断（大坐标多为 mm）",
    revision: str = "A",
) -> None:
    """GB/T 14689-style frame + Chinese title / revision blocks."""
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    from matplotlib.patches import Rectangle

    _configure_cjk_font()
    fig.patch.set_facecolor("#ffffff")

    ml = float(paper["margin_left"])
    mr = float(paper["margin_right"])
    mb = float(paper["margin_bottom"])
    mt = float(paper["margin_top"])
    # Outer (thick) + inner (thin) border
    ox, oy = ml * 0.55, mb * 0.55
    ow, oh = 1.0 - ox - mr * 0.55, 1.0 - oy - mt * 0.55
    fig.add_artist(
        Rectangle((ox, oy), ow, oh, transform=fig.transFigure, fill=False, edgecolor="#111827", linewidth=1.8, zorder=20)
    )
    ix, iy = ml, mb
    iw, ih = 1.0 - ml - mr, 1.0 - mb - mt
    fig.add_artist(
        Rectangle((ix, iy), iw, ih, transform=fig.transFigure, fill=False, edgecolor="#111827", linewidth=0.7, zorder=20)
    )

    # Centering marks (GB-style, ~5 mm into frame)
    cx, cy = 0.5, 0.5
    mark = 0.012
    for x0, x1, y0, y1 in (
        (cx, cx, oy, oy + mark),
        (cx, cx, oy + oh - mark, oy + oh),
        (ox, ox + mark, cy, cy),
        (ox + ow - mark, ox + ow, cy, cy),
    ):
        fig.add_artist(plt.Line2D([x0, x1], [y0, y1], transform=fig.transFigure, color="#111827", linewidth=1.2, zorder=21))

    # Zone grid (图一：数字列 / 字母行)
    n_cols = int(paper.get("zone_cols") or 10)
    n_rows = int(paper.get("zone_rows") or 8)
    zone_band = min(ml, mr, mb, mt) * 0.85
    for i in range(n_cols):
        x = ix + (i + 0.5) / n_cols * iw
        label = str(i + 1)
        fig.text(x, oy + zone_band * 0.35, label, ha="center", va="center", fontsize=5.5, color="#374151", zorder=22)
        fig.text(x, oy + oh - zone_band * 0.35, label, ha="center", va="center", fontsize=5.5, color="#374151", zorder=22)
        if 0 < i < n_cols:
            xl = ix + i / n_cols * iw
            fig.add_artist(
                plt.Line2D([xl, xl], [oy, oy + zone_band * 0.55], transform=fig.transFigure, color="#9ca3af", linewidth=0.4, zorder=21)
            )
            fig.add_artist(
                plt.Line2D([xl, xl], [oy + oh - zone_band * 0.55, oy + oh], transform=fig.transFigure, color="#9ca3af", linewidth=0.4, zorder=21)
            )
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for j in range(n_rows):
        y = iy + (n_rows - j - 0.5) / n_rows * ih
        lab = letters[j] if j < len(letters) else str(j)
        fig.text(ox + zone_band * 0.35, y, lab, ha="center", va="center", fontsize=5.5, color="#374151", zorder=22)
        fig.text(ox + ow - zone_band * 0.35, y, lab, ha="center", va="center", fontsize=5.5, color="#374151", zorder=22)
        if 0 < j < n_rows:
            yl = iy + (n_rows - j) / n_rows * ih
            fig.add_artist(
                plt.Line2D([ox, ox + zone_band * 0.55], [yl, yl], transform=fig.transFigure, color="#9ca3af", linewidth=0.4, zorder=21)
            )
            fig.add_artist(
                plt.Line2D([ox + ow - zone_band * 0.55, ox + ow], [yl, yl], transform=fig.transFigure, color="#9ca3af", linewidth=0.4, zorder=21)
            )

    bbox = bbox or {}
    dx, dy, dz = float(bbox.get("dx") or 0), float(bbox.get("dy") or 0), float(bbox.get("dz") or 0)
    envelope = f"{_fmt_len(dx)} × {_fmt_len(dy)} × {_fmt_len(dz)}" if (dx or dy or dz) else "—"
    dwg_no = (drawing_id or "DRAFT")[:12].upper()
    date_short = (generated_at or "")[:10]

    tb_w = float(paper["title_block_w"])
    tb_h = float(paper["title_block_h"])
    rev_h = float(paper["rev_h"])
    param_h = float(paper.get("param_h") or 0.05)
    bx = ix + iw - tb_w
    by = iy
    # Parameter table (L/B/H) above revision — 图一风格主尺度表
    param_y = by + tb_h + rev_h
    fig.add_artist(
        Rectangle(
            (bx, param_y),
            tb_w,
            param_h,
            transform=fig.transFigure,
            facecolor="#ffffff",
            edgecolor="#111827",
            linewidth=0.9,
            zorder=2,
        )
    )
    factor = _guess_to_mm_factor(max(dx, dy, dz, 1.0))
    rows = (("L", dx * factor), ("B", dy * factor), ("H", dz * factor))
    col_w = tb_w / 3.0
    fig.text(bx + 0.006, param_y + param_h * 0.78, "主尺度", ha="left", va="center", fontsize=5.2, color="#6b7280", zorder=4)
    for i, (sym, val) in enumerate(rows):
        x0 = bx + i * col_w
        if i:
            fig.add_artist(
                plt.Line2D([x0, x0], [param_y, param_y + param_h * 0.62], transform=fig.transFigure, color="#111827", linewidth=0.5, zorder=3)
            )
        unit = "m" if abs(val) >= 1000 else "mm"
        disp = f"{val / 1000.0:.2f}" if unit == "m" else f"{val:.0f}"
        fig.text(x0 + col_w * 0.5, param_y + param_h * 0.42, f"{sym}={disp} {unit}", ha="center", va="center", fontsize=7, fontweight="700", color="#111827", zorder=4)

    # Revision strip above title block
    rev_y = by + tb_h
    fig.add_artist(
        Rectangle(
            (bx, rev_y),
            tb_w,
            rev_h,
            transform=fig.transFigure,
            facecolor="#ffffff",
            edgecolor="#111827",
            linewidth=0.9,
            zorder=2,
        )
    )
    fig.add_artist(plt.Line2D([bx + tb_w * 0.12, bx + tb_w * 0.12], [rev_y, rev_y + rev_h], transform=fig.transFigure, color="#111827", linewidth=0.6, zorder=3))
    fig.add_artist(plt.Line2D([bx + tb_w * 0.32, bx + tb_w * 0.32], [rev_y, rev_y + rev_h], transform=fig.transFigure, color="#111827", linewidth=0.6, zorder=3))
    fig.text(bx + 0.008, rev_y + rev_h * 0.5, "修订", ha="left", va="center", fontsize=5.5, color="#6b7280", zorder=4)
    fig.text(bx + tb_w * 0.14, rev_y + rev_h * 0.5, f"Rev.{revision}", ha="left", va="center", fontsize=7, fontweight="700", color="#111827", zorder=4)
    fig.text(bx + tb_w * 0.34, rev_y + rev_h * 0.5, f"{date_short}  外形尺寸预览", ha="left", va="center", fontsize=6.5, color="#374151", zorder=4)

    # Title block
    fig.add_artist(
        Rectangle((bx, by), tb_w, tb_h, transform=fig.transFigure, facecolor="#ffffff", edgecolor="#111827", linewidth=1.1, zorder=2)
    )
    # Grid
    x_logo = bx + tb_w * 0.18
    for x in (x_logo, bx + tb_w * 0.55):
        fig.add_artist(plt.Line2D([x, x], [by, by + tb_h], transform=fig.transFigure, color="#111827", linewidth=0.65, zorder=3))
    for y_frac in (0.72, 0.48, 0.24):
        fig.add_artist(
            plt.Line2D([x_logo, bx + tb_w], [by + tb_h * y_frac, by + tb_h * y_frac], transform=fig.transFigure, color="#111827", linewidth=0.65, zorder=3)
        )
    fig.add_artist(plt.Line2D([bx, x_logo], [by + tb_h * 0.28, by + tb_h * 0.28], transform=fig.transFigure, color="#111827", linewidth=0.65, zorder=3))

    logo = _load_logo_array()
    if logo is not False and logo is not None:
        oi = OffsetImage(logo, zoom=0.26)
        ab = AnnotationBbox(
            oi,
            (bx + tb_w * 0.09, by + tb_h * 0.62),
            xycoords=fig.transFigure,
            frameon=False,
            box_alignment=(0.5, 0.5),
            zorder=4,
        )
        fig.add_artist(ab)
    else:
        fig.text(bx + tb_w * 0.09, by + tb_h * 0.62, "AE", ha="center", va="center", fontsize=13, fontweight="800", color="#0f172a", zorder=4)
    fig.text(bx + tb_w * 0.09, by + tb_h * 0.12, BRAND_NAME, ha="center", va="center", fontsize=5.5, color="#374151", zorder=4)

    def _cell(label: str, value: str, x: float, y_top: float, y_val: float, *, vmax: int = 40) -> None:
        fig.text(x, y_top, label, ha="left", va="top", fontsize=5.2, color="#6b7280", zorder=4)
        fig.text(x, y_val, str(value or "—")[:vmax], ha="left", va="center", fontsize=7.5, fontweight="600", color="#111827", zorder=4)

    _cell("图名", str(title or "总布置图")[:36], x_logo + 0.008, by + tb_h * 0.96, by + tb_h * 0.82)
    _cell("图号", dwg_no, x_logo + 0.008, by + tb_h * 0.70, by + tb_h * 0.58)
    _cell("来源", str(source_path or "—")[-42:], x_logo + 0.008, by + tb_h * 0.46, by + tb_h * 0.34, vmax=42)
    _cell("外包络", envelope, bx + tb_w * 0.56, by + tb_h * 0.96, by + tb_h * 0.82)
    _cell("比例", scale_label, bx + tb_w * 0.56, by + tb_h * 0.70, by + tb_h * 0.58)
    _cell("日期", generated_at, bx + tb_w * 0.56, by + tb_h * 0.46, by + tb_h * 0.34, vmax=28)

    # Signature row
    fig.text(bx + tb_w * 0.56, by + tb_h * 0.20, "设计", ha="left", va="top", fontsize=5.2, color="#6b7280", zorder=4)
    fig.text(bx + tb_w * 0.62, by + tb_h * 0.08, "—", ha="left", va="center", fontsize=7, color="#111827", zorder=4)
    fig.text(bx + tb_w * 0.74, by + tb_h * 0.20, "校核", ha="left", va="top", fontsize=5.2, color="#6b7280", zorder=4)
    fig.text(bx + tb_w * 0.80, by + tb_h * 0.08, "—", ha="left", va="center", fontsize=7, color="#111827", zorder=4)

    # Left info panel (height matches title+rev+param)
    left_h = tb_h + rev_h + param_h
    left_w = bx - ix - 0.008
    fig.add_artist(
        Rectangle(
            (ix, iy),
            max(left_w, 0.2),
            left_h,
            transform=fig.transFigure,
            facecolor="#ffffff",
            edgecolor="#111827",
            linewidth=1.0,
            zorder=2,
        )
    )
    fig.text(ix + 0.012, iy + left_h - 0.016, "投影 / 说明", ha="left", va="top", fontsize=5.5, color="#6b7280", zorder=4)
    fig.text(
        ix + 0.012,
        iy + left_h - 0.036,
        "第三角画法 · A 轴测 / B 俯视（总布置） / C 正视 / D 侧视",
        ha="left",
        va="top",
        fontsize=7,
        color="#111827",
        zorder=4,
    )
    fig.text(ix + 0.012, iy + 0.055, "单位与方法", ha="left", va="top", fontsize=5.5, color="#6b7280", zorder=4)
    fig.text(ix + 0.012, iy + 0.034, unit_hint, ha="left", va="top", fontsize=6.5, color="#374151", zorder=4)
    fig.text(
        ix + 0.012,
        iy + 0.014,
        f"{engine_label} · {BRAND_NAME} 轮廓工程图预览（非审图 / 非入级）",
        ha="left",
        va="bottom",
        fontsize=6,
        color="#6b7280",
        zorder=4,
    )

    # Header strip
    head_y = iy + ih - 0.032
    fig.add_artist(
        Rectangle(
            (ix, head_y),
            iw,
            0.032,
            transform=fig.transFigure,
            facecolor="#f3f4f6",
            edgecolor="#111827",
            linewidth=0.7,
            zorder=1,
        )
    )
    fig.text(ix + 0.012, head_y + 0.016, BRAND_NAME, ha="left", va="center", fontsize=10, fontweight="800", color="#0f172a", zorder=4)
    fig.text(0.50, head_y + 0.016, str(title or "外形尺寸图"), ha="center", va="center", fontsize=10, fontweight="700", color="#0f172a", zorder=4)
    fig.text(
        ix + iw - 0.012,
        head_y + 0.016,
        f"{paper['sheet_size']}  ·  外形尺寸 / 总布置",
        ha="right",
        va="center",
        fontsize=7.5,
        color="#374151",
        zorder=4,
    )


# Back-compat alias
_apply_sheet_chrome = _apply_gb_sheet_chrome


def _content_rect(paper: dict[str, Any]) -> dict[str, float]:
    """Drawable content box above title/rev/param blocks (figure coords)."""
    ml = float(paper["margin_left"])
    mr = float(paper["margin_right"])
    mb = float(paper["margin_bottom"])
    mt = float(paper["margin_top"])
    tb = float(paper["title_block_h"]) + float(paper["rev_h"]) + float(paper.get("param_h") or 0)
    return {
        "left": ml + 0.014,
        "right": 1.0 - mr - 0.014,
        "bottom": mb + tb + 0.010,
        "top": 1.0 - mt - 0.038,
    }


def _add_view_axes(fig, layout: str, paper: dict[str, Any], *, shaded: bool = False) -> list[tuple[str, Any]]:
    """Create 2D axes for ga or quad layout (professional line drawings, not 3D mesh)."""
    del shaded  # always 2D outlines
    box = _content_rect(paper)
    lay = _normalize_layout(layout)
    if lay == "quad":
        gs = fig.add_gridspec(
            2,
            2,
            left=box["left"],
            right=box["right"],
            top=box["top"],
            bottom=box["bottom"],
            wspace=0.06,
            hspace=0.08,
        )
        keys = [("iso", gs[0, 0]), ("top", gs[0, 1]), ("front", gs[1, 0]), ("right", gs[1, 1])]
    else:
        # GA: large plan left; front/right top-right; iso bottom-right (closer packing)
        gs = fig.add_gridspec(
            2,
            3,
            left=box["left"],
            right=box["right"],
            top=box["top"],
            bottom=box["bottom"],
            width_ratios=[2.8, 1.05, 1.05],
            height_ratios=[1.1, 1.0],
            wspace=0.05,
            hspace=0.07,
        )
        keys = [
            ("top", gs[:, 0]),
            ("front", gs[0, 1]),
            ("right", gs[0, 2]),
            ("iso", gs[1, 1:]),
        ]
    out = []
    for key, spec in keys:
        ax = fig.add_subplot(spec)
        out.append((key, ax))
    return out


def _plot_polylines_weighted(ax, polys: list, *, fill_hull: bool = True) -> tuple[list[float], list[float]]:
    from matplotlib.patches import Polygon as MplPolygon

    xs_all: list[float] = []
    ys_all: list[float] = []
    lengths: list[float] = []
    valid: list[list] = []
    for poly in polys:
        if len(poly) < 2:
            continue
        valid.append(poly)
        lengths.append(_poly_length(poly))
        for p in poly:
            xs_all.append(float(p[0]))
            ys_all.append(float(p[1]))
    if not valid:
        return xs_all, ys_all

    # Soft fill + stipple hatch under outlines (图一点阵填充感)
    if fill_hull and len(xs_all) >= 3:
        try:
            ring = _hull_ring(np.column_stack((xs_all, ys_all)))
            if len(ring) >= 3:
                patch = MplPolygon(
                    ring,
                    closed=True,
                    facecolor="#d1d5db",
                    edgecolor="none",
                    alpha=0.35,
                    hatch="......",
                    zorder=1,
                )
                ax.add_patch(patch)
        except Exception:
            pass

    thr = float(np.percentile(lengths, 72)) if lengths else 0.0
    max_len = max(lengths) if lengths else 0.0
    for poly, length in zip(valid, lengths):
        xs = [float(p[0]) for p in poly]
        ys = [float(p[1]) for p in poly]
        # Outer hull / long edges thick; internal silhouette thinner
        if length >= max_len * 0.98 and len(poly) >= 4:
            lw = 1.45
        elif length >= thr:
            lw = 1.05
        else:
            lw = 0.32
        ax.plot(xs, ys, color="#111827", linewidth=lw, solid_capstyle="round", solid_joinstyle="round", zorder=3)
    return xs_all, ys_all


def _savefig_sheet(fig, out_png: Path, out_pdf: Path | None = None) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    with mpl.rc_context({"pdf.fonttype": 42, "ps.fonttype": 42}):
        fig.savefig(out_png, facecolor="#ffffff", pad_inches=0)
        if out_pdf is not None:
            fig.savefig(out_pdf, format="pdf", facecolor="#ffffff", pad_inches=0)


def _finish_ortho_view(
    ax,
    key: str,
    xs_all: list[float],
    ys_all: list[float],
    *,
    unit_to_mm: float = 1.0,
) -> None:
    if not xs_all or not ys_all:
        return
    xmin, xmax = min(xs_all), max(xs_all)
    ymin, ymax = min(ys_all), max(ys_all)
    span = max(xmax - xmin, ymax - ymin, 1e-9)
    if key in ("top", "front", "right"):
        _draw_centerlines(ax, xmin, xmax, ymin, ymax)
        _draw_overall_dimensions(ax, xmin, xmax, ymin, ymax, unit_to_mm=unit_to_mm)
        pad_side = 0.16 * span
        pad_bottom = 0.22 * span
        pad_top = 0.08 * span
        ax.set_xlim(xmin - pad_side * 0.45, xmax + pad_side)
        ax.set_ylim(ymin - pad_bottom, ymax + pad_top)
    else:
        _draw_scale_bar(ax, span, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)


def render_drawing_sheet(
    points: np.ndarray,
    faces: np.ndarray,
    *,
    out_png: Path,
    title: str,
    source_path: str = "",
    drawing_id: str = "",
    generated_at: str | None = None,
    engine_label: str = "轮廓投影",
    subtitle: str | None = None,
    out_pdf: Path | None = None,
    sheet_size: str = "A3",
    layout: str = "ga",
    silhouette_mode: str = "mesh",
) -> dict[str, Any]:
    """Render mesh as professional 2D outline sheet (not triangulated wireframe)."""
    views = mesh_to_view_dict(
        np.asarray(points, dtype=float),
        np.asarray(faces, dtype=int),
        silhouette_mode=silhouette_mode,
    )
    solid = str(silhouette_mode or "").lower() == "solid"
    hint = (
        "实体轮廓：原始边柱+桩靴+优化光滑结构（边界+剪影）"
        if solid
        else "轮廓投影自网格/INP（边界+剪影边；非三角线网）"
    )
    # Write temp-less path via shared line renderer
    return _render_views_dict_sheet(
        views,
        out_png=out_png,
        title=title,
        source_path=source_path or (subtitle or "—"),
        drawing_id=drawing_id or "DRAFT",
        generated_at=generated_at,
        engine_label=engine_label,
        out_pdf=out_pdf,
        sheet_size=sheet_size,
        layout=layout,
        bbox_override=_bbox_from_points(np.asarray(points, dtype=float)),
        unit_hint=hint,
    )


def _render_views_dict_sheet(
    views: dict[str, Any],
    *,
    out_png: Path,
    title: str,
    source_path: str = "",
    drawing_id: str = "",
    generated_at: str | None = None,
    engine_label: str = "线框投影",
    out_pdf: Path | None = None,
    sheet_size: str = "A3",
    layout: str = "ga",
    bbox_override: dict[str, float] | None = None,
    unit_hint: str = "尺寸单位：按模型坐标推断（大坐标多为 mm）",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _configure_cjk_font()
    paper = _paper_spec(sheet_size)
    gen = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fig = plt.figure(figsize=paper["figsize"], dpi=paper["dpi"], facecolor="#ffffff")

    meta = meta or {}
    bbox = bbox_override or _bbox_from_line_views(views)
    if meta.get("bbox_mm") and not bbox_override:
        bm = meta["bbox_mm"]
        bbox = {
            "dx": float(bm.get("dx") or bbox.get("dx") or 0),
            "dy": float(bm.get("dy") or bbox.get("dy") or 0),
            "dz": float(bm.get("dz") or bbox.get("dz") or 0),
        }
    envelope_span = max(float(bbox.get("dx") or 0), float(bbox.get("dy") or 0), float(bbox.get("dz") or 0), 0.0)
    unit_to_mm = float(meta.get("unit_to_mm") or _guess_to_mm_factor(envelope_span))

    for key, ax in _add_view_axes(fig, layout, paper, shaded=False):
        ax.set_aspect("equal")
        ax.set_facecolor("#ffffff")
        _style_view_frame(ax, VIEW_LABELS.get(key, key))
        ax.set_xticks([])
        ax.set_yticks([])
        polys = (views.get(key) or {}).get("polylines") or []
        xs_all, ys_all = _plot_polylines_weighted(ax, polys, fill_hull=True)
        _finish_ortho_view(ax, key, xs_all, ys_all, unit_to_mm=unit_to_mm)

    span_mm = float(meta.get("span_mm") or 0) or _model_span_mm(bbox)
    drawable = float(paper["w_mm"]) * (0.55 if _normalize_layout(layout) == "ga" else 0.40)
    scale_label, scale_n = _compute_drawing_scale(span_mm, drawable)
    _apply_gb_sheet_chrome(
        fig,
        title=title,
        source_path=source_path,
        drawing_id=drawing_id or "DRAFT",
        generated_at=gen,
        engine_label=engine_label,
        paper=paper,
        bbox=bbox,
        scale_label=scale_label,
        unit_hint=str(meta.get("unit_guess") or unit_hint),
    )
    pdf_path = out_pdf if out_pdf is not None else out_png.with_suffix(".pdf")
    _savefig_sheet(fig, out_png, pdf_path)
    plt.close(fig)
    return {"scale": scale_label, "scale_n": scale_n, "sheet_size": paper["sheet_size"], "layout": _normalize_layout(layout)}


def resolve_upload_cad_path(file_id: str, workspace_root: Path | None = None) -> Path:
    from backend.tools.files import resolve_file

    root = workspace_root or _workspace_root()
    sf = resolve_file(root, str(file_id).strip())
    if sf.ext not in CAD_EXTS and sf.path.suffix.lower() not in CAD_EXTS:
        raise ValueError(f"上传文件格式不支持出图: {sf.ext}")
    return sf.path.resolve()


def _render_line_sheet_from_freecad_json(
    views_json: Path,
    *,
    out_png: Path,
    title: str,
    source_path: str = "",
    drawing_id: str = "",
    generated_at: str | None = None,
    engine_label: str = "线框投影",
    subtitle: str | None = None,
    out_pdf: Path | None = None,
    sheet_size: str = "A3",
    layout: str = "ga",
) -> dict[str, Any]:
    data = json.loads(views_json.read_text(encoding="utf-8"))
    views = data.get("views") or {}
    meta = data.get("meta") or {}
    return _render_views_dict_sheet(
        views,
        out_png=out_png,
        title=title,
        source_path=source_path or (subtitle or "—"),
        drawing_id=drawing_id,
        generated_at=generated_at,
        engine_label=engine_label,
        out_pdf=out_pdf,
        sheet_size=sheet_size,
        layout=layout,
        meta=meta,
        unit_hint="尺寸单位：按模型坐标推断（大坐标多为 mm）",
    )


def render_line_drawing_sheet(
    views_json: Path,
    *,
    out_png: Path,
    title: str = "总布置图",
    source_path: str = "",
    drawing_id: str = "TEST",
    sheet_size: str = "A3",
    layout: str = "ga",
    out_pdf: Path | None = None,
) -> dict[str, Any]:
    """Public helper for tests / offline synthesis from freecad_views.json."""
    return _render_line_sheet_from_freecad_json(
        views_json,
        out_png=out_png,
        title=title,
        source_path=source_path,
        drawing_id=drawing_id,
        out_pdf=out_pdf,
        sheet_size=sheet_size,
        layout=layout,
    )


def _try_freecad_line_drawing(src: Path, out_dir: Path) -> dict[str, Any] | None:
    ext = src.suffix.lower()
    if ext not in (".step", ".stp", ".iges", ".igs", ".stl"):
        return None
    try:
        from backend.tools.freecad_drawing_pack import run_freecad_drawing_views

        meta = run_freecad_drawing_views(src, out_dir / "freecad_views")
        return meta if isinstance(meta, dict) else None
    except Exception as e:
        (out_dir / "freecad_error.txt").write_text(str(e)[:4000], encoding="utf-8")
        return None


def build_cad_drawing_pack(
    path_str: str | None = None,
    *,
    file_id: str | None = None,
    workspace_root: Path | None = None,
    title: str | None = None,
    engine: str = "auto",
    sheet_size: str = "A3",
    layout: str = "ga",
    silhouette_mode: str | None = None,
) -> dict[str, Any]:
    """
    Build multi-view drawing pack.

    ``engine``:
    - ``auto``: FreeCAD line drawing for STEP/IGES/STL when available, else mesh/matplotlib
    - ``freecad``: require FreeCAD path for CAD solids
    - ``mesh``: matplotlib shaded mesh only

    ``layout``: ``ga`` (general-arrangement style) or ``quad`` (2×2).
    ``sheet_size``: ``A3`` | ``A1`` | ``A0`` (landscape).
    ``silhouette_mode``: ``mesh`` | ``solid`` (solid = clean cylinder/CAD outlines).
    """
    root = workspace_root or _workspace_root()
    size = _normalize_sheet_size(sheet_size)
    lay = _normalize_layout(layout)
    if file_id and str(file_id).strip():
        src = resolve_upload_cad_path(str(file_id).strip(), root)
        try:
            rel_src = str(src.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel_src = src.name
    else:
        if not path_str:
            raise ValueError("须提供 path 或 file_id")
        src = resolve_workspace_cad_path(path_str, root)
        rel_src = str(src.relative_to(root)).replace("\\", "/")

    drawing_id = uuid.uuid4().hex
    out_dir = root / "runs" / DRAWING_SUBDIR / drawing_id
    out_dir.mkdir(parents=True, exist_ok=True)

    sheet = out_dir / "drawing_sheet.png"
    sheet_pdf = out_dir / "drawing_sheet.pdf"
    eng = str(engine or "auto").strip().lower()
    used_engine = "mesh"
    freecad_meta: dict[str, Any] | None = None
    view_svgs: dict[str, str] = {}
    sheet_meta: dict[str, Any] = {"scale": "1:1", "scale_n": 1, "sheet_size": size, "layout": lay}
    sheet_title = title or f"{BRAND_NAME} · {src.name}"
    # Prefer solid outlines for GA assembly / reconstructed solids
    sil_mode = str(silhouette_mode or "").strip().lower()
    if not sil_mode:
        name_l = src.name.lower()
        sil_mode = (
            "solid"
            if ("drawing_assembly" in name_l or "reconstructed" in name_l or src.suffix.lower() == ".stl")
            else "mesh"
        )

    want_fc = eng in ("auto", "freecad")
    if want_fc:
        freecad_meta = _try_freecad_line_drawing(src, out_dir)
        views_json = out_dir / "freecad_views" / "freecad_views.json"
        poly_total = 0
        if freecad_meta:
            for info in (freecad_meta.get("views") or {}).values():
                poly_total += int((info or {}).get("polyline_count") or 0)
        if freecad_meta and views_json.is_file() and poly_total > 0:
            gen_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            sheet_meta = _render_line_sheet_from_freecad_json(
                views_json,
                out_png=sheet,
                out_pdf=sheet_pdf,
                title=sheet_title,
                source_path=rel_src,
                drawing_id=drawing_id,
                generated_at=gen_at,
                engine_label="线框投影",
                sheet_size=size,
                layout=lay,
            )
            used_engine = "freecad"
            for name, info in (freecad_meta.get("views") or {}).items():
                svg_name = (info or {}).get("svg")
                if svg_name:
                    view_svgs[name] = f"/runs/{DRAWING_SUBDIR}/{drawing_id}/freecad_views/{svg_name}"
        elif eng == "freecad" and not freecad_meta:
            raise RuntimeError(
                (out_dir / "freecad_error.txt").read_text(encoding="utf-8")
                if (out_dir / "freecad_error.txt").is_file()
                else "出图失败（请确认 D:\\freecad 或 FREECAD_CMD）"
            )
        if not sheet.is_file() or (freecad_meta and poly_total == 0):
            preview_obj = out_dir / "freecad_views" / "preview.obj"
            try:
                if preview_obj.is_file():
                    points, faces = _parse_obj(preview_obj)
                else:
                    points, faces = _load_mesh(src, out_dir)
                gen_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                sheet_meta = render_drawing_sheet(
                    points,
                    faces,
                    out_png=sheet,
                    out_pdf=sheet_pdf,
                    title=sheet_title,
                    source_path=rel_src,
                    drawing_id=drawing_id,
                    generated_at=gen_at,
                    engine_label="轮廓投影",
                    sheet_size=size,
                    layout=lay,
                    silhouette_mode=sil_mode,
                )
                used_engine = "freecad_mesh" if preview_obj.is_file() else "mesh"
                view_svgs = {}
            except Exception:
                if eng == "freecad":
                    raise

    if not sheet.is_file():
        points, faces = _load_mesh(src, out_dir)
        gen_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sheet_meta = render_drawing_sheet(
            points,
            faces,
            out_png=sheet,
            out_pdf=sheet_pdf,
            title=sheet_title,
            source_path=rel_src,
            drawing_id=drawing_id,
            generated_at=gen_at,
            engine_label="实体轮廓" if sil_mode == "solid" else "轮廓投影",
            sheet_size=size,
            layout=lay,
            silhouette_mode=sil_mode,
        )
        used_engine = "mesh"

    scale_label = str(sheet_meta.get("scale") or "1:1")
    pack = {
        "drawing_id": drawing_id,
        "source_path": rel_src,
        "source_name": src.name,
        "sheet": "drawing_sheet.png",
        "sheet_pdf": "drawing_sheet.pdf" if sheet_pdf.is_file() else None,
        "views": ["iso", "top", "front", "right"],
        "engine": used_engine,
        "brand": BRAND_NAME,
        "view_svgs": view_svgs,
        "sheet_size": sheet_meta.get("sheet_size") or size,
        "layout": sheet_meta.get("layout") or lay,
        "scale": scale_label,
        "scale_n": sheet_meta.get("scale_n"),
        "note": (
            f"{BRAND_NAME} 外形尺寸/总布置式线框工程图预览（非船级社审图出图）。"
            if used_engine == "freecad"
            else (
                f"{BRAND_NAME} 轮廓投影总布置式工程图（FreeCAD 线框为空时的回退）。"
                if used_engine == "freecad_mesh"
                else f"{BRAND_NAME} 轮廓投影外形尺寸图（边界+剪影，非三角线网）；非审图出图。"
            )
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "pack_manifest.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")

    rel_sheet = sheet.relative_to(root).as_posix()
    rel_manifest = (out_dir / "pack_manifest.json").relative_to(root).as_posix()
    rel_pdf = sheet_pdf.relative_to(root).as_posix() if sheet_pdf.is_file() else None
    return {
        "ok": True,
        "drawing_id": drawing_id,
        "source_path": rel_src,
        "sheet_url": f"/{rel_sheet}",
        "pdf_url": f"/{rel_pdf}" if rel_pdf else None,
        "manifest_url": f"/{rel_manifest}",
        "engine": used_engine,
        "view_svgs": view_svgs,
        "sheet_size": pack["sheet_size"],
        "layout": pack["layout"],
        "scale": scale_label,
        "pack": pack,
    }


__all__ = [
    "build_cad_drawing_pack",
    "resolve_workspace_cad_path",
    "resolve_upload_cad_path",
    "render_line_drawing_sheet",
    "render_drawing_sheet",
    "CAD_EXTS",
]
