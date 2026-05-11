from __future__ import annotations

import os
import json
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import meshio

from backend.tools.inp_beso_compat import assert_inp_supported_by_beso
from backend.tools.inp_mesh_scan import assert_inp_mesh_size_reasonable, auto_scale_filter_radius
from backend.tools.inp_elset import pick_usable_elset_name
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
    """
    收集 INP 中出现的体单元集名：显式 ``*ELSET``，以及 ``*Element`` / ``*Solid section`` 行里的 ``Elset=``。

    FCStd 流水线生成的 deck 往往不写 ``*ELSET``，仅用 ``*Element,..., Elset=design_space`` 分区；
    若只扫 ``*ELSET`` 会得到空列表，导致双域 beso_conf 无法触发、BESO 丢弃 nondesign_space。
    """
    names: list[str] = []
    seen: set[str] = set()
    pat_elset_line = re.compile(r"^\*ELSET\s*,\s*ELSET\s*=\s*([^,\s]+)", re.IGNORECASE)
    pat_elset_eq = re.compile(r"\bElset\s*=\s*([^,\s#]+)", re.IGNORECASE)

    def add(nm: str) -> None:
        t = (nm or "").strip().strip('"').strip("'")
        if not t or t in seen:
            return
        seen.add(t)
        names.append(t)

    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith("**"):
                continue
            m = pat_elset_line.match(s)
            if m:
                add(m.group(1))
                continue
            u = s.upper()
            if u.startswith("*ELEMENT") or ("SOLID" in u and "SECTION" in u):
                for m in pat_elset_eq.finditer(s):
                    add(m.group(1))
    return names


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
    iter_env = (os.environ.get("BESO_ITERATIONS_LIMIT") or "").strip()
    iter_line = ""
    if iter_env.isdigit() and int(iter_env) > 0:
        iter_line = f"iterations_limit = {int(iter_env)}\n"
    conf = f"""# Auto-generated by web agent (do not commit secrets)

path = r\"{work_dir}\"
path_calculix = r\"{ccx_path}\"
file_name = \"{file_name}\"

{iter_line}elset_name = \"{elset_name}\"
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


_RE_FIRST_SIMPLE_FILTER = re.compile(r'(\[\[\s*"simple"\s*,\s*)([\d.eE+-]+)', re.IGNORECASE)


def _parse_first_simple_filter_radius(conf_text: str) -> float | None:
    m = _RE_FIRST_SIMPLE_FILTER.search(conf_text)
    if not m:
        return None
    try:
        return float(m.group(2))
    except ValueError:
        return None


def _patch_first_simple_filter_radius(conf_text: str, new_r: float) -> str:
    return _RE_FIRST_SIMPLE_FILTER.sub(lambda m: f"{m.group(1)}{new_r}", conf_text, count=1)


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

    # Copy inp into run directory（若主 INP 已在 run_dir 内，避免 shutil.copy2 自覆盖导致 Windows WinError 32）
    inp_dst = run_dir / inp_src.name
    if inp_src.resolve() != inp_dst.resolve():
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

    assert_inp_supported_by_beso(inp_dst)
    assert_inp_mesh_size_reasonable(inp_dst)

    # Ensure we don't inherit FreeCAD/Python environment variables that can break subprocess resolution
    os.environ.pop("PYTHONHOME", None)
    os.environ.pop("PYTHONPATH", None)

    # Derive elset name（与 generator 一致，避免 meshio/Gmsh INP 误用 example_2 的 SolidMaterial*）
    elsets = _scan_elsets(inp_dst)
    elset_name = pick_usable_elset_name(elsets)
    elsets_ci = {e.strip().lower() for e in elsets if e.strip()}
    # FCStd / 任意双域 INP：必须让 beso_conf 同时声明 design_space 与 nondesign_space，
    # 否则 import_inp 会丢弃未在 domain_optimized 中出现的单元（柱体等非设计域会整段消失）。
    is_dual_design_nondesign_inp = "design_space" in elsets_ci and "nondesign_space" in elsets_ci
    is_oc4_dual_inp = inp_dst.name.lower() == "03_for_beso.inp" and is_dual_design_nondesign_inp
    is_sector120_inp = all(f"design_s{i}" in elsets_ci for i in range(3)) and "nondesign_space" in elsets_ci

    # Locate ccx
    ccx_path = Path(os.environ.get("CCX_PATH", r"D:\freecad\bin\ccx.exe")).resolve()
    if not ccx_path.exists():
        raise FileNotFoundError(f"ccx not found: {ccx_path}")

    conf_path = run_dir / "beso_conf.py"
    # 实际生效半径：优先读已有 beso_conf 里第一条 "simple" 滤波（旧任务常为 2.0），否则 manifest / 入参。
    r_req = float(filter_radius)
    try:
        mp = manifest.get("params") if isinstance(manifest.get("params"), dict) else {}
        if mp and mp.get("filter_radius") is not None:
            r_req = float(mp["filter_radius"])
    except Exception:
        r_req = float(filter_radius)

    conf_text_existing: str | None = None
    if conf_path.exists():
        try:
            conf_text_existing = conf_path.read_text(encoding="utf-8", errors="replace")
            rf = _parse_first_simple_filter_radius(conf_text_existing)
            if rf is not None:
                r_req = rf
        except Exception:
            pass

    try:
        fr_use, fr_note = auto_scale_filter_radius(inp_dst, r_req)
        if fr_note:
            on_log(f"[INFO] {fr_note}")
    except Exception:
        fr_use = float(r_req)

    oc4_dual_applied = False
    if is_sector120_inp or is_dual_design_nondesign_inp:
        try:
            from backend.tools.inp_oc4_design_nondesign import (
                repair_oc4_beso_inp_lines,
                write_beso_conf_example3_style,
                write_beso_conf_sector120_style,
            )

            raw_inp = inp_dst.read_text(encoding="utf-8", errors="replace")
            old_lines = raw_inp.splitlines()
            new_lines = repair_oc4_beso_inp_lines(old_lines)
            if new_lines != old_lines:
                inp_dst.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                elsets = _scan_elsets(inp_dst)
                elset_name = pick_usable_elset_name(elsets)
                if is_oc4_dual_inp:
                    on_log("[INFO] OC4：已修复 03_for_beso.inp（*STEP 前材料顺序 / 缺失 *MATERIAL）")
                else:
                    on_log("[INFO] 双域/扇区 INP：已整理 *STEP 前材料 / 固体截面顺序（如需要）")
            iter_env = (os.environ.get("BESO_ITERATIONS_LIMIT") or "").strip()
            # 未设置环境变量时用 "auto"（beso_main 按 mass_goal 等估算），避免长期卡在默认 8 次。
            iter_lim: int | str = (
                int(iter_env) if iter_env.isdigit() and int(iter_env) > 0 else "auto"
            )
            if is_sector120_inp:
                write_beso_conf_sector120_style(
                    conf_path,
                    work_dir=run_dir,
                    ccx_path=ccx_path,
                    inp_name=inp_dst.name,
                    mass_goal_ratio=mass_goal_ratio,
                    filter_radius=fr_use,
                    optimization_base=optimization_base,
                    iterations_limit=iter_lim,
                    save_iteration_results=max(1, int(save_every)),
                )
                oc4_dual_applied = True
                on_log("[INFO] 扇区 BESO：已写入 design_s0/1/2 + nondesign_space 的 beso_conf.py")
            else:
                write_beso_conf_example3_style(
                    conf_path,
                    work_dir=run_dir,
                    ccx_path=ccx_path,
                    inp_name=inp_dst.name,
                    mass_goal_ratio=mass_goal_ratio,
                    filter_radius=fr_use,
                    optimization_base=optimization_base,
                    iterations_limit=iter_lim,
                    save_iteration_results=max(1, int(save_every)),
                )
                oc4_dual_applied = True
                on_log(
                    "[INFO] 双域 BESO：已写入 design_space + nondesign_space 的 beso_conf.py（"
                    + ("OC4 03_for_beso" if is_oc4_dual_inp else "FCStd Analysis-beso 等")
                    + "）",
                )
        except Exception as e:
            on_log(f"[WARN] 双域/扇区 beso_conf / INP 预处理失败，将退回单域逻辑: {e}")

    if not oc4_dual_applied:
        if not conf_path.exists():
            _write_beso_conf(
                conf_path,
                work_dir=run_dir,
                ccx_path=ccx_path,
                file_name=inp_dst.name,
                elset_name=elset_name,
                mass_goal_ratio=mass_goal_ratio,
                filter_radius=fr_use,
                optimization_base=optimization_base,
                save_every=save_every,
            )
        elif conf_text_existing is not None:
            rf0 = _parse_first_simple_filter_radius(conf_text_existing)
            if rf0 is not None and abs(fr_use - rf0) > max(1e-9, 1e-6 * abs(rf0)):
                conf_path.write_text(
                    _patch_first_simple_filter_radius(conf_text_existing, fr_use),
                    encoding="utf-8",
                )
                on_log(f"[INFO] 已回写 {conf_path.name}：simple 滤波半径 {rf0:g} -> {fr_use:g}")

    iter_lim_env = (os.environ.get("BESO_ITERATIONS_LIMIT") or "").strip()
    if iter_lim_env.isdigit() and int(iter_lim_env) > 0 and conf_path.is_file():
        txt_lim = conf_path.read_text(encoding="utf-8", errors="replace")
        new_lim, n_lim = re.subn(
            r"^iterations_limit\s*=.*$",
            f"iterations_limit = {int(iter_lim_env)}",
            txt_lim,
            count=1,
            flags=re.MULTILINE,
        )
        if n_lim:
            conf_path.write_text(new_lim, encoding="utf-8")
            on_log(f"[INFO] iterations_limit = {int(iter_lim_env)}（BESO_ITERATIONS_LIMIT）")

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
        cmd = [str(py_exe), "-u", str(run_generated)]
    else:
        cmd = [str(py_exe), "-u", str(run_dir / "beso_main.py"), str(inp_dst)]
    if use_native_runner:
        on_log("[INFO] using native beso_main.py runner for compatibility.")
    on_log(f"[CMD] {' '.join(cmd)}")

    env = os.environ.copy()
    env["PYTHON_EXE"] = str(py_exe)
    env.setdefault("PYTHONUNBUFFERED", "1")
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

    # 后台线程持续读 stdout，避免子进程大量输出填满 PIPE 导致与主线程 readline 死锁（表现为优化“卡住”）。
    out_q: queue.Queue[str | None] = queue.Queue()

    def _drain_child_stdout() -> None:
        if not proc.stdout:
            out_q.put(None)
            return
        try:
            for line in iter(proc.stdout.readline, ""):
                out_q.put(line)
        finally:
            out_q.put(None)
            try:
                proc.stdout.close()
            except Exception:
                pass

    threading.Thread(target=_drain_child_stdout, name="beso-stdout-drain", daemon=True).start()

    def _drain_stdout_queue_nonblocking() -> None:
        while True:
            try:
                line = out_q.get_nowait()
            except queue.Empty:
                return
            if line is None:
                return
            on_log(line.rstrip("\n"))

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

            _drain_stdout_queue_nonblocking()

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

            # watcher：仅用 VTK 做 meshio→OBJ（BESO 的 file*_state1.inp 非 meshio 可解析格式，会误报失败）。
            best_mesh_src: Path | None = None
            best_iter: int | None = None
            source_vtk_name: str | None = None

            vtk_files = list(run_dir.glob("file*.vtk"))
            best_vtk: Path | None = None
            # 每迭代导出的 fileNNN.vtk 体积大；过小往往是未写完即被 meshio 读到导致 “Illegal VTK header”
            min_iter_vtk = int((os.environ.get("BESO_MIN_VTK_BYTES_PER_ITER") or "400000").strip())
            min_iter_vtk = max(4096, min_iter_vtk)
            for p in vtk_files:
                try:
                    if p.stat().st_size < min_iter_vtk:
                        continue
                except OSError:
                    continue
                m = re.match(r"^file(\d+)\.vtk$", p.name, re.IGNORECASE)
                if not m:
                    continue
                it = int(m.group(1))
                if best_iter is None or it > best_iter:
                    best_iter = it
                    best_vtk = p
            if best_vtk is None:
                rs = run_dir / "resulting_states.vtk"
                # 子进程可能已 create 但尚未 flush；过早 meshio.read 会得到空文件并打印误导性错误
                if rs.exists() and rs.stat().st_size >= 2048:
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
                    if best_mesh_src.suffix.lower() == ".vtk":
                        mesh = _read_vtk_for_preview(best_mesh_src, on_log)
                        # 默认不过滤：VTK→OBJ 若按 element_states 裁掉「void」，在双域或多 CELL 块时
                        # 易误删整块（预览像只剩设计域）。单域拓扑演化预览可设 BESO_PREVIEW_FILTER_VOID=1。
                        if (os.environ.get("BESO_PREVIEW_FILTER_VOID") or "").strip().lower() in (
                            "1",
                            "true",
                            "yes",
                        ):
                            mesh = _filter_mesh_by_latest_state(mesh)
                    else:
                        mesh = meshio.read(best_mesh_src)
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
                while True:
                    try:
                        line = out_q.get(timeout=0.3)
                    except queue.Empty:
                        break
                    if line is None:
                        break
                    on_log(line.rstrip("\n"))
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


def _read_vtk_for_preview(path: Path, on_log: Callable[[str], None], attempts: int = 12, delay: float = 0.12) -> meshio.Mesh:
    """避免 BESO 子进程尚未写完 VTK 时 meshio 读到半截文件（缺 CELL_TYPES）。"""
    last_err: Exception | None = None
    for _ in range(attempts):
        try:
            if not path.is_file():
                time.sleep(delay)
                continue
            if path.stat().st_size < 512:
                time.sleep(delay)
                continue
            # BESO 会在末尾追加多列 SCALARS，CELL_TYPES 常在文件前部
            head = path.read_bytes()[: min(path.stat().st_size, 600_000)]
            if b"CELL_TYPES" not in head:
                time.sleep(delay)
                continue
            return meshio.read(path)
        except Exception as e:
            last_err = e
            time.sleep(delay)
    if last_err:
        raise last_err
    raise RuntimeError(f"VTK not readable: {path}")


def _filter_mesh_by_latest_state(mesh: meshio.Mesh) -> meshio.Mesh:
    """
    BESO vtk 带 element_states* 标量时，可选地只保留 state>0 的单元（单域挖孔拓扑预览）。
    多 cell 块或双域模型上长度不对齐时，误删整块会使预览只剩「设计域」；故与长度不匹配的块整块保留。
    默认不在 OBJ 路径调用本函数；见环境变量 BESO_PREVIEW_FILTER_VOID。
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

    n_blocks = len(mesh.cells)
    filtered_cells: list[tuple[str, np.ndarray]] = []
    for block, state_arr in zip(mesh.cells, states_per_block):
        arr = np.asarray(state_arr).ravel()
        if arr.size == 0:
            filtered_cells.append((block.type, block.data))
            continue
        if arr.size != len(block.data):
            filtered_cells.append((block.type, block.data))
            continue
        mask = arr > 0.5
        if np.any(mask):
            filtered_cells.append((block.type, block.data[mask]))
        elif n_blocks > 1:
            # 多类型单元块时「全 0」常为状态列与块错位，保留以免非设计域整块消失
            filtered_cells.append((block.type, block.data))

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

