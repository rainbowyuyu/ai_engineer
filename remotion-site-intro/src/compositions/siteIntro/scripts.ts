/** Ch2 / Ch5 固定对话脚本（与产品能力一致，非虚构 API） */

export const AGENT_MODE_LABELS = [
  "深度思考",
  "联网检索",
  "CAD 工具",
  "附件",
] as const;

export const CHAT_SCRIPT_CH2: { role: "user" | "assistant"; text: string }[] = [
  {
    role: "user",
    text: "我有一份 IGES 塔筒分段，想走 OC4 设计域：几何清理、体网格、载荷 INP，再导出给后续仿真。",
  },
  {
    role: "assistant",
    text: "可以。先在侧栏选择「设计域」子流程；上传 IGES 后按步骤完成几何→网格→载荷，最后生成/审阅 INP。需要我同步解释每一步的检查点吗？",
  },
  {
    role: "user",
    text: "网格生成后我想进「构型优化编排」跑 BESO，四步编排里把上一步的 INP 接到任务里。",
  },
  {
    role: "assistant",
    text: "进入编排子流程后，按「准备→拓扑优化→后处理→汇总」推进；侧栏任务里可查看流式日志与结果查看器（VTK / STEP / INP）。",
  },
];

export const CHAT_SCRIPT_CH5: { role: "user" | "assistant"; text: string }[] = [
  {
    role: "user",
    text: "第一次用：我是不是上传文件、选任务类型，再点进子流程就行？",
  },
  {
    role: "assistant",
    text: "是的。主页输入区发送意图或上传附件；子流程条进入「设计域」或「构型优化编排」；侧栏保留多轮上下文与任务列表。",
  },
  {
    role: "user",
    text: "示例工程在仓库 examples 目录的话，我只用把标题和步骤对齐到界面里演示可以吗？",
  },
  {
    role: "assistant",
    text: "可以。教程段落用「清单」对齐关键动作：上传→选任务→进子流程→运行→回看结果；专有路径以文档为准，不在此硬编码。",
  },
];

export const TUTORIAL_CHECKLIST: string[] = [
  "上传 IGES / STEP / INP 等工程附件",
  "在侧栏创建任务并选择工作流意图",
  "通过子流程条进入「设计域」或「构型优化编排」",
  "在编排中完成四步并查看流式日志",
  "在结果查看器回放指标与交付物",
];
