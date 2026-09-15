"""Validate BESO state transfer against an unchanged engineering input deck.

The BESO INP importer checks only element identifiers. This module checks the
mesh, configured domains and state partition before writing its restart CSV.
The original full-precision input deck remains the solver input.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
import hashlib
import json
import re
import math
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Mesh:
    nodes: dict[int, tuple[float, ...]] = field(default_factory=dict)
    elements: dict[int, tuple[str, tuple[int, ...]]] = field(default_factory=dict)
    sets: dict[str, set[int | str]] = field(default_factory=dict)

    def element_set(self, name: str, stack: tuple[str, ...] = ()) -> set[int]:
        key = name.upper()
        if key in stack or key not in self.sets:
            raise ValueError("missing or recursive element set")
        result: set[int] = set()
        for value in self.sets[key]:
            if isinstance(value, int):
                result.add(value)
            else:
                result.update(self.element_set(value, (*stack, key)))
        if not result <= self.elements.keys():
            raise ValueError("element set references undefined elements")
        return result


def _element_size(kind: str) -> int:
    for prefix, count in (("C3D20", 20), ("C3D15", 15), ("C3D10", 10),
                          ("C3D8", 8), ("C3D6", 6), ("C3D4", 4)):
        if kind.startswith(prefix):
            return count
    for prefix in ("CPS", "CPE", "CAX", "M3D", "S"):
        if kind.startswith(prefix):
            suffix = kind[len(prefix):].rstrip("R")
            if suffix in {"3", "4", "6", "8"}:
                return int(suffix)
    raise ValueError(f"unsupported checkpoint element type: {kind}")


def read_mesh(path: Path) -> Mesh:
    """Read self-contained supported shell/solid decks, including set aliases."""
    mesh = Mesh()
    card, options, flags = "", {}, set()
    pending: list[int] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            if pending:
                raise ValueError("incomplete element connectivity")
            parts = [p.strip().upper() for p in line.split(",")]
            card = parts[0]
            options = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
            options = {k.strip(): v.strip() for k, v in options.items()}
            flags = set(p for p in parts[1:] if "=" not in p)
            if card in {"*INCLUDE", "*PART", "*INSTANCE"}:
                raise ValueError("checkpoint audit requires a self-contained mesh without assembly renumbering")
            if card == "*ELEMENT":
                _element_size(options.get("TYPE", ""))
            if card == "*ELSET":
                mesh.sets.setdefault(options["ELSET"], set())
            continue
        values = [p.strip() for p in line.split(",") if p.strip()]
        if card == "*NODE":
            nid = int(values[0])
            xyz = tuple(float(v.replace("D", "E")) for v in values[1:])
            if len(xyz) not in {2, 3} or nid in mesh.nodes or not all(math.isfinite(v) for v in xyz):
                raise ValueError("invalid or duplicate node")
            mesh.nodes[nid] = (*xyz, 0.0) if len(xyz) == 2 else xyz
        elif card == "*ELEMENT":
            pending.extend(int(v) for v in values)
            size = _element_size(options["TYPE"])
            if len(pending) < size + 1:
                continue
            if len(pending) != size + 1 or pending[0] in mesh.elements:
                raise ValueError("invalid or duplicate element")
            eid = pending[0]
            mesh.elements[eid] = (options["TYPE"], tuple(pending[1:]))
            if "ELSET" in options:
                mesh.sets.setdefault(options["ELSET"], set()).add(eid)
            pending = []
        elif card == "*ELSET":
            target = mesh.sets[options["ELSET"]]
            if "GENERATE" in flags:
                if len(values) not in {2, 3}:
                    raise ValueError("invalid generated element set")
                first, last = map(int, values[:2])
                step = int(values[2]) if len(values) == 3 else 1
                if first > last or step <= 0:
                    raise ValueError("invalid element range")
                target.update(range(first, last + 1, step))
            else:
                target.update(int(v) if v.isdigit() else v.upper() for v in values)
    if pending:
        raise ValueError("incomplete element at end of input")
    if any(n not in mesh.nodes for _, connectivity in mesh.elements.values() for n in connectivity):
        raise ValueError("element references an undefined node")
    return mesh


def read_literal_config(path: Path) -> dict[str, Any]:
    """Read generated BESO configuration without executing Python code."""
    values: dict[str, Any] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            raise ValueError("checkpoint config must contain literal assignments only")
        value = ast.literal_eval(node.value)
        target = node.targets[0]
        if isinstance(target, ast.Name):
            values[target.id] = value
        elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
            key = values[target.slice.id] if isinstance(target.slice, ast.Name) else ast.literal_eval(target.slice)
            values.setdefault(target.value.id, {})[key] = value
        else:
            raise ValueError("unsupported checkpoint config assignment")
    return values


def inspect_checkpoint(*, source_run: Path, target_input: Path,
                       workspace_root: Path, state1: Path | None = None) -> dict[str, Any]:
    root, source, target = workspace_root.resolve(), source_run.resolve(), target_input.resolve()
    for path in (source, target):
        path.relative_to(root)
    config_path = source / "beso_conf.py"
    config = read_literal_config(config_path)
    input_name = str(config["file_name"])
    if Path(input_name).name != input_name:
        raise ValueError("checkpoint input must be inside its source run")
    original = source / input_name
    status_path = source / "status.json"
    if status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("status") != "completed":
            raise ValueError("only completed solver runs may supply a checkpoint")
        completion = "job_status_completed"
    else:
        # Historical runs predate status.json. Require the actual solver's
        # terminal markers, not merely an exported state or sized geometry.
        status_path = original.with_suffix(".log")
        tail = "\n".join(status_path.read_text(encoding="utf-8").splitlines()[-8:])
        if (source / "failure.json").exists() or not re.search(r"^Finished at\s+.+\nTotal time\s+", tail, re.M):
            raise ValueError("historical solver run has no verified completion marker")
        completion = "legacy_solver_terminal_log"
    if sha256(original) != sha256(target):
        raise ValueError("continuation requires the identical full-precision input deck")
    if state1 is None:
        files = list(source.glob("file*_state1.inp"))
        state1 = max(files, key=lambda p: int(p.stem[4:].split("_")[0]))
    state1 = state1.resolve()
    if state1.parent != source or not state1.name.endswith("_state1.inp"):
        raise ValueError("checkpoint state must belong to its source run")
    state0 = state1.with_name(state1.name.replace("_state1.inp", "_state0.inp"))
    mesh = read_mesh(original)
    domains = config.get("domain_optimized") or {}
    if not domains:
        raise ValueError("no configured BESO domains")
    expected, protected = set(), set()
    for domain, optimized in domains.items():
        if not isinstance(optimized, bool) or len(config["domain_density"][domain]) != 2:
            raise ValueError("continuation supports explicit two-state BESO domains")
        ids = mesh.element_set(domain)
        if expected & ids:
            raise ValueError("overlapping configured domains")
        expected.update(ids)
        if not optimized:
            protected.update(ids)
    states: dict[int, int] = {}
    hashes = {str(p): sha256(p) for p in (original, config_path, status_path, state0, state1)}
    for state, path in enumerate((state0, state1)):
        exported = read_mesh(path)
        for nid, xyz in exported.nodes.items():
            if nid not in mesh.nodes or xyz != tuple(float(f"{v:.5E}") for v in mesh.nodes[nid]):
                raise ValueError("checkpoint node coordinates differ from the original mesh export")
        for eid, (kind, connectivity) in exported.elements.items():
            if eid not in expected or eid in states:
                raise ValueError("checkpoint has unknown or overlapping element states")
            original_kind, original_connectivity = mesh.elements[eid]
            if connectivity != original_connectivity or kind.startswith("C3D") != original_kind.startswith("C3D"):
                raise ValueError("checkpoint element connectivity or family changed")
            if state == 0 and eid in protected:
                raise ValueError("a protected element was removed")
            states[eid] = state
    if set(states) != expected:
        raise ValueError("checkpoint does not cover every configured element")
    return {"source_run": str(source), "input_path": str(original), "input_sha256": sha256(original),
            "source_state1_path": str(state1), "source_state1_sha256": hashes[str(state1)],
            "config": config, "source_hashes": hashes, "states": states,
            "nodes": len(mesh.nodes), "elements": len(mesh.elements),
            "configured_elements": len(expected), "retained_elements": sum(states.values()),
            "protected_elements": len(protected), "completion_evidence": completion,
            "state_partition_sha256": hashlib.sha256(json.dumps(sorted(states.items())).encode()).hexdigest(),
            "coordinate_comparison": "BESO %.5E export precision"}


def install_checkpoint(*, checkpoint: dict[str, Any], run_dir: Path,
                       target_input: Path, ccx_path: Path, iterations_limit: int | str = "auto") -> Path:
    """Install a validated state map and original physical config in a new run."""
    if Path(checkpoint["source_run"]).resolve() == run_dir.resolve():
        raise ValueError("continuation may not overwrite its source run")
    if iterations_limit != "auto" and (type(iterations_limit) is not int or not 1 <= iterations_limit <= 1000):
        raise ValueError("invalid continuation iteration budget")
    if sha256(target_input) != checkpoint["input_sha256"]:
        raise ValueError("input changed after checkpoint validation")
    if any(sha256(Path(p)) != h for p, h in checkpoint["source_hashes"].items()):
        raise ValueError("checkpoint changed during preparation")
    csv = run_dir / "initial_element_states.csv"
    csv.write_text("element_number,element_state\n" + "".join(
        f"{eid},{state}\n" for eid, state in sorted(checkpoint["states"].items())), encoding="utf-8")
    config = {**checkpoint["config"], "path": str(run_dir.resolve()),
              "file_name": target_input.name, "path_calculix": str(ccx_path.resolve()),
              "continue_from": str(csv.resolve()), "iterations_limit": iterations_limit}
    # These dictionaries are initialized by beso_main, then updated here.
    lines = []
    for key, value in config.items():
        if key.startswith("domain_") and isinstance(value, dict):
            lines.extend(f"{key}[{name!r}] = {item!r}" for name, item in value.items())
        else:
            lines.append(f"{key} = {value!r}")
    (run_dir / "beso_conf.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    audit = {k: v for k, v in checkpoint.items() if k != "states"}
    audit.update(restart_csv=str(csv), restart_csv_sha256=sha256(csv),
                 iterations_limit=iterations_limit, parameter_changes="execution paths and iteration allowance only",
                 checkpoint_semantics="element-state warm start; optimizer sensitivity history is reset")
    report = run_dir / "continuation_provenance.json"
    report.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
