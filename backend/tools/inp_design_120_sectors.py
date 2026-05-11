"""
将带 design_space / nondesign_space 的 CalculiX 体网格 INP 拆为 design_s0..2（绕 +Z 轴 120° 三等分）
并写出 slave->master 映射 JSON，供 beso_main 每步同步单元状态。

用法（仓库根）：
  python -m backend.tools.inp_design_120_sectors --inp examples/beso3/Analysis-beso.inp \\
      --out examples/beso3/Analysis-beso_sectors.inp --map-out examples/beso3/symmetry_120_map.json

最近邻映射使用纯 numpy 分块距离，避免依赖 scipy。
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Iterator

import numpy as np


def _parse_nodes(lines: list[str]) -> dict[int, tuple[float, float, float]]:
    nodes: dict[int, tuple[float, float, float]] = {}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if line.upper().startswith("*NODE"):
            i += 1
            while i < n and not lines[i].strip().startswith("*"):
                parts = lines[i].split(",")
                if len(parts) >= 4:
                    nid = int(parts[0].strip())
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    nodes[nid] = (x, y, z)
                i += 1
            continue
        i += 1
    return nodes


def _iter_c3d4_block(lines: list[str], elset: str) -> Iterator[tuple[int, tuple[int, int, int, int]]]:
    """Yield (eid, (n1,n2,n3,n4)) for *Element, TYPE=C3D4, Elset=elset block."""
    target = elset.strip()
    i = 0
    n = len(lines)
    pat = re.compile(r"^\*Element\s*,", re.I)
    while i < n:
        u = lines[i].strip()
        if pat.match(u) and "C3D4" in u.upper() and f"ELSET={target.upper()}" in u.upper().replace(" ", ""):
            i += 1
            while i < n and not lines[i].strip().startswith("*"):
                parts = [p.strip() for p in lines[i].split(",")]
                if len(parts) >= 5 and parts[0].isdigit():
                    eid = int(parts[0])
                    a, b, c, d = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                    yield eid, (a, b, c, d)
                i += 1
            return
        i += 1


def _collect_c3d4_block(lines: list[str], elset: str) -> dict[int, tuple[int, int, int, int]]:
    return {eid: nn for eid, nn in _iter_c3d4_block(lines, elset)}


def _element_centroids(
    elems: dict[int, tuple[int, int, int, int]],
    nodes: dict[int, tuple[float, float, float]],
) -> tuple[np.ndarray, np.ndarray]:
    """Return (eids_sorted N,), (N,3) centroids."""
    eids = sorted(elems.keys())
    cg = np.zeros((len(eids), 3), dtype=np.float64)
    for j, eid in enumerate(eids):
        a, b, c, d = elems[eid]
        for k, nid in enumerate((a, b, c, d)):
            p = nodes[nid]
            cg[j, :] += np.array(p, dtype=np.float64)
        cg[j, :] *= 0.25
    return np.array(eids, dtype=np.int64), cg


def _rotate_xy_about_pivot(xy: np.ndarray, pivot: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotate (N,2) points in plane about pivot; angle positive CCW when viewed from +Z."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    r = np.array([[c, -s], [s, c]], dtype=np.float64)
    q = xy - pivot[None, :]
    return (q @ r.T) + pivot[None, :]


def _nearest_master_batch(
    query_xy: np.ndarray,
    ref_xy: np.ndarray,
    ref_eids: np.ndarray,
    batch: int = 256,
) -> np.ndarray:
    """For each query row, index into ref_eids of nearest ref_xy (Euclidean in XY)."""
    out = np.empty(len(query_xy), dtype=np.int64)
    for i in range(0, len(query_xy), batch):
        q = query_xy[i : i + batch]
        diff = q[:, None, :] - ref_xy[None, :, :]
        d2 = np.einsum("ijk,ijk->ij", diff, diff)
        idx = np.argmin(d2, axis=1)
        out[i : i + batch] = ref_eids[idx]
    return out


def _sector_id(angle: float, theta0: float) -> int:
    twopi = 2.0 * math.pi
    a = (angle - theta0) % twopi
    return int(a // (twopi / 3.0))


def split_design_space_120(
    lines: list[str],
    nodes: dict[int, tuple[float, float, float]],
    design_elems: dict[int, tuple[int, int, int, int]],
    axis_xy: tuple[float, float],
    theta0_rad: float,
) -> tuple[dict[int, int], dict[int, list[int]], dict[int, list[int]]]:
    """
    Returns:
      eid -> sector 0/1/2
      sector -> list of eids
    """
    x0, y0 = axis_xy
    by_sec: dict[int, list[int]] = {0: [], 1: [], 2: []}
    eid_sec: dict[int, int] = {}
    for eid, nn in design_elems.items():
        cx = cy = cz = 0.0
        for nid in nn:
            p = nodes[nid]
            cx += p[0]
            cy += p[1]
            cz += p[2]
        cx *= 0.25
        cy *= 0.25
        ang = math.atan2(cy - y0, cx - x0)
        sid = _sector_id(ang, theta0_rad)
        eid_sec[eid] = sid
        by_sec[sid].append(eid)
    return eid_sec, by_sec


def build_symmetry_map(
    nodes: dict[int, tuple[float, float, float]],
    elems_s0: dict[int, tuple[int, int, int, int]],
    elems_s1: dict[int, tuple[int, int, int, int]],
    elems_s2: dict[int, tuple[int, int, int, int]],
    axis_xy: np.ndarray,
) -> list[list[int]]:
    """Pairs [slave_eid, master_eid] for all elements in sectors 1 and 2."""
    e0, c0 = _element_centroids(elems_s0, nodes)
    xy0 = c0[:, :2]
    pivot = axis_xy.astype(np.float64)

    pairs: list[list[int]] = []

    e1, c1 = _element_centroids(elems_s1, nodes)
    xy1_rot = _rotate_xy_about_pivot(c1[:, :2], pivot, math.radians(-120.0))
    m1 = _nearest_master_batch(xy1_rot, xy0, e0)
    for j, eid in enumerate(e1):
        pairs.append([int(eid), int(m1[j])])

    e2, c2 = _element_centroids(elems_s2, nodes)
    xy2_rot = _rotate_xy_about_pivot(c2[:, :2], pivot, math.radians(-240.0))
    m2 = _nearest_master_batch(xy2_rot, xy0, e0)
    for j, eid in enumerate(e2):
        pairs.append([int(eid), int(m2[j])])

    return pairs


def rewrite_inp_sectors(
    lines: list[str],
    design_by_sector: dict[int, list[int]],
    design_elems: dict[int, tuple[int, int, int, int]],
    nondesign_elems: dict[int, tuple[int, int, int, int]],
) -> str:
    """Rebuild full INP text: same nodes, replace design+nondesign element blocks and solid sections."""
    # Locate slice indices
    text = "\n".join(lines)
    lines = text.splitlines()

    def find_elset_line(name: str) -> int:
        pat = re.compile(rf"^\*Element\s*,.*Elset\s*=\s*{re.escape(name)}\s*$", re.I)
        for idx, line in enumerate(lines):
            if pat.match(line.strip()):
                return idx
        raise ValueError(f"找不到 *Element ... Elset={name}")

    i_ds = find_elset_line("design_space")
    i_nd = find_elset_line("nondesign_space")
    # end of nondesign block: first * after i_nd+1 that starts an INP keyword
    j = i_nd + 1
    while j < len(lines):
        s = lines[j].strip()
        if s.startswith("*") and not s.startswith("**"):
            break
        j += 1
    i_tail = j

    head = lines[:i_ds]
    tail = lines[i_tail:]

    def fmt_block(elset: str, eids: list[int]) -> list[str]:
        out = [f"*Element, TYPE=C3D4, Elset={elset}"]
        for eid in sorted(eids):
            a, b, c, d = design_elems[eid]
            out.append(f"{eid}, {a}, {b}, {c}, {d}")
        return out

    def fmt_nondesign() -> list[str]:
        out = ["*Element, TYPE=C3D4, Elset=nondesign_space"]
        for eid in sorted(nondesign_elems.keys()):
            a, b, c, d = nondesign_elems[eid]
            out.append(f"{eid}, {a}, {b}, {c}, {d}")
        return out

    mid: list[str] = []
    for s in (0, 1, 2):
        mid.extend(fmt_block(f"design_s{s}", design_by_sector[s]))
    mid.extend(fmt_nondesign())

    # Fix *Solid section lines in tail: replace two lines with four
    new_tail: list[str] = []
    replaced_ds = 0
    replaced_nd = 0
    pat_ds = re.compile(r"(?i)Elset\s*=\s*design_space\b")
    pat_nd = re.compile(r"(?i)Elset\s*=\s*nondesign_space\b")
    for line in tail:
        ls = line.strip()
        if ls.startswith("*Solid section") and pat_ds.search(ls):
            new_tail.append("*Solid section, Elset=design_s0, Material=Material-1")
            new_tail.append("*Solid section, Elset=design_s1, Material=Material-1")
            new_tail.append("*Solid section, Elset=design_s2, Material=Material-1")
            replaced_ds += 1
            continue
        if ls.startswith("*Solid section") and pat_nd.search(ls):
            new_tail.append("*Solid section, Elset=nondesign_space, Material=Material-1")
            replaced_nd += 1
            continue
        new_tail.append(line)
    if replaced_ds < 1 or replaced_nd < 1:
        raise ValueError(
            "未在 tail 中找到预期的 *Solid section（Elset=design_space 与 Elset=nondesign_space）"
        )

    all_lines = head + mid + new_tail
    return "\n".join(all_lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="design_space 120° 三等分 + 对称映射 JSON")
    ap.add_argument("--inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--map-out", type=Path, required=True)
    ap.add_argument("--axis-x0", type=float, default=None, help="柱轴在 XY 上参考点；默认取全部节点包围盒中心")
    ap.add_argument("--axis-y0", type=float, default=None)
    ap.add_argument("--theta0-deg", type=float, default=0.0, help="扇区 0 起始角（度），与 atan2 一致")
    args = ap.parse_args()

    raw = args.inp.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    nodes = _parse_nodes(lines)
    if not nodes:
        raise SystemExit("未解析到任何节点")

    design_elems = _collect_c3d4_block(lines, "design_space")
    nondesign_elems = _collect_c3d4_block(lines, "nondesign_space")
    if not design_elems or not nondesign_elems:
        raise SystemExit("需要同时存在 design_space 与 nondesign_space 的 C3D4 块")

    xs = [p[0] for p in nodes.values()]
    ys = [p[1] for p in nodes.values()]
    x_mid = 0.5 * (min(xs) + max(xs))
    y_mid = 0.5 * (min(ys) + max(ys))
    x0 = float(args.axis_x0) if args.axis_x0 is not None else x_mid
    y0 = float(args.axis_y0) if args.axis_y0 is not None else y_mid
    theta0 = math.radians(args.theta0_deg)

    eid_sec, by_sec = split_design_space_120(lines, nodes, design_elems, (x0, y0), theta0)
    elems_s0 = {e: design_elems[e] for e in by_sec[0]}
    elems_s1 = {e: design_elems[e] for e in by_sec[1]}
    elems_s2 = {e: design_elems[e] for e in by_sec[2]}
    if not elems_s0 or not elems_s1 or not elems_s2:
        raise SystemExit(
            f"某一扇区为空（s0={len(elems_s0)} s1={len(elems_s1)} s2={len(elems_s2)}）；请调整 --theta0-deg 或轴心"
        )

    axis_xy = np.array([x0, y0], dtype=np.float64)
    pairs = build_symmetry_map(nodes, elems_s0, elems_s1, elems_s2, axis_xy)

    out_text = rewrite_inp_sectors(lines, by_sec, design_elems, nondesign_elems)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out_text, encoding="utf-8")

    meta = {
        "axis_xy": [x0, y0],
        "theta0_deg": args.theta0_deg,
        "counts": {"design_s0": len(elems_s0), "design_s1": len(elems_s1), "design_s2": len(elems_s2)},
        "pairs": pairs,
    }
    args.map_out.parent.mkdir(parents=True, exist_ok=True)
    args.map_out.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[OK] wrote {args.out} and {args.map_out} ({len(pairs)} slave->master pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
