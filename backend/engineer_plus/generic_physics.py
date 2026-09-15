"""Explicit, auditable boundary/load generation for generic solid meshes."""
from __future__ import annotations
import json
import math
import re
from pathlib import Path
from typing import Any


def _nodes(inp: Path) -> list[tuple[int, float, float, float]]:
    lines = inp.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    inside = False
    for line in lines:
        s = line.strip()
        if not s or s.startswith("**"):
            continue
        if s.startswith("*"):
            inside = s.split(",", 1)[0].upper() == "*NODE"
            continue
        if inside:
            try:
                p = [x.strip() for x in s.split(",")]
                node = (int(p[0]), *(float(v.replace("D", "E").replace("d", "e")) for v in p[1:4]))
                if len(node) != 4 or node[0] <= 0 or not all(math.isfinite(v) for v in node[1:]):
                    raise ValueError("invalid node coordinates")
                out.append(node)
            except (ValueError, IndexError) as exc:
                raise ValueError("invalid *NODE record") from exc
    if len({n[0] for n in out}) != len(out):
        raise ValueError("duplicate mesh node ids")
    return out


def _node_sets(inp: Path) -> dict[str, list[int]]:
    """Resolve explicit, generated and named node sets in a flat mesh deck.

    Generated triples describe ranges, not three individual support nodes.
    Unresolved or cyclic aliases must never silently change a load partition.
    """
    lines = inp.read_text(encoding="utf-8", errors="replace").splitlines()
    sets: dict[str, list[int | str]] = {}
    available = {n[0] for n in _nodes(inp)}
    active: str | None = None
    generated = False
    node_block = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("**"):
            continue
        keyword = stripped.split(",", 1)[0].upper()
        if keyword in {"*NSET", "*NODE"}:
            options = [p.strip().upper() for p in stripped.split(",")[1:]]
            if any(p.startswith(("INSTANCE=", "ELSET=")) for p in options):
                raise ValueError("instance/element-derived node sets require a dedicated parser")
            match = re.search(r"(?:^|,)\s*NSET\s*=\s*([^,\s]+)", stripped, re.I)
            active = match.group(1).strip().upper() if match else None
            generated = "GENERATE" in options
            node_block = keyword == "*NODE"
            if not node_block and active is None:
                raise ValueError("*NSET requires a name")
            if active:
                sets.setdefault(active, [])
            continue
        if stripped.startswith("*"):
            active = None
            continue
        if active:
            tokens = [s.strip().upper() for s in stripped.split(",") if s.strip()]
            if node_block:
                sets[active].append(int(tokens[0]))
            elif generated:
                if len(tokens) not in (2, 3) or not all(t.isdigit() for t in tokens):
                    raise ValueError("invalid NSET GENERATE record")
                first, last = map(int, tokens[:2])
                step = int(tokens[2]) if len(tokens) == 3 else 1
                if first < 1 or step < 1 or last < first or (last - first) % step:
                    raise ValueError("invalid NSET GENERATE range")
                count = (last - first) // step + 1
                if count > len(available):
                    raise ValueError("generated node set exceeds mesh node count")
                sets[active].extend(range(first, last + 1, step))
            else:
                sets[active].extend(int(t) if t.isdigit() else t for t in tokens)

    resolved: dict[str, list[int]] = {}

    def resolve(name: str, chain: set[str]) -> list[int]:
        if name in resolved:
            return resolved[name]
        if name in chain:
            raise ValueError("cyclic node set reference")
        if name not in sets:
            raise ValueError(f"unknown node set reference: {name}")
        values: set[int] = set()
        for member in sets[name]:
            if isinstance(member, int):
                values.add(member)
            else:
                values.update(resolve(member, chain | {name}))
        if not values <= available:
            raise ValueError("node set contains ids absent from mesh")
        resolved[name] = sorted(values)
        return resolved[name]

    for name in sets:
        resolve(name, set())
    return resolved


def _node_ids(value: Any, *, label: str) -> list[int] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set)):
        raise ValueError(f"{label} must be a list of node ids")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError(f"{label} contains a non-integer node id")
        try:
            node = int(item)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{label} contains a non-integer node id") from exc
        if not isinstance(item, str) and item != node:
            raise ValueError(f"{label} contains a non-integer node id")
        if node <= 0:
            raise ValueError(f"{label} contains an invalid node id")
        result.append(node)
    return sorted(set(result))


def _dofs(value: Any, *, label: str, default: list[int]) -> list[int]:
    if value is None:
        return list(default)
    result = _node_ids(value, label=label)
    assert result is not None
    if any(node < 1 or node > 6 for node in result):
        raise ValueError(f"{label} must contain DOF values from 1 to 6")
    return result


def _finite_float(value: Any, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _solid_element_ids(text: str, node_ids: set[int]) -> list[int]:
    """Read a flat, mesh-only solid deck before assigning one explicit material."""
    sizes = {"C3D4": 4, "C3D10": 10, "C3D6": 6, "C3D15": 15,
             "C3D8": 8, "C3D8R": 8, "C3D20": 20, "C3D20R": 20}
    ids: set[int] = set()
    size = None
    pending: list[int] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("**"):
            continue
        if s.startswith("*"):
            if pending:
                raise ValueError("incomplete solid element connectivity")
            key = s.split(",", 1)[0].upper()
            if key in {"*INCLUDE", "*PART", "*ASSEMBLY", "*STEP", "*SOLID SECTION",
                       "*SHELL SECTION", "*BEAM SECTION", "*MATERIAL"}:
                raise ValueError("generic_physics requires a flat mesh-only solid deck")
            if "AI_PLUS_" in s.upper():
                raise ValueError("mesh uses reserved AI_PLUS names")
            size = None
            if key == "*ELEMENT":
                match = re.search(r"(?:^|,)\s*TYPE\s*=\s*([^,\s]+)", s, re.I)
                typ = match.group(1).upper() if match else ""
                if typ not in sizes:
                    raise ValueError(f"unsupported solid element type: {typ}")
                size = sizes[typ]
            continue
        if size is not None:
            try:
                pending.extend(int(t.strip()) for t in s.split(",") if t.strip())
            except ValueError as exc:
                raise ValueError("invalid solid element record") from exc
            if len(pending) > size + 1:
                raise ValueError("invalid solid element connectivity length")
            if len(pending) == size + 1:
                eid, *connectivity = pending
                if eid <= 0 or eid in ids or not set(connectivity) <= node_ids:
                    raise ValueError("invalid or duplicate solid element id/connectivity")
                ids.add(eid)
                pending = []
    if pending or not ids:
        raise ValueError("mesh has no complete solid elements")
    return sorted(ids)


def apply_explicit_physics(inp_path: str | Path, out_path: str | Path,
                           physics: dict[str, Any]) -> dict[str, Any]:
    """Create a deck from explicit physics and auditable node selection.

    ``support_nodes``/``load_nodes`` or existing named sets are preferred. The
    min-z/max-z selection remains an explicit, recorded fallback for simple
    solids, rather than an implicit interpretation of every CAD model.
    """
    inp, out = Path(inp_path).resolve(), Path(out_path).resolve()
    required = ("youngs_modulus_pa", "poissons_ratio")
    missing = [k for k in required if physics.get(k) is None]
    if missing:
        raise ValueError("generic_physics missing: " + ", ".join(missing))
    if physics.get("load_n") is None and physics.get("load_vector_n") is None:
        raise ValueError("generic_physics requires load_n or load_vector_n")
    nodes = _nodes(inp)
    if len(nodes) < 2:
        raise ValueError("mesh contains fewer than two parseable nodes")
    available = {n[0] for n in nodes}
    text = inp.read_text(encoding="utf-8", errors="replace")
    element_ids = _solid_element_ids(text, available)
    youngs_pa = _finite_float(physics["youngs_modulus_pa"], label="youngs_modulus_pa")
    poisson = _finite_float(physics["poissons_ratio"], label="poissons_ratio")
    if youngs_pa <= 0 or not -1 < poisson < 0.5:
        raise ValueError("invalid isotropic elastic material")
    length_unit = str(physics.get("mesh_length_unit", "m")).lower()
    if length_unit not in {"m", "mm"}:
        raise ValueError("mesh_length_unit must be m or mm")
    youngs_deck = youngs_pa * (1e-6 if length_unit == "mm" else 1.0)
    sets = _node_sets(inp)
    support = _node_ids(physics.get("support_nodes"), label="support_nodes")
    loaded = _node_ids(physics.get("load_nodes"), label="load_nodes")
    support_set = physics.get("support_set")
    load_set = physics.get("load_set")
    selection_mode = "explicit_nodes"
    if support is None and support_set is not None:
        support = sets.get(str(support_set).strip().upper())
        if not support:
            raise ValueError(f"support_set not found in mesh: {support_set}")
        selection_mode = "named_sets"
    if loaded is None and load_set is not None:
        loaded = sets.get(str(load_set).strip().upper())
        if not loaded:
            raise ValueError(f"load_set not found in mesh: {load_set}")
        selection_mode = "named_sets"
    if support is None or loaded is None:
        zmin, zmax = min(n[3] for n in nodes), max(n[3] for n in nodes)
        tol = _finite_float(
            physics.get("face_tolerance") or max((zmax - zmin) * 1e-6, 1e-9),
            label="face_tolerance",
        )
        if tol <= 0:
            raise ValueError("face_tolerance must be positive")
        if support is None:
            support = [n[0] for n in nodes if abs(n[3] - zmin) <= tol]
        if loaded is None:
            loaded = [n[0] for n in nodes if abs(n[3] - zmax) <= tol]
        selection_mode = "explicit_nodes_plus_extrema_fallback"
    assert support is not None and loaded is not None
    if not set(support) <= available or not set(loaded) <= available:
        raise ValueError("support/load node selection contains ids absent from mesh")
    if not support or not loaded or set(support) == set(loaded):
        raise ValueError("cannot identify distinct support and load faces from mesh extrema")
    support_dofs = _dofs(physics.get("support_dofs"), label="support_dofs", default=[1, 2, 3])
    vector = physics.get("load_vector_n")
    if vector is None:
        load = _finite_float(physics["load_n"], label="load_n")
        direction = physics.get("load_direction")
        if direction is None:
            direction = [0.0, 0.0, 1.0]
        direction = [_finite_float(v, label="load_direction") for v in direction]
        if len(direction) != 3:
            raise ValueError("load_direction must contain three values")
        norm = math.sqrt(sum(v * v for v in direction))
        if norm <= 0:
            raise ValueError("load_direction cannot be zero")
        vector = [load * v / norm for v in direction]
    if not isinstance(vector, (list, tuple)) or len(vector) != 3:
        raise ValueError("load_vector_n must contain three values")
    vector = [_finite_float(v, label="load_vector_n") for v in vector]
    total_load = math.sqrt(sum(v * v for v in vector))
    if total_load <= 0:
        raise ValueError("load_vector_n cannot be zero")
    per_node = [v / len(loaded) for v in vector]
    cards = [
        "** --- AI Engineer Plus explicit generic physics ---",
        "*MATERIAL, NAME=AI_PLUS_MATERIAL", "*ELASTIC",
        f"{youngs_deck}, {poisson}",
        "*ELSET, ELSET=AI_PLUS_SOLIDS",
        *[", ".join(map(str, element_ids[i:i + 16])) for i in range(0, len(element_ids), 16)],
        "*SOLID SECTION, ELSET=AI_PLUS_SOLIDS, MATERIAL=AI_PLUS_MATERIAL",
        "*NSET, NSET=AI_PLUS_SUPPORT",
        ", ".join(map(str, support)),
        "*NSET, NSET=AI_PLUS_LOAD",
        ", ".join(map(str, loaded)),
        "*STEP", "*STATIC", "1., 1., 1e-06, 1.",
        "*BOUNDARY",
        *[f"AI_PLUS_SUPPORT, {dof}, {dof}" for dof in support_dofs],
        "*CLOAD",
        *[f"AI_PLUS_LOAD, {dof}, {value}" for dof, value in zip((1, 2, 3), per_node) if value],
        "*NODE FILE", "U",
        "*EL FILE", "S, E",
        "*END STEP",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text.rstrip() + "\n" + "\n".join(cards) + "\n", encoding="utf-8")
    evidence = {"source_inp": str(inp), "output_inp": str(out), "support_nodes": support,
                "load_nodes": loaded, "support_dofs": support_dofs,
                "load_vector_n": vector, "per_node_load_vector_n": per_node,
                "total_load_n": total_load, "selection_mode": selection_mode,
                "assumption": (
                    "explicit node selection/set when supplied; otherwise support=min-z "
                    "and load=max-z, with the requested load vector distributed over load nodes"
                ),
                "physics": {k: physics[k] for k in required},
                "material_assignment": {"material": "AI_PLUS_MATERIAL", "elset": "AI_PLUS_SOLIDS",
                    "element_count": len(element_ids), "mesh_length_unit": length_unit,
                    "force_unit": "N", "youngs_modulus_deck": youngs_deck}}
    (out.with_suffix(out.suffix + ".physics.json")).write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence
