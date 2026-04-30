"""
IGES → BESO 可用 INP 的**代码路径**：优先使用 Gmsh **Python API**（进程内 mesh，无 gmsh.exe 子进程），
再由 meshio 写 Abaqus/CalculiX 风格 INP。若未安装 ``gmsh`` 包则回退到 ``gmsh_iges_to_inp`` 中的 exe 子进程逻辑。
"""
from __future__ import annotations

from pathlib import Path


def gmsh_sdk_available() -> bool:
    try:
        import gmsh  # noqa: F401
    except ImportError:
        return False
    return True


def mesh_iges_with_gmsh_sdk(
    iges_path: Path,
    out_msh: Path,
    *,
    dim: int,
    char_length_max: float,
    num_threads: int,
) -> None:
    """使用 Gmsh Python API 生成 ``.msh``（不写 .geo、不启子进程）。"""
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
        gmsh.merge(str(iges_path.resolve()))
        gmsh.model.occ.synchronize()
        try:
            gmsh.model.occ.removeAllDuplicates()
        except Exception:
            pass
        gmsh.model.mesh.generate(dim)
        gmsh.write(str(out_msh))
    finally:
        gmsh.finalize()
