#!/usr/bin/env python3
"""Train physics-informed static surrogate from manifest."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.surrogate.config import load_surrogate_config, model_bundle_dir
from backend.surrogate.model import train_from_manifest

DEFAULT_MANIFEST = REPO / "runs" / "_surrogate_dataset" / "manifest.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description="Train surrogate MLP")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()

    if not args.manifest.is_file():
        print(f"Missing manifest: {args.manifest}", file=sys.stderr)
        return 1

    cfg = load_surrogate_config()
    out = args.out_dir or model_bundle_dir(cfg)
    bundle = train_from_manifest(args.manifest, out, cfg=cfg)
    print(f"Trained {bundle.backend} model -> {out}")
    print(f"  metrics: {bundle.metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
