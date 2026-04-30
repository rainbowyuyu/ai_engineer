"""
IGES/IGS → BESO 可用 INP：**Open CASCADE** 曲面线性三角化（无 Gmsh、无体网格）。

默认在整体 ``BRepMesh_IncrementalMesh`` 之后用 ``StlAPI_Writer`` 导出 **单一 STL** 再经 meshio 读回，
使共边顶点焊接为连续壳网格；避免“按面拼节点”导致边上不共自由度、刚度奇异、CalculiX/BESO 极慢或界面无日志。

若 STL 路径失败，回退为按面读取三角化（并做几何容差合并，效果可能较差）。

依赖 ``cadquery-ocp``（``OCP``）与 ``meshio``。

环境变量：

- ``OCC_LINEAR_DEFLECTION``：线性偏差（模型单位，越大越快、越粗）。
- ``OCC_DEFLECTION_FRAC``：未设置 ``OCC_LINEAR_DEFLECTION`` 时，取 ``suggest_char_length_max(iges) * frac``（默认 0.04）。
- ``OCC_MERGE_TOL``：读入 STL 后再做共点合并的球半径；不设时用 ``max(1e-10*包围盒对角线, 0.005*线性偏差)``。设为 ``0`` 关闭。
"""
from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from pathlib import Path

import meshio
import numpy as np

from backend.tools.gmsh_iges_to_inp import suggest_char_length_max
from backend.tools.inp_beso_compat import assert_inp_supported_by_beso


def occ_sdk_available() -> bool:
    try:
        from OCP.IGESControl import IGESControl_Reader  # noqa: F401

        return True
    except ImportError:
        return False


def _linear_deflection(iges_path: Path, char_length_max: float | None, linear_deflection: float | None) -> float:
    if linear_deflection is not None:
        return max(1.0, float(linear_deflection))
    env = (os.environ.get("OCC_LINEAR_DEFLECTION") or "").strip()
    if env:
        return max(1.0, float(env))
    base = float(char_length_max) if char_length_max is not None else suggest_char_length_max(iges_path)
    frac_raw = (os.environ.get("OCC_DEFLECTION_FRAC") or "0.04").strip()
    try:
        frac = float(frac_raw)
    except ValueError:
        frac = 0.04
    return max(1.0, base * frac)


def _read_iges_shape(iges_path: Path):
    from OCP.IGESControl import IGESControl_Reader
    from OCP.IFSelect import IFSelect_RetDone

    r = IGESControl_Reader()
    st = r.ReadFile(str(iges_path.resolve()))
    if st != IFSelect_RetDone:
        raise RuntimeError(f"IGES 读入失败: status={st}")
    r.TransferRoots()
    return r.OneShape()


def _brep_mesh_once(shape, linear_deflection: float, angular_deflection: float) -> None:
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    BRepMesh_IncrementalMesh(shape, float(linear_deflection), False, float(angular_deflection), True)


def _collect_via_stl(shape) -> tuple[np.ndarray, np.ndarray]:
    """整体 STL：共边顶点焊接，适合作为壳 FEM 输入。"""
    from OCP.StlAPI import StlAPI_Writer

    fd, path = tempfile.mkstemp(suffix=".stl", prefix="occiges_")
    os.close(fd)
    stl_path = Path(path)
    try:
        writer = StlAPI_Writer()
        # 二进制 STL 易触发 meshio 误判（size 整数溢出），强制 ASCII 以便稳定读回焊接顶点。
        writer.ASCIIMode = True
        if not writer.Write(shape, str(stl_path)):
            raise RuntimeError("StlAPI_Writer.Write 返回 False")
        mesh = meshio.read(stl_path)
        tris = None
        for cb in mesh.cells:
            if cb.type == "triangle":
                tris = np.asarray(cb.data, dtype=np.int64)
                break
        if tris is None or tris.size == 0:
            raise RuntimeError("STL 中未找到 triangle 单元块")
        pts = np.asarray(mesh.points, dtype=np.float64)
        return pts, tris
    finally:
        stl_path.unlink(missing_ok=True)


def _collect_via_faces(shape) -> tuple[np.ndarray, np.ndarray]:
    """假定 ``shape`` 已 ``BRepMesh_IncrementalMesh``。按面拼三角网（共边可能不共点）。"""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    pts_blocks: list[np.ndarray] = []
    idx_blocks: list[np.ndarray] = []
    offset = 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            exp.Next()
            continue
        trsf = loc.Transformation()
        nb_v = tri.NbNodes()
        nb_t = tri.NbTriangles()
        if nb_v == 0 or nb_t == 0:
            exp.Next()
            continue
        local_pts = np.empty((nb_v, 3), dtype=np.float64)
        for i in range(1, nb_v + 1):
            p = tri.Node(i).Transformed(trsf)
            local_pts[i - 1] = (p.X(), p.Y(), p.Z())
        local_idx = np.empty((nb_t, 3), dtype=np.int64)
        for j in range(1, nb_t + 1):
            n1, n2, n3 = tri.Triangle(j).Get()
            local_idx[j - 1] = (n1 - 1, n2 - 1, n3 - 1)
        idx_blocks.append(offset + local_idx)
        pts_blocks.append(local_pts)
        offset += nb_v
        exp.Next()

    if not pts_blocks:
        raise RuntimeError("按面读取未得到任何三角网格。")

    return np.vstack(pts_blocks), np.vstack(idx_blocks)


def _bbox_diagonal(points: np.ndarray) -> float:
    lo = points.min(axis=0)
    hi = points.max(axis=0)
    return float(np.linalg.norm(hi - lo))


def _merge_coincident_vertices(points: np.ndarray, triangles: np.ndarray, tol: float) -> tuple[np.ndarray, np.ndarray]:
    if tol <= 0 or points.size == 0:
        return points, triangles

    inv = np.empty(len(points), dtype=np.int64)
    new_pts: list[np.ndarray] = []
    cells: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    inv_tol = 1.0 / tol

    def cell_key(p: np.ndarray) -> tuple[int, int, int]:
        return tuple(np.floor(p * inv_tol).astype(np.int64))

    for i in range(len(points)):
        p = points[i]
        ck = cell_key(p)
        hit: int | None = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    nk = (ck[0] + dx, ck[1] + dy, ck[2] + dz)
                    for j in cells.get(nk, ()):
                        if np.linalg.norm(new_pts[j] - p) <= tol:
                            hit = j
                            break
                    if hit is not None:
                        break
                if hit is not None:
                    break
            if hit is not None:
                break
        if hit is not None:
            inv[i] = hit
        else:
            j = len(new_pts)
            inv[i] = j
            cells[ck].append(j)
            new_pts.append(p.copy())

    new_arr = np.stack(new_pts, axis=0)
    tri = inv[triangles]
    ok = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    tri = tri[ok]
    return new_arr, tri


def _merge_tolerance(points: np.ndarray, linear_deflection: float) -> float:
    raw = (os.environ.get("OCC_MERGE_TOL") or "").strip()
    if raw in {"0", "0.0", "false", "no"}:
        return 0.0
    if raw:
        return max(0.0, float(raw))
    diag = _bbox_diagonal(points)
    return max(1e-10 * diag, 0.005 * float(linear_deflection), 1e-12)


def _write_s3_inp(points: np.ndarray, triangles: np.ndarray, dest_inp: Path) -> None:
    dest_inp = dest_inp.resolve()
    dest_inp.parent.mkdir(parents=True, exist_ok=True)
    partial = dest_inp.with_suffix(dest_inp.suffix + ".partial")
    partial.unlink(missing_ok=True)
    try:
        with partial.open("w", encoding="utf-8", newline="\n") as f:
            f.write("*Heading\n")
            f.write("IGES surface tessellation (Open CASCADE STL) -> S3 shell mesh for BESO\n")
            f.write("*NODE\n")
            for k in range(points.shape[0]):
                x, y, z = points[k]
                f.write(f"{k + 1}, {x:.16e}, {y:.16e}, {z:.16e}\n")
            f.write("*ELEMENT, type=S3, ELSET=EALL\n")
            for e, row in enumerate(triangles):
                a, b, c = int(row[0]) + 1, int(row[1]) + 1, int(row[2]) + 1
                f.write(f"{e + 1}, {a}, {b}, {c}\n")
        assert_inp_supported_by_beso(partial)
        os.replace(str(partial), str(dest_inp))
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def run_occ_iges_to_inp(
    iges_path: Path,
    dest_inp: Path,
    *,
    char_length_max: float | None = None,
    linear_deflection: float | None = None,
    angular_deflection: float | None = None,
    timeout_s: float | None = None,
    gmsh_bin: str | None = None,
) -> Path:
    """
    IGES → 仅壳单元（S3）的 INP。``timeout_s`` / ``gmsh_bin`` 仅为与 Gmsh 接口对齐，此处忽略。
    """
    del timeout_s, gmsh_bin
    if not occ_sdk_available():
        raise RuntimeError("未安装 Open CASCADE Python 绑定：请执行 pip install cadquery-ocp")
    iges_path = iges_path.resolve()
    if not iges_path.is_file():
        raise FileNotFoundError(f"IGES 文件不存在: {iges_path}")

    ld = _linear_deflection(iges_path, char_length_max, linear_deflection)
    ang = 0.5 if angular_deflection is None else float(angular_deflection)

    shape = _read_iges_shape(iges_path)
    _brep_mesh_once(shape, ld, ang)
    try:
        pts0, tri0 = _collect_via_stl(shape)
    except Exception:
        pts0, tri0 = _collect_via_faces(shape)
        n0 = len(pts0)
        mtol = _merge_tolerance(pts0, ld)
        if mtol > 0:
            pts1, tri1 = _merge_coincident_vertices(pts0, tri0, mtol)
            if n0 > 5000 and len(pts1) > 0.98 * n0:
                pts0, tri0 = _merge_coincident_vertices(pts0, tri0, mtol * 4.0)
            else:
                pts0, tri0 = pts1, tri1
    else:
        mtol = _merge_tolerance(pts0, ld)
        if mtol > 0:
            pts0, tri0 = _merge_coincident_vertices(pts0, tri0, mtol)

    _write_s3_inp(pts0, tri0, dest_inp)
    return dest_inp.resolve()
