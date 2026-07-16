#!/usr/bin/env python3
"""Generate surrogate training manifest via DOE perturbations + analytical/steel labels."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np

from backend.surrogate.dataset import write_manifest
from backend.surrogate.features import extract_feature_dict
from backend.surrogate.targets import DatasetRow
from backend.tools.mixed_platform_steel import compute_steel_report, scale_geometry_horizontal

DEFAULT_GEOM = REPO / "rules" / "optimized_geometry.json"
DEFAULT_OUT = REPO / "runs" / "_surrogate_dataset"


def _perturb_geometry(base: dict, rng: np.random.Generator) -> dict:
    sf = float(rng.uniform(0.88, 1.12))
    wt = float(rng.uniform(0.04, 0.09))
    g = scale_geometry_horizontal(base, sf)
    opt = g.setdefault("optimization_info", {})
    opt["wall_thickness_m"] = wt
    opt["scale_factor"] = sf
    return g


def _labels_for_geometry(geometry: dict) -> dict[str, float]:
    report = compute_steel_report(geometry, optimize=False, scale_factor=geometry.get("optimization_info", {}).get("scale_factor"))
    perf = (report.get("result") or {}).get("performance") or report.get("steel_summary") or {}
    steel_t = float(perf.get("struct_mass_t") or perf.get("steel_mass_t") or 0.0)
    pitch = float(perf.get("pitch_angle_deg") or 3.5)
    intensity = float(perf.get("steel_intensity_t_per_MW") or steel_t / 20.0)
    uc = min(0.99, max(0.5, 0.65 + pitch / 20.0))
    compliance = intensity * 0.01
    return {
        "max_uc_static": uc,
        "compliance_static": compliance,
        "steel_mass_t": steel_t,
        "pitch_proxy_deg": pitch,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate surrogate dataset manifest")
    ap.add_argument("--geometry", type=Path, default=DEFAULT_GEOM)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("-n", "--num-samples", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    base = json.loads(args.geometry.read_text(encoding="utf-8"))
    rng = np.random.default_rng(args.seed)
    rows: list[DatasetRow] = []

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(args.num_samples):
        geom = _perturb_geometry(base, rng)
        sid = uuid.uuid4().hex[:10]
        geom_path = args.out_dir / f"{sid}_geometry.json"
        geom_path.write_text(json.dumps(geom, ensure_ascii=False, indent=2), encoding="utf-8")
        feats = extract_feature_dict(geom)
        labels = _labels_for_geometry(geom)
        rows.append(
            DatasetRow(
                sample_id=sid,
                features=feats,
                labels=labels,
                geometry_path=str(geom_path.relative_to(REPO)),
                source="doe_analytical",
            )
        )

    manifest = args.out_dir / "manifest.jsonl"
    write_manifest(rows, manifest)
    print(f"Wrote {len(rows)} samples -> {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
