# SPDX-License-Identifier: LGPL-2.1-or-later
"""
在 FreeCAD 的 Python 中执行：FCStd →（``fuse_all_solids=false`` 时优先 FEM 写出 INP；``fuse_all_solids=true`` 时跳过 FEM，直接全实体 Compound + Gmsh，避免 FEM 仅剖分分析子集而缺外围非设计域）
→ 按 Pad001（或配置）划分 design_space / nondesign_space → 写出完整 CalculiX 静力 INP；可选 ``entire_mesh_design_space`` 全模型单域优化。

配置由环境变量 ``FC_FCSTD_PIPELINE_CONFIG`` 指向 UTF-8 JSON（建议扩展名 ``.fcpipeline``），字段：

- ``fcstd_path``：输入 .FCStd
- ``out_inp``：输出主 INP（如 Analysis-beso.inp）
- ``work_dir``：中间文件目录（STEP、网格 INP 等）
- ``repo_root``：仓库根（用于子进程调用 run_freecad_iges_to_inp.py）
- ``mesh_preset``：可选，默认 ``xlarge``
- ``design_solid_name``：可选，默认 ``Pad001``（中间三角结构）
- ``design_partition_tolerance_mm``：可选。划分设计/非设计域时 ``Shape.isInside`` 容差（mm）；**不设时**用 ``max(对角线·1e-8, 1e-4)``。旧版曾用 ``max(·, 1.0)``（至少 1 mm），会把柱体等误判进设计域，导致 INP 里看似没有非设计部分。
- ``nondesign_solid_names``：可选字符串数组。填写柱/脚等实体名（如 ``Pad``）后，划分规则为：重心在 ``design_solid_name`` 内且**不在**任一非设计实体内 → ``design_space``；在任一非设计实体内（或与设计域重叠时）→ ``nondesign_space``，避免三角域被 ``Pad`` 包进全非设计或柱体被宽松 ``Pad001`` 判进设计域。
- ``entire_mesh_design_space``：可选，默认 ``false``。为 ``true`` 时**不**按实体划分：全部体单元写入 ``design_space``，不写 ``nondesign_space``（单域 BESO；``beso.py`` 按单 ``design_space`` 生成 ``beso_conf``）。此时 ``design_solid_name`` / ``nondesign_solid_names`` 不参与划分。
- ``fuse_solid_names``：可选，默认 ``[\"Pad\",\"Pad001\"]``；仅当 **未** 启用 ``fuse_all_solids`` 时用于回退剖分。
- ``fuse_all_solids``：可选，默认 ``false``。为 ``true`` 时 **不再使用 FEM 导出**；优先导出文档中 **Part::Compound 装配体**（如名为 ``Compound`` 的对象，已含柱体与 PartDesign 体），避免把 ``Body``、``Pad`` 与仅含面的 ``Part::Feature`` 再拼成 OCCT Compound 导致剖分丢件；若无装配体再回退为收集闭合实体。
- ``fuse_exclude_names``：可选，在 ``fuse_all_solids`` 下要跳过的对象名列表（如辅助体）。
- ``fuse_all_compound_volume_ratio``：可选，默认 ``0.97``。优先导出装配 ``Part::Compound`` 时，若其各 ``Solid`` 体积和低于文档内全部可剖分体体积和的该比例，判定装配未含柱体等，**回退为合并全部可剖分体** 再出 STEP。
- ``E_mpa``, ``nu``, ``density_t_per_mm3``：材料（与 example_3 量级一致）
- ``cload_fx`` / ``cload_fy`` / ``cload_fz``：可选，在自动选取的 **顶区载荷节点** 上分别施加 **dof 1/2/3**（全局 X/Y/Z）的节点力（N）。默认仅 ``cload_fx=2.81e5``，``cload_fy``/``cload_fz`` 为 0。**纵向（Z）** 时设 ``cload_fx=0``、``cload_fz`` 为非零（向下可用负值）。若三者绝对值均近 0，则退回 ``cload_fx=2.81e5``。
- ``fix_z_band_mm``：可选，底部固定带厚度（沿 z），默认 800
- ``connection_cload_fx`` / ``connection_cload_fy`` / ``connection_cload_fz``：可选。在 **设计域与非设计域交界**、且靠近 **设计域底侧** 的节点上额外施加集中力（N），用于在底边与柱体三向连接处保留传力路径，减轻 BESO 把连接区完全挖空。三者均近 0 时不启用。
- ``connection_cload_z_band_mm``：可选，相对设计域最低 z 的竖向厚度（mm），用于筛选「底部交界」节点，默认 200。
- ``connection_cload_count``：可选，交界节点上施加点数，默认 3；在候选集中按 **XY 尽量分散** 选取。
- ``connection_fix_count``：可选，默认 0。为正整数时，在 **设计域/非设计域交界** 且靠近 **设计域底面** 的节点中选取若干点，写入 ``*Nset, Nset=bottom_tri_connection_fix`` 并对 **1～3 自由度全固定**，用于底边三向与柱体连接处不被 BESO 挖断传力路径（与顶区主载荷配合使用）。与 ``connection_cload_*`` 作用于同一批节点时，**固定点不再写 Cload**。
- ``connection_fix_z_band_mm``：可选，筛选「底部交界」固定点的竖向厚度（mm），默认 250。
- ``connection_protect_z_mm``：可选，默认 0。为正时，将 **与 nondesign 共节点** 且 **四面体任一顶点 z** 不高于「设计域最低顶点 z + 该值（mm）」的 **design_space** 单元改划入 **nondesign_space**（比用重心 z 更易包住底角与柱体相接的薄层），使连接带不参与 BESO 挖空。
- ``fem_bc_reference_inp``：可选。指向 **同一 FCStd** 经 FreeCAD FEM ``write_inp_file`` 得到的完整 CalculiX INP（含 *Step 内 *BOUNDARY / *CLOAD）。启用后从该文件 **还原** 固定与力，按坐标 **最近邻** 映射到当前体网格（如 Gmsh）；**不再**使用 ``fix_z_band_mm``、``cload_*``、``connection_*`` 的启发式约束与载荷。
- ``fem_bc_remap_max_dist_mm``：可选，默认 ``300``。参考节点与目标网格最近节点距离超过该值（mm）时跳过对应约束/载荷行（粗网格与细 FEM 表面节点可能相距数十至数百 mm）。
- ``fem_bc_bottom_fix_fallback``：可选，默认 ``true``。在启用 ``fem_bc_reference_inp`` 时预计算底带节点；若 FEM 映射后 **无任何固定约束**，则追加与启发式流水线相同的 ``bottom_fix``。
- ``fem_bc_bottom_fix_only_if_no_fem_boundary``：可选，默认 ``true``。为 ``false`` 时在 FEM 固定之外 **再** 加 ``bottom_fix``（易过约束，一般勿改）。
- ``fem_bc_cload_fallback_if_empty``：可选，默认 ``true``。若映射后 **无任何 Cload**，则按 ``cload_fx``/``cload_fy``/``cload_fz`` 在顶区节点施加单点力（与未启用 FEM 参考时一致）。

勿将 JSON 路径放在 FreeCADCmd 的 argv 中（会误打开）。

路径解析：``fcstd_path`` / ``out_inp`` / ``work_dir`` / ``repo_root`` 若为相对路径，均相对于 **配置文件所在目录** 解析（便于把 ``.fcpipeline`` 放在 ``examples/beso2/`` 下与 ``BESO3.FCStd`` 同目录）。

FreeCAD FEM 写出 INP 的入口：``Mod/Fem/femtools/ccxtools.py`` 中 ``FemToolsCcx.write_inp_file`` → ``femsolver.calculix.writer.FemInputWriterCcx``；本脚本在 ``fuse_all_solids=true`` 时优先全装配体 + Gmsh，以保证设计域与非设计域共网格。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_CONFIG_EXT = ".fcpipeline"


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _config_path() -> Path:
    env = (os.environ.get("FC_FCSTD_PIPELINE_CONFIG") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        _die(f"FC_FCSTD_PIPELINE_CONFIG 无效: {env}", 2)
    for a in sys.argv[1:]:
        p = Path(a)
        if p.is_file() and p.suffix.lower() == _CONFIG_EXT:
            return p.resolve()
    _die(
        f"用法: FreeCADCmd.exe freecad_fcstd_pipeline_runner.py <config{_CONFIG_EXT}>\n"
        f"或设置环境变量 FC_FCSTD_PIPELINE_CONFIG。",
        2,
    )


def _resolve_cfg_path(cfg_dir: Path, p: object) -> Path:
    """相对路径相对于配置文件所在目录。"""
    pp = Path(str(p))
    return pp.resolve() if pp.is_absolute() else (cfg_dir / pp).resolve()


def _try_fem_export(fcstd: Path, work_dir: Path, base: str) -> Path | None:
    import FreeCAD  # noqa: PLC0415
    from femtools import ccxtools  # noqa: PLC0415

    doc = FreeCAD.openDocument(str(fcstd))
    try:
        anas = [o for o in doc.Objects if o.TypeId == "Fem::FemAnalysis"]
        if not anas:
            return None
        tools = ccxtools.FemToolsCcx(analysis=anas[0])
        tools.update_objects()
        tools.setup_working_dir(str(work_dir), create=True)
        tools.set_base_name(base)
        msg = tools.check_prerequisites()
        if msg:
            FreeCAD.Console.PrintWarning("FEM export skipped: " + msg.replace("\n", " | ") + "\n")
            return None
        tools.write_inp_file()
        p = Path(tools.inp_file_name)
        return p if p.is_file() else None
    except Exception as e:
        print(f"[WARN] FEM export failed: {e}", file=sys.stderr)
        return None
    finally:
        FreeCAD.closeDocument(doc.Name)


def _geometry_shape(obj) -> object | None:
    """文档对象上可作为 Part.Shape 使用的几何；排除无拓扑或类型异常（如部分版本下非 TopoShape 的 Shape）。"""
    import Part  # noqa: PLC0415

    sh = getattr(obj, "Shape", None)
    if sh is None or not isinstance(sh, Part.Shape):
        return None
    try:
        if sh.isNull():
            return None
    except Exception:
        return None
    return sh


def _solid_volume_sum_mm3(sh: object) -> float:
    """Shape 体积（mm³）：Compound 取各 Solid 之和，避免 Shell 干扰。"""
    import Part  # noqa: PLC0415

    if not isinstance(sh, Part.Shape) or sh.isNull():
        return 0.0
    try:
        if sh.ShapeType == "Solid":
            return max(0.0, float(sh.Volume))
        tot = 0.0
        for s in sh.Solids:
            tot += max(0.0, float(s.Volume))
        if tot > 1e-18:
            return tot
        return max(0.0, float(sh.Volume))
    except Exception:
        return 0.0


def _shape_has_positive_solid_volume(sh: object) -> bool:
    import Part  # noqa: PLC0415

    if not isinstance(sh, Part.Shape) or sh.isNull():
        return False
    try:
        for s in sh.Solids:
            if float(s.Volume) > 1e-9:
                return True
    except Exception:
        return False
    return False


def _meshable_shape_for_step(obj) -> object | None:
    """仅闭合体网格：Solid 或含至少一个正体积 Solid 的 Compound；排除 Face/Shell/Wire 等。"""
    import Part  # noqa: PLC0415

    sh = _geometry_shape(obj)
    if sh is None:
        return None
    if sh.ShapeType == "Solid":
        try:
            return sh if float(sh.Volume) > 1e-9 else None
        except Exception:
            return None
    if sh.ShapeType == "Compound":
        solids = [s for s in sh.Solids if float(s.Volume) > 1e-9]
        if not solids:
            return None
        if len(solids) == 1:
            return solids[0]
        return Part.makeCompound(solids)
    return None


def _skip_for_mesh_export(obj, has_body: bool) -> bool:
    """不参与 STEP 导出的文档对象（FEM、草图、PartDesign 过程特征等）。"""
    if obj is None:
        return True
    tid = getattr(obj, "TypeId", "") or ""
    if tid.startswith("Fem::"):
        return True
    if tid.startswith("Sketcher::"):
        return True
    if tid.startswith("App::Material"):
        return True
    if tid in ("App::Origin", "App::Line", "App::Plane", "App::Point"):
        return True
    if tid == "PartDesign::FeatureBase":
        return True
    if has_body and tid in ("PartDesign::Pad", "PartDesign::Pocket", "PartDesign::Revolution", "PartDesign::Groove"):
        return True
    return False


def _primary_assembly_compound(doc) -> tuple[object | None, str | None]:
    """若存在用户装配用的 Part::Compound（常见名 Compound），返回其 Shape（已含柱体等），避免与 Body 重复合并。"""
    import Part  # noqa: PLC0415

    preferred = ("Compound", "Fusion", "Assembly")
    for nm in preferred:
        o = doc.getObject(nm)
        if o is None or getattr(o, "TypeId", "") != "Part::Compound":
            continue
        sh = _geometry_shape(o)
        if sh is None or not _shape_has_positive_solid_volume(sh):
            continue
        return sh, nm
    best_sh: object | None = None
    best_nm: str | None = None
    best_vol = -1.0
    for obj in doc.Objects:
        if obj is None or getattr(obj, "TypeId", "") != "Part::Compound":
            continue
        sh = _geometry_shape(obj)
        if sh is None or not _shape_has_positive_solid_volume(sh):
            continue
        try:
            vol = sum(float(s.Volume) for s in sh.Solids if float(s.Volume) > 1e-12)
        except Exception:
            continue
        if vol > best_vol:
            best_vol, best_sh, best_nm = vol, sh, obj.Name
    if best_sh is not None and best_vol > 1e-6:
        return best_sh, best_nm
    return None, None


def _collect_meshable_solids_for_step(doc) -> list[tuple[str, object]]:
    """无现成装配 Compound 时：收集 PartDesign::Body 与独立 Part 实体等可剖分体，排除过程特征与 FEM/草图。"""
    has_body = any(getattr(o, "TypeId", "") == "PartDesign::Body" for o in doc.Objects if o is not None)
    out: list[tuple[str, object]] = []
    for obj in doc.Objects:
        if _skip_for_mesh_export(obj, has_body):
            continue
        tid = getattr(obj, "TypeId", "")
        if tid.startswith("App::") and tid not in ("App::Part",):
            continue
        ms = _meshable_shape_for_step(obj)
        if ms is None:
            continue
        out.append((obj.Name, ms))
    out.sort(key=lambda t: t[0])
    return out


def _collect_volume_shapes_from_doc(doc) -> list[tuple[str, object]]:
    """兼容旧名：返回 (名, Shape)，供非 fuse_all 路径或调试；逻辑与可剖分体一致。"""
    return _collect_meshable_solids_for_step(doc)


def _export_fused_step(fcstd: Path, solid_names: list[str], out_step: Path) -> None:
    import FreeCAD  # noqa: PLC0415

    doc = FreeCAD.openDocument(str(fcstd))
    try:
        shapes = []
        for nm in solid_names:
            o = doc.getObject(nm)
            sh = _geometry_shape(o) if o is not None else None
            if sh is None:
                _die(f"FCStd 中未找到实体: {nm}", 3)
            shapes.append(sh)
        fused = shapes[0].fuse(shapes[1]) if len(shapes) > 1 else shapes[0]
        out_step.parent.mkdir(parents=True, exist_ok=True)
        fused.exportStep(str(out_step))
    finally:
        FreeCAD.closeDocument(doc.Name)


def _export_fused_all_solids(
    fcstd: Path,
    out_step: Path,
    exclude_names: frozenset[str] | None = None,
    *,
    compound_vs_parts_ratio: float = 0.97,
) -> None:
    """导出用于 Gmsh 的 STEP：优先文档中已装配的 Part::Compound（含柱体等）。

    若装配各 Solid 体积和明显小于文档内全部可剖分体体积之和，判定装配未含柱脚等，
    则合并全部可剖分体再导出，避免网格与 ``Analysis-beso.inp`` 只剩设计域。
    """
    import FreeCAD  # noqa: PLC0415
    import Part  # noqa: PLC0415

    ex = exclude_names or frozenset()
    ratio = float(compound_vs_parts_ratio)
    if not (0.5 < ratio <= 1.0):
        ratio = 0.97
    doc = FreeCAD.openDocument(str(fcstd))
    try:
        pairs = [(n, s) for n, s in _collect_meshable_solids_for_step(doc) if n not in ex]
        if not pairs:
            _die("fuse_all_solids：文档中未找到任何可剖分的闭合实体。", 3)
        v_parts = sum(_solid_volume_sum_mm3(s) for _nm, s in pairs)

        assy_sh, assy_nm = _primary_assembly_compound(doc)
        if assy_nm is not None and assy_nm in ex:
            assy_sh, assy_nm = None, None
        use_assembly = False
        if assy_sh is not None and assy_nm is not None and assy_nm not in ex:
            v_assy = _solid_volume_sum_mm3(assy_sh)
            if v_parts <= 1e-9:
                use_assembly = True
            elif v_assy >= v_parts * ratio:
                use_assembly = True
            else:
                print(
                    f"[WARN] fuse_all_solids：装配「{assy_nm}」Solid 体积和≈{v_assy:.6g} mm³，"
                    f"低于可剖分体体积和≈{v_parts:.6g} 的 {ratio:.0%}，"
                    "判定装配未含全部零件，改为合并全部可剖分体导出 STEP。",
                    file=sys.stderr,
                )

        if use_assembly and assy_sh is not None and assy_nm is not None and assy_nm not in ex:
            try:
                n_assy_sol = len(assy_sh.Solids) if hasattr(assy_sh, "Solids") else 0
            except Exception:
                n_assy_sol = 0
            # 单 Solid 装配且另有 PartDesign::Body 时，Compound 常未含侧立柱；改用 Body 最终形状
            body_obj = doc.getObject("Body")
            body_sh = _geometry_shape(body_obj) if body_obj is not None else None
            if (
                n_assy_sol <= 1
                and body_sh is not None
                and _shape_has_positive_solid_volume(body_sh)
                and float(_solid_volume_sum_mm3(body_sh)) > float(_solid_volume_sum_mm3(assy_sh)) * 1.01
            ):
                print(
                    "[INFO] fuse_all_solids: 装配「"
                    + assy_nm
                    + f"」仅 {n_assy_sol} 个 Solid，改用 PartDesign::Body 导出 STEP（含侧立柱等完整几何）。",
                    file=sys.stderr,
                )
                out_step.parent.mkdir(parents=True, exist_ok=True)
                body_sh.exportStep(str(out_step))
                return
            out_step.parent.mkdir(parents=True, exist_ok=True)
            assy_sh.exportStep(str(out_step))
            try:
                n_sol = len(assy_sh.Solids)
                n_sh = len(assy_sh.Shells)
                v_shape = float(assy_sh.Volume)
            except Exception:
                n_sol, n_sh, v_shape = -1, -1, float("nan")
            print(
                "[INFO] fuse_all_solids: 使用装配 Part::Compound「"
                + assy_nm
                + f"」导出 STEP（Shape.Volume≈{v_shape:.6g}, Solids={n_sol}, Shells={n_sh}），"
                "避免将 Body、Pad 与仅含面的 Part::Feature 再拼成 OCCT Compound 导致剖分丢件",
            )
            return

        shapes = [sh for _nm, sh in pairs]
        if len(shapes) == 1:
            compound = shapes[0]
        else:
            compound = Part.Compound(shapes)
        out_step.parent.mkdir(parents=True, exist_ok=True)
        compound.exportStep(str(out_step))
        print(
            "[INFO] fuse_all_solids: 合并",
            len(pairs),
            "个可剖分对象导出 STEP:",
            ", ".join(n for n, _ in pairs),
        )
    finally:
        FreeCAD.closeDocument(doc.Name)


def _is_fem_gmsh_mesh(obj) -> bool:
    tid = getattr(obj, "TypeId", "") or ""
    name = getattr(obj, "Name", "") or ""
    return tid.startswith("Fem::") and ("MeshGmsh" in name or "FemMesh" in tid)


def _find_fem_gmsh_mesh(doc, ref: str):
    """按对象 Name 或 FreeCAD Label（如 FEMMeshGmsh004）查找 Gmsh FEM 网格。"""
    ref = str(ref).strip()
    if not ref:
        return None
    o = doc.getObject(ref)
    if o is not None and _is_fem_gmsh_mesh(o):
        return o
    for obj in doc.Objects:
        if obj is None:
            continue
        if getattr(obj, "Label", "") == ref and _is_fem_gmsh_mesh(obj):
            return obj
    return None


def _copy_gmsh_mesh_settings(src, dst) -> None:
    """将参考 FemMeshGmsh 的尺寸/曲率等设置复制到临时网格对象。"""
    for prop in (
        "CharacteristicLengthMax",
        "CharacteristicLengthMin",
        "MeshSizeFromCurvature",
        "ElementOrder",
        "SecondOrderLinear",
        "Algorithm",
        "Algorithm3D",
        "OptimizeNetgen",
        "RecombinationAlgorithm",
        "SubdivisionAlgorithm",
        "GeometryTolerance",
    ):
        if hasattr(src, prop) and hasattr(dst, prop):
            try:
                setattr(dst, prop, getattr(src, prop))
            except Exception:
                pass


def _parse_length_mm(value: object) -> float:
    s = str(value).strip()
    if not s:
        return 0.0
    num = ""
    for ch in s:
        if ch.isdigit() or ch in ".-+eE":
            num += ch
        elif num:
            break
    return float(num) if num else float(s)


def _set_mesh_characteristic_lengths(
    mesh,
    *,
    char_max_mm: float | None = None,
    char_min_mm: float | None = None,
    mesh_scale: float | None = None,
) -> None:
    """覆盖或缩放 Gmsh CharacteristicLength（数值越小网格越细）。"""
    max_v = char_max_mm
    min_v = char_min_mm
    scale = float(mesh_scale) if mesh_scale is not None else None
    if scale is not None and scale > 0 and abs(scale - 1.0) > 1e-9:
        if max_v is None and hasattr(mesh, "CharacteristicLengthMax"):
            max_v = _parse_length_mm(mesh.CharacteristicLengthMax) * scale
        if min_v is None and hasattr(mesh, "CharacteristicLengthMin"):
            min_v = _parse_length_mm(mesh.CharacteristicLengthMin) * scale
    if max_v is not None and float(max_v) > 0 and hasattr(mesh, "CharacteristicLengthMax"):
        mesh.CharacteristicLengthMax = f"{float(max_v):g} mm"
    if min_v is not None and float(min_v) > 0 and hasattr(mesh, "CharacteristicLengthMin"):
        mesh.CharacteristicLengthMin = f"{float(min_v):g} mm"


def _gmsh_volume_mesh_from_fcstd_fem(
    fcstd: Path,
    mesh_ref: str,
    out_inp: Path,
    *,
    element_dimension: str = "3D",
    char_max_mm: float | None = None,
    char_min_mm: float | None = None,
    mesh_scale: float | None = None,
) -> None:
    """按 FCStd 内已有 FemMeshGmsh（如 Label=FEMMeshGmsh004）的几何与 Gmsh 参数生成体网格 INP。"""
    import FreeCAD  # noqa: PLC0415
    import ObjectsFem  # noqa: PLC0415
    from femmesh.gmshtools import GmshTools  # noqa: PLC0415

    doc = FreeCAD.openDocument(str(fcstd))
    tmp_name = "_PipelineGmshFromFcstd"
    try:
        ref_mesh = _find_fem_gmsh_mesh(doc, mesh_ref)
        if ref_mesh is None:
            _die(f"未找到 FEM Gmsh 网格（Name 或 Label）: {mesh_ref}", 3)
        geom = ref_mesh.Shape
        if geom is None:
            _die(f"FEM 网格「{ref_mesh.Name}」未绑定 Shape", 3)
        geom_name = getattr(geom, "Name", str(geom))
        print(
            f"[INFO] mesh_from_fcstd_fem_mesh: 参考「{ref_mesh.Name}」(Label={ref_mesh.Label})，"
            f"几何={geom_name}，参考单元维={getattr(ref_mesh, 'ElementDimension', '?')}，"
            f"导出体网格维={element_dimension}",
            file=sys.stderr,
        )
        existing = doc.getObject(tmp_name)
        if existing is not None:
            doc.removeObject(tmp_name)
        tmp_mesh = ObjectsFem.makeMeshGmsh(doc, tmp_name)
        tmp_mesh.Shape = geom
        _copy_gmsh_mesh_settings(ref_mesh, tmp_mesh)
        tmp_mesh.ElementDimension = str(element_dimension)
        _set_mesh_characteristic_lengths(
            tmp_mesh,
            char_max_mm=char_max_mm,
            char_min_mm=char_min_mm,
            mesh_scale=mesh_scale,
        )
        doc.recompute()
        print(
            f"[INFO] Gmsh 参数: Max={tmp_mesh.CharacteristicLengthMax!s} "
            f"Min={tmp_mesh.CharacteristicLengthMin!s} "
            f"Curvature={getattr(tmp_mesh, 'MeshSizeFromCurvature', 'n/a')}",
            file=sys.stderr,
        )
        tools = GmshTools(tmp_mesh)
        if not tools.run(True):
            _die("按 FCStd FEM 参考网格参数运行 Gmsh 失败", 4)
        fm = tmp_mesh.FemMesh
        if fm is None or fm.NodeCount < 1:
            _die("Gmsh 体网格为空", 4)
        tetra = int(getattr(fm, "TetraCount", 0) or 0)
        print(
            f"[INFO] 体网格: nodes={fm.NodeCount} tetra={tetra}",
            file=sys.stderr,
        )
        out_inp.parent.mkdir(parents=True, exist_ok=True)
        fm.write(str(out_inp))
    finally:
        FreeCAD.closeDocument(doc.Name)


def _run_gmsh_mesh(
    repo_root: Path,
    step_path: Path,
    mesh_inp: Path,
    preset: str,
    *,
    char_max_mm: float | None = None,
    char_min_mm: float | None = None,
) -> None:
    mesh_inp.parent.mkdir(parents=True, exist_ok=True)
    runner = repo_root / "scripts" / "run_freecad_iges_to_inp.py"
    py = Path(sys.executable)
    cmd = [
        str(py),
        str(runner),
        "--cad",
        str(step_path),
        "--out",
        str(mesh_inp),
        "--preset",
        preset,
        "--no-check-beso",
    ]
    if char_max_mm is not None and float(char_max_mm) > 0:
        cmd.extend(["--char-max", str(float(char_max_mm))])
    if char_min_mm is not None and float(char_min_mm) > 0:
        cmd.extend(["--char-min", str(float(char_min_mm))])
    print("[INFO] mesh cmd:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(repo_root))


def _looks_like_node_coord_line(parts: list[str]) -> bool:
    if len(parts) < 4:
        return False
    try:
        int(parts[0])
        float(parts[1])
        float(parts[2])
        float(parts[3])
    except ValueError:
        return False
    return True


def _parse_mesh_inp_line_scan(mesh_inp: Path) -> tuple[dict[int, tuple[float, float, float]], dict[int, tuple[int, int, int, int]]]:
    """手写扫描：兼容 *NODE 与首个 *ELEMENT 之间插入 *Nset 等卡片；允许多段 *ELEMENT TYPE=C3D4。"""
    nodes: dict[int, tuple[float, float, float]] = {}
    elements: dict[int, tuple[int, int, int, int]] = {}
    in_node_region = False
    in_c3d4_block = False
    with mesh_inp.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("**"):
                continue
            u = line.upper()
            if u.startswith("*NODE"):
                in_node_region = True
                in_c3d4_block = False
                continue
            if u.startswith("*ELEMENT"):
                if "C3D4" in u:
                    in_node_region = False
                    in_c3d4_block = True
                else:
                    in_c3d4_block = False
                    if in_node_region:
                        in_node_region = False
                continue
            if line.startswith("*"):
                in_c3d4_block = False
                continue
            if in_node_region:
                parts = [p.strip() for p in line.split(",")]
                if _looks_like_node_coord_line(parts):
                    nid = int(parts[0])
                    nodes[nid] = (float(parts[1]), float(parts[2]), float(parts[3]))
                continue
            if in_c3d4_block:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 5 and all(p.lstrip("-").isdigit() for p in parts):
                    eid = int(parts[0])
                    elements[eid] = (int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
    if not nodes or not elements:
        _die(f"解析网格失败(line scan): nodes={len(nodes)} elements={len(elements)}", 4)
    return nodes, elements


def _parse_mesh_inp(mesh_inp: Path) -> tuple[dict[int, tuple[float, float, float]], dict[int, tuple[int, int, int, int]]]:
    """体网格：收集全部线性四面体。优先 meshio（多段 *ELEMENT、二阶四面体角点等），失败则回退行扫描。"""
    try:
        import meshio  # noqa: PLC0415
    except ImportError:
        meshio = None  # type: ignore[assignment]
    if meshio is not None:
        try:
            mesh = meshio.read(mesh_inp, file_format="abaqus")
        except Exception:
            mesh = None
        else:
            nodes: dict[int, tuple[float, float, float]] = {}
            for i, p in enumerate(mesh.points):
                nodes[i + 1] = (float(p[0]), float(p[1]), float(p[2]))
            elements: dict[int, tuple[int, int, int, int]] = {}
            eid = 1
            other_volume: list[str] = []
            for cb in mesh.cells:
                if cb.type == "tetra":
                    for row in cb.data:
                        n1, n2, n3, n4 = (int(x) + 1 for x in row)
                        elements[eid] = (n1, n2, n3, n4)
                        eid += 1
                elif cb.type == "tetra10":
                    for row in cb.data:
                        n1, n2, n3, n4 = (int(x) + 1 for x in row[:4])
                        elements[eid] = (n1, n2, n3, n4)
                        eid += 1
                elif cb.type in ("hexahedron", "wedge", "pyramid"):
                    other_volume.append(cb.type)
            if other_volume:
                print(
                    "[WARN] meshio 发现非四面体体单元（已忽略）:",
                    ", ".join(sorted(set(other_volume))),
                    file=sys.stderr,
                )
            if nodes and elements:
                print(
                    f"[INFO] meshio 解析网格: nodes={len(nodes)} elements={len(elements)}",
                    file=sys.stderr,
                )
                return nodes, elements
    return _parse_mesh_inp_line_scan(mesh_inp)


def _design_object_shape_global(doc, design_name: str) -> object | None:
    """设计域实体在**全局坐标**下的 Shape；嵌套在 App::Part 内时 ``obj.Shape`` 可能为局部，需与 Gmsh 网格对齐。"""
    import Part  # noqa: PLC0415

    o = doc.getObject(design_name)
    if o is None:
        return None
    try:
        sh = Part.getShape(o, "", False, False, True)
        if sh is not None and not sh.isNull():
            return sh
    except TypeError:
        try:
            sh = Part.getShape(o, "", False, True)
            if sh is not None and not sh.isNull():
                return sh
        except Exception:
            pass
    except Exception:
        pass
    return _geometry_shape(o)


def _partition_tolerance_mm(shape: object, override_mm: float | None) -> float:
    """``isInside`` 容差（mm）。override 为正时优先使用。"""
    import Part  # noqa: PLC0415

    if override_mm is not None and float(override_mm) > 0.0:
        return float(override_mm)
    if not isinstance(shape, Part.Shape) or shape.isNull():
        return 1.0e-4
    try:
        diag = float(shape.BoundBox.DiagonalLength)
    except Exception:
        diag = 1.0
    # 旧逻辑 max(diag*1e-6, 1.0) 至少 1 mm，会把紧邻 Pad001 的柱体单元判进设计域。
    return max(diag * 1.0e-8, 1.0e-4)


def _split_design(
    fcstd: Path,
    design_name: str,
    nodes: dict[int, tuple[float, float, float]],
    elements: dict[int, tuple[int, int, int, int]],
    *,
    nondesign_solid_names: list[str] | None = None,
    partition_tolerance_mm: float | None = None,
    entire_mesh_design_space: bool = False,
) -> tuple[list[int], list[int]]:
    if entire_mesh_design_space:
        design = sorted(elements.keys())
        print(
            "[INFO] entire_mesh_design_space=true：全部 C3D4 划入 design_space（单域 BESO）。",
            file=sys.stderr,
        )
        return design, []

    import FreeCAD  # noqa: PLC0415

    doc = FreeCAD.openDocument(str(fcstd))
    try:
        sh = _design_object_shape_global(doc, design_name)
        if sh is None:
            _die(f"设计域对象不存在或无形状: {design_name}", 5)
        nd_shapes: list[tuple[str, object]] = []
        for raw in nondesign_solid_names or []:
            nm = str(raw).strip()
            if not nm or nm == design_name:
                continue
            s = _design_object_shape_global(doc, nm)
            if s is None:
                print(f"[WARN] nondesign_solid_names 中对象无形状，已跳过: {nm}", file=sys.stderr)
                continue
            nd_shapes.append((nm, s))
        design: list[int] = []
        nondesign: list[int] = []
        tol_d = _partition_tolerance_mm(sh, partition_tolerance_mm)
        for eid, (n1, n2, n3, n4) in elements.items():
            pts = [nodes[n1], nodes[n2], nodes[n3], nodes[n4]]
            cx = sum(p[0] for p in pts) / 4.0
            cy = sum(p[1] for p in pts) / 4.0
            cz = sum(p[2] for p in pts) / 4.0
            v = FreeCAD.Vector(cx, cy, cz)
            in_d = sh.isInside(v, tol_d, True)
            in_any_nd = False
            for _nm, s_nd in nd_shapes:
                t_nd = _partition_tolerance_mm(s_nd, partition_tolerance_mm)
                if s_nd.isInside(v, t_nd, True):
                    in_any_nd = True
                    break
            # 三角域：在 Pad001 内且不在柱/脚等 ND 体内；重叠域优先 ND，避免柱单元被宽松判进设计域
            if in_d and not in_any_nd:
                design.append(eid)
            elif in_any_nd:
                nondesign.append(eid)
            else:
                nondesign.append(eid)
        if not design:
            _die("design_space 为空；检查 design_solid_name、nondesign_solid_names 与网格是否对齐。", 6)
        if not nondesign:
            _die("nondesign_space 为空（若需全模型可优化，请在配置中设 entire_mesh_design_space=true）。", 7)
        return design, nondesign
    finally:
        FreeCAD.closeDocument(doc.Name)


def _xy_dist2(
    nodes: dict[int, tuple[float, float, float]], na: int, nb: int
) -> float:
    pa, pb = nodes[na], nodes[nb]
    dx, dy = pa[0] - pb[0], pa[1] - pb[1]
    return dx * dx + dy * dy


def _pick_connection_bottom_nodes(
    design: list[int],
    nondesign: list[int],
    elements: dict[int, tuple[int, int, int, int]],
    nodes: dict[int, tuple[float, float, float]],
    *,
    z_band_mm: float,
    count: int,
) -> list[int]:
    """设计域与非设计域共用的网格节点中，靠近设计域底面的若干点（底边—柱体连接处：附加 Cload 或 *Boundary 固定）。"""
    design_nodes: set[int] = set()
    for eid in design:
        design_nodes.update(elements[eid])
    nondesign_nodes: set[int] = set()
    for eid in nondesign:
        nondesign_nodes.update(elements[eid])
    iface = sorted(design_nodes & nondesign_nodes)
    if not iface:
        return []
    z_min_d = min(nodes[n][2] for n in design_nodes)
    band = max(float(z_band_mm), 1e-6)
    cands = [n for n in iface if nodes[n][2] <= z_min_d + band]
    if len(cands) < count:
        cands = sorted(iface, key=lambda nid: nodes[nid][2])[: max(count * 4, count)]
    if not cands:
        return []
    cands_unique = list(dict.fromkeys(cands))
    cands_unique.sort(key=lambda nid: (nodes[nid][2], nodes[nid][0] ** 2 + nodes[nid][1] ** 2))
    k = min(max(int(count), 1), len(cands_unique))
    if k == 1:
        return [cands_unique[0]]
    chosen: list[int] = [cands_unique[0]]
    pool = cands_unique[1:]
    while len(chosen) < k and pool:
        best = max(pool, key=lambda n: min(_xy_dist2(nodes, n, c) for c in chosen))
        chosen.append(best)
        pool = [n for n in pool if n != best]
    return chosen


def _merge_bottom_interface_design_into_nondesign(
    design: list[int],
    nondesign: list[int],
    elements: dict[int, tuple[int, int, int, int]],
    nodes: dict[int, tuple[float, float, float]],
    *,
    protect_z_mm: float,
) -> tuple[list[int], list[int], int]:
    """
    把「贴近设计域底面」且与 nondesign 网格相邻的设计域四面体并入 nondesign，
    供 BESO 跳过（domain_optimized=False 等效于不在设计域内被删除）。
    """
    pz = float(protect_z_mm)
    if pz <= 0.0 or not design or not nondesign:
        return design, nondesign, 0

    def _min_vertex_z(eid: int) -> float:
        a, b, c, d = elements[eid]
        return min(nodes[a][2], nodes[b][2], nodes[c][2], nodes[d][2])

    nondesign_nodes: set[int] = set()
    for eid in nondesign:
        nondesign_nodes.update(elements[eid])

    design_nodes_all: set[int] = set()
    for eid in design:
        design_nodes_all.update(elements[eid])
    z_floor = min(nodes[n][2] for n in design_nodes_all)
    z_cut = z_floor + pz
    new_design: list[int] = []
    promoted: list[int] = []
    for eid in design:
        a, b, c, d = elements[eid]
        if (
            a in nondesign_nodes
            or b in nondesign_nodes
            or c in nondesign_nodes
            or d in nondesign_nodes
        ) and _min_vertex_z(eid) <= z_cut:
            promoted.append(eid)
        else:
            new_design.append(eid)
    if not new_design:
        print(
            "[WARN] connection_protect_z_mm 过大，会清空 design_space，已跳过保护合并。",
            file=sys.stderr,
        )
        return design, nondesign, 0
    new_nondesign = list(nondesign) + promoted
    return new_design, new_nondesign, len(promoted)


def _assemble_out_inp(
    out_inp: Path,
    design: list[int],
    nondesign: list[int],
    nodes: dict[int, tuple[float, float, float]],
    elements: dict[int, tuple[int, int, int, int]],
    E_mpa: float,
    nu: float,
    density: float,
    cload_fx: float,
    cload_fy: float,
    cload_fz: float,
    fix_band: float,
    *,
    connection_cload_fx: float = 0.0,
    connection_cload_fy: float = 0.0,
    connection_cload_fz: float = 0.0,
    connection_cload_z_band_mm: float = 200.0,
    connection_cload_count: int = 3,
    connection_fix_count: int = 0,
    connection_fix_z_band_mm: float = 250.0,
    single_design_domain: bool = False,
) -> list[int]:
    from beso_inp_bc_remap import bottom_fix_nodes_for_volume_mesh, top_load_node_for_volume_mesh  # noqa: PLC0415

    bottom = bottom_fix_nodes_for_volume_mesh(nodes, elements, design, nondesign, float(fix_band))
    load_node = top_load_node_for_volume_mesh(nodes, top_band_mm=max(float(fix_band) * 2.0, 1.0))

    conn_fix_nodes: list[int] = []
    fix_n = max(0, int(connection_fix_count))
    if fix_n > 0:
        conn_fix_nodes = _pick_connection_bottom_nodes(
            design,
            nondesign,
            elements,
            nodes,
            z_band_mm=float(connection_fix_z_band_mm),
            count=fix_n,
        )
        if conn_fix_nodes:
            print(
                f"[INFO] bottom_tri_connection_fix: {len(conn_fix_nodes)} node(s) "
                f"(dof 1–3 fixed): {conn_fix_nodes}",
                file=sys.stderr,
            )
        else:
            print(
                "[WARN] connection_fix_count>0 但未找到交界节点，已跳过底边三向固定。",
                file=sys.stderr,
            )
    fixed_conn = frozenset(conn_fix_nodes)

    with out_inp.open("w", encoding="utf-8", newline="\n") as fo:
        fo.write("** Full model for BESO (FCStd pipeline)\n")
        fo.write("*Heading\n")
        fo.write("Model: examples/beso from FCStd + Gmsh volume mesh\n")
        fo.write("**\n*Node, NSET=Nall\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            fo.write(f"{nid}, {x}, {y}, {z}\n")
        fo.write("**\n** Volume elements\n")
        fo.write("*Element, TYPE=C3D4, Elset=design_space\n")
        for eid in sorted(design):
            a, b, c, d = elements[eid]
            fo.write(f"{eid}, {a}, {b}, {c}, {d}\n")
        if not single_design_domain:
            fo.write("*Element, TYPE=C3D4, Elset=nondesign_space\n")
            for eid in sorted(nondesign):
                a, b, c, d = elements[eid]
                fo.write(f"{eid}, {a}, {b}, {c}, {d}\n")
        fo.write("**\n*Nset, Nset=bottom_fix\n")
        _write_nset(fo, bottom)
        if conn_fix_nodes:
            fo.write("**\n*Nset, Nset=bottom_tri_connection_fix\n")
            _write_nset(fo, conn_fix_nodes)
        if single_design_domain:
            fo.write("**\n** Materials (MPa, t/mm^3) — 全设计域单材料\n")
            fo.write("*Material, Name=Material-design\n")
            fo.write("*Elastic\n")
            fo.write(f"{E_mpa}, {nu}\n")
            fo.write("*Density\n")
            fo.write(f"{density}\n")
            fo.write("**\n")
            fo.write("*Solid section, Elset=design_space, Material=Material-design\n")
        else:
            fo.write("**\n** Materials (MPa, t/mm^3) — 两域同名弹性常数、不同材料名，便于 PrePoMax 等区分显示\n")
            fo.write("*Material, Name=Material-design\n")
            fo.write("*Elastic\n")
            fo.write(f"{E_mpa}, {nu}\n")
            fo.write("*Density\n")
            fo.write(f"{density}\n")
            fo.write("*Material, Name=Material-nondesign\n")
            fo.write("*Elastic\n")
            fo.write(f"{E_mpa}, {nu}\n")
            fo.write("*Density\n")
            fo.write(f"{density}\n")
            fo.write("**\n")
            fo.write("*Solid section, Elset=design_space, Material=Material-design\n")
            fo.write("*Solid section, Elset=nondesign_space, Material=Material-nondesign\n")
        fo.write("**\n*Step\n*Static\n")
        fo.write("**\n*Boundary, op=NEW\n")
        fo.write("*Boundary\n")
        fo.write("bottom_fix, 1, 1, 0\n")
        fo.write("bottom_fix, 2, 2, 0\n")
        fo.write("bottom_fix, 3, 3, 0\n")
        if conn_fix_nodes:
            fo.write("bottom_tri_connection_fix, 1, 1, 0\n")
            fo.write("bottom_tri_connection_fix, 2, 2, 0\n")
            fo.write("bottom_tri_connection_fix, 3, 3, 0\n")
        fo.write("**\n*Cload, op=NEW\n")
        fo.write("*Cload\n")
        eps = 1e-9
        fx, fy, fz = float(cload_fx), float(cload_fy), float(cload_fz)
        if abs(fx) < eps and abs(fy) < eps and abs(fz) < eps:
            fx = 281000.0
        if abs(fx) >= eps:
            fo.write(f"{load_node}, 1, {fx}\n")
        if abs(fy) >= eps:
            fo.write(f"{load_node}, 2, {fy}\n")
        if abs(fz) >= eps:
            fo.write(f"{load_node}, 3, {fz}\n")
        cfx = float(connection_cload_fx)
        cfy = float(connection_cload_fy)
        cfz = float(connection_cload_fz)
        if abs(cfx) >= eps or abs(cfy) >= eps or abs(cfz) >= eps:
            n_conn = max(1, int(connection_cload_count))
            picked_conn = _pick_connection_bottom_nodes(
                design,
                nondesign,
                elements,
                nodes,
                z_band_mm=float(connection_cload_z_band_mm),
                count=n_conn,
            )
            conn_nodes = [n for n in picked_conn if n not in fixed_conn]
            if conn_nodes:
                for cn in conn_nodes:
                    if abs(cfx) >= eps:
                        fo.write(f"{cn}, 1, {cfx}\n")
                    if abs(cfy) >= eps:
                        fo.write(f"{cn}, 2, {cfy}\n")
                    if abs(cfz) >= eps:
                        fo.write(f"{cn}, 3, {cfz}\n")
                print(
                    f"[INFO] connection CLOAD on {len(conn_nodes)} interface node(s) "
                    f"(dof magnitudes fx={cfx} fy={cfy} fz={cfz}): {conn_nodes}",
                    file=sys.stderr,
                )
            elif picked_conn and fixed_conn:
                print(
                    "[WARN] connection CLOAD 与 bottom_tri_connection_fix 节点重合，已不在固定点施载。",
                    file=sys.stderr,
                )
            else:
                print(
                    "[WARN] connection CLOAD 已配置但未找到设计/非设计交界节点，已跳过。",
                    file=sys.stderr,
                )
        fo.write("**\n*Node file\n")
        fo.write("RF, U\n")
        fo.write("*El file\n")
        fo.write("S\n")
        fo.write("*End step\n")
    return list(conn_fix_nodes)


def _write_nset(f, ids: list[int]) -> None:
    """CalculiX splitline: at most 16 entries per line for *Nset data lines."""
    pos = 0
    for nid in sorted(ids):
        if pos < 8:
            f.write(f"{nid}, ")
            pos += 1
        else:
            f.write(f"{nid},\n")
            pos = 1
            f.write(f"{nid}, ")
    f.write("\n")


def main() -> int:
    import FreeCAD  # noqa: F401, PLC0415  # ensure FreeCAD path

    cfg_path = _config_path()
    cfg_dir = cfg_path.parent.resolve()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    fcstd = _resolve_cfg_path(cfg_dir, cfg["fcstd_path"])
    out_inp = _resolve_cfg_path(cfg_dir, cfg["out_inp"])
    work_dir = (
        _resolve_cfg_path(cfg_dir, cfg["work_dir"])
        if cfg.get("work_dir")
        else out_inp.parent.resolve()
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    repo_root = _resolve_cfg_path(cfg_dir, cfg.get("repo_root", cfg_dir))
    mesh_preset = str(cfg.get("mesh_preset", "xlarge"))
    design_name = str(cfg.get("design_solid_name", "Pad001"))
    fuse_all = bool(cfg.get("fuse_all_solids", False))
    fuse_exclude = frozenset(str(x) for x in (cfg.get("fuse_exclude_names") or []) if str(x).strip())
    fuse_names = list(cfg.get("fuse_solid_names", ["Pad", "Pad001"]))
    E_mpa = float(cfg.get("E_mpa", 200000.0))
    nu = float(cfg.get("nu", 0.27))
    density = float(cfg.get("density_t_per_mm3", 7.833e-9))
    cload_fx = float(cfg.get("cload_fx", 281000.0))
    cload_fy = float(cfg.get("cload_fy", 0.0))
    cload_fz = float(cfg.get("cload_fz", 0.0))
    fix_band = float(cfg.get("fix_z_band_mm", 800.0))
    conn_fx = float(cfg.get("connection_cload_fx", 0.0))
    conn_fy = float(cfg.get("connection_cload_fy", 0.0))
    conn_fz = float(cfg.get("connection_cload_fz", 0.0))
    conn_z_band = float(cfg.get("connection_cload_z_band_mm", 200.0))
    try:
        conn_n = int(cfg.get("connection_cload_count", 3))
    except (TypeError, ValueError):
        conn_n = 3
    try:
        conn_fix_n = int(cfg.get("connection_fix_count", 0))
    except (TypeError, ValueError):
        conn_fix_n = 0
    conn_fix_z = float(cfg.get("connection_fix_z_band_mm", 250.0))
    conn_protect_z = float(cfg.get("connection_protect_z_mm", 0.0))
    fem_bc_raw = cfg.get("fem_bc_reference_inp")
    fem_bc_inp: Path | None = None
    if fem_bc_raw is not None and str(fem_bc_raw).strip():
        fem_bc_inp = _resolve_cfg_path(cfg_dir, fem_bc_raw)
        if not fem_bc_inp.is_file():
            _die(f"fem_bc_reference_inp 不是有效文件: {fem_bc_inp}", 8)
    try:
        fem_bc_max_d = float(cfg.get("fem_bc_remap_max_dist_mm", 300.0))
    except (TypeError, ValueError):
        fem_bc_max_d = 300.0
    try:
        fem_bc_bottom_fb = bool(cfg.get("fem_bc_bottom_fix_fallback", True))
    except (TypeError, ValueError):
        fem_bc_bottom_fb = True
    try:
        fem_bc_bottom_only = bool(cfg.get("fem_bc_bottom_fix_only_if_no_fem_boundary", True))
    except (TypeError, ValueError):
        fem_bc_bottom_only = True
    try:
        fem_bc_cload_fb = bool(cfg.get("fem_bc_cload_fallback_if_empty", True))
    except (TypeError, ValueError):
        fem_bc_cload_fb = True
    nd_names_cfg = cfg.get("nondesign_solid_names")
    nondesign_solid_names: list[str] | None = (
        [str(x).strip() for x in nd_names_cfg if str(x).strip()] if isinstance(nd_names_cfg, list) else None
    )
    pt_raw = cfg.get("design_partition_tolerance_mm")
    partition_tol: float | None = None
    if pt_raw is not None:
        try:
            partition_tol = float(pt_raw)
        except (TypeError, ValueError):
            partition_tol = None

    try:
        entire_mesh_ds = bool(cfg.get("entire_mesh_design_space", False))
    except (TypeError, ValueError):
        entire_mesh_ds = False

    mesh_inp = work_dir / "_mesh_volume.inp"
    step_path = work_dir / "_fuse_export.step"
    mesh_from_fem_raw = cfg.get("mesh_from_fcstd_fem_mesh")
    mesh_from_fem = str(mesh_from_fem_raw).strip() if mesh_from_fem_raw else ""
    mesh_elem_dim = str(cfg.get("mesh_element_dimension", "3D")).strip() or "3D"

    mesh_path: Path | None = None
    if mesh_from_fem:
        char_max_cfg = cfg.get("mesh_char_max_mm")
        char_min_cfg = cfg.get("mesh_char_min_mm")
        char_max_mm = float(char_max_cfg) if char_max_cfg is not None else None
        char_min_mm = float(char_min_cfg) if char_min_cfg is not None else None
        mesh_scale_raw = cfg.get("mesh_char_scale")
        mesh_scale = float(mesh_scale_raw) if mesh_scale_raw is not None else None
        _gmsh_volume_mesh_from_fcstd_fem(
            fcstd,
            mesh_from_fem,
            mesh_inp,
            element_dimension=mesh_elem_dim,
            char_max_mm=char_max_mm,
            char_min_mm=char_min_mm,
            mesh_scale=mesh_scale,
        )
        mesh_path = mesh_inp
        print("[OK] FCStd FEM 参考网格 → 体网格 INP:", mesh_path)
    elif fuse_all:
        print(
            "[INFO] fuse_all_solids=true：跳过 FreeCAD FEM CalculiX 导出，"
            "使用 FCStd 内全部有体积实体的 Compound + Gmsh，以保证非设计域与整体设计域进入同一 INP。",
            file=sys.stderr,
        )
    else:
        exported = _try_fem_export(fcstd, work_dir, "fcstd_fem_export")
        if exported and exported.is_file():
            try:
                _n, _e = _parse_mesh_inp(exported)
                if len(_e) < 1:
                    raise ValueError("no C3D4 elements in FEM export")
                mesh_path = exported
                print("[OK] FEM CalculiX export:", mesh_path)
            except Exception as ex:
                print(f"[WARN] FEM INP 不可用，改用 Gmsh 体网格: {ex}", file=sys.stderr)
    if mesh_path is None and not mesh_from_fem:
        if fuse_all:
            use_prebuilt = bool(cfg.get("use_prebuilt_fuse_step", False))
            if use_prebuilt and step_path.is_file():
                print(
                    f"[INFO] use_prebuilt_fuse_step=true：使用已有 STEP {step_path}",
                    file=sys.stderr,
                )
            else:
                fv_ratio = float(cfg.get("fuse_all_compound_volume_ratio", 0.97))
                _export_fused_all_solids(
                    fcstd, step_path, fuse_exclude, compound_vs_parts_ratio=fv_ratio
                )
        else:
            _export_fused_step(fcstd, fuse_names, step_path)
        print("[OK] fused STEP:", step_path)
        char_max_cfg = cfg.get("mesh_char_max_mm")
        char_min_cfg = cfg.get("mesh_char_min_mm")
        char_max_mm = float(char_max_cfg) if char_max_cfg is not None else None
        char_min_mm = float(char_min_cfg) if char_min_cfg is not None else None
        _run_gmsh_mesh(
            repo_root,
            step_path,
            mesh_inp,
            mesh_preset,
            char_max_mm=char_max_mm,
            char_min_mm=char_min_mm,
        )
        mesh_path = mesh_inp
        print("[OK] volume mesh INP:", mesh_path)

    nodes, elements = _parse_mesh_inp(mesh_path)
    design, nondesign = _split_design(
        fcstd,
        design_name,
        nodes,
        elements,
        nondesign_solid_names=nondesign_solid_names,
        partition_tolerance_mm=partition_tol,
        entire_mesh_design_space=entire_mesh_ds,
    )
    npromoted = 0
    if conn_protect_z > 0.0:
        design, nondesign, npromoted = _merge_bottom_interface_design_into_nondesign(
            design,
            nondesign,
            elements,
            nodes,
            protect_z_mm=conn_protect_z,
        )
        if npromoted > 0:
            print(
                f"[INFO] connection_protect_z_mm={conn_protect_z}: "
                f"{npromoted} C3D4 moved design_space -> nondesign_space (bottom interface band).",
                file=sys.stderr,
            )
        elif conn_protect_z > 0.0:
            print(
                f"[INFO] connection_protect_z_mm={conn_protect_z}: "
                "0 C3D4 matched (no shared-node design tets in bottom slab; try larger value).",
                file=sys.stderr,
            )
    print(f"[OK] design_space={len(design)} nondesign_space={len(nondesign)}")
    conn_fix_nodes_written: list[int] = []
    fem_bc_stats: dict[str, object] | None = None
    if fem_bc_inp is not None:
        _scripts_dir = Path(__file__).resolve().parent
        if str(_scripts_dir) not in sys.path:
            sys.path.insert(0, str(_scripts_dir))
        from beso_inp_bc_remap import write_beso_inp_with_remapped_bc  # noqa: PLC0415

        print(
            f"[INFO] fem_bc_reference_inp：从 {fem_bc_inp.name} 映射边界与 Cload（max_dist={fem_bc_max_d} mm）",
            file=sys.stderr,
        )
        fem_bc_stats = write_beso_inp_with_remapped_bc(
            out_inp=out_inp,
            design=design,
            nondesign=nondesign,
            nodes=nodes,
            elements=elements,
            E_mpa=E_mpa,
            nu=nu,
            density=density,
            fem_reference_inp=fem_bc_inp,
            max_dist_mm=fem_bc_max_d,
            fix_z_band_mm=fix_band,
            bottom_fix_fallback=fem_bc_bottom_fb,
            bottom_fix_only_if_no_fem_boundary=fem_bc_bottom_only,
            cload_fallback_if_empty=fem_bc_cload_fb,
            cload_fx=cload_fx,
            cload_fy=cload_fy,
            cload_fz=cload_fz,
            single_design_domain=entire_mesh_ds,
        )
        _mr = float(fem_bc_stats.get("max_remap_distance_mm") or 0.0)
        print(
            f"[INFO] FEM BC remap: skipped_boundary={fem_bc_stats.get('skipped_boundary_specs')} "
            f"skipped_cload={fem_bc_stats.get('skipped_cload_rows')} "
            f"cload_pairs={fem_bc_stats.get('cload_pairs')} "
            f"max_remap_dist_mm={_mr:.4g}",
            file=sys.stderr,
        )
    else:
        conn_fix_nodes_written = _assemble_out_inp(
            out_inp,
            design,
            nondesign,
            nodes,
            elements,
            E_mpa,
            nu,
            density,
            cload_fx,
            cload_fy,
            cload_fz,
            fix_band,
            connection_cload_fx=conn_fx,
            connection_cload_fy=conn_fy,
            connection_cload_fz=conn_fz,
            connection_cload_z_band_mm=conn_z_band,
            connection_cload_count=conn_n,
            connection_fix_count=conn_fix_n,
            connection_fix_z_band_mm=conn_fix_z,
            single_design_domain=entire_mesh_ds,
        )
    manifest = {
        "fcstd": str(fcstd),
        "out_inp": str(out_inp),
        "work_dir": str(work_dir),
        "design_solid_name": design_name,
        "nondesign_solid_names": nondesign_solid_names or [],
        "design_partition_tolerance_mm": partition_tol,
        "cload_fx": cload_fx,
        "cload_fy": cload_fy,
        "cload_fz": cload_fz,
        "connection_cload_fx": conn_fx,
        "connection_cload_fy": conn_fy,
        "connection_cload_fz": conn_fz,
        "connection_cload_z_band_mm": conn_z_band,
        "connection_cload_count": conn_n,
        "connection_fix_count": conn_fix_n,
        "connection_fix_z_band_mm": conn_fix_z,
        "connection_fix_nodes": conn_fix_nodes_written,
        "connection_protect_z_mm": conn_protect_z,
        "connection_protect_promoted": npromoted,
        "fem_bc_reference_inp": str(fem_bc_inp) if fem_bc_inp else None,
        "fem_bc_remap_max_dist_mm": fem_bc_max_d if fem_bc_inp else None,
        "fem_bc_bottom_fix_fallback": fem_bc_bottom_fb if fem_bc_inp else None,
        "fem_bc_bottom_fix_only_if_no_fem_boundary": fem_bc_bottom_only if fem_bc_inp else None,
        "fem_bc_cload_fallback_if_empty": fem_bc_cload_fb if fem_bc_inp else None,
        "fem_bc_remap_stats": fem_bc_stats,
        "entire_mesh_design_space": entire_mesh_ds,
        "nodes": len(nodes),
        "elements_total": len(elements),
        "design_space": len(design),
        "nondesign_space": len(nondesign),
    }
    man_path = work_dir / "beso_dual_domain_manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("[OK] wrote", out_inp, out_inp.stat().st_size)
    print("[OK] manifest", man_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
