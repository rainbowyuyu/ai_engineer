"""
OC4 半潜式浮式风机概念阶段拓扑优化：与 Chen et al. (2026) Ocean Engineering 方法论对齐的 LLM 上下文片段。

论文：「A novel design methodology for a semi-submersible floating wind turbine utilizing
topology optimization at the conceptual phase」（OC4 + NREL 5 MW 参考；BESO；设计域为三边柱围成区域；
120° 绕 Z 轴材料对称；柔度最小化 + 体积分数约束约 15%；系泊连接处全约束 + 轮毂等效水平推力经塔传至
主柱顶端；拓扑结果再经水动力几何重构——与本产品「设计域 → 编排 → BESO」链路对应的是前两阶段。）
"""

# 供各 Qwen system prompt 拼接；保持客观、可执行，避免杜撰数值以外的仿真结论。
LLM_CONTEXT_BLOCK_ZH = (
    "【方法论对齐（Chen et al., 2026, Ocean Engineering｜半潜式 FOWT 概念阶段 BESO）】\n"
    "1) 参考体：OC4 半潜平台 + NREL 5 MW 风机；设计域为三根边柱所围区域（概念上与原文 Fig.3 一致）。\n"
    "2) TO 表述：在离散 0/1 设计变量下最小化结构柔度（compliance），并满足目标体积分数约束；"
    "实现上对应 BESO 的 `optimization_base=stiffness` 与 `mass_goal_ratio≈0.15`（目标保留固体体积/质量比，"
    "与文中约 15% 体积分数约束同量级；若网格极粗或应力发散，可在用户明确要求时略调高）。\n"
    "3) 载荷/边界概念：系泊侧底部连接区采用强约束（全固定带）；风推力以水平力形式作用于塔顶/轮毂高度，"
    "经塔传至平台主柱顶端区域——你在建议 *BOUNDARY/*CLOAD 与分区参数时应与此物理图景一致。\n"
    "4) 对称性：材料分布宜绕竖轴 120° 对称（三角半潜柱位）；若用户未提对称，仍优先给出对称、可制造的载荷与固定方案。\n"
    "5) 拓扑之后：原文还包含基于拓扑启示的水动力外形重构（斜撑、去 Y 形 pontoon 等）；本产品设计域步骤负责「可算 INP」，"
    "几何interpretation 可在对话中提示用户或结合后续 CAD/二次参数化，不在此步强行改网格拓扑。\n"
)
