from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.qwen_client import QwenClient

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
BASE_CONF = WORKSPACE_ROOT / "beso" / "beso_conf.py"
EXAMPLE2_CONF = WORKSPACE_ROOT / "beso" / "wiki_files" / "example_2" / "input_and_results" / "beso_conf.py"
EXAMPLE3_CONF = WORKSPACE_ROOT / "beso" / "wiki_files" / "example_3" / "work_files" / "analysis_files" / "beso_conf.py"


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
    if "analysis-1" in name or "plan" in name or "mesh" in name:
        return "primary_candidate"
    return "inp_candidate"


def _pick_primary_inp(items: list[InputFileItem]) -> str | None:
    if not items:
        return None
    preferred = [
        "femmeshgmsh.inp",
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
    preferred = "SolidMaterialElementGeometry2D"
    if preferred in domains:
        mapping["default_design_domain"] = preferred
    else:
        mapping["default_design_domain"] = domains[0]
    # Add extra candidates for UI inspection.
    for d in domains[:10]:
        mapping[d] = d
    return mapping


def scan_input_directory(scan_dir: str) -> InputBundle:
    root = Path(scan_dir).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"scan directory not found: {scan_dir}")

    files: list[InputFileItem] = []
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in {".inp", ".py", ".vtk", ".log", ".obj", ".step", ".stp"}:
            continue
        files.append(
            InputFileItem(
                name=p.name,
                path=str(p.resolve()),
                ext=ext,
                role=_classify_file(p),
            )
        )

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
                {"role": "system", "content": "你是结构优化文件路由器，只输出 JSON。"},
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
) -> GeneratedCodeBundle:
    optimization_base = optimization_base if optimization_base in {"failure_index", "stiffness"} else "failure_index"
    primary_inp = bundle.primary_inp or _llm_choose_primary(bundle)
    if not primary_inp:
        raise ValueError("No usable primary inp file was detected")

    primary_name = Path(primary_inp).name
    elsets = _scan_elsets(Path(primary_inp))
    if "SolidMaterialElementGeometry2D" in elsets:
        elset_name = "SolidMaterialElementGeometry2D"
        elset_source = "rule"
    elif elsets:
        elset_name = elsets[0]
        elset_source = "rule"
    else:
        elset_name = "all_available"
        elset_source = "default"

    load_case_names = [Path(p).name for p in bundle.aux_inps.get("load_case", [])]
    set_definition_names = [Path(p).name for p in bundle.aux_inps.get("set_definition", [])]
    other_inp_names = [Path(p).name for p in bundle.aux_inps.get("other_inp", [])]
    all_aux_names = load_case_names + set_definition_names + other_inp_names
    extra_comment = ", ".join(all_aux_names) if all_aux_names else "(none)"

    conf_text = _build_conf_from_examples(
        bundle=bundle,
        run_dir=run_dir,
        ccx_path=ccx_path,
        primary_name=primary_name,
        mass_goal_ratio=mass_goal_ratio,
        filter_radius=filter_radius,
        optimization_base=optimization_base,
        save_every=save_every,
        fallback_elset=elset_name,
        extra_comment=extra_comment,
    )

    manifest = {
        "scan_dir": bundle.scan_dir,
        "primary_inp": primary_name,
        "use_native_runner": ("example_1" in bundle.scan_dir.lower() or "plane_mesh" in primary_name.lower()),
        "aux_inps": {
            "load_case": load_case_names,
            "set_definition": set_definition_names,
            "other_inp": other_inp_names,
        },
        "step_mapping": bundle.step_mapping,
        "domain_mapping_candidates": bundle.domain_mapping_candidates,
        "params": {
            "mass_goal_ratio": mass_goal_ratio,
            "filter_radius": filter_radius,
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
print(f"[RUNNER] primary={{inp.name}} aux_count={{len(aux)}} load_cases={{len(strategy.load_cases)}}")
cmd = [os.environ.get("PYTHON_EXE", sys.executable), str(run_dir / "beso_main.py"), str(inp)]
raise SystemExit(subprocess.call(cmd, cwd=str(run_dir), env=os.environ.copy()))
"""

    return GeneratedCodeBundle(
        files={
            "task_manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
            "input_router.py": input_router,
            "strategy.py": strategy,
            "beso_conf.py": conf_text,
            "run_generated.py": run_script,
        },
        reasoning_summary=f"Detected primary input {primary_name}, merged auxiliary inp files, and generated full runnable pipeline files.",
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
    scan_s = bundle.scan_dir.lower()
    p = primary_name.lower()
    if "example_1" in scan_s or "plane_mesh" in p:
        if BASE_CONF.exists():
            return BASE_CONF
    if "example_3" in scan_s or "analysis-1" in p:
        if EXAMPLE3_CONF.exists():
            return EXAMPLE3_CONF
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
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    save_every: int,
    fallback_elset: str,
    extra_comment: str,
) -> str:
    tpl_path = _choose_conf_template(bundle, primary_name)
    if tpl_path.exists():
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
