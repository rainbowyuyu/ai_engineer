"""主 INP 模型定义段体量估计（不解析 *INCLUDE），用于在 BESO import_inp 前避免 MemoryError。"""
from __future__ import annotations

import math
import os
from pathlib import Path


def beso_mesh_hard_limits() -> tuple[int, int]:
    """返回 (max_nodes, max_elements) 硬上限。"""
    max_n = int((os.environ.get("BESO_MAX_INP_NODES") or "250000").strip() or "250000")
    max_e = int((os.environ.get("BESO_MAX_INP_ELEMENTS") or "500000").strip() or "500000")
    return max(10_000, max_n), max(20_000, max_e)


def beso_mesh_target_elements() -> int:
    """
    拓扑优化推荐目标单元数（软目标）。
    过大则慢/易 OOM；过小则分辨率不足。默认约 15 万，落在硬上限内留余量。
    """
    raw = (os.environ.get("BESO_TARGET_INP_ELEMENTS") or "150000").strip()
    try:
        t = int(raw)
    except ValueError:
        t = 150_000
    _max_n, max_e = beso_mesh_hard_limits()
    # 目标不超过硬上限的 ~70%，并夹在实用区间
    return int(max(40_000, min(t, int(max_e * 0.70), 350_000)))


def count_nodes_and_elements_in_inp(inp_path: Path) -> tuple[int, int]:
    """
    统计 ``*NODE`` / ``*ELEMENT`` 下首段连续数据行数量（遇下一个 ``*`` 关键字即结束该段）。
    不展开 *INCLUDE；对纯网格 INP 足够用于体量告警。
    """
    in_nodes = False
    in_elems = False
    n_nodes = 0
    n_elems = 0
    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith("**"):
                continue
            if s[0] == "*":
                tag = s.upper().split(",")[0].strip()
                if tag.startswith("*NODE"):
                    in_nodes, in_elems = True, False
                elif tag.startswith("*ELEMENT"):
                    in_nodes, in_elems = False, True
                elif tag.startswith("*STEP"):
                    in_nodes = in_elems = False
                else:
                    in_nodes = False
                    if in_elems:
                        in_elems = False
                continue
            if s[0].isdigit() or (s[0] == "-" and len(s) > 1 and s[1].isdigit()):
                if in_nodes:
                    n_nodes += 1
                elif in_elems:
                    n_elems += 1
    return n_nodes, n_elems


def mesh_exceeds_beso_limits(inp_path: Path) -> tuple[bool, int, int, int, int]:
    """返回 (超限?, nn, ne, max_n, max_e)。"""
    max_n, max_e = beso_mesh_hard_limits()
    nn, ne = count_nodes_and_elements_in_inp(inp_path)
    return (nn > max_n or ne > max_e), nn, ne, max_n, max_e


def suggest_cl_scale_to_fit_beso(nn: int, ne: int, *, target_elements: int | None = None) -> float:
    """
    由当前节点/单元数估计 CharacteristicLengthMax 需要放大的倍数（>=1）。
    体网格大致 ne ∝ 1/h³，故 h_new/h_old ≈ (ne/target)^(1/3)。
    """
    max_n, max_e = beso_mesh_hard_limits()
    tgt = int(target_elements) if target_elements is not None else beso_mesh_target_elements()
    tgt = max(20_000, min(tgt, max_e))
    factors: list[float] = [1.0]
    if ne > tgt:
        factors.append((float(ne) / float(tgt)) ** (1.0 / 3.0))
    if ne > max_e:
        factors.append((float(ne) / float(max_e)) ** (1.0 / 3.0))
    if nn > max_n:
        factors.append((float(nn) / float(max_n)) ** (1.0 / 3.0))
    # 略加裕度，避免卡在上限边缘
    return float(max(factors) * 1.12)


def inp_node_bbox_diagonal(inp_path: Path) -> float:
    """
    扫描 ``*NODE`` 段（遇 ``*ELEMENT`` 即停）估计包围盒对角线长度，与节点坐标同单位。
    用于判断 ``filter_radius`` 是否与模型尺度匹配。
    """
    in_nodes = False
    xmin = ymin = zmin = float("inf")
    xmax = ymax = zmax = float("-inf")
    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith("**"):
                continue
            if s[0] == "*":
                tag = s.upper().split(",")[0].strip()
                if tag.startswith("*NODE"):
                    in_nodes = True
                elif tag.startswith("*ELEMENT"):
                    break
                elif tag.startswith("*STEP"):
                    break
                else:
                    in_nodes = False
                continue
            if in_nodes and (s[0].isdigit() or (s[0] == "-" and len(s) > 1 and s[1].isdigit())):
                parts = [p.strip() for p in s.split(",")]
                if len(parts) < 4:
                    continue
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                except ValueError:
                    continue
                xmin = min(xmin, x)
                xmax = max(xmax, x)
                ymin = min(ymin, y)
                ymax = max(ymax, y)
                zmin = min(zmin, z)
                zmax = max(zmax, z)
    if xmax <= xmin or ymax <= ymin or zmax <= zmin:
        return 0.0
    dx = xmax - xmin
    dy = ymax - ymin
    dz = zmax - zmin
    return float(math.sqrt(dx * dx + dy * dy + dz * dz))


def _prepare2s_sector_count_upper_bound(diag: float, r: float) -> float:
    """用对角线估计立方等效边长，悲观估计 ``prepare2s`` 中 sector 字典项数量上界。"""
    if r <= 0.0 or diag <= 0.0:
        return float("inf")
    span = diag / (3.0**0.5)
    n = max(1.0, span / r + 4.0)
    return n * n * n


def auto_scale_filter_radius(inp_path: Path, requested: float) -> tuple[float, str | None]:
    """
    ``beso_filters.prepare2s`` 用 ``r_min`` 在单元质心包围盒上划分三维格子，并为每个格子建 ``dict`` 项；
    ``r_min`` 过小时 ``~(span/r)^3`` 极大，会长时间卡住或触发 MemoryError。

    当对角线较大时抬升半径（与 INP 坐标同单位）。除尺度比外，还按预估 sector 数设下限，避免
    上百万空格子在 Python 中占满内存；并抬到「近邻连通」粗估下限，避免
    ``simple filter failed due to division by 0``（无近邻单元）导致灵敏度噪声与振荡拓扑。
    可用环境变量 ``BESO_PREPARE2S_MAX_SECTORS``（默认 250000）调节松紧。
    """
    diag = inp_node_bbox_diagonal(inp_path)
    r = float(requested)
    if diag <= 500.0 or r <= 0.0:
        return r, None

    max_sectors = float((os.environ.get("BESO_PREPARE2S_MAX_SECTORS") or "250000").strip())
    max_sectors = max(50_000.0, min(max_sectors, 5_000_000.0))

    span = diag / (3.0**0.5)
    n_target = max(2.0, max_sectors ** (1.0 / 3.0) - 4.0)
    r_from_sectors = span / n_target

    # 与模型尺度成比例的下限（略放宽，优先满足 sector 上界）
    min_r = max(100.0, diag / 200.0, r_from_sectors)
    max_r = max(min_r, diag / 12.0)

    # 近邻连通下限：过小则 prepare2s 对孤立单元除零，拓扑呈「噪声海绵」并 OSCILLATION
    r_conn = 0.0
    try:
        r_conn = float(beso_simple_filter_radius_min_for_connectivity(inp_path))
        # 略低于离线脚本推荐，避免过平滑；仍须盖住典型质心间距
        r_conn = max(500.0, min(r_conn * 0.85, diag / 6.0))
    except Exception:
        r_conn = 0.0
    if r_conn > 0:
        min_r = max(min_r, r_conn)
        max_r = max(max_r, min_r)

    if r >= min_r * 0.98:
        return r, None
    r2 = min(max(r, min_r), max_r)
    est = _prepare2s_sector_count_upper_bound(diag, r2)
    note = (
        f"主 INP 节点包围盒对角线约 {diag:.0f}；filter_radius 过小会导致 BESO「simple」滤波失败"
        f"（无近邻 / prepare2s sector 过多，估计上界约 {est:.0f}）并得到噪声拓扑。"
        f"已从 {r:g} 调整为 {r2:g}（与节点坐标同单位；连通下限≈{r_conn:g}）。"
    )
    return r2, note

def beso_simple_filter_radius_min_for_connectivity(inp_path: Path) -> float:
    """
    粗估「不易触发 simple 滤波除零」的特征尺度下限，供离线脚本 / 管线写 ``beso_conf`` 时参考。

    **注意**：``run_beso_job`` 不再强制把用户半径抬到此下限（否则会显著过平滑、拓扑变差）；
    若 BESO 报 ``simple filter failed due to division by 0``，请在 UI 设置或 ``beso_conf`` 中略增大
    ``filter_radius``，或细化设计域网格。
    """
    diag = inp_node_bbox_diagonal(inp_path)
    _, ne = count_nodes_and_elements_in_inp(inp_path)
    if diag <= 0.0 or ne <= 0:
        return 5000.0
    if diag <= 800.0:
        return float(max(2.0, min(diag * 0.12, diag * 0.35)))
    nef = float(ne)
    n_edge = max(8.0, nef ** (1.0 / 3.0))
    h_typ = diag / n_edge
    return float(max(2000.0, min(h_typ * 3.5, diag / 4.0)))


def assert_inp_mesh_size_reasonable(inp_path: Path) -> None:
    """超过默认上限时直接报错，避免 beso_lib.import_inp 在弱内存环境下 OOM。"""
    over, nn, ne, max_n, max_e = mesh_exceeds_beso_limits(inp_path)
    if not over:
        return
    tgt = beso_mesh_target_elements()
    scale = suggest_cl_scale_to_fit_beso(nn, ne, target_elements=tgt)
    raise ValueError(
        "主 INP 网格体量过大，可能在 BESO 读入时触发 MemoryError。\n"
        f"估计：约 {nn} 个节点、{ne} 个单元（上限 {max_n} / {max_e}；拓扑优化建议约 {tgt} 单元）。\n"
        "请加大 CAD 剖分尺寸（如 characteristic_length_max / GMSH_CHAR_LENGTH_MAX）或简化几何；\n"
        f"经验上将 CharacteristicLengthMax 再放大约 ×{scale:.2f} 后重划网格。"
        "也可提高环境变量 BESO_MAX_INP_NODES / BESO_MAX_INP_ELEMENTS（自担内存风险）。"
    )
