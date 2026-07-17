#!/usr/bin/env python3
"""Smoke: run Table S.1 case1/2/3 demos and print audit paths."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.replan.simulate_cases import run_case_demo


def main() -> int:
    all_ok = True
    for cid in ("case1", "case2", "case3"):
        out = run_case_demo(cid)
        ok = bool(out.get("ok"))
        all_ok = all_ok and ok
        eid = (out.get("result") or {}).get("event", {}) or {}
        eid = eid.get("event_id") or "—"
        print(f"{'OK' if ok else 'FAIL'} {cid}: {out.get('title')}")
        print(f"   event_id={eid}")
        print(f"   outcome={out.get('outcome', {}).get('note', '')[:100]}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
