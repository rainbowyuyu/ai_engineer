"""Runtime dependency preflight; reports readiness without starting a job."""
from __future__ import annotations
import os
import shutil
from pathlib import Path
from backend.qwen_runtime_config import get_qwen_config
from backend.pipeline.execution_mode import probe_solvers

def runtime_preflight() -> dict:
    names = {"calculix": ("ccx", "calculix"), "gmsh": ("gmsh",),
             "freecad": ("FreeCADCmd", "FreeCAD")}
    env_names = {"calculix": "CALCULIX_CMD", "gmsh": "GMSH_CMD", "freecad": "FREECAD_CMD"}
    found = {}
    sources = {}
    for kind, candidates in names.items():
        configured = (os.environ.get(env_names[kind]) or "").strip()
        if configured and Path(configured).is_file():
            found[kind] = str(Path(configured).resolve())
            sources[kind] = env_names[kind]
        else:
            found[kind] = next((shutil.which(x) for x in candidates if shutil.which(x)), None)
            sources[kind] = "PATH" if found[kind] else None
    # Reuse the Live solver probe, which also knows the supported Windows
    # installation locations used by the actual execution path.
    live_probe = probe_solvers().to_dict()
    if not found["calculix"] and live_probe.get("ccx_ok"):
        found["calculix"] = live_probe.get("ccx_path")
        sources["calculix"] = "execution_mode probe"
    if not found["freecad"] and live_probe.get("freecad_ok"):
        found["freecad"] = live_probe.get("freecad_cmd")
        sources["freecad"] = "execution_mode probe"
    if not found["gmsh"] and live_probe.get("gmsh_ok"):
        found["gmsh"] = "python module"
        sources["gmsh"] = "execution_mode probe"
    runtime_key = get_qwen_config().api_key
    api_key = bool((runtime_key or os.environ.get("QWEN_API_KEY")
                    or os.environ.get("LLM_API_KEY") or "").strip())
    physics_ready = all(found.values())
    return {"ready_for_physics": physics_ready, "ready_for_ai_review": api_key,
            "ready_for_live": physics_ready and api_key, "executables": found,
            "qwen_configured": api_key, "executable_sources": sources,
            "missing": [k for k, v in found.items() if not v] + ([] if api_key else ["QWEN_API_KEY"])}


probe_readiness = runtime_preflight

__all__ = ["runtime_preflight", "probe_readiness"]
