"""力方向 → CalculiX *CLOAD 参数（对齐 BESO9.FCStd：顶区 / 圆周、DirectionVector = −Z）。"""

from __future__ import annotations

from typing import Any

# FreeCAD BESO9 ConstraintForce：DirectionVector (0,0,-1)，顶面圆周边施力
DEFAULT_BESO9_FORCE_N = 2.45e7
FORCE_DIRECTIONS = ("-Z", "+Z", "+X", "-X", "+Y", "-Y")

_DIR_LABELS_ZH = {
    "-Z": "竖直向下（重力 / RNA 竖向等效）",
    "+Z": "竖直向上",
    "+X": "水平 +X（额定风推 / 塔基推力）",
    "-X": "水平 −X（额定风推）",
    "+Y": "水平 +Y（额定风推）",
    "-Y": "水平 −Y（额定风推）",
}


def normalize_force_direction(raw: str | None) -> str:
    d = (raw or "-Z").strip().upper().replace(" ", "")
    if d in ("Z-", "DOWN", "GRAVITY", "NEG_Z"):
        return "-Z"
    if d in ("Z+", "UP", "POS_Z"):
        return "+Z"
    if d in FORCE_DIRECTIONS:
        return d
    return "-Z"


def force_direction_label_zh(direction: str | None) -> str:
    return _DIR_LABELS_ZH.get(normalize_force_direction(direction), _DIR_LABELS_ZH["-Z"])


def load_case_from_force_direction(
    direction: str | None,
    *,
    total_force_n: float | None = None,
    beso9_ring: bool = True,
) -> dict[str, Any]:
    """
    将用户选择的力方向转为 partition / run_loads 的 load_case 字段。

    beso9_ring=True 时：顶区多节点均分总力（近似 BESO9 顶环圆周载荷），便于预览多条黄箭头。
    """
    d = normalize_force_direction(direction)
    abs_mag = abs(float(total_force_n)) if total_force_n is not None else DEFAULT_BESO9_FORCE_N
    if abs_mag <= 0:
        abs_mag = DEFAULT_BESO9_FORCE_N
    dof_mag = {
        "-Z": (3, -abs_mag),
        "+Z": (3, abs_mag),
        "+X": (1, abs_mag),
        "-X": (1, -abs_mag),
        "+Y": (2, abs_mag),
        "-Y": (2, -abs_mag),
    }
    dof, signed_total = dof_mag[d]
    out: dict[str, Any] = {
        "force_direction": d,
        "cload_dof": dof,
        "cload_mag": float(signed_total),
    }
    if beso9_ring:
        out["cload_mode"] = "beso9_ring"
        out["fix_mode"] = "beso9_arcs"
        # 总力由 partition 按环上节点数均分；不再用 top_count 误抓顶角尖点
    else:
        out["cload_mode"] = "single_top"
    return out


def merge_force_direction_into_load_case(
    load_case: dict[str, Any] | None,
    direction: str | None,
    *,
    total_force_n: float | None = None,
) -> dict[str, Any]:
    """已有 load_case 时保留 band 等字段，用方向覆盖 dof / mag / 分布模式。"""
    base = dict(load_case or {})
    # 若调用方已给了显式总力，优先；否则用 load_case.cload_mag 绝对值或 BESO9 默认
    if total_force_n is None and base.get("cload_mag") is not None:
        try:
            total_force_n = abs(float(base["cload_mag"]))
        except (TypeError, ValueError):
            total_force_n = None
    forced = load_case_from_force_direction(direction, total_force_n=total_force_n, beso9_ring=True)
    base.update(forced)
    return base
