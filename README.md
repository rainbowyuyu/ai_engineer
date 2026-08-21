# The AI Engineer

Companion code for the manuscript **"Closed-loop AI achieves certifiable engineering design"**.

This repository implements **The AI Engineer**: an agentic orchestration stack that couples large language models with deterministic engineering backends (geometry, mesh, topology optimization, size optimization, and multi-physics verification) in a verification-closed loop. Exploration terminates only when an internal **Automated Reviewer** judges a candidate certification-ready; formal Approval in Principle (AIP) is used as an external calibration, not as the per-run objective.

> Preprint / manuscript companion. High-fidelity run bundles and datasets will be deposited with a DOI upon publication; anonymized artifacts are available from the corresponding author on reasonable request.

## What this system does

| Phase | Role |
|------|------|
| **I — Requirements** | Parse natural-language owner intent, site constraints, and classification provisions into a structured job descriptor |
| **II — Closed-loop design** | FreeCAD geometry → mesh → CalculiX–BESO topology optimization → parametric upscaling → PSO size optimization → Zwind aero-hydro-servo-elastic evaluation, with autonomous replan on geometric, numerical, or limit-state failures |
| **III — Deliverables** | Engineering drawings and structured design reports |
| **IV — Internal gate** | Automated Reviewer scores capacity, steel intensity, unit cost, constructability, and fatigue life; halt when composite score **S ≥ 85** (grade A) and no sub-score below 60 |

Reference fleet scoring and regulatory-alignment checks (Spearman rank correlation against classification-society benchmarks) support the claim that the internal gate is a calibrated surrogate for professional review, not an arbitrary heuristic.

## Repository layout

```
backend/           FastAPI app, job manager, WebSocket events, orchestrator gates,
                   Automated Reviewer / validation, OC4 design-domain services, tools
frontend_static/   Browser UI for the design workflow (/ui/)
beso/              BESO core scripts used by the CalculiX loop
graph/             Workflow / dependency graph assets
scripts/           Reproducibility and documentation helpers
tests/             Unit and API tests
third_party/       Bundled CAD utilities (text-to-cad)
deploy/            Optional deployment notes
```

Local run outputs (`runs/`), scratch extracts (`tmp_*`, `_tmp_*`), IDE folders, and secrets (`.env`) are **not** part of the published tree.

## Requirements

- **OS**: Windows is the primary development environment; Linux/macOS may work for API-only paths
- **Python**: 3.10+ (3.11/3.12 recommended) in a virtual environment
- **CalculiX** (`ccx`): set `CCX_PATH`
- **FreeCADCmd** (CAD → INP, mesh preview): set `FREECAD_CMD`
- **Optional**: Node.js (CAD Explorer catalog); LLM API key for the assistant / orchestrator language layer; Zwind for full FOWT time-domain campaigns described in the paper

Pinned Python packages: see `backend/requirements.txt`.

## Quick start

```powershell
python -m venv .\.venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -r .\backend\requirements.txt

$env:PYTHONPATH = (Get-Location).Path
# Optional: $env:QWEN_API_KEY = "..."
.\.venv\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

- UI: `http://127.0.0.1:8000/ui/`
- Health: `GET /health`
- OpenAPI: `/docs`

Copy `.env.example` to `.env` for local overrides. **Never commit API keys.**

### Common environment variables

| Variable | Purpose |
|----------|---------|
| `WORKSPACE_ROOT` | Sandbox root for uploads and scan directories |
| `CCX_PATH` | CalculiX executable |
| `FREECAD_CMD` | FreeCADCmd executable |
| `QWEN_API_KEY` / `QWEN_BASE_URL` / `QWEN_MODEL` | Optional LLM backend (OpenAI-compatible) |
| `MAX_UPLOAD_BYTES` | Upload size cap (default 256 MB) |

## Reproducibility notes (aligned with the manuscript)

- Solver backends (CalculiX, Zwind) are deterministic given identical inputs; orchestration decisions from the language model may vary with sampling. For regulatory-style reproduction, freeze tool schemas, pin dependency versions, and use multi-seed campaigns as described in the Methods / Statistics sections of the paper.
- Artifacts in a complete run bundle are intended to be versioned under content hashes (SHA-256 manifests) so that clarification threads can be traced to the emitting computational step.
- Third-party solvers retain their own licenses: CalculiX, FreeCAD, Gmsh, Zwind, etc.

## Citation

If you use this software, please cite the manuscript:

> Yu, T. et al. Closed-loop AI achieves certifiable engineering design. *(preprint / in preparation)*.

Corresponding author: Lilin Wang — `lilin.wang@zju.edu.cn`

## License and patents

Source in this repository is released for research reproducibility under the terms stated in the repository license file (if present) and third-party notices. Authors are applying for national and international patents related to the system; commercial use may require a separate agreement.

## Security

- Do not commit secrets (`.env`, API keys, certificates).
- Rotate any key that may have been exposed in chat logs or screenshots.

## 中文摘要

本仓库为论文《Closed-loop AI achieves certifiable engineering design》的伴生代码：**The AI Engineer** 将大语言模型与确定性工程后端（几何/网格、BESO–CalculiX、尺寸优化、Zwind 等）组成闭环；以 **Automated Reviewer**（S ≥ 85）作为内部终止门，以船级社 AIP 作为外部校准证据。本地运行产物、临时抽取文件与编辑器目录已从公开树中排除，请勿提交密钥。
