#!/usr/bin/env python3
"""Smoke test: NL → design checklist → persist → optional validation hook."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.design_requirements.geometry_bridge import apply_checklist_to_geometry
from backend.design_requirements.markdown import checklist_to_markdown
from backend.design_requirements.nl_parser import parse_design_checklist
from backend.design_requirements.paths import load_checklist, save_checklist
from backend.validation.geometry_metrics import extract_geometry_metrics

SAMPLE_NL = (
    "阳江三山场址 20MW 半潜式漂浮基础，Hs=12 m、Tp=14 s，"
    "钢耗目标 300 t/MW，CCS AIP，需校核稳性与水密。"
)
GEOMETRY = REPO / "rules" / "optimized_geometry.json"


def main() -> int:
    cl = parse_design_checklist(SAMPLE_NL)
    md = checklist_to_markdown(cl)
    out = save_checklist(cl, markdown=md)
    loaded = load_checklist(cl.meta.checklist_id)
    assert loaded is not None
    print(f"OK checklist_id={cl.meta.checklist_id}")
    print(f"   parser={cl.meta.parser} mw={cl.project.target_capacity_mw} Hs={cl.site.Hs_m}")
    print(f"   out={out}")
    print(f"   md_chars={len(md)}")

    geom = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    geom2 = apply_checklist_to_geometry(geom, cl)
    m = extract_geometry_metrics(geom2)
    assert any("Phase I" in a or "设计清单" in a for a in m.assumptions)
    print(f"   validation assumptions ok ({len(m.assumptions)} notes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
