"""主 INP 的 *ELSET 解析与 BESO 模板兼容性（避免 meshio/Gmsh 与 example_2 域名不一致）。"""
from __future__ import annotations

from pathlib import Path

# example 模板里假定存在的 ELSET / domain 名
EXAMPLE2_DOMAIN_NAMES = frozenset({"SolidMaterial001Solid", "SolidMaterialSolid"})
EXAMPLE3_DOMAIN_NAMES = frozenset({"design_space", "nondesign_space"})


def pick_usable_elset_name(elsets: list[str]) -> str:
    """Gmsh/meshio 常在末尾写 gmsh:bounding_entities，一般不是体设计域。"""
    if "SolidMaterialElementGeometry2D" in elsets:
        return "SolidMaterialElementGeometry2D"
    usable = [e for e in elsets if "bounding_entities" not in e.lower()]
    if usable:
        return sorted(usable)[0]
    return "all_available"


def template_elsets_match_primary(tpl_path: Path, primary_elsets: list[str], ex2: Path, ex3: Path) -> bool:
    """若主 INP 里没有任何模板假定存在的 ELSET，则不能用该模板里的 domain_* 块。"""
    names = frozenset(primary_elsets)
    try:
        resolved = tpl_path.resolve()
    except OSError:
        return False
    try:
        if resolved == ex2.resolve():
            return bool(EXAMPLE2_DOMAIN_NAMES & names)
        if resolved == ex3.resolve():
            return bool(EXAMPLE3_DOMAIN_NAMES & names)
    except OSError:
        return False
    return True
