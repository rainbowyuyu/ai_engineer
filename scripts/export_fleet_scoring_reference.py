#!/usr/bin/env python3
"""导出机队 AI Review 五维参考表（JSON + Markdown）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
REF = REPO / "rules" / "fleet_ai_review_reference.yaml"
OUT_JSON = REPO / "rules" / "fleet_ai_review_reference.json"


def main() -> int:
    if not REF.is_file():
        print(f"Missing {REF}", file=sys.stderr)
        return 1
    data = yaml.safe_load(REF.read_text(encoding="utf-8"))
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    cols = ["项目", "状态", "MW", "t/MW", "万元/MW", "施工年", "疲劳年", "钢耗可信度"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for p in data.get("projects") or []:
        m = p.get("metrics") or {}
        c = p.get("confidence") or {}
        lines.append(
            "| {name} | {st} | {mw} | {si} | {cost} | {cy} | {fl} | {conf} |".format(
                name=p.get("short_name", ""),
                st=p.get("status", ""),
                mw=m.get("capacity_mw", "—"),
                si=m.get("steel_t_per_MW", "—"),
                cost=m.get("unit_cost_cny_per_MW", "—"),
                cy=m.get("construction_years", "—"),
                fl=m.get("fatigue_life_years", "—"),
                conf=c.get("steel_t_per_MW", "—"),
            )
        )

    print(f"Wrote {OUT_JSON}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
