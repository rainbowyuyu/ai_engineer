from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.qwen_client import QwenClient


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

    def as_dict(self) -> dict[str, Any]:
        return {
            "scan_dir": self.scan_dir,
            "primary_inp": self.primary_inp,
            "files": [
                {"name": x.name, "path": x.path, "ext": x.ext, "role": x.role}
                for x in self.files
            ],
            "notes": self.notes,
        }


@dataclass
class GeneratedCodeBundle:
    files: dict[str, str]
    reasoning_summary: str
    field_sources: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "reasoning_summary": self.reasoning_summary,
            "field_sources": self.field_sources,
        }


def _classify_file(path: Path) -> str:
    name = path.name.lower()
    if path.suffix.lower() != ".inp":
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
    return InputBundle(scan_dir=str(root), primary_inp=primary_inp, files=files, notes=notes)


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

    extra_inps = [
        Path(x.path).name
        for x in bundle.files
        if x.ext == ".inp" and Path(x.path).name != primary_name and x.role in {"load_case", "set_definition", "inp_candidate"}
    ]
    extra_comment = ", ".join(extra_inps) if extra_inps else "(none)"

    conf_text = f"""# Auto-generated by hybrid agent
path = r"{run_dir}"
path_calculix = r"{ccx_path}"
file_name = "{primary_name}"

elset_name = "{elset_name}"
domain_optimized[elset_name] = True
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

# Detected auxiliary inp files: {extra_comment}
mass_goal_ratio = {mass_goal_ratio}
filter_list = [["simple", {filter_radius}]]
optimization_base = "{optimization_base}"
save_iteration_results = {save_every}
save_resulting_format = "inp vtk"
"""

    run_script = f"""from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

run_dir = Path(__file__).resolve().parent
inp = run_dir / "{primary_name}"
cmd = [os.environ.get("PYTHON_EXE", sys.executable), str(run_dir / "beso_main.py"), str(inp)]
raise SystemExit(subprocess.call(cmd, cwd=str(run_dir), env=os.environ.copy()))
"""

    return GeneratedCodeBundle(
        files={
            "beso_conf.py": conf_text,
            "run_generated.py": run_script,
        },
        reasoning_summary=f"Detected primary input {primary_name} and generated config plus run entry.",
        field_sources={
            "primary_inp": "rule_or_llm",
            "elset_name": elset_source,
            "mass_goal_ratio": "user_or_agent",
            "filter_radius": "user_or_agent",
            "optimization_base": "user_or_agent",
            "save_every": "user_or_agent",
        },
    )
