from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.qwen_client import QwenClient
from backend.tools.inp_beso_compat import check_inp_beso_compat_error
from backend.tools.inp_elset import pick_usable_elset_name, template_elsets_match_primary
from backend.tools.inp_mesh_scan import auto_scale_filter_radius

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
BASE_CONF = WORKSPACE_ROOT / "beso" / "beso_conf.py"
EXAMPLE2_CONF = WORKSPACE_ROOT / "beso" / "wiki_files" / "example_2" / "input_and_results" / "beso_conf.py"
EXAMPLE3_CONF = WORKSPACE_ROOT / "beso" / "wiki_files" / "example_3" / "work_files" / "analysis_files" / "beso_conf.py"

# wiki 示例目录常在子文件夹下放 INP（如 example_2/input_and_results），仅扫一层根目录会漏文件
_SCAN_SKIP_DIR_NAMES = frozenset(
    {".git", "__pycache__", ".venv", ".venv_web", "node_modules", "runs", "frontend_static"}
)
_SCAN_MAX_DIR_DEPTH = 6
_SCAN_INPUT_EXTENSIONS = frozenset({".inp", ".py", ".vtk", ".log", ".obj", ".step", ".stp", ".igs", ".iges"})


@dataclass
class InputFileItem:
    name: str
    path: str
    ext: str
    role: str


@dataclass
class InputBundle:
    scan_dir: str
    primary_inp: str | None
    files: list[InputFileItem]
    notes: list[str]
    aux_inps: dict[str, list[str]]
    step_mapping: dict[str, int]
    domain_mapping_candidates: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "scan_dir": self.scan_dir,
            "primary_inp": self.primary_inp,
            "files": [
                {"name": x.name, "path": x.path, "ext": x.ext, "role": x.role}
                for x in self.files
            ],
            "notes": self.notes,
            "aux_inps": self.aux_inps,
            "step_mapping": self.step_mapping,
            "domain_mapping_candidates": self.domain_mapping_candidates,
        }


@dataclass
class GeneratedCodeBundle:
    files: dict[str, str]
    reasoning_summary: str
    field_sources: dict[str, str]
    selected_inputs: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "reasoning_summary": self.reasoning_summary,
            "field_sources": self.field_sources,
            "selected_inputs": self.selected_inputs,
        }


def _classify_file(path: Path) -> str:
    name = path.name.lower()
    ext = path.suffix.lower()
    if ext == ".py":
        return "code_file"
    if ext == ".log":
        return "log_file"
    if ext == ".vtk":
        return "viz_file"
    if ext in {".igs", ".iges"}:
        return "cad_geometry"
    if ext != ".inp":
        return "other"
    if re.search(r"file\d+_state\d+\.inp$", name):
        return "result_state"
    if re.search(r"file\d+\.inp$", name):
        return "result_frame"
    if "force_lc" in name:
        return "load_case"
    if "node_elem_sets" in name or "node_sets" in name:
        return "set_definition"
    if "femmeshgmsh" in name:
        return "primary_candidate"
    if "for_beso" in name:
        return "primary_candidate"
    if "analysis-1" in name or "plan" in name:
        return "primary_candidate"
    return "inp_candidate"


def _pick_primary_inp(items: list[InputFileItem]) -> str | None:
    if not items:
        return None
    preferred = [
        "03_for_beso.inp",
        "beso2-femmeshgmsh.inp",
        "femmeshgmsh.inp",
        "from_cad_gmsh.inp",
        "analysis-1.inp",
        "plane_mesh.inp",
    ]
    inp_items = [x for x in items if x.ext == ".inp" and x.role not in {"result_state", "result_frame"}]
    if not inp_items:
        return None
    lower_map = {Path(x.path).name.lower(): x.path for x in inp_items}
    for n in preferred:
        if n in lower_map:
            return lower_map[n]
    inp_items = sorted(inp_items, key=lambda x: (0 if x.role == "primary_candidate" else 1, len(Path(x.path).name)))
    return inp_items[0].path


def _extract_lc_index(path: str) -> int | None:
    name = Path(path).name
    m = re.search(r"LC(\d+)", name, re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1))


def _scan_domain_mapping(primary_inp: Path) -> dict[str, str]:
    domains = _scan_elsets(primary_inp)
    mapping: dict[str, str] = {}
    if not domains:
        return mapping
    mapping["default_design_domain"] = pick_usable_elset_name(domains)
    # Add extra candidates for UI inspection.
    for d in domains[:10]:
        mapping[d] = d
    return mapping


def _collect_input_file_items(root: Path) -> list[InputFileItem]:
    """
    在 root 下按有限深度 BFS 收集支持的输入文件（兼容 wiki example_2/3 子目录结构）。
    """
    items: list[InputFileItem] = []
    seen: set[str] = set()
    q: deque[tuple[Path, int]] = deque([(root.resolve(), 0)])
    while q:
        dpath, depth = q.popleft()
        try:
            for p in sorted(dpath.iterdir()):
                if p.name.startswith("."):
                    continue
                if p.is_dir():
                    if p.name in _SCAN_SKIP_DIR_NAMES:
                        continue
                    if depth < _SCAN_MAX_DIR_DEPTH:
                        q.append((p.resolve(), depth + 1))
                    continue
                if not p.is_file():
                    continue
                ext = p.suffix.lower()
                if ext not in _SCAN_INPUT_EXTENSIONS:
                    continue
                key = str(p.resolve())
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    InputFileItem(
                        name=p.name,
                        path=key,
                        ext=ext,
                        role=_classify_file(p),
                    )
                )
        except (PermissionError, OSError):
            continue
    items.sort(key=lambda x: x.path.lower())
    return items


def scan_input_directory(scan_dir: str) -> InputBundle:
    root = Path(scan_dir).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"scan directory not found: {scan_dir}")

    files = _collect_input_file_items(root)

    notes: list[str] = []
    if any("force_lc" in x.name.lower() for x in files):
        notes.append("Detected multi-load-case files (Force_LC), using example_2 style grouping.")
    if any("analysis-1" in x.name.lower() for x in files):
        notes.append("Detected Analysis-1 model, prioritizing example_3 style routing.")

    primary_inp = _pick_primary_inp(files)

    load_case_inps = sorted(
        [x.path for x in files if x.ext == ".inp" and x.role == "load_case"],
        key=lambda p: (_extract_lc_index(p) is None, _extract_lc_index(p) or 9999, Path(p).name.lower()),
    )
    set_definition_inps = sorted([x.path for x in files if x.ext == ".inp" and x.role == "set_definition"], key=lambda p: Path(p).name.lower())
    other_inps = sorted(
        [
            x.path
            for x in files
            if x.ext == ".inp"
            and x.path != primary_inp
            and x.path not in set(load_case_inps + set_definition_inps)
            and x.role not in {"result_state", "result_frame"}
        ],
        key=lambda p: Path(p).name.lower(),
    )

    step_mapping: dict[str, int] = {}
    for i, p in enumerate(load_case_inps, start=1):
        step_mapping[Path(p).name] = _extract_lc_index(p) or i

    domain_mapping_candidates: dict[str, str] = {}
    if primary_inp:
        domain_mapping_candidates = _scan_domain_mapping(Path(primary_inp))
        if Path(primary_inp).name.lower() == "from_cad_gmsh.inp":
            err = check_inp_beso_compat_error(Path(primary_inp))
            if err:
                notes.append(
                    "from_cad_gmsh.inp 与拓扑优化流程不兼容（需壳/实体单元如 C3D4、C3D8、S4 等）。"
                    f" 摘要：{err}"
                )

    return InputBundle(
        scan_dir=str(root),
        primary_inp=primary_inp,
        files=files,
        notes=notes,
        aux_inps={
            "load_case": load_case_inps,
            "set_definition": set_definition_inps,
            "other_inp": other_inps,
        },
        step_mapping=step_mapping,
        domain_mapping_candidates=domain_mapping_candidates,
    )


def _scan_elsets(inp_path: Path) -> list[str]:
    elsets: list[str] = []
    pat = re.compile(r"^\*ELSET\s*,\s*ELSET\s*=\s*([^,\s]+)", re.IGNORECASE)
    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pat.match(line.strip())
            if m:
                elsets.append(m.group(1))
    return sorted(set(elsets))


def _scan_dir_session_beso_conf_path(bundle: InputBundle) -> Path:
    return Path(bundle.scan_dir).resolve() / "beso_conf.py"


def _primary_inp_suggests_oc4_dual_domain(primary_name: str, primary_elsets: list[str]) -> bool:
    """主文件为 ``03_for_beso.inp`` 且 ELSET 含 design_space + nondesign_space 时视为 OC4 双域任务。"""
    if primary_name.lower() != "03_for_beso.inp":
        return False
    lc = {e.strip().lower() for e in primary_elsets if e.strip()}
    return "design_space" in lc and "nondesign_space" in lc


def _should_use_oc4_session_beso_conf(bundle: InputBundle, primary_name: str) -> bool:
    scan_norm = bundle.scan_dir.replace("\\", "/").lower()
    if "_design_domain" in scan_norm:
        return True
    if primary_name.lower() == "03_for_beso.inp":
        return True
    return False


def _is_oc4_dual_domain_beso_conf_text(text: str) -> bool:
    return "design_space" in text and "nondesign_space" in text


def _patch_beso_conf_runtime_paths(
    text: str,
    *,
    run_dir: Path,
    ccx_path: Path,
    primary_name: str,
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    save_every: int,
) -> str:
    """
    仅改写运行期路径与常用超参，保留 OC4 finalize 写入的双域 domain_* 块，
    避免 _build_conf_from_examples 用单 elset 模板覆盖 design_space / nondesign_space。
    """
    conf = text
    conf = _replace_assignment(conf, "path", f'r"{run_dir}"')
    conf = _replace_assignment(conf, "path_calculix", f'r"{ccx_path}"')
    conf = _replace_assignment(conf, "file_name", f'"{primary_name}"')
    conf = _replace_assignment(conf, "mass_goal_ratio", str(float(mass_goal_ratio)))
    conf = _replace_assignment(conf, "filter_list", f'[["simple", {float(filter_radius)}]]')
    conf = _replace_assignment(conf, "optimization_base", f'"{optimization_base}"')
    conf = _replace_assignment(conf, "save_iteration_results", str(int(save_every)))
    conf = _replace_assignment(conf, "save_resulting_format", '"inp vtk"')
    if optimization_base == "stiffness":
        conf = _replace_assignment(conf, "reference_points", '"integration points"')
        conf = _replace_assignment(conf, "reference_value", '"max"')
    return conf


def _llm_choose_primary(bundle: InputBundle, qwen: QwenClient | None = None) -> str | None:
    qwen = qwen or QwenClient()
    if not qwen.api_key:
        return None
    inp_files = [Path(x.path).name for x in bundle.files if x.ext == ".inp"]
    if not inp_files:
        return None
    prompt = (
        "从候选 inp 文件中选择最适合作为拓扑优化主输入的文件名，只输出 JSON。\n"
        "格式: {\"primary_inp\":\"文件名或null\",\"reason\":\"一句话\"}\n"
        f"候选列表: {json.dumps(inp_files, ensure_ascii=False)}"
    )
    try:
        resp = qwen.chat(
            [
                {"role": "system", "content": "你是「AI Engineer」中的结构优化主 INP 路由器，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        content = resp["choices"][0]["message"]["content"]
        data = json.loads(content)
        picked = data.get("primary_inp")
        if not picked:
            return None
        for x in bundle.files:
            if Path(x.path).name == picked:
                return x.path
        return None
    except Exception:
        return None


def build_generated_code(
    bundle: InputBundle,
    run_dir: Path,
    ccx_path: Path,
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    save_every: int,
    primary_inp_override: str | None = None,
) -> GeneratedCodeBundle:
    optimization_base = optimization_base if optimization_base in {"failure_index", "stiffness"} else "failure_index"
    primary_inp = primary_inp_override or bundle.primary_inp or _llm_choose_primary(bundle)
    if not primary_inp:
        raise ValueError("No usable primary inp file was detected")

    primary_name = Path(primary_inp).name
    elsets = _scan_elsets(Path(primary_inp))
    elset_name = pick_usable_elset_name(elsets)
    if elset_name == "SolidMaterialElementGeometry2D":
        elset_source = "rule"
    elif elset_name == "all_available":
        elset_source = "default" if not elsets else "default_ignore_gmsh_boundary"
    else:
        elset_source = "rule"

    load_case_names = [Path(p).name for p in bundle.aux_inps.get("load_case", [])]
    set_definition_names = [Path(p).name for p in bundle.aux_inps.get("set_definition", [])]
    other_inp_names = [Path(p).name for p in bundle.aux_inps.get("other_inp", [])]
    all_aux_names = load_case_names + set_definition_names + other_inp_names
    extra_comment = ", ".join(all_aux_names) if all_aux_names else "(none)"

    filter_radius_used, filter_radius_note = auto_scale_filter_radius(Path(primary_inp), float(filter_radius))

    scan_conf = _scan_dir_session_beso_conf_path(bundle)
    session_raw = ""
    use_session_oc4 = False
    if scan_conf.is_file() and _should_use_oc4_session_beso_conf(bundle, primary_name):
        session_raw = scan_conf.read_text(encoding="utf-8", errors="ignore")
        if _is_oc4_dual_domain_beso_conf_text(session_raw):
            use_session_oc4 = True

    if use_session_oc4:
        patched = _patch_beso_conf_runtime_paths(
            session_raw,
            run_dir=run_dir,
            ccx_path=ccx_path,
            primary_name=primary_name,
            mass_goal_ratio=mass_goal_ratio,
            filter_radius=filter_radius_used,
            optimization_base=optimization_base,
            save_every=save_every,
        )
        conf_header = (
            "# Auto-generated: preserved OC4 session beso_conf.py (design_space + nondesign_space).\n"
            f"# Source: {scan_conf.as_posix()}\n"
            f"# Detected auxiliary inp files: {extra_comment}\n\n"
        )
        conf_text = conf_header + patched
        elset_source = "oc4_session_beso_conf"
    elif _primary_inp_suggests_oc4_dual_domain(primary_name, elsets) and EXAMPLE3_CONF.exists():
        raw_tpl = EXAMPLE3_CONF.read_text(encoding="utf-8", errors="ignore")
        patched = _patch_beso_conf_runtime_paths(
            raw_tpl,
            run_dir=run_dir,
            ccx_path=ccx_path,
            primary_name=primary_name,
            mass_goal_ratio=mass_goal_ratio,
            filter_radius=filter_radius_used,
            optimization_base=optimization_base,
            save_every=save_every,
        )
        conf_header = (
            "# Auto-generated: OC4 dual-domain beso_conf from wiki example_3 template "
            "(03_for_beso.inp + design_space/nondesign_space ELSETs; scan_dir 无会话 beso_conf 时).\n"
            f"# Detected auxiliary inp files: {extra_comment}\n\n"
        )
        conf_text = conf_header + patched
        elset_source = "oc4_example3_dual_template"
    else:
        conf_text = _build_conf_from_examples(
            bundle=bundle,
            run_dir=run_dir,
            ccx_path=ccx_path,
            primary_name=primary_name,
            primary_elsets=elsets,
            mass_goal_ratio=mass_goal_ratio,
            filter_radius=filter_radius_used,
            optimization_base=optimization_base,
            save_every=save_every,
            fallback_elset=elset_name,
            extra_comment=extra_comment,
        )

    manifest = {
        "scan_dir": bundle.scan_dir,
        "primary_inp": primary_name,
        # 直接跑 beso_main：避免 run_generated 子进程包一层后 stdout 块缓冲，日志在 [CMD] 后长时间空白。
        "use_native_runner": True,
        "aux_inps": {
            "load_case": load_case_names,
            "set_definition": set_definition_names,
            "other_inp": other_inp_names,
        },
        "step_mapping": bundle.step_mapping,
        "domain_mapping_candidates": bundle.domain_mapping_candidates,
        "params": {
            "mass_goal_ratio": mass_goal_ratio,
            "filter_radius": filter_radius_used,
            "optimization_base": optimization_base,
            "save_every": save_every,
        },
        "field_sources": {
            "primary_inp": "rule_or_llm",
            "elset_name": elset_source,
            "mass_goal_ratio": "user_or_agent",
            "filter_radius": "user_or_agent",
            "optimization_base": "user_or_agent",
            "save_every": "user_or_agent",
        },
    }

    input_router = """from __future__ import annotations
from pathlib import Path
import json


def load_manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "task_manifest.json").read_text(encoding="utf-8"))


def resolve_inputs(run_dir: Path) -> tuple[Path, list[Path]]:
    manifest = load_manifest(run_dir)
    primary = run_dir / manifest["primary_inp"]
    if not primary.exists():
        raise FileNotFoundError(f"primary inp missing: {primary}")
    aux = []
    for group in ("load_case", "set_definition", "other_inp"):
        for name in manifest.get("aux_inps", {}).get(group, []):
            p = run_dir / name
            if p.exists():
                aux.append(p)
    return primary, aux
"""

    strategy = """from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json


@dataclass
class OptimizationStrategy:
    primary_inp: str
    load_cases: list[str]
    step_mapping: dict[str, int]
    aggregate_mode: str = "max"


def load_strategy(run_dir: Path) -> OptimizationStrategy:
    manifest = json.loads((run_dir / "task_manifest.json").read_text(encoding="utf-8"))
    return OptimizationStrategy(
        primary_inp=manifest["primary_inp"],
        load_cases=list(manifest.get("aux_inps", {}).get("load_case", [])),
        step_mapping=dict(manifest.get("step_mapping", {})),
        aggregate_mode="max",
    )
"""

    run_script = f"""from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
from input_router import resolve_inputs
from strategy import load_strategy

run_dir = Path(__file__).resolve().parent
inp, aux = resolve_inputs(run_dir)
strategy = load_strategy(run_dir)
print(
    f"[RUNNER] primary={{inp.name}} aux_count={{len(aux)}} load_cases={{len(strategy.load_cases)}}",
    flush=True,
)
py = os.environ.get("PYTHON_EXE", sys.executable)
cmd = [py, "-u", str(run_dir / "beso_main.py"), str(inp)]
raise SystemExit(
    subprocess.call(cmd, cwd=str(run_dir), env=os.environ.copy(), stdout=sys.stdout, stderr=sys.stderr)
)
"""

    reasoning_summary = (
        f"Detected primary input {primary_name}, merged auxiliary inp files, and generated full runnable pipeline files."
    )
    if filter_radius_note:
        reasoning_summary += " " + filter_radius_note

    return GeneratedCodeBundle(
        files={
            "task_manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
            "input_router.py": input_router,
            "strategy.py": strategy,
            "beso_conf.py": conf_text,
            "run_generated.py": run_script,
        },
        reasoning_summary=reasoning_summary,
        field_sources={
            "primary_inp": "rule_or_llm",
            "elset_name": elset_source,
            "mass_goal_ratio": "user_or_agent",
            "filter_radius": "user_or_agent",
            "optimization_base": "user_or_agent",
            "save_every": "user_or_agent",
        },
        selected_inputs={
            "primary_inp": primary_name,
            "aux_inps": manifest["aux_inps"],
            "step_mapping": manifest["step_mapping"],
            "domain_mapping_candidates": manifest["domain_mapping_candidates"],
        },
    )


def _choose_conf_template(bundle: InputBundle, primary_name: str) -> Path:
    """
    仅在与目录/文件名明显对应时再选用各示例的 beso_conf；
    其它「无模板」单文件（如 CAD 生成的 from_cad_gmsh.inp）走 **example_1 的 BASE_CONF**，
    避免原先无条件优先 example_2 导致 ELSET 不匹配、落到极简兜底配置。
    """
    scan_s = bundle.scan_dir.lower()
    p = primary_name.lower()
    looks_example2 = "example_2" in scan_s or any(
        "force_lc" in x.name.lower() for x in bundle.files if x.ext == ".inp"
    )

    if "example_1" in scan_s or "plane_mesh" in p:
        if BASE_CONF.exists():
            return BASE_CONF
    if "example_3" in scan_s or "analysis-1" in p or "analysis_1" in p or "for_beso" in p:
        if EXAMPLE3_CONF.exists():
            return EXAMPLE3_CONF
    if looks_example2 and EXAMPLE2_CONF.exists():
        return EXAMPLE2_CONF
    if BASE_CONF.exists():
        return BASE_CONF
    if EXAMPLE2_CONF.exists():
        return EXAMPLE2_CONF
    if EXAMPLE3_CONF.exists():
        return EXAMPLE3_CONF
    return BASE_CONF


def _replace_assignment(text: str, key: str, value_expr: str) -> str:
    pat = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if pat.search(text):
        return pat.sub(lambda _m: f"{key} = {value_expr}", text, count=1)
    return text + f"\n{key} = {value_expr}\n"


def _build_conf_from_examples(
    bundle: InputBundle,
    run_dir: Path,
    ccx_path: Path,
    primary_name: str,
    primary_elsets: list[str],
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    save_every: int,
    fallback_elset: str,
    extra_comment: str,
) -> str:
    tpl_path = _choose_conf_template(bundle, primary_name)
    if tpl_path.exists() and template_elsets_match_primary(tpl_path, primary_elsets, EXAMPLE2_CONF, EXAMPLE3_CONF):
        conf = tpl_path.read_text(encoding="utf-8", errors="ignore")
    else:
        conf = ""

    if not conf.strip():
        # Last-resort minimal config if example templates are unavailable.
        conf = (
            'path = "."\n'
            'path_calculix = ""\n'
            f'file_name = "{primary_name}"\n'
            f'elset_name = "{fallback_elset}"\n'
            "domain_optimized[elset_name] = True\n"
            "domain_density[elset_name] = [1e-6, 1]\n"
            "domain_thickness[elset_name] = [1.0, 1.0]\n"
            "domain_offset[elset_name] = 0.0\n"
            "domain_orientation[elset_name] = []\n"
            'domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]\n'
            'domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]\n'
            "domain_same_state[elset_name] = False\n"
        )

    conf = _replace_assignment(conf, "path", f'r"{run_dir}"')
    conf = _replace_assignment(conf, "path_calculix", f'r"{ccx_path}"')
    conf = _replace_assignment(conf, "file_name", f'"{primary_name}"')
    # BASE / 示例模板里的 elset_name 需与主 INP 中实际 ELSET（如 EALL）一致；domain_*[elset_name] 依赖该变量。
    conf = _replace_assignment(conf, "elset_name", f'"{fallback_elset}"')
    conf = _replace_assignment(conf, "mass_goal_ratio", str(float(mass_goal_ratio)))
    conf = _replace_assignment(conf, "filter_list", f'[["simple", {float(filter_radius)}]]')
    conf = _replace_assignment(conf, "optimization_base", f'"{optimization_base}"')
    conf = _replace_assignment(conf, "save_iteration_results", str(int(save_every)))
    conf = _replace_assignment(conf, "save_resulting_format", '"inp vtk"')
    conf = _replace_assignment(conf, "reference_points", '"integration points"')
    conf = _replace_assignment(conf, "reference_value", '"max"')

    if "elset_name =" not in conf:
        conf += f'\nelset_name = "{fallback_elset}"\n'
        conf += "domain_optimized[elset_name] = True\n"
        conf += "domain_density[elset_name] = [1e-6, 1]\n"

    header = (
        "# Auto-generated from BESO example template.\n"
        "# Template source: "
        f"{tpl_path.as_posix() if tpl_path.exists() else '(fallback)'}\n"
        f"# Detected auxiliary inp files: {extra_comment}\n\n"
    )
    return header + conf
