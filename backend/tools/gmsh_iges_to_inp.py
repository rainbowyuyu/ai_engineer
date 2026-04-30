"""
IGES/IGS → volume/surface mesh via Gmsh CLI, then meshio → Abaqus/CalculiX-style .inp.

Requires ``gmsh`` on PATH or ``GMSH`` / ``GMSH_BIN`` environment variable pointing to the executable.
"""
from __future__ import annotations

import multiprocessing
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import meshio
from meshio import Mesh

from backend.tools.inp_beso_compat import assert_inp_supported_by_beso
from backend.tools.iges_mesh_code import gmsh_sdk_available, mesh_iges_with_gmsh_sdk

OUTPUT_INP_NAME = "from_cad_gmsh.inp"


def _mesh_drop_cells_below_dim(mesh: Mesh, min_dim: int = 2) -> Mesh | None:
    """剔除线/点单元，避免 meshio 写成 B31* 等 BESO 无法读取的梁单元主导 INP。"""
    keep = [i for i, cb in enumerate(mesh.cells) if getattr(cb, "dim", 0) >= min_dim]
    if not keep:
        return None
    new_cells = [mesh.cells[i] for i in keep]
    new_cell_data: dict = {}
    for key, blocks in mesh.cell_data.items():
        new_cell_data[key] = [blocks[i] for i in keep]
    new_cell_sets: dict = {}
    for key, blocks in mesh.cell_sets.items():
        new_cell_sets[key] = [blocks[i] for i in keep]
    return Mesh(
        mesh.points,
        new_cells,
        point_data=mesh.point_data,
        cell_data=new_cell_data,
        field_data=mesh.field_data,
        point_sets=mesh.point_sets,
        cell_sets=new_cell_sets,
        gmsh_periodic=getattr(mesh, "gmsh_periodic", None),
        info=mesh.info,
    )


def _mesh_keep_abaqus_supported_cells(mesh: Mesh) -> Mesh:
    """Gmsh 常带 vertex 等 0D 块，meshio 的 abaqus 写出器不支持，写 INP 前需剔除。"""
    from meshio.abaqus._abaqus import meshio_to_abaqus_type

    allowed = frozenset(meshio_to_abaqus_type.keys())
    keep = [i for i, cb in enumerate(mesh.cells) if cb.type in allowed]
    if not keep:
        types = sorted({cb.type for cb in mesh.cells})
        raise RuntimeError(
            "Gmsh 网格中没有任何 meshio 可写入 Abaqus INP 的单元类型。"
            f" 当前块类型: {types}"
        )
    new_cells = [mesh.cells[i] for i in keep]
    new_cell_data: dict = {}
    for key, blocks in mesh.cell_data.items():
        new_cell_data[key] = [blocks[i] for i in keep]
    new_cell_sets: dict = {}
    for key, blocks in mesh.cell_sets.items():
        new_cell_sets[key] = [blocks[i] for i in keep]
    return Mesh(
        mesh.points,
        new_cells,
        point_data=mesh.point_data,
        cell_data=new_cell_data,
        field_data=mesh.field_data,
        point_sets=mesh.point_sets,
        cell_sets=new_cell_sets,
        gmsh_periodic=getattr(mesh, "gmsh_periodic", None),
        info=mesh.info,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bundled_gmsh_candidates() -> list[Path]:
    """项目根下常见放置位置（例如解压到 <repo>/gmsh/gmsh.exe）。"""
    g = _repo_root() / "gmsh"
    return [g / "gmsh.exe", g / "gmsh.bat", g / "gmsh"]


def resolve_gmsh_bin() -> str | None:
    for key in ("GMSH", "GMSH_BIN"):
        v = (os.environ.get(key) or "").strip()
        if v and Path(v).exists():
            return str(Path(v).resolve())
        if v:
            return v
    w = shutil.which("gmsh")
    if w:
        return w
    for p in _bundled_gmsh_candidates():
        if p.is_file():
            return str(p.resolve())
    return None


def _posix(p: Path) -> str:
    return str(p.resolve()).replace("\\", "/")


def _num_threads_gmsh() -> int:
    raw = (os.environ.get("GMSH_NUM_THREADS") or "").strip()
    if raw:
        try:
            return max(1, min(64, int(raw)))
        except ValueError:
            pass
    return max(1, min(8, multiprocessing.cpu_count() or 1))


def suggest_char_length_max(iges_path: Path) -> float:
    """
    大 IGES 若仍用很细的 max edge length，Gmsh 会极慢。可用环境变量 GMSH_CHAR_LENGTH_MAX 覆盖。
    """
    env = (os.environ.get("GMSH_CHAR_LENGTH_MAX") or "").strip()
    if env:
        try:
            return max(5.0, float(env))
        except ValueError:
            pass
    try:
        mb = iges_path.stat().st_size / (1024 * 1024)
    except OSError:
        return 80.0
    if mb >= 8.0:
        return 600.0
    if mb >= 2.0:
        return 300.0
    if mb >= 0.5:
        return 160.0
    if mb >= 0.1:
        return 100.0
    return 70.0


def default_gmsh_timeout_s() -> float:
    raw = (os.environ.get("GMSH_TIMEOUT_S") or "").strip()
    if raw:
        try:
            return max(60.0, float(raw))
        except ValueError:
            pass
    return 600.0


def write_gmsh_msh_to_beso_inp(msh_path: Path, dest_inp: Path) -> Path:
    """
    读取 ``.msh``，经 meshio 过滤与 BESO 校验后写入 ``dest_inp``。

    Returns:
        ``dest_inp``
    """
    msh_path = msh_path.resolve()
    dest_inp = dest_inp.resolve()
    dest_inp.parent.mkdir(parents=True, exist_ok=True)

    mesh = meshio.read(msh_path, file_format="gmsh")
    if not mesh.cells:
        raise ValueError("Gmsh 产出空网格")
    mesh_fd = _mesh_drop_cells_below_dim(mesh, 2)
    if mesh_fd is None or not mesh_fd.cells:
        raise ValueError(
            "Gmsh 网格在去掉线/点单元后无剩余面或体单元；"
            "IGES 可能不是封闭实体或未能生成体网格，可尝试调整 GMSH_CHAR_LENGTH_MAX。"
        )
    mesh_w = _mesh_keep_abaqus_supported_cells(mesh_fd)
    partial = dest_inp.with_suffix(dest_inp.suffix + ".partial")
    partial.unlink(missing_ok=True)
    try:
        meshio.write(partial, mesh_w, file_format="abaqus")
        assert_inp_supported_by_beso(partial)
        os.replace(str(partial), str(dest_inp))
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return dest_inp


def _geo_merge_mesh(iges: Path, out_msh: Path, dim: int, char_max: float, num_threads: int) -> str:
    ig = _posix(iges)
    om = _posix(out_msh)
    nt = int(num_threads)
    # Coherence：缝合 OCC 重复拓扑，利于封闭体与体网格
    heal = "Coherence;\n"
    # 降低仅由边/曲率驱动的过细尺寸，减轻“全是线梁”倾向（仍可用 GMSH_CHAR_LENGTH_MAX 控制）
    mesh_opts = (
        "Mesh.MeshSizeFromPoints = 0;\n"
        "Mesh.MeshSizeFromCurvature = 0;\n"
        "Mesh.MeshSizeExtendFromBoundary = 1;\n"
    )
    # OpenCASCADE kernel for STEP/IGES
    return (
        f'SetFactory("OpenCASCADE");\n'
        f"General.NumThreads = {nt};\n"
        f'Merge "{ig}";\n'
        f"{heal}"
        f"Mesh.CharacteristicLengthMax = {char_max};\n"
        "Mesh.CharacteristicLengthMin = 0.05;\n"
        f"{mesh_opts}"
        f"Mesh {dim};\n"
        f'Save "{om}";\n'
    )


def _run_gmsh_cli_iges_to_inp(
    iges_path: Path,
    dest_inp: Path,
    *,
    char_m: float,
    timeout: float,
    threads: int,
    gmsh_bin: str | None,
) -> Path:
    """使用 ``gmsh.exe`` + ``.geo`` 子进程（回退路径）。"""
    exe = (gmsh_bin or "").strip() or resolve_gmsh_bin()
    if not exe:
        raise RuntimeError(
            "未找到 Gmsh 可执行文件：请安装 Gmsh 并加入 PATH，或设置 GMSH / GMSH_BIN；"
            "也可执行 pip install gmsh 使用 Python API 路径（无需 gmsh.exe）。"
        )

    dest_inp = dest_inp.resolve()
    dest_inp.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gmsh_iges_cli_") as tmp:
        tmp = Path(tmp)
        out_msh = tmp / "mesh_out.msh"
        geo_path = tmp / "convert.geo"
        last_err = ""

        for dim in (3, 2):
            geo_path.write_text(_geo_merge_mesh(iges_path, out_msh, dim, char_m, threads), encoding="utf-8")
            cmd = [exe, str(geo_path), "-"]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(tmp),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                raise RuntimeError(
                    f"Gmsh 超时（>{timeout}s）。可设置环境变量 GMSH_TIMEOUT_S、GMSH_CHAR_LENGTH_MAX 后重试。"
                ) from e

            if proc.returncode == 0 and out_msh.is_file() and out_msh.stat().st_size > 0:
                try:
                    write_gmsh_msh_to_beso_inp(out_msh, dest_inp)
                    return dest_inp
                except ValueError as ex:
                    last_err = str(ex)
                    continue
                except Exception as ex:
                    raise RuntimeError(f"写入 INP 失败（meshio/abaqus）：{ex}") from ex

            last_err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"

        raise RuntimeError(f"Gmsh 子进程网格失败（已尝试 3D/2D）：{last_err[:2000]}")


def run_gmsh_iges_to_inp(
    iges_path: Path,
    dest_inp: Path,
    *,
    char_length_max: float | None = None,
    timeout_s: float | None = None,
    gmsh_bin: str | None = None,
) -> Path:
    """
    IGES → BESO 可用 INP。

    1. **优先**：Gmsh **Python API**（``pip install gmsh``，进程内 ``mesh.generate``，无子进程）。
    2. **回退**：``gmsh.exe`` + ``.geo`` 子进程（需 ``GMSH``/``PATH``/捆绑路径）。

    Returns ``dest_inp`` on success.
    """
    iges_path = iges_path.resolve()
    if not iges_path.is_file():
        raise FileNotFoundError(f"IGES 文件不存在: {iges_path}")

    dest_inp = dest_inp.resolve()
    dest_inp.parent.mkdir(parents=True, exist_ok=True)

    char_m = float(char_length_max) if char_length_max is not None else suggest_char_length_max(iges_path)
    timeout = float(timeout_s) if timeout_s is not None else default_gmsh_timeout_s()
    threads = _num_threads_gmsh()

    if os.environ.get("CAD_FORCE_GMSH_CLI", "").strip().lower() in {"1", "true", "yes"}:
        return _run_gmsh_cli_iges_to_inp(iges_path, dest_inp, char_m=char_m, timeout=timeout, threads=threads, gmsh_bin=gmsh_bin)

    if gmsh_sdk_available():
        with tempfile.TemporaryDirectory(prefix="gmsh_iges_sdk_") as tmp:
            tmp = Path(tmp)
            out_msh = tmp / "mesh_out.msh"
            last_err = ""
            for dim in (3, 2):
                try:
                    mesh_iges_with_gmsh_sdk(
                        iges_path,
                        out_msh,
                        dim=dim,
                        char_length_max=char_m,
                        num_threads=threads,
                    )
                except Exception as ex:
                    last_err = str(ex)
                    continue
                if out_msh.is_file() and out_msh.stat().st_size > 0:
                    try:
                        return write_gmsh_msh_to_beso_inp(out_msh, dest_inp)
                    except ValueError as ex:
                        last_err = str(ex)
                        continue
            if last_err:
                try:
                    return _run_gmsh_cli_iges_to_inp(
                        iges_path, dest_inp, char_m=char_m, timeout=timeout, threads=threads, gmsh_bin=gmsh_bin
                    )
                except Exception as cli_e:
                    raise RuntimeError(
                        "Gmsh Python API 与 gmsh.exe 子进程均未成功。"
                        f" API 末次错误：{last_err[:1200]}；子进程：{cli_e}"
                    ) from cli_e

    return _run_gmsh_cli_iges_to_inp(iges_path, dest_inp, char_m=char_m, timeout=timeout, threads=threads, gmsh_bin=gmsh_bin)


def list_iges_in_dir(scan_dir: Path) -> list[Path]:
    scan_dir = scan_dir.resolve()
    if not scan_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(scan_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in {".igs", ".iges"}:
            out.append(p)
    return out
