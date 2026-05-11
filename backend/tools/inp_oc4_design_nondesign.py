"""
将 OC4 设计域体网格 INP 划分为 example_3 风格：``design_space``（可优化）与
``nondesign_space``（柱走廊附近单元，不参与 BESO 密度更新）。

划分依据：与 ``oc4.igs`` 中识别的主柱轴线（中心柱 + 三根外柱）的径向距离，
小于 ``band_scale * R_shaft`` 的体单元归入 nondesign_space。

另：在网格末尾追加最小 *STEP（底面 z 固定 + 顶区单点竖向力），便于 CalculiX/BESO 冒烟；
真实系泊/风载需按新节点号自行替换（与旧 BESO2-FEMMeshGmsh.inp 不兼容）。
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from backend.tools.oc4_design_domain_iges import (
    CylinderAxis,
    _extract_revolution_cylinders,
    _merge_parallel_axis_pairs,
    _pick_oc4_key_columns,
)

_ELEM_HEAD = re.compile(
    r"^\*Element\s*,\s*TYPE\s*=\s*(\w+)\s*,\s*ELSET\s*=\s*(\S+)",
    re.IGNORECASE,
)
_ELEM_HEAD_NO_ELSET = re.compile(r"^\*Element\s*,\s*TYPE\s*=\s*(\w+)\s*$", re.IGNORECASE)

# FreeCAD / Gmsh / meshio / Abaqus 等：*Solid section / *SOLID SECTION / *SOLIDSECTION（无空格）
_SOLID_SECTION_HEADER = re.compile(
    r"^\s*\*\s*(?:Solid\s+Section|SOLID\s+SECTION|SOLIDSECTION)\s*(?:,|\s*$)",
    re.IGNORECASE,
)


def _solid_section_header_bare_line(stripped: str) -> bool:
    """仅关键字、参数在下一行以逗号开头（Abaqus 续行）。"""
    if not stripped or stripped.startswith("**"):
        return False
    return bool(
        re.match(r"^\s*\*\s*(?:Solid\s+Section|SOLID\s+SECTION|SOLIDSECTION)\s*$", stripped, re.IGNORECASE)
    )


def _is_solid_section_start(lines: list[str], i: int) -> bool:
    """行 i 是否为固体截面卡起始（含续行首行）。"""
    if i >= len(lines):
        return False
    s = _strip_inp_line(lines[i])
    if _SOLID_SECTION_HEADER.match(s):
        return True
    if _solid_section_header_bare_line(s) and i + 1 < len(lines):
        return _strip_inp_line(lines[i + 1]).startswith(",")
    return False


def _solid_section_block_end_exclusive(lines: list[str], start_idx: int) -> int:
    """固体截面块结束下标（不含），与 beso_lib._consume_solid_section_block 一致。"""
    n = len(lines)
    i = start_idx + 1
    while i < n:
        t = _strip_inp_line(lines[i])
        if not t:
            i += 1
            continue
        if t.startswith("**"):
            i += 1
            continue
        if t.startswith("*") and not t.startswith(","):
            break
        if t.startswith(","):
            i += 1
            continue
        i += 1
    return i


def _extract_solid_section_blocks_flat(lines: list[str]) -> tuple[list[str], list[str]]:
    """
    从行序列中抽出全部固体截面块（含续行），返回 (flat_solid_lines, remainder)。
    """
    solid_flat: list[str] = []
    remainder: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if _is_solid_section_start(lines, i):
            j = _solid_section_block_end_exclusive(lines, i)
            solid_flat.extend(lines[i:j])
            i = j
            continue
        remainder.append(lines[i])
        i += 1
    return solid_flat, remainder


def _reorder_pre_step_materials_before_solids(lines: list[str]) -> list[str]:
    """
    将首个 *STEP 之前的模型定义规范为：非材料非固体行 + 全部 *MATERIAL 块 + 全部 *SOLID* 截面。
    修复「*SOLIDSECTION 未被识别为首个截面 → 材料被抽到固体之前」导致的 CalculiX nonexistent material。
    """
    idx = _find_first_step_line_index(lines)
    if idx >= len(lines):
        return lines
    pre, post = lines[:idx], lines[idx:]
    mats, rem = _extract_all_material_blocks_in_order(pre)
    s_flat, core = _extract_solid_section_blocks_flat(rem)
    return core + mats + s_flat + post


def _inject_missing_material_blocks_for_solid_refs(lines: list[str]) -> list[str]:
    """
    最后一道防线：*STEP 前有 *SOLID / *SOLIDSECTION 引用 MATERIAL=，但缺少对应 ``*MATERIAL, NAME=`` 时，
    在首个固体截面之前注入 ``*MATERIAL`` + ``*ELASTIC``。

    覆盖旧流水/手工裁剪后出现的「仅有 *Solid section 而无材料卡」deck（见 runs/.../03_for_beso.inp 类故障）。
    """
    idx_step = _find_first_step_line_index(lines)
    if idx_step >= len(lines):
        return lines
    pre = lines[:idx_step]
    post = lines[idx_step:]
    refs = _collect_solid_material_refs_in_model_lines(pre)
    if not refs:
        return lines
    defs_ci = {(d or "").strip().upper() for d in _collect_defined_material_names(pre) if (d or "").strip()}
    yb = _parse_first_elastic_from_lines(pre) or (210000.0, 0.3)
    e, nu = float(yb[0]), float(yb[1])
    to_add: list[str] = []
    seen_ru: set[str] = set()
    for r in refs:
        raw = (r or "").strip()
        if not raw:
            continue
        ru = raw.upper()
        if ru in defs_ci or ru in seen_ru:
            continue
        seen_ru.add(ru)
        mat_san = _sanitize_ccx_material_name(raw)
        to_add.extend(
            [
                "** --- OC4: auto-injected *MATERIAL + *ELASTIC (solid ref had no deck definition) ---",
                f"*MATERIAL, NAME={mat_san}",
                "*ELASTIC",
                f"{e}, {nu}",
            ]
        )
        defs_ci.add(mat_san.strip().upper())
    if not to_add:
        return lines
    ins = _find_first_solid_section_line_index(pre)
    if ins < 0:
        ins = len(pre)
    new_pre = pre[:ins] + to_add + pre[ins:]
    return new_pre + post


def repair_oc4_beso_inp_lines(lines: list[str]) -> list[str]:
    """
    对 OC4 主 INP（通常为 ``03_for_beso.inp``）做 *STEP 前材料顺序整理 + 缺失 *MATERIAL 注入。
    供 ``run_beso_job`` 等对磁盘上已有文件兜底（旧分区或仅拷贝进 run 目录的 deck）。
    """
    rep = _inject_missing_material_blocks_for_solid_refs(
        _reorder_pre_step_materials_before_solids(list(lines))
    )
    return _decimalize_node_coordinate_data_lines(rep)


def _strip_inp_line(ln: str) -> str:
    return ln.strip().lstrip("\ufeff\ufffe")


def _decimalize_node_coordinate_data_lines(lines: list[str]) -> list[str]:
    """
    将 *NODE 数据行中的科学计数法改为定点小数。

    meshio 等导出的 ``1, -3.68e+04, ...`` 在部分 CalculiX 构建下会在首条 *NODE 即报错，
    导致 nk 未建立并连带 *NSET / *BOUNDARY / *CLOAD 全部失效；写定点坐标可规避。
    """
    out: list[str] = []
    in_nodes = False
    for raw in lines:
        s = _strip_inp_line(raw)
        if s.upper().startswith("*NODE"):
            in_nodes = True
            out.append(raw)
            continue
        if in_nodes:
            if not s:
                out.append(raw)
                continue
            if s.startswith("**"):
                out.append(raw)
                continue
            if s.startswith("*"):
                in_nodes = False
                out.append(raw)
                continue
            parts = [p.strip() for p in s.split(",")]
            if len(parts) >= 4 and parts[0].lstrip("-").isdigit():
                try:
                    nid = int(parts[0])
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    tail = [t for t in parts[4:] if t]
                    body = f"{nid}, {x:.10f}, {y:.10f}, {z:.10f}"
                    if tail:
                        body += ", " + ", ".join(tail)
                    out.append(body)
                    continue
                except ValueError:
                    pass
            out.append(raw)
            continue
        out.append(raw)
    return out


def _find_first_solid_section_line_index(lines: list[str]) -> int:
    """返回首个 *SOLID SECTION / *SOLIDSECTION 行索引；未找到返回 -1。"""
    i = 0
    while i < len(lines):
        s = _strip_inp_line(lines[i])
        if s.startswith("**"):
            i += 1
            continue
        if _is_solid_section_start(lines, i):
            return i
        i += 1
    return -1


def _find_first_step_line_index(lines: list[str]) -> int:
    for i, ln in enumerate(lines):
        if _strip_inp_line(ln).upper().startswith("*STEP"):
            return i
    return len(lines)


_MATERIAL_NAME_RE = re.compile(r"(?i)\bNAME\s*=\s*([^,\n]+)")


def _parse_first_material_name(lines: list[str]) -> str | None:
    """从首个 *MATERIAL 行解析材料名，保持与 INP 原文一致的大小写（CalculiX 需与 *MATERIAL 定义一致）。"""
    n = len(lines)
    i = 0
    while i < n:
        s = _strip_inp_line(lines[i])
        if not s or s.startswith("**"):
            i += 1
            continue
        if not re.match(r"^\*\s*MATERIAL\b", s, re.I):
            i += 1
            continue
        merged = s
        j = i + 1
        while j < n:
            t = _strip_inp_line(lines[j])
            if not t or t.startswith("**"):
                j += 1
                continue
            if t.startswith("*"):
                break
            if t.startswith(","):
                merged += t
                j += 1
                continue
            break
        m = _MATERIAL_NAME_RE.search(merged)
        if m:
            name = m.group(1).strip()
            if name:
                return name
        i = j if j > i else i + 1
    return None


def _parse_material_from_first_solid_section(lines: list[str]) -> str | None:
    """若无 NAME=，则从首个 *SOLID SECTION 的 MATERIAL= 取值（保持大小写）；支持参数续行。"""
    n = len(lines)
    i = 0
    while i < n:
        s = _strip_inp_line(lines[i])
        if s.startswith("**"):
            i += 1
            continue
        if not _is_solid_section_start(lines, i):
            i += 1
            continue
        merged = s
        j = i + 1
        while j < n:
            t = _strip_inp_line(lines[j])
            if not t or t.startswith("**"):
                j += 1
                continue
            if t.startswith("*"):
                break
            if t.startswith(","):
                merged += t
                j += 1
                continue
            break
        m = re.search(r"(?i)\bMATERIAL\s*=\s*([^,\n]+)", merged)
        if m:
            name = m.group(1).strip()
            if name:
                return name
        i = j if j > i else i + 1
    return None


def _parse_first_elastic_from_lines(lines: list[str]) -> tuple[float, float] | None:
    """从行序列中读取首个 *ELASTIC 后第一条数据行的 E、ν（与 CalculiX / Abaqus 一致）。"""
    n = len(lines)
    i = 0
    while i < n:
        s = _strip_inp_line(lines[i])
        if re.match(r"^\*\s*ELASTIC\b", s, re.I):
            j = i + 1
            while j < n:
                t = _strip_inp_line(lines[j])
                if not t or t.startswith("**"):
                    j += 1
                    continue
                if t.startswith("*"):
                    return None
                parts = [p.strip() for p in t.split(",")]
                try:
                    e = float(parts[0])
                    nu = float(parts[1]) if len(parts) > 1 else 0.3
                    return (e, nu)
                except (ValueError, IndexError):
                    return None
            return None
        i += 1
    return None


def _material_names_from_blocks(mat_lines: list[str]) -> list[str]:
    return _collect_defined_material_names(mat_lines)


def _ensure_material_block_for_name(
    mat_lines: list[str],
    mat: str,
    *,
    fallback_elastic_lines: list[str],
) -> list[str]:
    """
    若抽出的材料块中尚无 ``mat`` 的定义（常见于 *INCLUDE 材料或续行未被收集），
    在块末追加 *MATERIAL + *ELASTIC（与 wiki example_3 ``Analysis-1.inp`` 一致），避免 CalculiX nonexistent material。
    """
    names = _material_names_from_blocks(mat_lines)
    mu = mat.strip().upper()
    if any(x.strip().upper() == mu for x in names):
        return mat_lines
    yb = _parse_first_elastic_from_lines(mat_lines) or _parse_first_elastic_from_lines(fallback_elastic_lines)
    if yb is None:
        yb = (210000.0, 0.3)
    e, nu = yb
    extra = [
        "** --- OC4: material for design_space / nondesign_space (injected when missing in main deck) ---",
        f"*MATERIAL, NAME={mat}",
        "*ELASTIC",
        f"{e}, {nu}",
    ]
    return [*mat_lines, *extra]


_CCX_MATERIAL_NAME_SAFE = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


def _sanitize_ccx_material_name(name: str, *, fallback: str = "MSteel") -> str:
    """CalculiX / Abaqus 材料名：仅 ASCII 安全字符与长度，避免 deck 解析异常。"""
    s = (name or "").strip()
    if not s:
        return fallback
    s = re.sub(r"[^A-Za-z0-9_.\-]", "_", s)
    s = s.strip("._-") or fallback
    s = s[:80]
    if not _CCX_MATERIAL_NAME_SAFE.match(s):
        return fallback
    return s


def _material_list_contains_ci(names: list[str], mat: str) -> bool:
    mu = (mat or "").strip().upper()
    if not mu:
        return False
    return any((x or "").strip().upper() == mu for x in names)


def _collect_solid_material_refs_in_model_lines(model_lines: list[str]) -> list[str]:
    """收集模型定义段中所有 *SOLID SECTION 的 MATERIAL= 引用（含续行）。"""
    refs: list[str] = []
    n = len(model_lines)
    i = 0
    while i < n:
        s = _strip_inp_line(model_lines[i])
        if s.startswith("**"):
            i += 1
            continue
        is_solid = _is_solid_section_start(model_lines, i)
        if not is_solid:
            i += 1
            continue
        merged = s
        j = i + 1
        while j < n:
            t = _strip_inp_line(model_lines[j])
            if not t or t.startswith("**"):
                j += 1
                continue
            if t.startswith("*") and not t.startswith(","):
                break
            if t.startswith(","):
                merged += t
                j += 1
                continue
            break
        m = re.search(r"(?i)\bMATERIAL\s*=\s*([^,\n]+)", merged)
        if m:
            refs.append(m.group(1).strip())
        i = j if j > i else i + 1
    return refs


def _validate_oc4_partition_output(out_lines: list[str]) -> list[str]:
    """
    写出前校验：*STEP 之前每个 *SOLID SECTION 的 MATERIAL 均有对应 *MATERIAL, NAME=。
    失败抛出 ValueError（由 API 转为 400）；仅提示类问题返回 warnings。
    """
    idx = _find_first_step_line_index(out_lines)
    if idx >= len(out_lines):
        raise ValueError("生成的 INP 中未找到 *STEP，无法提交 CalculiX。")
    pre = out_lines[:idx]
    defs = _collect_defined_material_names(pre)
    dset_ci = {(d or "").strip().upper() for d in defs if (d or "").strip()}
    refs = _collect_solid_material_refs_in_model_lines(pre)
    if not refs:
        raise ValueError("模型定义段中未找到任何 *SOLID SECTION，OC4 分区输出异常。")
    for r in refs:
        ru = (r or "").strip().upper()
        if ru and ru not in dset_ci:
            raise ValueError(
                f"*STEP 前有 *SOLID SECTION 引用材料「{r}」，但未找到匹配的 *MATERIAL, NAME=（"
                f"已解析材料名: {defs!r}）。请检查网格 INP 或重新划分载荷。"
            )
    warns: list[str] = []
    if any(_strip_inp_line(x).upper().startswith("*INCLUDE") for x in pre):
        warns.append(
            "模型定义中含 *INCLUDE：若材料仅在子文件中定义，请确认 CalculiX 能解析到与 *SOLID SECTION 一致的材料名。"
        )
    return warns


def _collect_defined_material_names(lines: list[str]) -> list[str]:
    """
    收集 INP 中所有 *MATERIAL 的 NAME= 值（保留与 deck 完全一致的拼写）。
    支持 Abaqus 续行：*MATERIAL 后若干行以逗号开头拼到同一逻辑行再解析。
    """
    names: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        s = _strip_inp_line(lines[i])
        if not s or s.startswith("**"):
            i += 1
            continue
        if not re.match(r"^\*\s*MATERIAL\b", s, re.I):
            i += 1
            continue
        merged = s
        j = i + 1
        while j < n:
            t = _strip_inp_line(lines[j])
            if not t or t.startswith("**"):
                j += 1
                continue
            if t.startswith("*"):
                break
            if t.startswith(","):
                merged += t
                j += 1
                continue
            break
        m = _MATERIAL_NAME_RE.search(merged)
        if m:
            name = m.group(1).strip()
            if name:
                names.append(name)
        i = j if j > i else i + 1
    return names


def _canon_material_name(defined: list[str], want: str) -> str:
    """
    将候选名对齐到 deck 中已定义的材料名（大小写不敏感匹配，返回 deck 原文）。
    若 deck 中有材料但无法匹配候选名，回退为 ``defined[0]``，避免 *SOLID 引用不存在的材料。
    """
    w = (want or "").strip()
    if not defined:
        return w or "MSteel"
    if not w:
        return defined[0]
    for x in defined:
        if x == w:
            return x
    wu = w.upper()
    for x in defined:
        if x.upper() == wu:
            return x
    return defined[0]


# *MATERIAL 之后、下一个 *MATERIAL 或模型级关键字之前的子卡（CalculiX 常见写法）
_MATERIAL_SUBCARD = re.compile(
    r"^\s*\*\s*(ELASTIC|DENSITY|PLASTIC|HYPERELASTIC|CONDUCTIVITY|SPECIFIC\s+HEAT|HEAT\s+CAPACITY|"
    r"EXPANSION|CREEP|USER\s+MATERIAL|DEPVAR|POTENTIAL)\b",
    re.I,
)


def _extract_all_material_blocks_in_order(lines: list[str]) -> tuple[list[str], list[str]]:
    """
    从行序列中抽出全部 *MATERIAL 块（含 NAME 续行、*ELASTIC 等子卡及数据行），
    返回 (material_lines, remainder)。remainder 保持非材料行的原有顺序。
    """
    material_lines: list[str] = []
    remainder: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        s = _strip_inp_line(lines[i])
        if not s:
            remainder.append(lines[i])
            i += 1
            continue
        if s.startswith("**"):
            remainder.append(lines[i])
            i += 1
            continue
        if not re.match(r"^\*\s*MATERIAL\b", s, re.I):
            remainder.append(lines[i])
            i += 1
            continue

        blk0 = i
        i += 1
        while i < n:
            t = _strip_inp_line(lines[i])
            if not t or t.startswith("**"):
                i += 1
                continue
            if t.startswith("*"):
                break
            if t.startswith(","):
                i += 1
                continue
            break

        while i < n:
            t = _strip_inp_line(lines[i])
            if not t or t.startswith("**"):
                i += 1
                continue
            if t.startswith(","):
                i += 1
                continue
            if t.startswith("*"):
                if re.match(r"^\*\s*MATERIAL\b", t, re.I):
                    break
                if _MATERIAL_SUBCARD.match(t):
                    i += 1
                    while i < n:
                        u = _strip_inp_line(lines[i])
                        if not u or u.startswith("**"):
                            i += 1
                            continue
                        if u.startswith("*"):
                            break
                        i += 1
                    continue
                break
            i += 1

        material_lines.extend(lines[blk0:i])

    return material_lines, remainder


def _vertical_columns_from_oc4_iges(src_iges: Path) -> list[CylinderAxis]:
    cyls = _extract_revolution_cylinders(src_iges)
    vertical = [c for c in cyls if abs(float(c.direction[2])) > 0.96]
    vertical = _merge_parallel_axis_pairs(vertical)
    vertical = [
        c
        for c in vertical
        if c.radius >= 1200.0
        and (c.length >= 5000.0 or (c.length >= 350.0 and c.radius >= 2600.0))
    ]
    if len(vertical) < 4:
        raise ValueError(f"从 {src_iges} 识别到的主立柱不足 4 根，无法划分柱走廊。")
    center_col, outer_cols, _, _ = _pick_oc4_key_columns(vertical)
    return [center_col, *outer_cols]


def _dist_point_to_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    lab2 = float(np.dot(ab, ab))
    if lab2 <= 1.0e-18:
        return float(np.linalg.norm(p - a))
    t = float(np.dot(p - a, ab) / lab2)
    t = max(0.0, min(1.0, t))
    q = a + t * ab
    return float(np.linalg.norm(p - q))


def _in_any_column_corridor(
    centroid: np.ndarray,
    cols: list[CylinderAxis],
    band_scale: float,
) -> bool:
    for c in cols:
        d = _dist_point_to_segment(centroid, np.asarray(c.p0, dtype=float), np.asarray(c.p1, dtype=float))
        if d < float(c.radius) * band_scale:
            return True
    return False


def _parse_nodes(lines: list[str]) -> dict[int, np.ndarray]:
    nodes: dict[int, np.ndarray] = {}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip().upper().startswith("*NODE"):
            i += 1
            while i < n and not lines[i].strip().startswith("*"):
                parts = [p.strip() for p in lines[i].split(",")]
                if len(parts) >= 4 and parts[0].isdigit():
                    nid = int(parts[0])
                    nodes[nid] = np.array([float(parts[1]), float(parts[2]), float(parts[3])], dtype=float)
                i += 1
            continue
        i += 1
    if not nodes:
        raise ValueError("INP 中未解析到任何 *NODE 数据")
    return nodes


def _parse_volume_elements(lines: list[str]) -> tuple[list[tuple[int, str, list[int]]], set[int]]:
    """
    返回 (体单元列表, 所有出现的体单元号集合)。
    体单元类型：C3D4, C3D10, C3D8, C3D8R 等（以 C3D 开头）。
    """
    out: list[tuple[int, str, list[int]]] = []
    all_ids: set[int] = set()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        m = _ELEM_HEAD.match(s)
        m2 = _ELEM_HEAD_NO_ELSET.match(s) if not m else None
        if not m and not m2:
            i += 1
            continue
        typ = (m.group(1) if m else m2.group(1)).upper()
        if not typ.startswith("C3D"):
            i += 1
            continue
        i += 1
        while i < n and not lines[i].strip().startswith("*"):
            parts = [p.strip() for p in lines[i].split(",")]
            if not parts or not parts[0].isdigit():
                i += 1
                continue
            eid = int(parts[0])
            nids = [int(x) for x in parts[1:] if x.isdigit()]
            use: list[int] | None = None
            if typ == "C3D4" and len(nids) >= 4:
                use = nids[:4]
            elif typ == "C3D10" and len(nids) >= 10:
                use = nids[:10]
            elif typ in {"C3D8", "C3D8R", "C3D8I"} and len(nids) >= 8:
                use = nids[:8]
            if use is not None:
                all_ids.add(eid)
                out.append((eid, typ, use))
            i += 1
        continue
    return out, all_ids


def _centroid(nodes: dict[int, np.ndarray], nids: list[int]) -> np.ndarray:
    pts = np.stack([nodes[i] for i in nids if i in nodes], axis=0)
    return np.mean(pts, axis=0)


def _format_elset_block(name: str, ids: list[int], per_line: int = 16) -> list[str]:
    lines = [f"*ELSET, ELSET={name}"]
    for i in range(0, len(ids), per_line):
        chunk = ids[i : i + per_line]
        lines.append(", ".join(str(x) for x in chunk) + ",")
    return lines


def summarize_mesh_for_loads(mesh_inp: Path) -> dict[str, Any]:
    """
    为自然语言载荷解析提供网格摘要（节点 z 范围、最高节点、顶端若干节点号）。
    不读完整单元，仅 *NODE。
    """
    mesh_inp = mesh_inp.resolve()
    text = mesh_inp.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    nodes = _parse_nodes(lines)
    if not nodes:
        raise ValueError("网格中无节点，无法摘要")
    zvals = {nid: float(p[2]) for nid, p in nodes.items()}
    zmin = min(zvals.values())
    zmax = max(zvals.values())
    by_z_desc = sorted(nodes.keys(), key=lambda i: zvals[i], reverse=True)
    load_node_max_z = int(by_z_desc[0])
    sample_n = min(48, len(by_z_desc))
    top_node_ids_sample = [int(x) for x in by_z_desc[:sample_n]]
    return {
        "n_nodes": len(nodes),
        "z_min": zmin,
        "z_max": zmax,
        "load_node_max_z": load_node_max_z,
        "top_node_ids_sample": top_node_ids_sample,
    }


def _build_cload_entries(
    nodes: dict[int, np.ndarray],
    *,
    load_node_max_z: int,
    cload_mag: float,
    load_case: dict[str, Any] | None,
) -> tuple[list[tuple[int, int, float]], str]:
    """
    返回 ( (node_id, dof, magnitude), ... ) 与 cload_mode 标签。
    与 examples/oc4/from_cad_b31.inp 等一致：单条 *CLOAD 关键字下多行数据。
    """
    lc = dict(load_case) if load_case else {}
    mode = str(lc.get("cload_mode") or "single_top").strip().lower()
    dof = int(lc.get("cload_dof") or 3)
    if dof not in (1, 2, 3):
        dof = 3

    zvals = {nid: float(nodes[nid][2]) for nid in nodes}
    by_z_desc = sorted(nodes.keys(), key=lambda i: zvals[i], reverse=True)

    def _mag_one() -> float:
        v = lc.get("cload_mag")
        if v is not None:
            return float(v)
        return float(cload_mag)

    def _mag_each() -> float:
        v = lc.get("cload_each")
        if v is not None:
            return float(v)
        return float(cload_mag)

    if mode in ("single", "single_top", "max_z", "one_node"):
        mag = _mag_one()
        return [(int(load_node_max_z), dof, mag)], mode

    if mode in ("top_count", "count_top", "n_top"):
        n = int(lc.get("top_node_count") or lc.get("count") or 1)
        n = max(1, min(n, len(by_z_desc), 500))
        mag = _mag_each()
        return [(int(nid), dof, mag) for nid in by_z_desc[:n]], mode

    if mode in ("top_fraction", "fraction_top"):
        frac = float(lc.get("top_fraction") or lc.get("fraction") or 0.01)
        frac = max(1.0 / max(len(by_z_desc), 1), min(frac, 0.5))
        n = max(1, int(round(len(by_z_desc) * frac)))
        n = min(n, len(by_z_desc), 500)
        mag = _mag_each()
        return [(int(nid), dof, mag) for nid in by_z_desc[:n]], mode

    if mode == "explicit":
        raw = lc.get("explicit_cloads") or lc.get("cloads")
        if not isinstance(raw, list) or not raw:
            mag = _mag_one()
            return [(int(load_node_max_z), dof, mag)], "explicit_fallback"
        out: list[tuple[int, int, float]] = []
        node_set = set(nodes.keys())
        for item in raw:
            if not isinstance(item, dict):
                continue
            nid = int(item.get("node") or item.get("nid") or 0)
            d = int(item.get("dof") or dof)
            m = float(item.get("magnitude") or item.get("mag") or item.get("value") or 0.0)
            if nid not in node_set or d not in (1, 2, 3):
                continue
            out.append((nid, d, m))
        if not out:
            mag = _mag_one()
            return [(int(load_node_max_z), dof, mag)], "explicit_fallback"
        return out, mode

    mag = _mag_one()
    return [(int(load_node_max_z), dof, mag)], "single_top"


def partition_oc4_mesh_inp(
    mesh_inp: Path,
    src_oc4_iges: Path,
    out_inp: Path,
    *,
    band_scale: float = 1.22,
    z_fix_band: float = 800.0,
    cload_mag: float = -5.0e6,
    material_name: str | None = None,
    load_case: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    读取 meshio/Gmsh 风格体网格 INP，写出带 design_space / nondesign_space 与最小 *STEP 的 INP。

    Returns:
        统计 dict：n_design, n_nondesign, n_fixed_nodes, load_node, cload_mode, n_cload_lines 等。
    """
    mesh_inp = mesh_inp.resolve()
    text = mesh_inp.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    lc = dict(load_case) if load_case else {}
    band_scale = float(lc.get("band_scale", band_scale))
    z_fix_band = float(lc.get("z_fix_band", z_fix_band))
    band_scale = max(1.0, min(band_scale, 3.0))
    z_fix_band = max(10.0, z_fix_band)

    cols = _vertical_columns_from_oc4_iges(src_oc4_iges.resolve())
    nodes = _parse_nodes(lines)
    vol_elems, _ = _parse_volume_elements(lines)

    design: list[int] = []
    nondesign: list[int] = []
    for eid, typ, nids in vol_elems:
        c = _centroid(nodes, nids)
        if _in_any_column_corridor(c, cols, band_scale):
            nondesign.append(eid)
        else:
            design.append(eid)

    if not design:
        raise RuntimeError("design_space 为空：请减小 band_scale 或检查网格/柱识别。")
    if not nondesign:
        steal_n = max(8, len(design) // 8000)
        steal = set(sorted(design)[:steal_n])
        nondesign = list(steal)
        design = [x for x in design if x not in steal]

    zvals = np.array([nodes[i][2] for i in nodes], dtype=float)
    zmin = float(np.min(zvals))
    zmax = float(np.max(zvals))
    fixed_nodes = [nid for nid, p in nodes.items() if float(p[2]) <= zmin + z_fix_band]
    load_cand = [(nid, float(nodes[nid][2])) for nid in nodes]
    load_node = int(max(load_cand, key=lambda t: t[1])[0])

    cload_entries, cload_mode = _build_cload_entries(
        nodes,
        load_node_max_z=load_node,
        cload_mag=float(lc.get("cload_mag", cload_mag)),
        load_case=lc if lc else None,
    )

    defined_mats = _collect_defined_material_names(lines)
    mat = material_name
    if mat is None:
        mat = _parse_first_material_name(lines)
    if mat is None:
        mat = _parse_material_from_first_solid_section(lines)
    if mat is None:
        mat = "MSteel"
    mat = _canon_material_name(defined_mats, mat)
    mat = _sanitize_ccx_material_name(mat)

    if not fixed_nodes:
        raise RuntimeError(
            "未找到可用于底面约束的节点（z 落在 z_min+z_fix_band 内为空）。"
            "请增大 z_fix_band 或检查网格坐标/单位。"
        )
    node_ids = set(nodes.keys())
    for nid, dof, _mag in cload_entries:
        if int(nid) not in node_ids:
            raise RuntimeError(f"*CLOAD 引用的节点 {nid} 不在 *NODE 中，请检查载荷配置。")
        if int(dof) not in (1, 2, 3):
            raise RuntimeError(f"*CLOAD 自由度 {dof} 非法（应为 1～3）。")

    idx_step = _find_first_step_line_index(lines)
    idx_solid = _find_first_solid_section_line_index(lines)
    if idx_solid < 0:
        # 部分体网格 INP 仅有 *MATERIAL / *ELASTIC / *ELEMENT 而无显式体截面：在首个 *STEP 前插入双截面。
        idx_solid = idx_step
        j = idx_step
        tail_before_step: list[str] = []
    else:
        j = idx_solid + 1
        while j < len(lines) and not _strip_inp_line(lines[j]).startswith("*"):
            j += 1
        tail_before_step = lines[j:idx_step]

    head = lines[:idx_solid]
    mid: list[str] = [
        "** --- OC4 pipeline: design_space / nondesign_space (wiki example_3 style) ---",
    ]
    mid.extend(_format_elset_block("nondesign_space", sorted(nondesign)))
    mid.extend(_format_elset_block("design_space", sorted(design)))
    mid.append("**")
    mid.append(f"*Solid section, Elset=design_space, Material={mat}")
    mid.append(f"*Solid section, Elset=nondesign_space, Material={mat}")

    nset_blk = ["**", "*NSET, NSET=fixed_zmin"]
    for i in range(0, len(sorted(fixed_nodes)), 16):
        chunk = sorted(fixed_nodes)[i : i + 16]
        nset_blk.append(", ".join(str(x) for x in chunk) + ",")

    cload_lines = [f"{nid}, {d}, {mag:.12g}" for nid, d, mag in cload_entries]
    step_blk = [
        "** --- Static step (CalculiX): fixed_zmin boundary + concentrated loads (from_cad_b31 style) ---",
        "*STEP",
        "*STATIC",
        "1., 1., 1e-05, 1.",
        "*BOUNDARY",
        "fixed_zmin, 1, 3, 0",
        "*CLOAD",
        *cload_lines,
        "*NODE FILE",
        "U",
        "*EL FILE",
        "S",
        "*END STEP",
    ]

    # 与 wiki example_3 ``Analysis-1.inp`` 一致：全部 *MATERIAL / *ELASTIC 在前，*Solid section 在后；
    # 并从主 deck 抽出材料块，避免「固体截面早于材料定义」；缺定义时注入 *MATERIAL + *ELASTIC。
    combined_pre = head + tail_before_step
    mat_lines_raw, core_lines = _extract_all_material_blocks_in_order(combined_pre)
    names_before_ensure = _material_names_from_blocks(mat_lines_raw)
    mat_lines = _ensure_material_block_for_name(mat_lines_raw, mat, fallback_elastic_lines=lines)
    material_injected = not _material_list_contains_ci(names_before_ensure, mat)
    out_lines = core_lines + mat_lines + mid + nset_blk + step_blk
    out_lines = _reorder_pre_step_materials_before_solids(out_lines)
    _snap_post_reorder = list(out_lines)
    out_lines = _inject_missing_material_blocks_for_solid_refs(out_lines)
    out_lines = _decimalize_node_coordinate_data_lines(out_lines)
    validation_warnings = list(_validate_oc4_partition_output(out_lines))
    if out_lines != _snap_post_reorder:
        validation_warnings.append(
            "检测到 *STEP 前有固体截面引用材料，但 deck 中缺少匹配的 *MATERIAL 定义，已自动注入材料块。"
        )
    if material_injected:
        validation_warnings.append(
            f"已在 *STEP 前自动注入 *MATERIAL, NAME={mat} 与 *ELASTIC（主 deck 中此前无该材料名）。"
        )
    out_inp.parent.mkdir(parents=True, exist_ok=True)
    out_inp.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return {
        "n_design": len(design),
        "n_nondesign": len(nondesign),
        "n_fixed_nodes": len(fixed_nodes),
        "load_node": int(load_node),
        "cload_mode": cload_mode,
        "n_cload_lines": len(cload_entries),
        "cload_nodes": [int(t[0]) for t in cload_entries],
        "material_name": mat,
        "material_injected": bool(material_injected),
        "validation_warnings": validation_warnings,
    }


def _iter_line(iterations_limit: int | str) -> str:
    if isinstance(iterations_limit, int):
        return f"iterations_limit = {iterations_limit}"
    return f'iterations_limit = "{iterations_limit}"'


def write_beso_conf_example3_style(
    target: Path,
    *,
    work_dir: Path,
    ccx_path: Path,
    inp_name: str,
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    iterations_limit: int | str = 8,
    save_iteration_results: int = 1,
) -> None:
    """双域 ``design_space`` + ``nondesign_space``，与 wiki example_3 beso_conf 结构一致。"""
    work_dir = work_dir.resolve()
    ccx_path = ccx_path.resolve()
    il = _iter_line(iterations_limit)
    txt = f'''# Auto-generated by oc4_beso_full_pipeline (example_3 style: two elsets)

path = r"{work_dir}"
path_calculix = r"{ccx_path}"
file_name = "{inp_name}"

{il}

elset_name = "design_space"
domain_optimized[elset_name] = True
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

elset_name = "nondesign_space"
domain_optimized[elset_name] = False
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

mass_goal_ratio = {mass_goal_ratio}
filter_list = [["simple", {filter_radius}]]
optimization_base = "{optimization_base}"
save_iteration_results = {max(1, int(save_iteration_results))}
save_resulting_format = "inp vtk"
'''
    target.write_text(txt, encoding="utf-8")


def write_beso_conf_sector120_style(
    target: Path,
    *,
    work_dir: Path,
    ccx_path: Path,
    inp_name: str,
    mass_goal_ratio: float,
    filter_radius: float,
    optimization_base: str,
    iterations_limit: int | str = 8,
    save_iteration_results: int = 1,
) -> None:
    """``design_s0``/``design_s1``/``design_s2`` + ``nondesign_space``（仅 ``design_s0`` 开关优化，另两扇区由 beso_main 映射同步）。"""
    work_dir = work_dir.resolve()
    ccx_path = ccx_path.resolve()
    il = _iter_line(iterations_limit)
    txt = f'''# Auto-generated: beso3 120° sectors + nondesign_space

path = r"{work_dir}"
path_calculix = r"{ccx_path}"
file_name = "{inp_name}"

{il}

elset_name = "design_s0"
domain_optimized[elset_name] = True
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

elset_name = "design_s1"
domain_optimized[elset_name] = False
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

elset_name = "design_s2"
domain_optimized[elset_name] = False
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

elset_name = "nondesign_space"
domain_optimized[elset_name] = False
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \\n210000e-6,  0.3", "*ELASTIC \\n210000,  0.3"]
domain_same_state[elset_name] = False

mass_goal_ratio = {mass_goal_ratio}
filter_list = [["simple", {filter_radius}]]
optimization_base = "{optimization_base}"
save_iteration_results = {max(1, int(save_iteration_results))}
save_resulting_format = "inp vtk"
'''
    target.write_text(txt, encoding="utf-8")
