"""主 INP 是否含 BESO（beso_lib.import_inp）可读的壳/实体单元 — 用于任务启动前校验。"""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

# 与 beso/beso_lib.py 中 *ELEMENT 分支一致（Abaqus 写法，大写比较）
BESO_SUPPORTED_CCX_TYPES = frozenset(
    {
        "S3",
        "CPS3",
        "CPE3",
        "CAX3",
        "M3D3",
        "S6",
        "CPS6",
        "CPE6",
        "CAX6",
        "M3D6",
        "S4",
        "S4R",
        "CPS4",
        "CPS4R",
        "CPE4",
        "CPE4R",
        "CAX4",
        "CAX4R",
        "M3D4",
        "M3D4R",
        "S8",
        "S8R",
        "CPS8",
        "CPS8R",
        "CPE8",
        "CPE8R",
        "CAX8",
        "CAX8R",
        "M3D8",
        "M3D8R",
        "C3D4",
        "C3D10",
        "C3D8",
        "C3D8R",
        "C3D8I",
        "C3D20",
        "C3D20R",
        "C3D20RI",
        "C3D6",
        "C3D15",
    }
)


def _parse_abaqus_element_type(element_line: str) -> str | None:
    for part in element_line.split(","):
        s = part.strip()
        if s[:5].upper() == "TYPE=":
            return s.split("=", 1)[1].strip().upper()
    return None


_INCLUDE_LINE_PAT = re.compile(r"^\*INCLUDE\s*,\s*INPUT\s*=\s*([^\r\n,]+)", re.IGNORECASE)


def _include_specs_in_inp(inp_path: Path) -> list[str]:
    out: list[str] = []
    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = _INCLUDE_LINE_PAT.match(line.strip())
            if m:
                out.append(m.group(1).strip().strip('"').strip("'"))
    return out


def _resolve_include_inp(host_dir: Path, spec: str) -> Path | None:
    """与常见 CalculiX 用法一致：相对路径相对主/宿主 INP 所在目录。"""
    spec = spec.strip().strip('"').strip("'")
    if not spec:
        return None
    raw = Path(spec)
    candidates = [host_dir / spec, host_dir / raw.name]
    for c in candidates:
        try:
            if c.is_file() and c.suffix.lower() == ".inp":
                return c.resolve()
        except OSError:
            continue
    return None


def _element_types_in_single_inp(inp_path: Path) -> Counter[str]:
    ctr: Counter[str] = Counter()
    with inp_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            ls = line.strip()
            if len(ls) < 9 or ls[0] != "*" or ls[:8].upper() != "*ELEMENT":
                continue
            t = _parse_abaqus_element_type(ls)
            if t:
                ctr[t] += 1
    return ctr


def scan_inp_abaqus_element_types(inp_path: Path) -> Counter[str]:
    """
    扫描 *ELEMENT, TYPE=… 出现次数（按卡片计数）。

    若主文件无 *ELEMENT（例如仅含 *INCLUDE 的装配 INP），则沿 *INCLUDE 在宿主文件目录下
    BFS 解析子 INP（与 example_2 的 file000.inp + FEMMeshGmsh_Node_Elem_sets.inp 一致）。
    最多遍历文件数由环境变量 ``BESO_INP_INCLUDE_SCAN_MAX`` 控制（默认 64），防环与过深链。
    """
    max_files = int((os.environ.get("BESO_INP_INCLUDE_SCAN_MAX") or "64").strip())
    max_files = max(1, min(max_files, 500))

    ctr: Counter[str] = Counter()
    seen: set[Path] = set()
    queue: list[Path] = [inp_path.resolve()]

    while queue and len(seen) < max_files:
        p = queue.pop(0)
        try:
            rp = p.resolve()
        except OSError:
            continue
        if rp in seen:
            continue
        if not rp.is_file():
            continue
        seen.add(rp)
        ctr.update(_element_types_in_single_inp(rp))
        host_dir = rp.parent
        for spec in _include_specs_in_inp(rp):
            child = _resolve_include_inp(host_dir, spec)
            if child is not None and child not in seen:
                queue.append(child)
    return ctr


def check_inp_beso_compat_error(inp_path: Path) -> str | None:
    """返回首行错误说明；若可运行 BESO 则返回 None（不抛异常，供扫描/UI 使用）。"""
    try:
        assert_inp_supported_by_beso(inp_path)
    except ValueError as e:
        return str(e).strip().split("\n")[0]
    return None


def assert_inp_supported_by_beso(inp_path: Path) -> None:
    """若无任何 BESO 支持的单元类型，抛出带说明的 ValueError。"""
    ctr = scan_inp_abaqus_element_types(inp_path)
    if not ctr:
        raise ValueError(
            "主 INP 及已解析的 *INCLUDE 子文件中均未发现 *ELEMENT 定义，无法运行 BESO。\n"
            "若网格在单独文件中，请确认 *INCLUDE, INPUT=… 指向的文件已随主 INP 一并上传到任务目录。"
        )
    good = {t: n for t, n in ctr.items() if t in BESO_SUPPORTED_CCX_TYPES}
    if good:
        return
    brief = ", ".join(f"{k}×{v}" for k, v in sorted(ctr.items(), key=lambda kv: (-kv[1], kv[0]))[:12])
    raise ValueError(
        "BESO 无法优化当前网格：未发现支持的壳/实体单元（如 C3D4、C3D8、S4、CPS4 等）。\n"
        f"当前 *ELEMENT 类型（节选）：{brief}\n"
        "梁单元（B31* 等）、刚体（R3D*）等不在支持范围内。\n"
        "若来自 CAD→Gmsh：请确认几何为可体网格的封闭实体，并生成四面体/六面体体网格后再导出。"
    )
