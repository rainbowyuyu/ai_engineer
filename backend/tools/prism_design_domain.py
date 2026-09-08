"""beso9 式三棱柱设计域：规格、自然语言解析、FreeCAD 建域/网格封装。"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.tools.freecad_inp_mesh_vtk import resolve_freecad_python

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FREECAD_SCRIPT = _REPO_ROOT / "scripts" / "freecad_prism_design_domain.py"

# beso9 defaults (mm / N)
DEFAULT_SIDE_MM = 95000.0
DEFAULT_HEIGHT_ABOVE_MM = 17000.0
DEFAULT_HEIGHT_BELOW_MM = 21000.0
DEFAULT_CORNER_R_MM = 7500.0
DEFAULT_LOAD_DIAMETER_MM = 12000.0
DEFAULT_FORCE_N = 2.45e7
DEFAULT_RING_H_MM = 100.0
DEFAULT_RING_WALL_MM = 200.0
DEFAULT_MESH_MAX_MM = 2000.0
DEFAULT_MESH_MIN_MM = 1000.0
DEFAULT_MASS_GOAL_RATIO = 0.15


@dataclass
class PrismDesignSpec:
    """Equilateral prism + corner dig-outs + top load ring (beso9 family)."""

    side_mm: float = DEFAULT_SIDE_MM
    height_above_mm: float = DEFAULT_HEIGHT_ABOVE_MM
    height_below_mm: float = DEFAULT_HEIGHT_BELOW_MM
    corner_r_mm: float = DEFAULT_CORNER_R_MM
    load_diameter_mm: float = DEFAULT_LOAD_DIAMETER_MM
    force_n: float = DEFAULT_FORCE_N
    ring_h_mm: float = DEFAULT_RING_H_MM
    ring_wall_mm: float = DEFAULT_RING_WALL_MM
    mesh_max_mm: float = DEFAULT_MESH_MAX_MM
    mesh_min_mm: float = DEFAULT_MESH_MIN_MM
    mass_goal_ratio: float = DEFAULT_MASS_GOAL_RATIO
    title: str = "BESO 三棱柱设计域（顶点挖圆柱 + 圆周载荷）"
    notes: list[str] = field(default_factory=list)
    fast_demo: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PrismDesignSpec":
        if not data:
            return cls()
        base = cls()
        kw: dict[str, Any] = {}
        for f in base.__dataclass_fields__:
            if f in data and data[f] is not None:
                if f == "notes":
                    kw[f] = [str(x) for x in (data[f] or [])]
                elif f == "title":
                    kw[f] = str(data[f])
                elif f == "fast_demo":
                    kw[f] = bool(data[f])
                else:
                    kw[f] = float(data[f])
        return cls(**{**asdict(base), **kw})

    def apply_fast_demo_mesh(self) -> None:
        """Coarser mesh for quicker demos (still real FreeCAD + gmsh)."""
        self.fast_demo = True
        self.mesh_max_mm = max(self.mesh_max_mm, 4000.0)
        self.mesh_min_mm = max(self.mesh_min_mm, 2000.0)

    def height_total_mm(self) -> float:
        return float(self.height_above_mm) + float(self.height_below_mm)

    def equilateral_vertices_xy(self) -> list[list[float]]:
        side = float(self.side_mm)
        h = side * math.sqrt(3.0) / 2.0
        return [
            [0.0, 2.0 * h / 3.0],
            [side / 2.0, -h / 3.0],
            [-side / 2.0, -h / 3.0],
        ]


def parse_prism_design_brief(text: str) -> PrismDesignSpec:
    """Rule-based NL parse for prism topology prompts (Chinese / English)."""
    spec = PrismDesignSpec()
    t = str(text or "").strip()
    if not t:
        return spec
    low = t.lower()

    def _num(m: re.Match[str] | None) -> float | None:
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except Exception:
            return None

    # side length: 边长 95 m / 80m / side 95m / 95000 mm
    m = re.search(r"边长\s*[:=]?\s*([\d.]+)\s*(m|米|mm)?", t, re.I)
    if not m:
        m = re.search(r"side(?:\s*length)?\s*[:=]?\s*([\d.]+)\s*(m|mm)?", low)
    if m:
        v = _num(m)
        unit = (m.group(2) or "m").lower()
        if v is not None:
            spec.side_mm = v if unit == "mm" else v * 1000.0

    m = re.search(r"水上\s*([\d.]+)\s*(m|米|mm)?", t, re.I)
    if m:
        v = _num(m)
        unit = (m.group(2) or "m").lower()
        if v is not None:
            spec.height_above_mm = v if unit == "mm" else v * 1000.0
    m = re.search(r"水下\s*([\d.]+)\s*(m|米|mm)?", t, re.I)
    if m:
        v = _num(m)
        unit = (m.group(2) or "m").lower()
        if v is not None:
            spec.height_below_mm = v if unit == "mm" else v * 1000.0

    m = re.search(
        r"(?:挖角|挖去)\s*(?:半径|R)?\s*[:=]?\s*([\d.]+)\s*(m|米|mm)?"
        r"|角\s*R\s*[:=]?\s*([\d.]+)\s*(m|米|mm)?"
        r"|corner\s*r(?:adius)?\s*[:=]?\s*([\d.]+)\s*(m|mm)?",
        t,
        re.I,
    )
    if m:
        v = None
        unit = "m"
        for i in (1, 3, 5):
            if m.group(i):
                try:
                    v = float(m.group(i).replace(",", ""))
                except Exception:
                    v = None
                unit = (m.group(i + 1) or "m").lower()
                break
        if v is not None:
            spec.corner_r_mm = v if unit == "mm" else v * 1000.0

    m = re.search(
        r"(?:载荷|荷载)\s*(?:圆|环)?\s*(?:直径|Ø|ø|⌀)\s*[:=]?\s*([\d.]+)\s*(m|米|mm)?"
        r"|load\s*(?:ring|circle)?\s*(?:diameter|ø|⌀)\s*[:=]?\s*([\d.]+)\s*(m|mm)?"
        r"|(?:Ø|⌀)\s*([\d.]+)\s*(m|米|mm)",
        t,
        re.I,
    )
    if m:
        v = None
        unit = "m"
        for i in (1, 3, 5):
            if m.group(i):
                try:
                    v = float(m.group(i).replace(",", ""))
                except Exception:
                    v = None
                unit = (m.group(i + 1) or "m").lower()
                break
        if v is not None and v > 0:
            mm = v if unit == "mm" else v * 1000.0
            if 100 < mm < 100_000:
                spec.load_diameter_mm = mm

    m = re.search(r"(?:力|force|重力)\s*[:=]?\s*([\d.]+)\s*(e[+\-]?\d+)?\s*N?", t, re.I)
    if m:
        raw = m.group(1) + (m.group(2) or "")
        try:
            fv = float(raw)
            if fv > 1e3:
                spec.force_n = fv
        except Exception:
            pass
    m = re.search(r"([\d.]+)\s*[×xX\*]\s*10\s*\^?\s*([+\-]?\d+)\s*N", t)
    if m:
        try:
            spec.force_n = float(m.group(1)) * (10 ** int(m.group(2)))
        except Exception:
            pass

    # volume fraction / mass_goal_ratio
    m = re.search(r"体积分数\s*[:=]?\s*([\d.]+)\s*%?", t)
    if not m:
        m = re.search(r"mass[_\s-]?goal(?:_ratio)?\s*[:=]?\s*([\d.]+)", low)
    if not m:
        m = re.search(r"\b([\d.]+)\s*%\s*(?:体积|体积分数|vf|volume)", t, re.I)
    if m:
        v = _num(m)
        if v is not None:
            spec.mass_goal_ratio = v / 100.0 if v > 1.0 else v

    if re.search(r"粗网格|快演示|快速演示|fast\s*demo|coarse\s*mesh", t, re.I):
        spec.apply_fast_demo_mesh()

    if re.search(r"beso9|beso_9|默认几何", t, re.I):
        # keep defaults already set; only override if user also gave numbers
        pass

    verts = spec.equilateral_vertices_xy()
    spec.notes = [
        f"三棱柱高度 {spec.height_total_mm() / 1000:.1f} m"
        f"（水面以下 {spec.height_below_mm / 1000:.1f} m，水面以上 {spec.height_above_mm / 1000:.1f} m）",
        f"三棱柱边长 {spec.side_mm / 1000:.1f} m；三顶点挖圆柱 R={spec.corner_r_mm / 1000:.1f} m",
        f"受力：Ø{spec.load_diameter_mm / 1000:.1f} m 圆周，重力 {spec.force_n:.3g} N（-Z）",
        f"体积分数目标 mass_goal_ratio={spec.mass_goal_ratio:.4g}",
    ]
    if spec.fast_demo:
        spec.notes.append(f"粗网格演示 mesh_max={spec.mesh_max_mm:g} mm")
    spec.title = (
        f"棱柱设计域 · 边长 {spec.side_mm / 1000:.0f} m · VF {spec.mass_goal_ratio * 100:.0f}%"
    )
    # silence unused
    _ = verts
    return spec


def design_spec_json_from_prism(spec: PrismDesignSpec) -> dict[str, Any]:
    verts = spec.equilateral_vertices_xy()
    z_top = float(spec.height_above_mm) + float(spec.ring_h_mm)
    z_bot = -float(spec.height_below_mm)
    return {
        "title": spec.title,
        "unit": "mm",
        "source": "prism_design_domain / FreeCAD",
        "waterline_z_mm": 0.0,
        "height_total_mm": spec.height_total_mm(),
        "height_below_wl_mm": float(spec.height_below_mm),
        "height_above_wl_mm": float(spec.height_above_mm),
        "z_min_mm": z_bot,
        "z_max_mm": z_top,
        "side_length_mm": float(spec.side_mm),
        "sharp_vertices_xy_mm": verts,
        "corner_circle_radius_mm": float(spec.corner_r_mm),
        "corner_cyl_radius_mm": float(spec.corner_r_mm),
        "corner_centers_xy_mm": verts,
        "corner_style": "cylinder_digout_at_vertices",
        "load_circle_diameter_mm": float(spec.load_diameter_mm),
        "load_circle_radius_mm": float(spec.load_diameter_mm) / 2.0,
        "load_circle_center_xyz_mm": [0.0, 0.0, z_top],
        "load_application": "circumference_edge",
        "load_force_n": float(spec.force_n),
        "load_direction": "-Z",
        "mass_goal_ratio": float(spec.mass_goal_ratio),
        "mesh_max_mm": float(spec.mesh_max_mm),
        "mesh_min_mm": float(spec.mesh_min_mm),
        "notes": list(spec.notes),
        "prism_spec": spec.to_dict(),
    }


def prism_sessions_root(workspace: Path) -> Path:
    return Path(workspace).resolve() / "runs" / "_prism_sessions"


def new_prism_session_id() -> str:
    return uuid.uuid4().hex


def prism_session_dir(workspace: Path, session_id: str) -> Path:
    return prism_sessions_root(workspace) / str(session_id).strip()


def write_prism_session_meta(sdir: Path, meta: dict[str, Any]) -> dict[str, Any]:
    sdir.mkdir(parents=True, exist_ok=True)
    path = sdir / "meta.json"
    cur: dict[str, Any] = {}
    if path.is_file():
        try:
            cur = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    cur.update(meta)
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur


def read_prism_session_meta(sdir: Path) -> dict[str, Any]:
    path = sdir / "meta.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_prism_design_files(sdir: Path, spec: PrismDesignSpec) -> Path:
    sdir.mkdir(parents=True, exist_ok=True)
    spec_path = sdir / "prism_spec.json"
    design_path = sdir / "design_spec.json"
    spec_path.write_text(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    design_path.write_text(
        json.dumps(design_spec_json_from_prism(spec), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return spec_path


def _run_freecad_script(args: list[str], *, timeout_s: float) -> str:
    if not _FREECAD_SCRIPT.is_file():
        raise FileNotFoundError(f"缺少 FreeCAD 脚本: {_FREECAD_SCRIPT}")
    exe = resolve_freecad_python()
    cmd = [str(exe), str(_FREECAD_SCRIPT), *args]
    env = os.environ.copy()
    fc_bin = exe.parent
    extras = [str(fc_bin), str(fc_bin / "Lib"), str(fc_bin / "Lib" / "site-packages")]
    env["PYTHONPATH"] = os.pathsep.join(extras + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=env,
    )
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        raise RuntimeError(f"FreeCAD prism 失败 (code {proc.returncode}): {out[-2500:]}")
    return out


def run_prism_build_fcstd(
    *,
    spec: PrismDesignSpec,
    out_fcstd: Path,
    timeout_s: float = 600.0,
) -> Path:
    out_fcstd = out_fcstd.resolve()
    out_fcstd.parent.mkdir(parents=True, exist_ok=True)
    spec_path = out_fcstd.parent / "prism_spec.json"
    spec_path.write_text(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    _run_freecad_script(
        ["build", "--spec", str(spec_path), "--out", str(out_fcstd)],
        timeout_s=timeout_s,
    )
    if not out_fcstd.is_file():
        raise RuntimeError(f"未生成 FCStd: {out_fcstd}")
    return out_fcstd


def run_prism_mesh_inp(
    *,
    fcstd: Path,
    out_inp: Path,
    spec: PrismDesignSpec | None = None,
    timeout_s: float = 3600.0,
) -> Path:
    fcstd = fcstd.resolve()
    out_inp = out_inp.resolve()
    out_inp.parent.mkdir(parents=True, exist_ok=True)
    args = ["mesh", "--fcstd", str(fcstd), "--out-inp", str(out_inp)]
    if spec is not None:
        args.extend(
            [
                "--mesh-max",
                str(float(spec.mesh_max_mm)),
                "--mesh-min",
                str(float(spec.mesh_min_mm)),
            ]
        )
    _run_freecad_script(args, timeout_s=timeout_s)
    if not out_inp.is_file() or out_inp.stat().st_size < 10_000:
        raise RuntimeError(f"INP 不完整: {out_inp}")
    return out_inp


__all__ = [
    "PrismDesignSpec",
    "parse_prism_design_brief",
    "design_spec_json_from_prism",
    "prism_sessions_root",
    "new_prism_session_id",
    "prism_session_dir",
    "write_prism_session_meta",
    "read_prism_session_meta",
    "write_prism_design_files",
    "run_prism_build_fcstd",
    "run_prism_mesh_inp",
]
