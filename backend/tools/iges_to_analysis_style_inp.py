"""
IGES → 「example_3 / Analysis-1」风格的 CalculiX/Abaqus INP（算法与实现）。

================================================================================
算法概览（目标：形式对齐 Analysis-1.inp）
================================================================================

1. **几何与封闭性**
   - Gmsh + OpenCASCADE 读入 IGES，``occ.synchronize`` + ``removeAllDuplicates`` 缝合重复拓扑。
   - **体网格前提**：必须存在可划分三维区域的封闭体积（若干 Solid）。
   -  jacket 类模型常为薄壁曲面壳：若无封闭 Solid，``mesh.generate(3)`` 会失败或得到退化结果；
     此时需在 CAD 侧加厚、缝合成实体，或使用 ``oc4_design_domain_iges`` 等多实体 IGES。

2. **网格生成策略（与现有 gmsh_iges_to_inp 的差异）**
   - **强制三维**：仅 ``dim=3``（不写回退 2D 壳主导网格），以逼近 Analysis-1 的实体离散。
   - **四面体优先**：``Mesh.RecombineAll = 0``、``Mesh.Recombine3DAll = 0``，避免六面体主导；
     ``Algorithm3D`` 默认 Delaunay（Gmsh 1），得到线性四面体，对应 ``C3D4``。
   - **尺寸场**：``CharacteristicLengthMax`` / Min 与现有 ``suggest_char_length_max`` 一致，
     可用 ``GMSH_CHAR_LENGTH_MAX`` 覆盖。

3. **单元集划分（design_space / nondesign_space）**
   - Analysis-1 将全部实体单元写在 ``Elset=Solid_Part-1``，再用 ``*Elset`` 拆成
     ``nondesign_space`` 与 ``design_space``（互补）。
   - 自动化策略（几何启发式，可替换为 CAD 物理组导入）：
     - 计算每个四面体质心；
     - 若给定 ``design_bbox=(xmin,xmax,ymin,ymax,zmin,zmax)``：质心落入盒内 → ``design_space``，否则 ``nondesign_space``；
     - 若未给定 bbox：**默认全部单元归入 design_space**（``nondesign_space`` 为空时在写出阶段跳过空集，
       或按需并入单个占位单元策略——此处跳过空 elset 以避免无效deck）。

4. **INP 拼装层次（对齐 wiki Analysis-1）**
   - ``*Heading`` + Abaqus 风格分段注释 ``**``
   - ``*Node``（科学计数法）
   - ``*Element, Type=C3D4, Elset=Solid_Part-1``（全线性四面体）
   - ``*Nset``：可选 ``fixed_support``（用于最小可算边界）
   - ``*Elset``：`design_space` / `nondesign_space`
   - ``*Material, Name=Material-1`` + ``*Elastic``（默认与 Analysis-1：200000, 0.27）
   - ``*Solid section`` × 2
   - **不包含**：螺栓面 ``Nset``、``Rigid body``、真实 ``Cload``——这些依赖设计意图，
     应由用户在 HyperMesh/Abaqus 侧标注或通过 ``*INCLUDE`` 追加示例尾部；
     可选 ``minimal_static_step=True`` 仅生成 **底部节点固定 + 空载荷步骨架**，便于连通性检查。

5. **与 meshio 路径的关系**
   - 本模块优先保证 **结构语义** 与 Analysis-1 一致；若仅需快速 BESO 可读 INP，仍可使用 ``cad_iges_to_inp.py``
     （允许 2D/混合网格）。

详见 ``run_iges_to_analysis_style_inp()``。
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import meshio
import numpy as np

from backend.tools.gmsh_iges_to_inp import suggest_char_length_max, _num_threads_gmsh


def _mesh_iges_solid_tetra_msh(
    iges_path: Path,
    out_msh: Path,
    *,
    char_length_max: float,
    num_threads: int,
) -> None:
    """Gmsh 三维实体网格 → ``.msh``（以四面体为主）。"""
    import gmsh

    out_msh = out_msh.resolve()
    out_msh.parent.mkdir(parents=True, exist_ok=True)
    if out_msh.exists():
        out_msh.unlink()

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", float(num_threads))
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", float(char_length_max))
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 0.05)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        gmsh.option.setNumber("Mesh.RecombineAll", 0)
        gmsh.option.setNumber("Mesh.Recombine3DAll", 0)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.merge(str(iges_path.resolve()))
        gmsh.model.occ.synchronize()
        try:
            gmsh.model.occ.removeAllDuplicates()
        except Exception:
            pass
        gmsh.model.mesh.generate(3)
        gmsh.write(str(out_msh))
    finally:
        gmsh.finalize()


def _extract_tetra_connectivity(mesh: meshio.Mesh) -> np.ndarray:
    blocks = [cb.data for cb in mesh.cells if cb.type == "tetra"]
    if not blocks:
        types = sorted({cb.type for cb in mesh.cells})
        raise ValueError(
            "网格中无四面体单元（C3D4 所需）。当前单元类型: "
            f"{types}。封闭实体 IGES 才会产生体网格四面体。"
        )
    return np.vstack(blocks).astype(np.int64)


def _centroid_in_bbox(centers: np.ndarray, bbox: tuple[float, float, float, float, float, float]) -> np.ndarray:
    xmin, xmax, ymin, ymax, zmin, zmax = bbox
    return (
        (centers[:, 0] >= xmin)
        & (centers[:, 0] <= xmax)
        & (centers[:, 1] >= ymin)
        & (centers[:, 1] <= ymax)
        & (centers[:, 2] >= zmin)
        & (centers[:, 2] <= zmax)
    )


def _fmt_scientific_line_xyz(row: np.ndarray) -> str:
    x, y, z = float(row[0]), float(row[1]), float(row[2])
    return f"{x:.8E}, {y:.8E}, {z:.8E}"


def _write_elset_lines(lines: list[str], name: str, ids: np.ndarray, per_line: int = 16) -> None:
    if ids.size == 0:
        return
    lines.append(f"*Elset, Elset={name}")
    chunk: list[str] = []
    for i, eid in enumerate(ids.tolist()):
        chunk.append(str(int(eid)))
        if len(chunk) >= per_line:
            lines.append(", ".join(chunk) + ",")
            chunk = []
    if chunk:
        lines.append(", ".join(chunk))


def _write_analysis_style_inp(
    dest: Path,
    *,
    points: np.ndarray,
    tetra: np.ndarray,
    design_mask: np.ndarray,
    heading: str,
    young: float,
    nu: float,
    minimal_static_step: bool,
    fix_bottom_tol_frac: float,
) -> None:
    """写出类 Analysis-1 主干（无螺栓集 / 刚性体 / 真实载荷）。"""
    n_nodes = points.shape[0]
    n_elem = tetra.shape[0]

    lines: list[str] = []
    lines.append("**")
    lines.append("** Heading +++++++++++++++++++++++++++++++++++++++++++++++++")
    lines.append("**")
    lines.append("*Heading")
    lines.append(heading)
    lines.append("**")
    lines.append("** Nodes +++++++++++++++++++++++++++++++++++++++++++++++++++")
    lines.append("**")
    lines.append("*Node")
    for i in range(n_nodes):
        nid = i + 1
        lines.append(f"{nid}, {_fmt_scientific_line_xyz(points[i])}")

    lines.append("**")
    lines.append("** Elements ++++++++++++++++++++++++++++++++++++++++++++++++")
    lines.append("**")
    lines.append("*Element, Type=C3D4, Elset=Solid_Part-1")
    for e in range(n_elem):
        eid = e + 1
        n1, n2, n3, n4 = (int(tetra[e, j]) + 1 for j in range(4))
        lines.append(f"{eid}, {n1}, {n2}, {n3}, {n4}")

    fixed_nodes: np.ndarray | None = None
    if minimal_static_step:
        zmin = float(points[:, 2].min())
        dz = float(points[:, 2].max() - zmin) or 1.0
        tol = max(fix_bottom_tol_frac * dz, 1.0e-9)
        fn = np.nonzero(np.abs(points[:, 2] - zmin) <= tol)[0] + 1
        if fn.size > 0:
            fixed_nodes = fn.astype(np.int64)
            lines.append("**")
            lines.append("** Node sets +++++++++++++++++++++++++++++++++++++++++++++++")
            lines.append("**")
            lines.append("*Nset, Nset=fixed_support")
            chunk = []
            for nid in fixed_nodes.tolist():
                chunk.append(str(int(nid)))
                if len(chunk) >= 16:
                    lines.append(", ".join(chunk) + ",")
                    chunk = []
            if chunk:
                lines.append(", ".join(chunk))

    lines.append("**")
    lines.append("** Element sets ++++++++++++++++++++++++++++++++++++++++++++")
    lines.append("**")
    all_ids = np.arange(1, n_elem + 1, dtype=np.int64)
    design_ids = all_ids[design_mask]
    nondesign_ids = all_ids[~design_mask]
    _write_elset_lines(lines, "nondesign_space", nondesign_ids)
    _write_elset_lines(lines, "design_space", design_ids)

    lines.append("**")
    lines.append("** Materials +++++++++++++++++++++++++++++++++++++++++++++++")
    lines.append("**")
    lines.append("*Material, Name=Material-1")
    lines.append("*Elastic")
    lines.append(f"{young:g}, {nu:g}")
    lines.append("**")
    lines.append("** Sections ++++++++++++++++++++++++++++++++++++++++++++++++")
    lines.append("**")
    lines.append("*Solid section, Elset=design_space, Material=Material-1")
    if nondesign_ids.size > 0:
        lines.append("*Solid section, Elset=nondesign_space, Material=Material-1")
    lines.append("**")
    lines.append("** Constraints +++++++++++++++++++++++++++++++++++++++++++++")
    lines.append("**")
    lines.append("** （自动生成 deck 不含 Rigid body；可参考 Analysis-1.inp 追加）")
    lines.append("**")

    if minimal_static_step and fixed_nodes is not None and fixed_nodes.size > 0:
        lines.append("**")
        lines.append("** Steps +++++++++++++++++++++++++++++++++++++++++++++++++++")
        lines.append("**")
        lines.append("** Step-1（最小骨架：固定底部节点） +++++++++++++++++++++++++")
        lines.append("**")
        lines.append("*Step")
        lines.append("*Static")
        lines.append("*Boundary")
        lines.append("fixed_support, 1, 3, 0.")
        lines.append("*Node file")
        lines.append("U")
        lines.append("*El file")
        lines.append("S")
        lines.append("*End step")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_iges_to_analysis_style_inp(
    iges_path: Path,
    dest_inp: Path,
    *,
    char_length_max: float | None = None,
    design_bbox: tuple[float, float, float, float, float, float] | None = None,
    heading: str | None = None,
    young_modulus: float = 200000.0,
    poisson: float = 0.27,
    minimal_static_step: bool = False,
    fix_bottom_tol_frac: float = 1.0e-4,
) -> Path:
    """
    IGES → 类 ``Analysis-1.inp`` 结构的实体四面体 INP。

    Parameters
    ----------
    iges_path
        输入 ``.igs`` / ``.iges``。
    dest_inp
        输出 ``.inp``。
    char_length_max
        Gmsh 最大特征尺寸；默认 ``suggest_char_length_max``。
    design_bbox
        可选轴对齐盒 ``(xmin,xmax,ymin,ymax,zmin,zmax)``，用于拆分 ``design_space`` /
        ``nondesign_space``（按四面体质心）。
    heading
        ``*Heading`` 下一行说明文字。
    young_modulus, poisson
        与 Analysis-1 一致的默认弹性参数（单位与示例相同：MPa 量级）。
    minimal_static_step
        是否写出最小 ``*Step``（底部节点 ``fixed_support``）。
    fix_bottom_tol_frac
        判定底部节点时的相对 ``z`` 容差（相对模型 ``z`` 跨度比例）。
    """
    iges_path = iges_path.resolve()
    if not iges_path.is_file():
        raise FileNotFoundError(iges_path)

    cm = float(char_length_max) if char_length_max is not None else suggest_char_length_max(iges_path)
    nt = _num_threads_gmsh()
    title = heading or f"Gmsh solid tetra mesh from {iges_path.name}"

    with tempfile.TemporaryDirectory(prefix="iges_analysis_style_") as tmp:
        tmp_p = Path(tmp)
        msh_path = tmp_p / "vol.msh"
        _mesh_iges_solid_tetra_msh(iges_path, msh_path, char_length_max=cm, num_threads=nt)
        mesh = meshio.read(msh_path)
        tetra = _extract_tetra_connectivity(mesh)
        points = np.asarray(mesh.points, dtype=float)

        centers = points[tetra].mean(axis=1)
        n_elem = tetra.shape[0]
        if design_bbox is not None:
            design_mask = _centroid_in_bbox(centers, design_bbox)
            if not np.any(design_mask):
                design_mask = np.ones(n_elem, dtype=bool)
        else:
            design_mask = np.ones(n_elem, dtype=bool)

    _write_analysis_style_inp(
        dest_inp.resolve(),
        points=points,
        tetra=tetra,
        design_mask=design_mask,
        heading=title,
        young=young_modulus,
        nu=poisson,
        minimal_static_step=minimal_static_step,
        fix_bottom_tol_frac=fix_bottom_tol_frac,
    )
    return dest_inp.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="IGES → Analysis-1 风格的实体 C3D4 INP（见模块文档字符串）")
    parser.add_argument("iges", type=str)
    parser.add_argument("out_inp", type=str)
    parser.add_argument("--char-max", type=float, default=None)
    parser.add_argument("--bbox", type=float, nargs=6, metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"))
    parser.add_argument("--minimal-step", action="store_true")
    parser.add_argument("--young", type=float, default=200000.0)
    parser.add_argument("--nu", type=float, default=0.27)
    args = parser.parse_args()
    bbox = tuple(args.bbox) if args.bbox is not None else None
    run_iges_to_analysis_style_inp(
        Path(args.iges),
        Path(args.out_inp),
        char_length_max=args.char_max,
        design_bbox=bbox,
        minimal_static_step=args.minimal_step,
        young_modulus=args.young,
        poisson=args.nu,
    )
    print(Path(args.out_inp).resolve())
    return 0


if __name__ == "__main__":
    os.environ.setdefault("QT_LOGGING_RULES", "qt.widgets.qgraphicsview.warning=false")
    raise SystemExit(main())
