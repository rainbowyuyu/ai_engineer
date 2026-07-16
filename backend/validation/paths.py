"""Validation output paths aligned with WORKSPACE_ROOT /runs static mount."""
from __future__ import annotations

import os
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

FIGURE_STEMS = (
    "fig_benchmark_position",
    "fig_benchmark_capacity",
    "fig_benchmark_unit_cost",
    "fig_benchmark_construction",
    "fig_benchmark_fatigue",
    "fig_score_radar",
    "fig_fleet_metrics_bars",
    "fig_rule_heatmap",
    "fig_capacity_intensity",
    "fig_ai_review_validity",
    "fig_surrogate_pinn",
)

ALLOWED_ARTIFACTS = frozenset(
    {
        "validation_report.md",
        "validation_report.docx",
        "validation_report_detailed.docx",
        "validation_score.json",
        "input_geometry_snapshot.json",
    }
    | {f"{s}.png" for s in FIGURE_STEMS}
    | {f"{s}.pdf" for s in FIGURE_STEMS}
)


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", str(_REPO_ROOT))).resolve()


def validation_runs_root() -> Path:
    root = workspace_root() / "runs" / "_validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def find_validation_dir(validation_id: str) -> Path | None:
    root = validation_runs_root()
    direct = root / validation_id
    if direct.is_dir() and (direct / "validation_score.json").is_file():
        return direct.resolve()
    if root.is_dir():
        for d in root.iterdir():
            if not d.is_dir():
                continue
            score = d / "validation_score.json"
            if not score.is_file():
                continue
            try:
                import json

                data = json.loads(score.read_text(encoding="utf-8"))
                if data.get("validation_id") == validation_id:
                    return d.resolve()
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    return None


def artifact_urls(validation_id: str, out_dir: Path) -> dict[str, object]:
    """Public URLs for artifacts (API file route — works with /ui/ and static /runs)."""
    out_dir = out_dir.resolve()
    api_base = f"/api/validation/{validation_id}/files"
    urls: dict[str, object] = {
        "report_md": f"{api_base}/validation_report.md",
        "score_json": f"{api_base}/validation_score.json",
        "export_word": f"/api/validation/{validation_id}/export/word",
        "export_word_detailed": f"/api/validation/{validation_id}/export/word/detailed",
    }
    if (out_dir / "validation_report.docx").is_file():
        urls["report_docx"] = f"{api_base}/validation_report.docx"
    if (out_dir / "validation_report_detailed.docx").is_file():
        urls["report_docx_detailed"] = f"{api_base}/validation_report_detailed.docx"
    figures: dict[str, list[str]] = {}
    for stem in FIGURE_STEMS:
        paths: list[str] = []
        for ext in (".png", ".pdf"):
            name = f"{stem}{ext}"
            if (out_dir / name).is_file():
                paths.append(f"{api_base}/{name}")
        if paths:
            figures[stem] = paths
    urls["figures"] = figures

    # Legacy static mount paths (same origin /runs when WORKSPACE_ROOT matches)
    try:
        runs_root = workspace_root() / "runs"
        rel = out_dir.resolve().relative_to(runs_root)
        urls["static_base"] = f"/runs/{rel.as_posix()}"
    except ValueError:
        pass

    return urls


def safe_artifact_name(filename: str) -> str | None:
    name = str(filename or "").strip().replace("\\", "/").split("/")[-1]
    if not name or ".." in name:
        return None
    if name in ALLOWED_ARTIFACTS:
        return name
    if re.fullmatch(r"fig_[a-z0-9_]+\.(png|pdf)", name):
        return name
    return None
