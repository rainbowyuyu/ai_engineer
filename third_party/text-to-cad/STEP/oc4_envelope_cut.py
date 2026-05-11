"""由 oc4.step 上若干 @cad 面包络成轴对齐实体，并挖去与指定柱体实例相交部分。

包络面（去重）：o1.3.f1, o1.5.f1, o1.7.f1, o1.50.f1
切除工具：在 o1.30、o1.28 上取 f1 参考面，沿面法向双向拉伸成棱柱再布尔差（仅挖与包络相交部分；整壳转 Solid 对 o1.28 退化不可靠）

依赖：在仓库根运行 scripts/step；需将 .agents/skills/cad/scripts 加入 PYTHONPATH。
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / ".agents" / "skills" / "cad" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from OCP.Bnd import Bnd_Box  # noqa: E402
from OCP.BRep import BRep_Tool  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepBndLib import BRepBndLib  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism  # noqa: E402
from OCP.BRepTools import BRepTools  # noqa: E402
from OCP.GeomLProp import GeomLProp_SLProps  # noqa: E402
from OCP.TopAbs import TopAbs_FACE  # noqa: E402
from OCP.TopExp import TopExp  # noqa: E402
from OCP.TopTools import TopTools_IndexedMapOfShape  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402
from OCP.gp import gp_Pnt, gp_Vec  # noqa: E402

from build123d.topology import Shape  # noqa: E402

from common.step_scene import (  # noqa: E402
    load_step_scene,
    scene_leaf_occurrences,
    scene_occurrence_shape,
    occurrence_selector_id,
)


def _leaf_by_occ_id(scene, occ_id: str):
    for node in scene_leaf_occurrences(scene):
        if occurrence_selector_id(node) == occ_id:
            return node
    raise RuntimeError(f"leaf occurrence not found: {occ_id}")


def _face_on_occurrence(scene, occ_id: str, face_ordinal: int):
    node = _leaf_by_occ_id(scene, occ_id)
    shape = scene_occurrence_shape(scene, node)
    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
    if face_ordinal < 1 or face_ordinal > face_map.Extent():
        raise RuntimeError(f"{occ_id}.f{face_ordinal} out of range 1..{face_map.Extent()}")
    return TopoDS.Face_s(face_map.FindKey(face_ordinal))


def _merge_face_bboxes(scene, specs: list[tuple[str, int]]) -> Bnd_Box:
    box = Bnd_Box()
    for occ_id, fo in specs:
        face = _face_on_occurrence(scene, occ_id, fo)
        BRepBndLib.Add_s(face, box)
    return box


def _expand_box(box: Bnd_Box, margin: float) -> Bnd_Box:
    if box.IsVoid():
        return box
    mn = box.CornerMin()
    mx = box.CornerMax()
    x0, y0, z0 = mn.X(), mn.Y(), mn.Z()
    x1, y1, z1 = mx.X(), mx.Y(), mx.Z()
    out = Bnd_Box()
    out.Update(
        x0 - margin,
        y0 - margin,
        z0 - margin,
        x1 + margin,
        y1 + margin,
        z1 + margin,
    )
    return out


def _prism_tool_from_face(face, half_length: float):
    """沿面法向 ±half_length 双向拉伸并合并，得到与柱体区域相交的切除工具。"""
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
    u = 0.5 * (umin + umax)
    v = 0.5 * (vmin + vmax)
    surf = BRep_Tool.Surface_s(face)
    props = GeomLProp_SLProps(surf, u, v, 1, 1)
    props.SetParameters(u, v)
    n = props.Normal()
    vx, vy, vz = n.X() * half_length, n.Y() * half_length, n.Z() * half_length
    p_pos = BRepPrimAPI_MakePrism(face, gp_Vec(vx, vy, vz), True, True).Shape()
    p_neg = BRepPrimAPI_MakePrism(face, gp_Vec(-vx, -vy, -vz), True, True).Shape()
    fuse = BRepAlgoAPI_Fuse(p_pos, p_neg)
    fuse.Build()
    if not fuse.IsDone():
        raise RuntimeError("bidirectional prism fuse failed for column face")
    return fuse.Shape()


def gen_step():
    # 包络参考面（用户列表去重）
    envelope_specs = [
        ("o1.3", 1),
        ("o1.5", 1),
        ("o1.7", 1),
        ("o1.50", 1),
    ]
    # 与 @cad[STEP/oc4#o1.30.f1]、@cad[STEP/oc4#o1.28.f1] 对应：用各自第 1 号面做法向包络切除
    column_face_specs = (("o1.30", 1), ("o1.28", 1))

    step_path = (_REPO_ROOT / "STEP" / "oc4.step").resolve()
    scene = load_step_scene(step_path)

    merged = _merge_face_bboxes(scene, envelope_specs)
    if merged.IsVoid():
        raise RuntimeError("envelope face union bbox is void")

    diag = float(merged.CornerMin().Distance(merged.CornerMax()))
    margin = max(1.0, min(500.0, 0.002 * diag))
    fuzzy = max(10.0, 1e-6 * diag)
    env_box = _expand_box(merged, margin)

    mn = env_box.CornerMin()
    mx = env_box.CornerMax()
    env_solid = BRepPrimAPI_MakeBox(
        gp_Pnt(mn.X(), mn.Y(), mn.Z()),
        gp_Pnt(mx.X(), mx.Y(), mx.Z()),
    ).Shape()

    env_bb = Bnd_Box()
    BRepBndLib.Add_s(env_solid, env_bb)
    diag_env = float(env_bb.CornerMin().Distance(env_bb.CornerMax()))
    prism_half = max(3.0 * diag_env, 50000.0)

    result = env_solid
    for occ_id, fo in column_face_specs:
        col_face = _face_on_occurrence(scene, occ_id, fo)
        cutter = _prism_tool_from_face(col_face, prism_half)
        cut = BRepAlgoAPI_Cut(result, cutter)
        cut.SetFuzzyValue(fuzzy)
        cut.Build()
        if not cut.IsDone():
            raise RuntimeError(f"BRep cut failed for column tool {occ_id}.f{fo}")
        result = cut.Shape()

    return Shape(result)
