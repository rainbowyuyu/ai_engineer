#!/usr/bin/env python3
"""Smoke: generate dataset, train surrogate, run validation with use_surrogate."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.validation.pipeline import run_validation

DATASET = REPO / "runs" / "_surrogate_dataset"
SAMPLE = REPO / "rules" / "optimized_geometry.json"
OUT = REPO / "runs" / "_surrogate_smoke"


def main() -> int:
    subprocess.check_call(
        [sys.executable, str(REPO / "scripts" / "generate_surrogate_dataset.py"), "-n", "25"],
        cwd=str(REPO),
    )
    subprocess.check_call(
        [sys.executable, str(REPO / "scripts" / "train_surrogate.py")],
        cwd=str(REPO),
    )

    geometry = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)

    base = run_validation(geometry, out_dir=OUT / "no_surrogate", use_surrogate=False)
    sur = run_validation(geometry, out_dir=OUT / "with_surrogate", use_surrogate=True)

    print(f"baseline score={base['overall_score']:.2f}")
    print(f"surrogate score={sur['overall_score']:.2f}")
    print(f"surrogate_context={sur.get('surrogate_context')}")
    ctx = sur.get("surrogate_context") or {}
    if not ctx.get("enabled"):
        print("WARN: surrogate not enabled in smoke run (model may be missing)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
