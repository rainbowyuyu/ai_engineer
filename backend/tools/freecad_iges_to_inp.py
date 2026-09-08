"""
CAD（IGES/STEP）→ CalculiX INP：经 FreeCAD FEM + Gmsh。

由仓库根目录下的 ``scripts/freecad_iges_to_inp_runner.py`` 在 FreeCAD 环境内执行；
本模块负责写临时 ``.fcigesmesh`` 配置并启动 ``FreeCADCmd`` / 同目录 ``python.exe``。
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

OUTPUT_INP_NAME = "from_cad_gmsh.inp"


def _extent_from_obj_preview(cad_path: Path) -> float | None:
    """从同目录 design_preview.obj / source_preview.obj 估计包围盒对角线（mm）。"""
    parent = cad_path.parent
    for name in ("design_preview.obj", "source_preview.obj"):
        obj = parent / name
        if not obj.is_file():
            continue
        xmin = ymin = zmin = float("inf")
        xmax = ymax = zmax = float("-inf")
        n = 0
        try:
            with obj.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.startswith("v "):
                        continue
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    try:
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    except ValueError:
                        continue
                    xmin, xmax = min(xmin, x), max(xmax, x)
                    ymin, ymax = min(ymin, y), max(ymax, y)
                    zmin, zmax = min(zmin, z), max(zmax, z)
                    n += 1
                    if n >= 250_000:
                        break
        except OSError:
            continue
        if n < 8 or xmax <= xmin:
            continue
        return float(math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2))
    return None


def _extent_from_session_meta(cad_path: Path) -> float | None:
    """设计域会话：用 triangle_side / corner 等估计特征尺度（mm）。"""
    sj = cad_path.parent / "session.json"
    if not sj.is_file():
        return None
    try:
        meta = json.loads(sj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(meta, dict):
        return None
    try:
        side = float(meta.get("triangle_side_mm") or 0.0)
    except (TypeError, ValueError):
        side = 0.0
    if side >= 2000.0:
        try:
            z_span = float(meta.get("domain_z_span_mm") or 0.0)
        except (TypeError, ValueError):
            z_span = 0.0
        horiz = side * (2.0 / math.sqrt(3.0))
        if z_span > 100.0:
            return float(math.sqrt(horiz * horiz + z_span * z_span))
        return float(horiz)
    try:
        cr = float(meta.get("corner_r_mm") or 0.0)
    except (TypeError, ValueError):
        cr = 0.0
    if cr >= 500.0:
        return float(max(cr / 0.08, cr * 12.0))
    return None


def _prism_volume_mm3_from_session(cad_path: Path) -> float | None:
    """等边三棱柱体积估计（mm³），供单元尺寸反算。"""
    sj = cad_path.parent / "session.json"
    if not sj.is_file():
        return None
    try:
        meta = json.loads(sj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(meta, dict):
        return None
    try:
        side = float(meta.get("triangle_side_mm") or 0.0)
        z_span = float(meta.get("domain_z_span_mm") or 0.0)
    except (TypeError, ValueError):
        return None
    if side < 2000.0:
        return None
    if z_span < 100.0:
        z_span = side * 0.28  # 缺高度时的保守占比
    # 等边三角形面积 * 高
    return float(0.25 * math.sqrt(3.0) * side * side * z_span)


def estimate_domain_extent_mm(cad_path: Path) -> float | None:
    """估计设计域特征尺度（包围盒对角线量级，mm）。"""
    for fn in (_extent_from_session_meta, _extent_from_obj_preview):
        try:
            v = fn(cad_path)
        except Exception:
            v = None
        if v is not None and float(v) >= 500.0:
            return float(v)
    return None


def default_coarse_char_length_max(cad_path: Path) -> float:
    """
    OC4 设计域「体网格」默认尺寸：面向 BESO 拓扑优化的可运行体量
    （约数万～十几万单元），CharacteristicLengthMax **越大越粗**。
    """
    base = float(suggest_char_length_max(cad_path))
    return float(min(35_000.0, max(base * 1.12, base + 150.0, 900.0)))


def suggest_char_length_max(cad_path: Path) -> float:
    """
    估计 Gmsh CharacteristicLengthMax（mm）。
    优先按几何体积/尺度 + BESO 目标单元数；文件体量仅作弱回退。
    可用 ``GMSH_CHAR_LENGTH_MAX`` 强制覆盖。
    """
    env = (os.environ.get("GMSH_CHAR_LENGTH_MAX") or "").strip()
    if env:
        try:
            return max(5.0, float(env))
        except ValueError:
            pass

    from backend.tools.inp_mesh_scan import beso_mesh_target_elements

    target = float(beso_mesh_target_elements())
    # 正则四面体体积系数约 a³/(6√2) ≈ 0.117 a³
    tet_coef = 0.117
    vol = _prism_volume_mm3_from_session(cad_path)
    if vol is not None and vol > 0.0:
        h = (vol / (target * tet_coef)) ** (1.0 / 3.0)
        return float(min(25_000.0, max(h, 900.0)))

    extent = estimate_domain_extent_mm(cad_path)
    if extent is not None and extent >= 2000.0:
        # 约 55 个单元跨对角线 → 百米级域 h ~ 2m，对应约十万级单元
        h_edge = extent / 55.0
        v_proxy = (extent**3) * 0.08
        h_vol = max(80.0, (v_proxy / (target * tet_coef)) ** (1.0 / 3.0))
        h = max(h_edge, h_vol * 0.85)
        return float(min(25_000.0, max(h, 900.0)))

    try:
        mb = cad_path.stat().st_size / (1024 * 1024)
    except OSError:
        return 1200.0
    # 设计域 STEP 往往文件小、几何大：抬高地板，避免百万级单元
    if mb >= 8.0:
        return 2200.0
    if mb >= 2.0:
        return 1800.0
    if mb >= 0.5:
        return 1400.0
    if mb >= 0.1:
        return 1200.0
    return 1000.0


def default_mesh_timeout_s() -> float:
    for key in ("FREECAD_MESH_TIMEOUT_S", "GMSH_TIMEOUT_S"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            try:
                return max(60.0, float(raw))
            except ValueError:
                pass
    return 7200.0


def list_iges_in_dir(scan_dir: Path) -> list[Path]:
    scan_dir = scan_dir.resolve()
    if not scan_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(scan_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in {".igs", ".iges"}:
            out.append(p)
    return out


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runner_script() -> Path:
    p = _repo_root() / "scripts" / "freecad_iges_to_inp_runner.py"
    if not p.is_file():
        raise FileNotFoundError(f"未找到 FreeCAD runner 脚本: {p}")
    return p


def resolve_freecad_cmd(explicit: Path | None = None) -> Path:
    if explicit is not None:
        p = explicit.resolve()
        if not p.is_file():
            raise FileNotFoundError(f"无效的 FreeCAD 可执行文件: {p}")
        return p
    env = (os.environ.get("FREECAD_CMD") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"环境变量 FREECAD_CMD 指向的文件不存在: {env}")
    for name in ("FreeCADCmd.exe", "freecadcmd.exe"):
        w = shutil.which(name)
        if w:
            return Path(w).resolve()
    guess = Path(r"D:\freecad\bin\freecadcmd.exe")
    if guess.is_file():
        return guess.resolve()
    raise FileNotFoundError(
        "未找到 FreeCADCmd：请设置环境变量 FREECAD_CMD，或将 FreeCADCmd 加入 PATH。"
    )


def mesh_python_exe(freecad_cmd: Path) -> Path:
    py = freecad_cmd.parent / "python.exe"
    if py.is_file():
        return py.resolve()
    return freecad_cmd.resolve()


def run_freecad_cad_to_inp(
    cad_path: Path,
    dest_inp: Path,
    *,
    char_length_max: float | None = None,
    char_length_min: float = 0.0,
    timeout_s: float | None = None,
    length_unit: str = "mm",
    compound_part_strategy: str = "largest_volume",
    element_order: str = "1st",
    element_dimension: str = "From Shape",
    geometry_tolerance: float = 0.0,
    optimize_std: bool = True,
    mesh_size_from_curvature: int | None = None,
    freecad_cmd: Path | None = None,
    check_beso: bool = True,
    cancel_event: threading.Event | None = None,
    proc_box: list[subprocess.Popen | None] | None = None,
) -> Path:
    """
    调用 FreeCAD + Gmsh 将 ``cad_path`` 写成 ``dest_inp``。

    Returns:
        ``dest_inp`` 解析后的路径。
    """
    cad_path = cad_path.resolve()
    if not cad_path.is_file():
        raise FileNotFoundError(f"CAD 文件不存在: {cad_path}")
    dest_inp = dest_inp.resolve()
    dest_inp.parent.mkdir(parents=True, exist_ok=True)

    cl_max = float(char_length_max) if char_length_max is not None else float(suggest_char_length_max(cad_path))
    cfg: dict[str, object] = {
        "cad_path": str(cad_path),
        "out_inp": str(dest_inp),
        "compound_part_strategy": compound_part_strategy,
        "element_dimension": element_dimension,
        "geometry_tolerance": geometry_tolerance,
        "optimize_std": optimize_std,
        "length_unit": length_unit,
        "characteristic_length_max": cl_max,
        "characteristic_length_min": float(char_length_min),
        "element_order": element_order,
    }
    if mesh_size_from_curvature is not None:
        cfg["mesh_size_from_curvature"] = int(mesh_size_from_curvature)

    fc = resolve_freecad_cmd(freecad_cmd)
    exe = mesh_python_exe(fc)
    runner = runner_script()
    timeout = float(timeout_s) if timeout_s is not None else default_mesh_timeout_s()

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".fcigesmesh",
        delete=False,
        encoding="utf-8",
    ) as tf:
        json.dump(cfg, tf, indent=2)
        tmp_cfg = Path(tf.name)

    if cancel_event and cancel_event.is_set():
        raise RuntimeError("转换已取消")

    env = os.environ.copy()
    env["FC_IGES_MESH_CONFIG"] = str(tmp_cfg)
    proc: subprocess.Popen | None = None
    try:
        try:
            proc = subprocess.Popen(
                [str(exe), str(runner)],
                cwd=str(_repo_root()),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            raise RuntimeError(f"无法启动 FreeCAD 子进程：{e}") from e
        if proc_box is not None:
            if len(proc_box) < 1:
                proc_box.append(proc)
            else:
                proc_box[0] = proc

        deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
        while True:
            if cancel_event and cancel_event.is_set():
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=15)
                except Exception:
                    pass
                raise RuntimeError("转换已取消")
            ret = proc.poll()
            if ret is not None:
                break
            if deadline is not None and time.monotonic() > deadline:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=15)
                except Exception:
                    pass
                raise RuntimeError(
                    f"FreeCAD 网格转换超时（>{timeout}s）。可调大环境变量 FREECAD_MESH_TIMEOUT_S 或 GMSH_TIMEOUT_S。"
                )
            time.sleep(0.35)
    finally:
        tmp_cfg.unlink(missing_ok=True)
        if proc_box is not None and proc_box:
            proc_box[0] = None

    if proc is None:
        raise RuntimeError("FreeCAD 子进程未能启动")
    if proc.returncode != 0:
        raise RuntimeError(
            f"FreeCAD 子进程退出码 {proc.returncode}；请检查 CAD 与 FreeCAD/Gmsh 安装及几何。"
        )

    if not dest_inp.is_file():
        raise RuntimeError(f"未生成输出 INP: {dest_inp}")

    if check_beso:
        from backend.tools.inp_beso_compat import assert_inp_supported_by_beso
        from backend.tools.inp_mesh_scan import assert_inp_mesh_size_reasonable

        assert_inp_supported_by_beso(dest_inp)
        assert_inp_mesh_size_reasonable(dest_inp)

    return dest_inp


__all__ = [
    "default_coarse_char_length_max",
    "estimate_domain_extent_mm",
    "OUTPUT_INP_NAME",
    "default_mesh_timeout_s",
    "list_iges_in_dir",
    "mesh_python_exe",
    "resolve_freecad_cmd",
    "runner_script",
    "run_freecad_cad_to_inp",
    "suggest_char_length_max",
]
