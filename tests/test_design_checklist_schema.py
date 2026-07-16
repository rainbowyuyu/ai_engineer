"""Schema / merge / markdown tests for DesignChecklist."""
from __future__ import annotations

from backend.design_requirements.markdown import checklist_to_markdown
from backend.design_requirements.models import DesignChecklist, ProjectSpec
from backend.design_requirements.nl_parser import parse_design_checklist
from backend.design_requirements.rule_fallback import merge_partial_dict, parse_rule_fallback


def test_clamp_mw_and_hs():
    p = ProjectSpec(target_capacity_mw=100)
    assert p.target_capacity_mw == 50.0
    cl = DesignChecklist(site={"Hs_m": 99})
    assert cl.site.Hs_m == 20.0


def test_merge_partial_and_markdown():
    base = parse_rule_fallback("20 MW 平台")
    merged = merge_partial_dict(
        base,
        {
            "project": {"title": "测试项目"},
            "gaps": ["水深未明确"],
        },
    )
    assert merged.project.title == "测试项目"
    assert "水深未明确" in merged.gaps
    md = checklist_to_markdown(merged)
    assert "设计清单" in md
    assert "项目概况" in md
    assert len(md) > 100


def test_parse_design_checklist_rule_path(monkeypatch):
    class FakeQwen:
        api_key = ""

    monkeypatch.setattr("backend.design_requirements.nl_parser.QwenClient", lambda: FakeQwen())
    cl = parse_design_checklist("20MW，Hs=10，钢耗 280 t/MW")
    assert cl.meta.parser == "rule_fallback"
    assert cl.project.target_capacity_mw == 20.0
    assert cl.site.Hs_m == 10.0
    assert cl.performance_targets.steel_intensity_t_per_MW == 280.0
    assert cl.job_descriptor.theta.oc4_loads.band_scale > 0
