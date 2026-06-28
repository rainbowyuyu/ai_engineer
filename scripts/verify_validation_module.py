#!/usr/bin/env python3
"""Smoke test: run validation on rules/optimized_geometry.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.validation.pipeline import run_validation

SAMPLE = REPO / "rules" / "optimized_geometry.json"
OUT = REPO / "runs" / "_validation" / "_smoke_latest"


def main() -> int:
    geometry = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if OUT.exists():
        import shutil
        shutil.rmtree(OUT, ignore_errors=True)
    result = run_validation(
        geometry,
        out_dir=OUT,
        use_llm_rationale=False,
        candidate_label="BESO7",
    )
    print(f"OK validation_id={result['validation_id']}")
    print(f"   score={result['overall_score']} grade={result['grade']}")
    print(f"   report={result['report_md']}")
    for stem, paths in (result.get("figures") or {}).items():
        print(f"   figure {stem}: {paths[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
