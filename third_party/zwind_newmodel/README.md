# Zwind / OpenSees FOWT model (paper Fig. 2b–e) — full in-repo bundle

This directory is the **complete Zwind aero–hydro–servo–elastic** evaluation stack
used for the 20 MW flagship design in
*Closed-loop AI achieves certifiable engineering design*.

Paper mapping:

- Phase II: PSO size optimization coupled to Zwind under operational / extreme cases
- **Fig. 2b–e**: AI vs TuQiang dynamics, DLC1.1, DLC 6.1, ultimate loads

## Layout (~550 MB)

| Path | Role |
|------|------|
| `Aero_Driver_x64.dll` / `Hydro_Driver_x64.dll` / `Servo_Driver_x64.dll` | Coupled drivers |
| `opensees.pyd` + Intel / TCL runtime DLLs | OpenSees Python extension + deps |
| `user_force64.dll` | Custom force interface |
| `test0820_hardcode.py` | Time-domain campaign driver (AI geometry) |
| `testpitch.py` | Pitch / decay helper |
| `optimized_geometry30.json` | AI platform geometry (30° outer columns) |
| `Aerodyn/` `hydrodynNbody/` `servoData*/` | Input decks + DISCON / ServoDyn |
| `OPSout/` | Time-history and max-abs outputs (incl. `test0820_hardcode/`) |
| `ops_*.out` | Additional load / balance dumps at bundle root |
| `paper_fig2_metrics.json` | Canonical Fig. 2b–e numbers |
| `draw.py` / `draw_fig2_panels.py` | Nature-style panel plotting |
| `fig_*_*.png` / `figures/` | Reference and unified Fig. 2 panels |

## Run the coupled campaign (Windows)

```powershell
cd third_party\zwind_newmodel
# PATH / DLL directories are set inside test0820_hardcode.py
..\..\..\.venv\Scripts\python.exe test0820_hardcode.py
```

Outputs land in `OPSout/test0820_hardcode/`.

## Regenerate Fig. 2b–e only (no solvers)

From the repo root:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python third_party\zwind_newmodel\draw_fig2_panels.py `
  --out submission\figures\fig2_panels
.\.venv\Scripts\python scripts\export_nature_submission_figures.py
```

## Bridge into beso_ai

- `backend/surrogate/zwind_adapter.py` → loads `paper_fig2_metrics.json`
- `rules/ai_vs_tuqiang_comparison.yaml` → economic + structural panels aligned to this bundle
- Orchestrator replan target `zwind` → points here for subprocess / envelope import

## Notes

- Bundle size is large (~550 MB). Prefer shallow clones or Git LFS if the remote enforces quotas.
- Drivers are Windows x64. Cold re-runs need a matching Python that can load `opensees.pyd`.
- License of Aero/Hydro/Servo drivers and Zwind remain with their original owners; this tree is for paper companion reproducibility inside the project.
