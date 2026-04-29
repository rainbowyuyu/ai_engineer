from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import meshio
import numpy as np


def _choose_beso_source_dir(workspace_root: Path, manifest: dict[str, Any], inp_src: Path) -> Path:
    """
    Pick runtime BESO source directory.
    - example_2 multi-file tasks should use files under wiki_files/example_2/input_and_results
    - otherwise fallback to default workspace_root/beso
    """
    default_dir = (workspace_root / "beso").resolve()
    ex2_dir = (workspace_root / "beso" / "wiki_files" / "example_2" / "input_and_results").resolve()

    scan_dir = str(manifest.get("scan_dir", "")).lower()
    primary_inp = str(manifest.get("primary_inp", "")).lower()
    aux = manifest.get("aux_inps", {}) if isinstance(manifest, dict) else {}
    has_multi_load = bool(aux.get("load_case")) if isinstance(aux, dict) else False
    is_example2_like = ("example_2" in scan_dir) or has_multi_load or ("femmeshgmsh" in primary_inp)

    if is_example2_like and ex2_dir.exists():
        required = ["beso_main.py", "beso_lib.py", "beso_filters.py", "beso_separate.py", "beso_conf.py"]
        if all((ex2_dir / f).exists() for f in required):
            return ex2_dir
    # fallback
    return default_dir

def _scan_elsets(inp_path: Path) -> list[str]:
    elsets: list[str] = []
    pat = re.compile(r"^\*ELSET\s*,\s*ELSET\s*=\s*([^,\s]+)", re.IGNORECASE)
    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pat.match(line.strip())
            if m:
                elsets.append(m.group(1))
    return elsets


def _scan_includes(inp_path: Path) -> list[str]:
    includes: list[str] = []
    pat = re.compile(r"^\*INCLUDE\s*,\s*INPUT\s*=\s*([^\r\n,]+)", re.IGNORECASE)
    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pat.match(line.strip())
            if m:
                includes.append(m.group(1).strip().strip('"').strip("'"))
    return includes


def _normalize_include_lines(inp_path: Path) -> None:
    pat = re.compile(r"^(\*INCLUDE\s*,\s*INPUT\s*=\s*)([^\r\n,]+)(.*)$", re.IGNORECASE)
    changed = False
    out_lines: list[str] = []
    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = pat.match(line.strip())
            if m:
                fixed = f"{m.group(1)}{m.group(2).strip()}{m.group(3)}"
                out_lines.append(fixed)
                changed = True
            else:
                out_lines.append(line)
    if changed:
        inp_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _norm_name_token(name: str) -> str:
    base = Path(name).name.lower()
    return re.sub(r"[^a-z0-9]+", "", base)


def _resolve_include_source(
    include_name: str,
    inp_src: Path,
    run_dir: Path,
    workspace_root: Path,
) -> Path | None:
    """
    Resolve missing *INCLUDE file with robust fallbacks for example_2 naming variants.
    """
    inc_base = Path(include_name).name
    src_dir = inp_src.parent

    # 0) already copied under another compatible name in run_dir
    run_siblings = list(run_dir.glob("*.inp"))
    if run_siblings:
        inc_tok = _norm_name_token(inc_base)
        for p in run_siblings:
            tok = _norm_name_token(p.name)
            if tok == inc_tok:
                return p

    # 1) exact in source directory
    exact = src_dir / inc_base
    if exact.exists():
        return exact

    # 2) common variant mapping: Node_Elem_sets <-> Node_sets
    variants = {
        inc_base,
        inc_base.replace("_Elem_sets", "_sets"),
        inc_base.replace("_elem_sets", "_sets"),
        inc_base.replace("Node_Elem_sets", "Node_sets"),
        inc_base.replace("node_elem_sets", "node_sets"),
    }
    for v in variants:
        p = src_dir / v
        if p.exists():
            return p

    # 3) fuzzy match in source directory by token similarity
    cand = [p for p in src_dir.glob("*.inp") if p.is_file()]
    if cand:
        inc_tok = _norm_name_token(inc_base)
        ranked = sorted(
            cand,
            key=lambda p: (
                0 if _norm_name_token(p.name) == inc_tok else 1,
                0 if "nodesets" in _norm_name_token(p.name) and "nodeelemsets" in inc_tok else 1,
                len(_norm_name_token(p.name)),
            ),
        )
        if ranked:
            top = ranked[0]
            top_tok = _norm_name_token(top.name)
            if top_tok == inc_tok or ("nodeelemsets" in inc_tok and "nodesets" in top_tok):
                return top

    # 4) workspace fallback (existing behavior, but token-aware)
    matches = list(workspace_root.glob(f"**/{inc_base}"))
    if matches:
        return matches[0]
    ws_inps = [p for p in workspace_root.glob("**/*.inp") if p.is_file()]
    if ws_inps:
        inc_tok = _norm_name_token(inc_base)
        ranked = sorted(
            ws_inps,
            key=lambda p: (
                0 if _norm_name_token(p.name) == inc_tok else 1,
                0 if "example_2" in str(p).lower() else 1,
                len(_norm_name_token(p.name)),
            ),
        )
        top = ranked[0]
        top_tok = _norm_name_token(top.name)
        if top_tok == inc_tok or ("nodeelemsets" in inc_tok and "nodesets" in top_tok):
            return top
    return None


def _write_beso_conf(
    target_path: Path,
    work_dir: Path,
    ccx_path: Path,
    file_name: str,
    elset_name: str,
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    save_every: int,
) -> None:
    conf = f"""# Auto-generated by web agent (do not commit secrets)

path = r\"{work_dir}\"
path_calculix = r\"{ccx_path}\"
file_name = \"{file_name}\"

elset_name = \"{elset_name}\"
domain_optimized[elset_name] = True
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[(\"stress_von_Mises\", 450.0e6)], [(\"stress_von_Mises\", 450.0)]]
domain_material[elset_name] = [\"*ELASTIC \\n210000e-6,  0.3\", \"*ELASTIC \\n210000,  0.3\"]
domain_same_state[elset_name] = False

mass_goal_ratio = {mass_goal_ratio}
filter_list = [[\"simple\", {filter_radius}]]
optimization_base = \"{optimization_base}\"
save_iteration_results = {save_every}
save_resulting_format = \"inp vtk\"
"""
    target_path.write_text(conf, encoding="utf-8")


def run_beso_job(
    workspace_root: Path,
    run_dir: Path,
    inp_path: Optional[str],
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    save_every: int,
    cancel_flag: threading.Event,
    on_log: Callable[[str], None],
    on_vtk: Callable[[str], None],
    on_artifact: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    workspace_root = workspace_root.resolve()
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    if not inp_path:
        raise ValueError("inp_path is required")
    inp_src = Path(inp_path).resolve()
    if not inp_src.exists():
        raise FileNotFoundError(inp_src)

    manifest_path = run_dir / "task_manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    # Copy inp into run directory
    inp_dst = run_dir / inp_src.name
    shutil.copy2(inp_src, inp_dst)
    _normalize_include_lines(inp_dst)
    selected_aux: set[str] = set()
    if manifest:
        aux = manifest.get("aux_inps", {})
        for group in ("load_case", "set_definition", "other_inp"):
            for name in aux.get(group, []):
                if isinstance(name, str) and name:
                    selected_aux.add(name)
    # Copy auxiliary inp files according to manifest; fallback to sibling mode for legacy behavior.
    if selected_aux:
        for name in sorted(selected_aux):
            sib = inp_src.parent / name
            if not sib.exists():
                on_log(f"[WARN] auxiliary inp missing: {name}")
                continue
            dst = run_dir / sib.name
            if not dst.exists():
                shutil.copy2(sib, dst)
    else:
        sibling_inps = list(inp_src.parent.glob("*.inp"))
        for sib in sibling_inps:
            dst = run_dir / sib.name
            if dst.resolve() == inp_dst.resolve():
                continue
            if not dst.exists():
                shutil.copy2(sib, dst)

    # Auto-heal INCLUDE dependencies for single-file uploads or missing auxiliary pieces.
    includes = _scan_includes(inp_dst)
    for inc in includes:
        inc_name = Path(inc).name
        dst = run_dir / inc_name
        if dst.exists():
            continue
        src_resolved = _resolve_include_source(inc_name, inp_src=inp_src, run_dir=run_dir, workspace_root=workspace_root)
        if src_resolved is not None:
            try:
                shutil.copy2(src_resolved, dst)
                if src_resolved.name != inc_name:
                    on_log(f"[INFO] include alias resolved: {inc_name} <= {src_resolved.name}")
                else:
                    on_log(f"[INFO] recovered include file: {inc_name}")
                continue
            except Exception:
                pass
        on_log(f"[WARN] include file not found: {inc_name}")

    # Ensure we don't inherit FreeCAD/Python environment variables that can break subprocess resolution
    os.environ.pop("PYTHONHOME", None)
    os.environ.pop("PYTHONPATH", None)

    # Derive elset name
    elsets = _scan_elsets(inp_dst)
    elset_name = "SolidMaterialElementGeometry2D" if "SolidMaterialElementGeometry2D" in elsets else (elsets[0] if elsets else "all_available")

    # Locate ccx
    ccx_path = Path(os.environ.get("CCX_PATH", r"D:\freecad\bin\ccx.exe")).resolve()
    if not ccx_path.exists():
        raise FileNotFoundError(f"ccx not found: {ccx_path}")

    conf_path = run_dir / "beso_conf.py"
    # Respect generated config if pre-created by generator.
    if not conf_path.exists():
        _write_beso_conf(
            conf_path,
            work_dir=run_dir,
            ccx_path=ccx_path,
            file_name=inp_dst.name,
            elset_name=elset_name,
            mass_goal_ratio=mass_goal_ratio,
            filter_radius=filter_radius,
            optimization_base=optimization_base,
            save_every=save_every,
        )

    # Run beso_main.py, ensuring it loads our config (same dir). Pick source set by task type.
    beso_src = _choose_beso_source_dir(workspace_root, manifest, inp_src)
    if not beso_src.exists():
        raise FileNotFoundError(f"beso source folder missing: {beso_src}")
    on_log(f"[INFO] runtime source selected: {beso_src}")

    # Minimal set of files needed
    required = [
        "beso_main.py",
        "beso_lib.py",
        "beso_filters.py",
        "beso_separate.py",
    ]
    # default source has beso_plots.py; example_2 source usually does not need it
    if (beso_src / "beso_plots.py").exists():
        required.append("beso_plots.py")
    for f in required:
        shutil.copy2(beso_src / f, run_dir / f)
        if on_artifact:
            on_artifact({"kind": "code", "path": f, "name": f, "meta": {"group": "runtime"}})

    # Always use the same interpreter as the backend process, to avoid
    # accidentally picking FreeCAD's python from PATH on Windows.
    py_exe = Path(os.environ.get("PYTHON_EXE", sys.executable)).resolve()
    if not py_exe.exists():
        py_exe = Path(sys.executable).resolve()

    use_native_runner = bool(manifest.get("use_native_runner"))
    run_generated = run_dir / "run_generated.py"
    if run_generated.exists() and not use_native_runner:
        cmd = [str(py_exe), str(run_generated)]
    else:
        cmd = [
            str(py_exe),
            str(run_dir / "beso_main.py"),
            str(inp_dst),
        ]
    if use_native_runner:
        on_log("[INFO] using native beso_main.py runner for compatibility.")
    on_log(f"[CMD] {' '.join(cmd)}")

    env = os.environ.copy()
    env["PYTHON_EXE"] = str(py_exe)
    # Force non-GUI rendering so Windows won't pop up plot windows.
    env.setdefault("MPLBACKEND", "Agg")

    proc = subprocess.Popen(
        cmd,
        cwd=str(run_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    last_iter_seen: int = -1
    last_mesh_token: str | None = None
    last_img_mtime: dict[str, float] = {}
    last_resulting_states_mtime: float = 0.0
    beso_log_path = run_dir / f"{inp_dst.stem}.log"
    last_beso_log_pos: int = 0
    proc_exit_code: int | None = None
    try:
        while True:
            if cancel_flag.is_set():
                on_log("[INFO] cancelling job, terminating process...")
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break

            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                on_log(line.rstrip("\n"))

            # Tail BESO log file to expose real optimization progress in UI/log stream.
            if beso_log_path.exists():
                try:
                    with beso_log_path.open("r", encoding="utf-8", errors="ignore") as f_log:
                        f_log.seek(last_beso_log_pos)
                        chunk = f_log.read()
                        last_beso_log_pos = f_log.tell()
                    if chunk:
                        for ln in chunk.splitlines():
                            s = ln.strip()
                            if not s:
                                continue
                            # keep stream concise but meaningful
                            if re.match(r"^\d+\s+", s) or s.startswith("i") or "iterations_limit" in s or "ERROR" in s or "FI_" in s:
                                on_log(f"[BESO] {s}")
                except Exception:
                    pass

            # watcher: images
            if on_artifact:
                for name in ("Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png"):
                    p = run_dir / name
                    if not p.exists():
                        continue
                    m = p.stat().st_mtime
                    prev = last_img_mtime.get(name, 0.0)
                    if m > prev:
                        last_img_mtime[name] = m
                        on_artifact({"kind": "image", "path": name, "name": name})

            # watcher: prefer state1 inp frames (true topology result), fallback to vtk
            best_mesh_src: Path | None = None
            best_iter: int | None = None
            source_vtk_name: str | None = None

            state1_inps = list(run_dir.glob("file*_state1.inp"))
            for p in state1_inps:
                m = re.match(r"^file(\d+)_state1\.inp$", p.name, re.IGNORECASE)
                if not m:
                    continue
                it = int(m.group(1))
                if best_iter is None or it > best_iter:
                    best_iter = it
                    best_mesh_src = p
                    source_vtk_name = f"file{it:03d}.vtk"

            if best_mesh_src is None:
                vtk_files = list(run_dir.glob("file*.vtk"))
                best_vtk: Path | None = None
                for p in vtk_files:
                    m = re.match(r"^file(\d+)\.vtk$", p.name, re.IGNORECASE)
                    if not m:
                        continue
                    it = int(m.group(1))
                    if best_iter is None or it > best_iter:
                        best_iter = it
                        best_vtk = p
                if best_vtk is None:
                    rs = run_dir / "resulting_states.vtk"
                    if rs.exists():
                        rs_mtime = rs.stat().st_mtime
                        if rs_mtime > last_resulting_states_mtime:
                            last_resulting_states_mtime = rs_mtime
                            best_vtk = rs
                            best_iter = last_iter_seen + 1
                if best_vtk is not None:
                    best_mesh_src = best_vtk
                    source_vtk_name = best_vtk.name if best_vtk.suffix.lower() == ".vtk" else None

            if best_mesh_src is not None and best_iter is not None:
                mesh_token = best_mesh_src.name
                should_update = (best_iter > last_iter_seen) or (mesh_token != last_mesh_token and mesh_token.startswith("file"))
                if not should_update:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue

                last_iter_seen = max(last_iter_seen, best_iter)
                last_mesh_token = mesh_token
                # write per-iteration obj so frontend can play frames
                frame_obj = run_dir / f"file{best_iter:03d}.obj"
                latest_obj = run_dir / "latest.obj"
                try:
                    mesh = meshio.read(best_mesh_src)
                    if best_mesh_src.suffix.lower() == ".vtk":
                        mesh = _filter_mesh_by_latest_state(mesh)
                    mesh = _strip_to_geometry(mesh)
                    meshio.write(frame_obj, mesh, file_format="obj")
                    # keep a stable pointer for "latest"
                    try:
                        latest_obj.write_text(frame_obj.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
                    except Exception:
                        # fallback to copy bytes
                        shutil.copy2(frame_obj, latest_obj)

                    on_vtk(latest_obj.name)
                    if on_artifact:
                        on_artifact(
                            {
                                "kind": "mesh",
                                "path": frame_obj.name,
                                "name": frame_obj.name,
                                "meta": {"source_vtk": source_vtk_name, "iter": best_iter},
                            }
                        )
                except Exception as e:
                    on_log(f"[WARN] mesh->obj convert failed: {e}")
                    on_vtk(best_mesh_src.name)
                    if on_artifact:
                        on_artifact(
                            {"kind": "mesh", "path": best_mesh_src.name, "name": best_mesh_src.name, "meta": {"iter": best_iter}}
                        )

            if proc.poll() is not None:
                proc_exit_code = proc.returncode
                # drain remaining
                if proc.stdout:
                    for rest in proc.stdout:
                        on_log(rest.rstrip("\n"))
                break

            time.sleep(0.05)
    finally:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    if proc_exit_code is None:
        proc_exit_code = proc.returncode
    if proc_exit_code not in (0, None):
        raise RuntimeError(f"beso_main exited with code {proc_exit_code}")


def _filter_mesh_by_latest_state(mesh: meshio.Mesh) -> meshio.Mesh:
    """
    BESO vtk files contain per-iteration cell_data like element_states000, element_states010, ...
    We keep only elements with state > 0 in the latest available state field so the 3D preview
    reflects topology evolution instead of showing the full original domain.
    """
    state_keys = [k for k in mesh.cell_data.keys() if k.startswith("element_states")]
    if not state_keys:
        return mesh

    def _suffix_num(k: str) -> int:
        m = re.search(r"(\d+)$", k)
        return int(m.group(1)) if m else -1

    latest_key = max(state_keys, key=_suffix_num)
    states_per_block = mesh.cell_data.get(latest_key, [])
    if not states_per_block or len(states_per_block) != len(mesh.cells):
        return mesh

    filtered_cells = []
    for block, state_arr in zip(mesh.cells, states_per_block):
        arr = np.asarray(state_arr).ravel()
        if arr.size == 0:
            continue
        mask = arr > 0.5
        if np.any(mask):
            filtered_cells.append((block.type, block.data[mask]))

    if not filtered_cells:
        return mesh

    return meshio.Mesh(points=mesh.points, cells=filtered_cells)


def _strip_to_geometry(mesh: meshio.Mesh) -> meshio.Mesh:
    """
    Convert mesh into OBJ-compatible surface cells (triangle/quad only),
    and drop all metadata to avoid incompatibilities across iterations.
    """
    allowed = {"triangle", "quad"}
    surface_cells: list[tuple[str, np.ndarray]] = []
    volume_blocks: list[tuple[str, np.ndarray]] = []

    for c in mesh.cells:
        if c.type in allowed:
            surface_cells.append((c.type, c.data))
        elif c.type in {"tetra", "hexahedron", "wedge", "pyramid"}:
            volume_blocks.append((c.type, c.data))

    if not surface_cells and volume_blocks:
        tri_faces: list[tuple[int, int, int]] = []
        quad_faces: list[tuple[int, int, int, int]] = []

        # Keep only boundary faces: face appears exactly once.
        face_counter: dict[tuple[int, ...], tuple[int, ...]] = {}
        face_hits: dict[tuple[int, ...], int] = {}

        def add_face(face: tuple[int, ...]) -> None:
            key = tuple(sorted(face))
            face_hits[key] = face_hits.get(key, 0) + 1
            if key not in face_counter:
                face_counter[key] = face

        for ctype, data in volume_blocks:
            for row in data:
                n = [int(x) for x in row.tolist()]
                if ctype == "tetra":
                    faces = [
                        (n[0], n[1], n[2]),
                        (n[0], n[1], n[3]),
                        (n[0], n[2], n[3]),
                        (n[1], n[2], n[3]),
                    ]
                elif ctype == "hexahedron":
                    faces = [
                        (n[0], n[1], n[2], n[3]),
                        (n[4], n[5], n[6], n[7]),
                        (n[0], n[1], n[5], n[4]),
                        (n[1], n[2], n[6], n[5]),
                        (n[2], n[3], n[7], n[6]),
                        (n[3], n[0], n[4], n[7]),
                    ]
                elif ctype == "wedge":
                    faces = [
                        (n[0], n[1], n[2]),
                        (n[3], n[4], n[5]),
                        (n[0], n[1], n[4], n[3]),
                        (n[1], n[2], n[5], n[4]),
                        (n[2], n[0], n[3], n[5]),
                    ]
                else:  # pyramid
                    faces = [
                        (n[0], n[1], n[2], n[3]),
                        (n[0], n[1], n[4]),
                        (n[1], n[2], n[4]),
                        (n[2], n[3], n[4]),
                        (n[3], n[0], n[4]),
                    ]
                for f in faces:
                    add_face(f)

        for key, count in face_hits.items():
            if count != 1:
                continue
            f = face_counter[key]
            if len(f) == 3:
                tri_faces.append((f[0], f[1], f[2]))
            elif len(f) == 4:
                quad_faces.append((f[0], f[1], f[2], f[3]))

        if tri_faces:
            surface_cells.append(("triangle", np.asarray(tri_faces, dtype=np.int64)))
        if quad_faces:
            surface_cells.append(("quad", np.asarray(quad_faces, dtype=np.int64)))

    # Final fallback: keep whatever mesh has, but this may still fail for OBJ.
    if not surface_cells:
        surface_cells = [(c.type, c.data) for c in mesh.cells]

    return meshio.Mesh(points=mesh.points, cells=surface_cells)

