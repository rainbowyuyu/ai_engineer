"""Unit tests: BESO9-style fixed arcs + top load ring node selection."""

from __future__ import annotations

import math

import numpy as np

from backend.tools.inp_oc4_design_nondesign import (
    _build_cload_entries,
    select_beso9_fixed_nodes,
    select_beso9_ring_load_nodes,
)
from backend.tools.oc4_force_direction import load_case_from_force_direction


def _synthetic_beso9_nodes(
    *,
    side: float = 95000.0,
    corner_r: float = 7500.0,
    load_r: float = 6000.0,
    zmin: float = -21000.0,
    zmax: float = 17000.0,
) -> tuple[dict[int, np.ndarray], dict]:
    h = (side * math.sqrt(3)) / 2.0
    centers = [
        (0.0, (2.0 * h) / 3.0),
        (side / 2.0, -h / 3.0),
        (-side / 2.0, -h / 3.0),
    ]
    cx = sum(c[0] for c in centers) / 3.0
    cy = sum(c[1] for c in centers) / 3.0
    centers = [(c[0] - cx, c[1] - cy) for c in centers]

    nodes: dict[int, np.ndarray] = {}
    nid = 1
    for cx0, cy0 in centers:
        for a in np.linspace(0, 2 * math.pi, 24, endpoint=False):
            nodes[nid] = np.array(
                [cx0 + corner_r * math.cos(a), cy0 + corner_r * math.sin(a), zmin],
                dtype=float,
            )
            nid += 1
    for a in np.linspace(0, 2 * math.pi, 36, endpoint=False):
        nodes[nid] = np.array([load_r * math.cos(a), load_r * math.sin(a), zmax], dtype=float)
        nid += 1
    for x in np.linspace(-side / 3, side / 3, 8):
        for y in np.linspace(-side / 3, side / 3, 8):
            nodes[nid] = np.array([x, y, zmin], dtype=float)
            nid += 1
    nodes[nid] = np.array([centers[0][0], centers[0][1], zmax], dtype=float)

    lc = {
        "corner_centers_xy_mm": [[c[0], c[1]] for c in centers],
        "domain_center_xy_mm": [0.0, 0.0],
        "corner_r_mm": corner_r,
        "load_radius_mm": load_r,
        "cload_mode": "beso9_ring",
        "cload_dof": 3,
        "cload_mag": -2.45e7,
    }
    return nodes, lc


def test_beso9_fixed_are_corner_arcs_not_full_slab():
    nodes, lc = _synthetic_beso9_nodes()
    fixed = select_beso9_fixed_nodes(nodes, lc)
    assert len(fixed) >= 36
    assert len(fixed) < 100
    zs = [float(nodes[i][2]) for i in fixed]
    assert max(zs) <= min(zs) + 1.0


def test_beso9_load_is_top_ring_not_corner_tip():
    nodes, lc = _synthetic_beso9_nodes()
    ring = select_beso9_ring_load_nodes(nodes, lc)
    assert len(ring) >= 20
    rs = [math.hypot(float(nodes[i][0]), float(nodes[i][1])) for i in ring]
    assert abs(sum(rs) / len(rs) - 6000.0) < 200.0
    tip = max(nodes.keys())
    assert tip not in ring or len(ring) > 1

    entries, mode = _build_cload_entries(
        nodes, load_node_max_z=tip, cload_mag=-2.45e7, load_case=lc
    )
    assert mode == "beso9_ring"
    assert len(entries) == len(ring)
    assert abs(sum(m for _, _, m in entries) + 2.45e7) < 1.0


def test_force_direction_uses_beso9_ring_mode():
    lc = load_case_from_force_direction("-Z")
    assert lc["cload_mode"] == "beso9_ring"
    assert lc["fix_mode"] == "beso9_arcs"
