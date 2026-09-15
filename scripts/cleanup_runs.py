#!/usr/bin/env python3
"""Preview or remove stale files under WORKSPACE_ROOT/runs.

Examples:
    python scripts/cleanup_runs.py
    python scripts/cleanup_runs.py --apply --days 14
    python scripts/cleanup_runs.py --apply --include-archives
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.runs_cleanup import RunsCleanupConfig, RunsCleaner, default_runs_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean stale generated data under runs/")
    parser.add_argument("--workspace-root", help="workspace root; defaults to WORKSPACE_ROOT or repo root")
    parser.add_argument("--days", type=float, help="retention period in days")
    parser.add_argument("--include-archives", action="store_true", help="also remove stale runs/_archive entries")
    parser.add_argument("--max-items", type=int, help="maximum deletion candidates per run")
    parser.add_argument("--apply", action="store_true", help="actually delete; default is preview only")
    args = parser.parse_args()

    if args.workspace_root:
        os.environ["WORKSPACE_ROOT"] = str(Path(args.workspace_root).expanduser().resolve())
    cfg = RunsCleanupConfig.from_env().with_overrides(
        retention_days=args.days,
        include_archives=True if args.include_archives else None,
        max_items=args.max_items,
    )
    report = RunsCleaner(default_runs_root()).cleanup(config=cfg, dry_run=not args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
