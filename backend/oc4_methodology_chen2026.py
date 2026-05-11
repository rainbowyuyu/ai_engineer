"""
OC4 半潜式浮式风机概念阶段拓扑优化：与 Chen et al. (2026) Ocean Engineering 方法论对齐的 LLM 上下文。

论文：「A novel design methodology for a semi-submersible floating wind turbine utilizing
topology optimization at the conceptual phase」（OC4 + NREL 5 MW 参考；BESO；设计域为三边柱围成区域；
120° 绕 Z 轴材料对称；柔度最小化 + 体积分数约束约 15%；系泊连接处全约束 + 轮毂等效水平推力经塔传至
主柱顶端；拓扑结果再经水动力几何重构——与本产品「设计域 → 编排 → BESO」链路对应的是前两阶段。）

仓库内**工程定标**（与 `examples/beso`、`scripts/run_freecad_fcstd_export_inp.py`、设计域会话
`runs/_design_domain` 产物一致）：下文 `LLM_CONTEXT_BLOCK_ZH` 为唯一权威叙述，其它提示词勿另起一套矛盾说法。
"""

# 供各 Qwen system prompt 拼接；保持客观、可执行，避免杜撰数值以外的仿真结论。
LLM_CONTEXT_BLOCK_ZH = (
    "【定标·OC4 概念 BESO 全流程基准（勿与下文矛盾的随口建议混用）】\n"
    "A. 产物与顺序（二选一，勿乱序改名）\n"
    "  (1) 平台设计域会话（IGES/STEP 链）：`01_design_domain.step`（及 `01_design_domain.igs`）→ `02_mesh_body.inp`（体网格）"
    "→ `03_for_beso.inp`（含 *STEP/*BOUNDARY/*CLOAD、双 Elset）。收尾 `finalize` 写 `beso_conf.py`。\n"
    "      设计域实体默认与 `examples/beso/BESO3-Compound.iges` **同量级包络**：Gmsh merge 源装配后取 OCC 轴对齐包围盒，"
    "竖向与梁系推导范围求交，再布尔减柱/桩靴（对齐 FCStd 中 Pad001 占下层大块可设计体积的做法，而非仅三边柱内心小三角）。"
    "另可复制为 `{stem}-Compound.iges` 便于与主 IGES 并列扫描；**剖分仍使用** `01_design_domain.step`。\n"
    "  (2) FCStd 基准（仓库 `examples/beso/input.FCStd`）：`scripts/run_freecad_fcstd_export_inp.py` "
    "→ `Analysis-beso.inp`；FEM 若仅为壳/缺材料则自动回退为 Pad+Pad001 融合 STEP + Gmsh 体网格；"
    "设计域单元=重心落在 **Pad001** 实体内的四面体，其余为 **nondesign_space**。\n"
    "B. 设计域「怎么画 / 怎么建几何」\n"
    "  - OC4：`build_oc4_design_domain_iges` 默认用**整装配包围盒 slab** 生成实心设计域（与 BESO3-Compound 包络一致），"
    "再布尔减柱；可选 `OC4_DESIGN_DOMAIN_ENVELOPE=triangle` 退回旧三棱柱包络；\n"
    "优化范围由后续 INP 中 `design_space` Elset 承载，柱走廊等保留体用 `nondesign_space`（见 D）。\n"
    "  - FCStd/部件级：在 CAD 中将**可删添材料区域**做成独立实体（如 Pad001），外围/柱体为 Pad 等；"
    "网格后按实体 `isInside(单元重心)` 划分，勿在对话中发明未在几何中出现的第三套域名。\n"
    "C. 力与载荷「应长什么样」（CalculiX 静力卡）\n"
    "  - 必有：`*Step` + `*Static`；`*Material` + `*Elastic`（与模型单位一致，常用 MPa）+ `*Density`（t/mm³ 或 kg/mm³ 与弹性一致）；"
    "每个参与优化的实体集各一条 `*Solid section, Elset=…, Material=…`。\n"
    "  - 边界：系泊/底部概念 → **强约束**：用 `*Nset` 收集底面或低 z 带状节点，`*Boundary` 固定 1–3 自由度（全固定带）；"
    "与 Chen 文系泊区固定一致，勿用无物理含义的单点全模型固定代替面集。\n"
    "  - 荷载：风推力等效 → **水平集中力** `*Cload` 作用于塔顶/平台顶区代表节点（常用 +X；量级随几何缩放，"
    "仓库基准约 2.81e5 N 量级作试算，用户有规范值则以规范为准）。\n"
    "  - 输出：至少 `*Node file` 含 U、RF；`*El file` 含 S，供 BESO 读 `.dat`。\n"
    "D. 是否设计域「怎么划分」（INP + beso_conf 必须对齐）\n"
    "  - INP 内两个**实体**单元集：`*Elset, Elset=design_space` 与 `*Elset, Elset=nondesign_space`，"
    "且各集在 `*Element` 卡片中通过 `Elset=` 与之一一对应；`beso_conf.py` 里 "
    "`domain_optimized['design_space']=True`、`domain_optimized['nondesign_space']=False`，名称**大小写与 INP 完全一致**。\n"
    "  - OC4 体网格后可用 `inp_oc4_design_nondesign` 思路：按柱轴邻近带划 `nondesign_space`，其余为 `design_space`；"
    "FCStd 基准则用 Pad001 体内判据（见 A(2)）。\n"
    "E. OC4 拓扑优化「怎么做」（BESO 参数定标）\n"
    "  - 目标：柔度最小化 → `optimization_base='stiffness'`，`reference_points='integration points'`。\n"
    "  - 体积：Chen 文约 15% 保留固体 → `mass_goal_ratio≈0.15`（略调仅当用户明确或数值不稳定）。\n"
    "  - 稳定：`filter_list=[['simple', R]]`，R 取设计域平均单元尺寸的若干倍，或会话 `beso_conf` 中 `\"auto\"`；"
    "加减质量比常用 0.04/0.08（相对）起步。\n"
    "F. 对称与后处理\n"
    "  - 材料分布宜 120° 绕竖轴对称（三角柱位）；BESO 本体不强制对称，对称需在几何/约束或后处理中体现。\n"
    "  - 拓扑后的水动力外形重构（OpenFAST/AQWA 等）不在本工具链内；本链交付**可算 INP + BESO**。\n"
)
