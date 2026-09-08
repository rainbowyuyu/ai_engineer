"""Live vs Preview execution mode for conversation-driven pipeline."""
from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

ExecutionMode = Literal["live", "preview"]


@dataclass(frozen=True)
class SolverProbe:
    freecad_cmd: str | None
    freecad_ok: bool
    ccx_path: str | None
    ccx_ok: bool
    gmsh_ok: bool
    mode_recommended: ExecutionMode

    def to_dict(self) -> dict:
        return asdict(self)


def _which_ok(path: str | None) -> bool:
    if not path:
        return False
    p = Path(path)
    if p.is_file():
        return True
    return shutil.which(path) is not None


@lru_cache(maxsize=1)
def probe_solvers() -> SolverProbe:
    freecad = (os.environ.get("FREECAD_CMD") or "").strip() or None
    if not freecad:
        # common Windows defaults used elsewhere in repo
        for cand in (
            r"D:\freecad\bin\FreeCADCmd.exe",
            "FreeCADCmd",
            "freecadcmd",
        ):
            if _which_ok(cand):
                freecad = cand
                break
    ccx = (os.environ.get("CCX_PATH") or "").strip() or None
    if not ccx:
        for cand in (r"D:\freecad\bin\ccx.exe", "ccx"):
            if _which_ok(cand):
                ccx = cand
                break
    gmsh_ok = False
    try:
        import gmsh  # noqa: F401

        gmsh_ok = True
    except Exception:
        gmsh_ok = False
    freecad_ok = _which_ok(freecad)
    ccx_ok = _which_ok(ccx)
    live = freecad_ok and ccx_ok and gmsh_ok
    return SolverProbe(
        freecad_cmd=freecad,
        freecad_ok=freecad_ok,
        ccx_path=ccx,
        ccx_ok=ccx_ok,
        gmsh_ok=gmsh_ok,
        mode_recommended="live" if live else "preview",
    )


def clear_solver_probe_cache() -> None:
    probe_solvers.cache_clear()


def resolve_execution_mode(requested: str | None = None) -> tuple[ExecutionMode, SolverProbe]:
    """Return effective mode. ``live`` refused when solvers missing → falls back to preview."""
    probe = probe_solvers()
    raw = (requested or os.environ.get("BESO_EXECUTION_MODE") or "").strip().lower()
    if raw in ("live", "preview"):
        if raw == "live" and probe.mode_recommended != "live":
            return "preview", probe
        return raw, probe  # type: ignore[return-value]
    return probe.mode_recommended, probe


def assert_live_or_raise(mode: ExecutionMode) -> None:
    if mode != "live":
        probe = probe_solvers()
        raise RuntimeError(
            "Execution mode is Preview (canned / incomplete solvers). "
            f"freecad_ok={probe.freecad_ok}, ccx_ok={probe.ccx_ok}, gmsh_ok={probe.gmsh_ok}. "
            "Install FreeCADCmd + CalculiX + gmsh, set FREECAD_CMD/CCX_PATH, then set_execution_mode(live)."
        )
