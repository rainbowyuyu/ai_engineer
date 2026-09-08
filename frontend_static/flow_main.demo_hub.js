/**
 * 新功能体验中心 — 完整案例编排
 */
import {
  playReplanJourney,
  normalizeReplanJourneyData,
  replanDataToJourneyPayload,
} from "./flow_main.replan_journey.js";

const BASE_URL_KEY = "beso.settings.baseUrl";
const TASK_KEY = "beso.demo_hub.task_id";

const $ = (sel) => document.querySelector(sel);

const CASE_DEFS = [
  {
    id: "case1",
    panel: "case1",
    title: "案例 1 · 网格失败 → 重规划 → 相位闸",
    tagline: "Table S.1 Case1 · Gmsh 质量阈值",
    duration: "约 1.5 分钟",
    facts: [
      { k: "阶段", v: "Phase II · 网格" },
      { k: "信号", v: "翻转单元 / 质量过低" },
      { k: "动作", v: "refine_mesh" },
    ],
    story:
      "体网格划分出现翻转单元，系统检测到 Fₚ（ρₚ=1），自动收紧 characteristic_length_max 并播放逐步旅程。在 ρₚ 未清除前，finalize 被相位闸拦截；清除 ρₚ 后方可进入编排。",
    inputs: {
      phase: "II",
      step: "mesh",
      failure_signal: "mesh_quality_min < τ, inverted elements",
      theta_before: { characteristic_length_max: 2.5 },
    },
    steps: [
      {
        id: "c1-s1",
        label: "① 注入失败上下文",
        detail: "绑定演示任务 ID",
        async run(ctx) {
          return { task_id: ctx.ensureTaskId() };
        },
      },
      {
        id: "c1-s2",
        label: "② 调用 Case1 重规划 + 播放旅程",
        detail: "POST /api/replan/cases/case1/demo",
        async run(ctx) {
          const data = await ctx.api(
            `/api/replan/cases/case1/demo?task_id=${encodeURIComponent(ctx.ensureTaskId())}`,
            { method: "POST" },
          );
          ctx.lastReplan = data;
          await ctx.playJourneyInStage(data);
          if (data.version?.commit) {
            ctx.addArtifact("replan_commit.json", data.version.commit.url);
          }
          return {
            event_id: data.result?.event?.event_id || data.event_id,
            theta_after: data.result?.theta_after,
            guided_steps: data.guided_steps?.length,
            version_commit: data.version?.commit?.commit_id,
          };
        },
      },
      {
        id: "c1-s3",
        label: "③ 标记 ρₚ = 1",
        detail: "POST /api/workflow/mark-rho",
        async run(ctx) {
          const data = await ctx.api(`/api/workflow/mark-rho?task_id=${encodeURIComponent(ctx.taskId)}`, {
            method: "POST",
          });
          ctx.updateGate(1);
          return { rho_pending: data.state?.rho_pending };
        },
      },
      {
        id: "c1-s4",
        label: "④ 检查 finalize 闸（应拦截）",
        detail: "GET can-advance phase_ii_finalize",
        async run(ctx) {
          const data = await ctx.api(
            `/api/workflow/can-advance?task_id=${encodeURIComponent(ctx.taskId)}&transition=phase_ii_finalize`,
          );
          return { ok: data.ok, reason: data.verdict?.reason };
        },
      },
      {
        id: "c1-s5",
        label: "⑤ 清除 ρₚ（模拟旅程完成）",
        detail: "POST /api/workflow/clear-rho",
        async run(ctx) {
          await ctx.api(`/api/workflow/clear-rho?task_id=${encodeURIComponent(ctx.taskId)}`, { method: "POST" });
          ctx.updateGate(0);
          return { rho_pending: 0 };
        },
      },
      {
        id: "c1-s6",
        label: "⑥ 再次检查 finalize 闸（应通过）",
        async run(ctx) {
          const data = await ctx.api(
            `/api/workflow/can-advance?task_id=${encodeURIComponent(ctx.taskId)}&transition=phase_ii_finalize`,
          );
          return { ok: data.ok, verdict: data.verdict?.reason };
        },
      },
    ],
  },
  {
    id: "case2",
    panel: "case2",
    title: "案例 2 · BESO/CalculiX 失败 → 重规划",
    tagline: "Table S.1 Case2 · 残差平台",
    duration: "约 1.5 分钟",
    facts: [
      { k: "阶段", v: "Phase II · 求解" },
      { k: "信号", v: "残差平台不收敛" },
      { k: "动作", v: "relax increment" },
    ],
    story:
      "静力求解不收敛，引擎建议调整 load_increment / max_iterations。播放 Case2 旅程后，编排入口在 ρₚ≠0 时被拦截；获取 resume payload 后清除 ρₚ 继续。",
    inputs: {
      phase: "II",
      step: "beso_solver",
      failure_signal: "residual plateau",
      theta_before: { max_iterations: 80, load_increment: 0.08 },
    },
    steps: [
      {
        id: "c2-s1",
        label: "① 准备任务",
        async run(ctx) {
          return { task_id: ctx.ensureTaskId() };
        },
      },
      {
        id: "c2-s2",
        label: "② Case2 演示 + 旅程",
        async run(ctx) {
          const data = await ctx.api(
            `/api/replan/cases/case2/demo?task_id=${encodeURIComponent(ctx.ensureTaskId())}`,
            { method: "POST" },
          );
          ctx.lastReplan = data;
          await ctx.playJourneyInStage(data);
          return { theta_after: data.result?.theta_after, resume: data.resume };
        },
      },
      {
        id: "c2-s3",
        label: "③ ρₚ 阻塞编排闸",
        async run(ctx) {
          await ctx.api(`/api/workflow/mark-rho?task_id=${encodeURIComponent(ctx.taskId)}`, { method: "POST" });
          ctx.updateGate(1);
          const data = await ctx.api(
            `/api/workflow/can-advance?task_id=${encodeURIComponent(ctx.taskId)}&transition=design_domain_to_orchestrate`,
          );
          return { ok: data.ok, reason: data.verdict?.reason };
        },
      },
      {
        id: "c2-s4",
        label: "④ 获取 BESO 重跑 payload",
        detail: "POST /api/replan/resume",
        async run(ctx) {
          const theta = ctx.lastReplan?.result?.theta_after || { max_iterations: 120, load_increment: 0.12 };
          const data = await ctx.api("/api/replan/resume", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target: "beso", theta_after: theta, task_id: ctx.taskId }),
          });
          return { chat_body: data.chat_body };
        },
      },
      {
        id: "c2-s5",
        label: "⑤ 清除 ρₚ · 编排可进",
        async run(ctx) {
          await ctx.api(`/api/workflow/clear-rho?task_id=${encodeURIComponent(ctx.taskId)}`, { method: "POST" });
          ctx.updateGate(0);
          const data = await ctx.api(
            `/api/workflow/can-advance?task_id=${encodeURIComponent(ctx.taskId)}&transition=design_domain_to_orchestrate`,
          );
          return { ok: data.ok };
        },
      },
    ],
  },
  {
    id: "case3",
    panel: "case3",
    title: "案例 3 · 验证通过 → 终止门 → 候选 → 审计",
    tagline: "Phase IV 探索闭环",
    duration: "约 1 分钟",
    facts: [
      { k: "终止门", v: "S ≥ 85" },
      { k: "候选", v: "多方案打分" },
      { k: "产物", v: "审计清单" },
    ],
    story:
      "登记两个设计候选，Reviewer 综合分 86.5、子分均≥60，终止门通过。生成 SHA-256 审计清单并选出最高分候选，汇总可归档交付物。",
    inputs: {
      candidates: [
        { label: "方案 A · 保守型", overall_score: 82 },
        { label: "方案 B · 推荐型", overall_score: 88.5 },
      ],
      halt_gate: { overall_score: 86.5, S_min: 85, subscore_min: 60 },
    },
    steps: [
      {
        id: "c3-s1",
        label: "① 登记多候选并排序",
        async run(ctx) {
          const tid = ctx.ensureTaskId();
          await ctx.api("/api/candidates/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: tid, label: "方案 A · 保守型", overall_score: 82 }),
          });
          await ctx.api("/api/candidates/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: tid, label: "方案 B · 推荐型", overall_score: 88.5 }),
          });
          const list = await ctx.api(`/api/candidates?task_id=${encodeURIComponent(tid)}`);
          ctx.lastCandidates = list.candidates || [];
          ctx.renderCandidateList(ctx.lastCandidates);
          return { ranked: list.candidates };
        },
      },
      {
        id: "c3-s2",
        label: "② 评估探索终止门",
        async run(ctx) {
          const data = await ctx.api("/api/workflow/evaluate-halt-gate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              overall_score: 86.5,
              ai_review_scores: { capacity: 72, steel: 65, cost: 68, construction: 70, fatigue: 66 },
              regulatory_review_scores: { stability: 64, layout: 62 },
            }),
          });
          // 保持候选排行可见，再叠终止门横幅
          if (ctx.lastCandidates) ctx.renderCandidateList(ctx.lastCandidates);
          ctx.renderHaltResult(data.halt_gate);
          return data.halt_gate;
        },
      },
      {
        id: "c3-s3",
        label: "③ 生成 SHA-256 审计清单",
        async run(ctx) {
          const data = await ctx.api(`/api/audit/manifest?task_id=${encodeURIComponent(ctx.taskId)}`);
          ctx.addArtifact("audit_manifest.json", data.audit_manifest_url);
          ctx.renderAuditManifest(data);
          return { entry_count: data.entry_count, url: data.audit_manifest_url };
        },
      },
      {
        id: "c3-s4",
        label: "④ 选最高分候选（写入版本）",
        async run(ctx) {
          const data = await ctx.api("/api/candidates/select-best", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: ctx.taskId }),
          });
          if (data.version?.commit) {
            ctx.addArtifact("select_best_commit.json", data.version.commit.url);
          }
          if (ctx.lastCandidates) ctx.renderCandidateList(ctx.lastCandidates, data.candidate?.candidate_id);
          ctx.renderHaltResult?.({ ok: true, reason: `已选定：${data.candidate?.label || "最优方案"} · 已写入版本` });
          return { best: data.candidate, version_commit: data.version?.commit?.commit_id };
        },
      },
      {
        id: "c3-s5",
        label: "⑤ 查看方案选择版本链",
        async run(ctx) {
          const procs = await ctx.api(`/api/versions/processes?task_id=${encodeURIComponent(ctx.taskId)}`);
          const cand = (procs.processes || []).find((p) => p.process_type === "candidate_select");
          if (!cand) return { processes: procs.processes, note: "无候选版本进程" };
          const log = await ctx.api(
            `/api/versions/log?task_id=${encodeURIComponent(ctx.taskId)}&process_id=${encodeURIComponent(cand.process_id)}`,
          );
          ctx.renderVersionGraph([
            {
              process_id: cand.process_id,
              label: "方案选择版本链",
              commits: (log.commits || []).map((c) => ({
                commit_id: c.commit_id,
                message: c.message,
                handlers: c.handlers_applied,
              })),
            },
          ]);
          return {
            process_id: cand.process_id,
            commit_count: (log.commits || []).length,
            HEAD: cand.HEAD,
            commits: log.commits,
          };
        },
      },
    ],
  },
  {
    id: "case4",
    panel: "case4",
    title: "案例 4 · 工作区路径 → 工程图四视图",
    tagline: "主页 @路径 同款",
    duration: "约 30 秒",
    facts: [
      { k: "输入", v: "INP 路径" },
      { k: "输出", v: "四视图 PNG" },
      { k: "品牌", v: "AI Engineer" },
    ],
    story:
      "引用工作区 INP 路径，生成轴测/俯视/正视/侧视合成 PNG，与主页对话 @beso/.../file.inp 能力一致。",
    inputs: {
      user_message: "@beso/wiki_files/example_1/Plane_mesh.inp 请绘制工程图",
      path: "beso/wiki_files/example_1/Plane_mesh.inp",
    },
    steps: [
      {
        id: "c4-s1",
        label: "① 提交工作区路径",
        async run(ctx) {
          ctx.cadPath = "beso/wiki_files/example_1/Plane_mesh.inp";
          return { path: ctx.cadPath };
        },
      },
      {
        id: "c4-s2",
        label: "② 生成四视图工程图",
        async run(ctx) {
          const data = await ctx.api("/api/cad/drawing-pack", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: ctx.cadPath }),
          });
          ctx.renderDrawingSheet(data);
          ctx.addArtifact("drawing_sheet.png", data.sheet_url);
          return { drawing_id: data.drawing_id, sheet_url: data.sheet_url };
        },
      },
      {
        id: "c4-s3",
        label: "③ 输出说明",
        async run() {
          return { views: ["iso", "top", "front", "right"], disclaimer: "预览级 · 非审图出图" };
        },
      },
    ],
  },
  {
    id: "case5",
    panel: "case5",
    title: "案例 5 · 进程文件版本管理",
    tagline: "类 Git · 重规划 / 方案选择各一条版本链",
    duration: "约 1 分钟",
    facts: [
      { k: "进程", v: "重规划 / 方案选择" },
      { k: "操作", v: "commit · diff · checkout" },
      { k: "处理", v: "handlers 绑定" },
    ],
    story:
      "每个进程（重规划、方案选择）维护独立的文件版本线：commit 快照用户/系统修改的文件，记录对应处理（handlers），支持 log / diff / checkout。演示种子两条进程并检出最新版本。",
    inputs: {
      processes: ["replan", "candidate_select"],
      ops: ["open", "commit", "log", "diff", "checkout"],
    },
    steps: [
      {
        id: "c5-s1",
        label: "① 绑定任务并查看 handlers 目录",
        async run(ctx) {
          const tid = ctx.ensureTaskId();
          const replanH = await ctx.api("/api/versions/handlers?process_type=replan");
          const candH = await ctx.api("/api/versions/handlers?process_type=candidate_select");
          ctx.renderHandlersCatalog(replanH.handlers || [], candH.handlers || []);
          return {
            task_id: tid,
            replan_handlers: (replanH.handlers || []).map((h) => h.id),
            candidate_handlers: (candH.handlers || []).map((h) => h.id),
          };
        },
      },
      {
        id: "c5-s2",
        label: "② 种子：重规划 + 方案选择版本链",
        detail: "POST /api/versions/demo/seed",
        async run(ctx) {
          const data = await ctx.api("/api/versions/demo/seed", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: ctx.taskId, include_replan: true, include_candidates: true }),
          });
          ctx.versionSeed = data;
          const lanes = (data.processes || []).map((p) => ({
            process_id: p.process?.process_id,
            label:
              p.process?.process_type === "replan"
                ? "重规划进程"
                : p.process?.process_type === "candidate_select"
                  ? "方案选择进程"
                  : p.process?.label,
            commits: (p.commits || []).map((c) => ({
              commit_id: c.commit_id,
              message: c.message,
              handlers: c.handlers_applied,
            })),
          }));
          ctx.renderVersionGraph(lanes);
          for (const p of data.processes || []) {
            for (const c of p.commits || []) {
              if (c.url) ctx.addArtifact(`${String(c.commit_id).slice(0, 8)}.json`, c.url);
            }
          }
          return {
            process_count: (data.process_list || []).length,
            commits: lanes.flatMap((l) => (l.commits || []).map((c) => c.commit_id)),
          };
        },
      },
      {
        id: "c5-s3",
        label: "③ 列出版本 log（重规划进程）",
        async run(ctx) {
          const pid = "replan-demo";
          const log = await ctx.api(
            `/api/versions/log?task_id=${encodeURIComponent(ctx.taskId)}&process_id=${encodeURIComponent(pid)}`,
          );
          ctx.replanLog = log.commits || [];
          ctx.renderVersionGraph([
            {
              process_id: pid,
              label: "重规划版本链（最新在右）",
              commits: (log.commits || []).map((c) => ({
                commit_id: c.commit_id,
                message: c.message,
                handlers: c.handlers_applied,
              })),
            },
          ]);
          return { process_id: pid, commits: log.commits };
        },
      },
      {
        id: "c5-s4",
        label: "④ Diff 基线 → 重规划后",
        async run(ctx) {
          const commits = ctx.replanLog || [];
          if (commits.length < 2) return { note: "提交不足，跳过 diff" };
          const to = commits[0].commit_id;
          const from = commits[1].commit_id;
          const data = await ctx.api("/api/versions/diff", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              task_id: ctx.taskId,
              process_id: "replan-demo",
              from_commit: from,
              to_commit: to,
            }),
          });
          ctx.renderDiff(data.diff);
          return data.diff;
        },
      },
      {
        id: "c5-s5",
        label: "⑤ Checkout HEAD 到工作区",
        async run(ctx) {
          const commits = ctx.replanLog || [];
          const head = commits[0]?.commit_id;
          if (!head) throw new Error("无 HEAD 可检出");
          const data = await ctx.api("/api/versions/checkout", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              task_id: ctx.taskId,
              process_id: "replan-demo",
              commit_id: head,
            }),
          });
          if (data.dest_url) ctx.addArtifact("checkout/", data.dest_url);
          ctx.renderCheckout(data);
          return {
            commit_id: head,
            dest_dir: data.dest_dir,
            restored: data.restored,
            handlers: (data.handlers_available || []).map((h) => h.id),
          };
        },
      },
    ],
  },
  {
    id: "case6",
    panel: "case6",
    title: "教学回放 · BESO7（canned）",
    tagline: "预计算资产回放 · 非 live 求解",
    duration: "约 3 分钟",
    facts: [
      { k: "模式", v: "Preview / 教学" },
      { k: "资产", v: "BESO7.FCStd" },
      { k: "入口", v: "?demo=beso7-pipeline" },
    ],
    story:
      "【教学旁路】使用 BESO7 预计算 INP/帧回放与模拟重规划，便于无 CalculiX 时走通界面。正式对话真跑请用「对话真跑 · 10MW」。",
    inputs: {
      asset: "examples/beso/beso7/BESO7.FCStd",
      entry: "index.html?demo=beso7-pipeline",
    },
    steps: [
      {
        id: "c6-s1",
        label: "① 预检：种子会话 + 清单（真实 API）",
        detail: "POST …/bootstrap",
        async run(ctx) {
          const data = await ctx.api("/api/demo/beso7-live-pipeline/bootstrap", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: ctx.ensureTaskId() }),
          });
          ctx.flow = { boot: data };
          ctx.taskId = data.task_id;
          const inp = $("#demoTaskId");
          if (inp) inp.value = ctx.taskId;
          // Register on homepage left taskbar so main-flow demo is visible
          try {
            await ctx.api("/api/tasks/upsert", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                task_id: data.task_id,
                title: "全流程演示 · BESO7",
                file_name: "BESO7.FCStd",
                scan_dir: data.scan_dir || "",
                status: "uploaded",
                progress: 8,
                step: 1,
                ui_stage: "landing",
                oc4_design_domain_session_id: data.session_id || null,
                allow_sidebar_reorder: true,
              }),
            });
          } catch {
            /* non-fatal */
          }
          ctx.renderFlowIoBoard({
            step: 1,
            total: 2,
            title: "已种子真实会话（下一步进入主工作台）",
            detail: data.process?.detail || "",
            accent: "cyan",
            meta: [
              ["task_id", data.task_id],
              ["checklist_id", data.checklist_id],
              ["session_id", data.session_id],
            ],
            io: data.io,
            note: "任务已写入主页左侧任务栏。点击下一步将打开主工作台：设计域 Agent + 编排流式说明会真实运行。",
          });
          return { task_id: data.task_id, session_id: data.session_id, checklist_id: data.checklist_id };
        },
      },
      {
        id: "c6-s2",
        label: "② 打开主工作台 · 引导大模型全流程",
        detail: "index.html?demo=beso7-pipeline",
        async run(ctx) {
          const boot = ctx.flow?.boot || {};
          const tid = boot.task_id || ctx.ensureTaskId();
          const href = `./index.html?demo=beso7-pipeline&task_id=${encodeURIComponent(tid)}`;
          setStageHtml(
            "case6",
            `<div class="demoBeso7Launch">
              <p class="demoBeso7Kicker">真实功能区 · 非假装舞台</p>
              <h3>即将进入主工作台全流程引导</h3>
              <ul class="demoBeso7Facts">
                <li>主页助手：确认清单 θ 与下一步设计域</li>
                <li>设计域：智能体盘点 02/03 INP 等产物</li>
                <li>网格失败 → ρₚ + versions（真实后端）</li>
                <li>finalize 清单 θ → 编排流式说明 → job_context → solver replan</li>
              </ul>
              <a class="btn btnPrimary demoBeso7OpenBtn" id="demoBeso7OpenNow" href="${esc(href)}">立即进入主工作台引导</a>
              <p class="demoBeso7Hint">请在新打开的页面观看：底部「全流程演示」教练条会标注入/产出；设计域与编排为真实 UI。</p>
              <p class="mono demoBeso7Path">${esc(boot.fcstd_rel || "examples/beso/beso7/BESO7.FCStd")}</p>
            </div>`,
          );
          window.setTimeout(() => {
            const a = document.getElementById("demoBeso7OpenNow");
            if (a) a.click();
          }, 600);
          return { open_url: href, note: "已打开主工作台" };
        },
      },
    ],
  },
  {
    id: "case7",
    panel: "case7",
    title: "对话真跑 · 10MW",
    tagline: "Live 闭环 · 机型预设 + 人为可介入",
    duration: "视求解器而定",
    facts: [
      { k: "预设", v: "10 MW" },
      { k: "路径", v: "助手工具链" },
      { k: "HITL", v: "改几何后续跑" },
    ],
    story:
      "对话驱动真闭环：应用 10MW 预设 → 设计清单 → 设计域（可人为改模型）→ CalculiX–BESO → 尺寸/评审。缺 FreeCAD/ccx/gmsh 时会进入 Preview 并明确标注，不会冒充成功。",
    inputs: {
      preset_id: "10",
      entry: "index.html?live=10mw",
    },
    steps: [
      {
        id: "c7-s1",
        label: "① 探测求解器 / 执行模式",
        detail: "probe live|preview",
        async run(ctx) {
          // Soft probe via OpenAPI health; detailed probe is in-chat tool
          let health = { ok: true };
          try {
            health = await ctx.api("/health");
          } catch (e) {
            health = { ok: false, error: String(e?.message || e) };
          }
          ctx.renderFlowIoBoard({
            step: 1,
            total: 2,
            title: "准备对话真跑（10MW）",
            detail: "下一步打开主工作台；在侧栏对话中说：「按 10MW 预设做闭环设计，需要时暂停让我改几何」。",
            accent: "cyan",
            meta: [
              ["preset", "10"],
              ["health", health?.ok === false ? "down" : "up"],
            ],
            note: "助手将调用 apply_turbine_preset / start_design_domain_session / start_beso_job 等真工具。",
          });
          return health;
        },
      },
      {
        id: "c7-s2",
        label: "② 打开主工作台 · 预填 10MW 对话",
        detail: "index.html?live=10mw",
        async run(ctx) {
          const tid = ctx.ensureTaskId();
          const prompt = encodeURIComponent(
            "请按 10MW 机型预设启动对话驱动闭环：先 probe_execution，再 apply_turbine_preset(10)，创建设计域并在 mesh 前允许我人为改模型，然后真跑 BESO 与尺寸/评审。缺求解器时明确进入 Preview，不要调用 demo 回放。",
          );
          const href = `./index.html?live=10mw&task_id=${encodeURIComponent(tid)}&prefill=${prompt}`;
          setStageHtml(
            "case7",
            `<div class="demoBeso7Launch">
              <p class="demoBeso7Kicker">Live / Preview · 非教学回放</p>
              <h3>对话真跑 · 10MW FOWT</h3>
              <ul class="demoBeso7Facts">
                <li>机型预设 5/10/15/20 MW</li>
                <li>助手工具：设计域 / BESO / 尺寸 / 评审</li>
                <li>HITL：replace-geometry / 参数化提交</li>
              </ul>
              <a class="btn btnPrimary demoBeso7OpenBtn" id="demoLive10OpenNow" href="${esc(href)}">打开主工作台并预填提示</a>
            </div>`,
          );
          window.setTimeout(() => document.getElementById("demoLive10OpenNow")?.click(), 500);
          return { open_url: href };
        },
      },
    ],
  },
];

function normalizeBaseUrl(raw) {
  let s = String(raw || "").trim().replace(/\/+$/, "");
  if (!s) return "";
  if (!/^https?:\/\//i.test(s)) s = `http://${s}`;
  return s.replace(/\/ui$/i, "").replace(/\/$/, "");
}

function apiBase() {
  const custom = normalizeBaseUrl($("#demoApiBase")?.value || localStorage.getItem(BASE_URL_KEY) || "");
  if (custom) return custom;
  const o = window.location.origin;
  if (o && o !== "null" && /^https?:\/\//i.test(o) && !o.startsWith("file:")) {
    return o.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

let logLines = [];

function logResponse(label, data) {
  const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  logLines.unshift(`// ${ts} · ${label}\n${JSON.stringify(data, null, 2)}\n`);
  if (logLines.length > 16) logLines.length = 16;
  const el = $("#demoLogBody");
  if (el) el.textContent = logLines.join("\n");
}

function toast(msg) {
  const t = $("#demoToast");
  if (!t) return;
  t.textContent = msg;
  t.removeAttribute("hidden");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => t.setAttribute("hidden", ""), 3200);
}

function getTaskId() {
  return String($("#demoTaskId")?.value || "").trim();
}

function newTaskId() {
  const id = `demo-${crypto.randomUUID?.() || Date.now()}`;
  const inp = $("#demoTaskId");
  if (inp) inp.value = id;
  try {
    localStorage.setItem(TASK_KEY, id);
  } catch {
    /* ignore */
  }
  return id;
}

function showPanel(name) {
  document.querySelectorAll(".demoPanel").forEach((p) => {
    const on = p.dataset.panel === name;
    p.classList.toggle("is-active", on);
    if (on) p.removeAttribute("hidden");
    else p.setAttribute("hidden", "");
  });
  document.querySelectorAll(".demoHubNavBtn").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.panel === name);
  });
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function buildCasePanels() {
  const mount = $("#demoCasePanelsMount");
  const pick = $("#demoCasePickGrid");
  if (!mount) return;

  for (const def of CASE_DEFS) {
    if (pick) {
      const card = document.createElement("article");
      card.className = "demoCasePickCard";
      card.innerHTML = `
        <span class="demoCasePickDur">${esc(def.duration)}</span>
        <h3>${esc(def.title)}</h3>
        <p>${esc(def.tagline)}</p>
        <p class="demoCasePickStory">${esc(def.story.slice(0, 90))}…</p>
        <div class="demoCasePickActions">
          <button type="button" class="btn btnSoft demoCasePickBtn" data-goto="${esc(def.panel)}">进入</button>
          <button type="button" class="btn btnPrimary demoRunCaseBtn" data-case="${esc(def.id)}">▶ 运行</button>
        </div>
      `;
      pick.appendChild(card);
    }

    const factsHtml = (def.facts || [])
      .map((f) => `<span class="demoFactChip"><strong>${esc(f.k)}</strong> ${esc(f.v)}</span>`)
      .join("");

    const section = document.createElement("section");
    section.className = "demoPanel demoCasePanel";
    section.id = `panel-${def.panel}`;
    section.dataset.panel = def.panel;
    section.hidden = true;
    section.innerHTML = `
      <header class="demoCaseHero">
        <p class="demoHeroKicker">${esc(def.tagline)} · ${esc(def.duration)}</p>
        <h2>${esc(def.title)}</h2>
        <p class="demoCaseStory">${esc(def.story)}</p>
      </header>
      <div class="demoCaseLayout">
        <div class="demoFactStrip">${factsHtml}</div>
        <div class="demoCaseToolbar">
          <div class="demoCaseActions">
            <button type="button" class="btn btnPrimary demoRunCaseBtn" data-case="${esc(def.id)}">▶ 运行完整案例</button>
            <button type="button" class="btn btnSoft demoResetCaseBtn" data-case="${esc(def.id)}">重置</button>
          </div>
          <div class="demoGateVisual demoGateVisual--compact" id="gate-${def.id}" data-state="idle"${
            def.id === "case1" || def.id === "case2" ? "" : ' hidden style="display:none"'
          }>
            <div class="demoGateOrb"></div>
            <div class="demoGateLabel" id="gate-label-${def.id}">相位闸 · 待命</div>
          </div>
        </div>
        <div class="demoStepRailWrap">
          <div class="demoStepRail" id="timeline-${def.id}" role="list"></div>
        </div>
        <p class="demoStepHint" id="step-hint-${def.id}" hidden></p>
        <div class="demoVizBoard" id="stage-${def.id}">
          <p class="demoVizPlaceholder">点击「运行完整案例」观看可视化结果；运行后可点击上方步骤回看…</p>
        </div>
        <div class="demoArtifactsBar" id="artifacts-${def.id}"></div>
        <details class="demoTechDetails">
          <summary>技术细节（JSON，可选）</summary>
          <pre class="demoTechBody" id="io-out-${def.id}">{}</pre>
        </details>
      </div>
      <div id="halt-${def.id}" hidden></div>
      <ul id="cands-${def.id}" hidden></ul>
      <ul id="versions-${def.id}" hidden></ul>
    `;
    mount.appendChild(section);

    const tl = section.querySelector(`#timeline-${def.id}`);
    if (tl) {
      def.steps.forEach((step, idx) => {
        const pill = document.createElement("button");
        pill.type = "button";
        pill.className = "demoStepPill";
        pill.dataset.stepId = step.id;
        pill.dataset.caseId = def.id;
        pill.dataset.state = "pending";
        pill.setAttribute("role", "listitem");
        pill.innerHTML = `
          <span class="demoStepPillNum">${idx + 1}</span>
          <span class="demoStepPillLabel">${esc(step.label.replace(/^[①②③④⑤⑥⑦⑧⑨]\s*/, ""))}</span>
        `;
        pill.title = `${step.detail || step.label}（运行后可点击回看）`;
        tl.appendChild(pill);
      });
    }
  }
}

function getCaseDef(caseId) {
  return CASE_DEFS.find((c) => c.id === caseId);
}

function summarizeStep(stepId, output) {
  if (!output || typeof output !== "object") return "";
  if (output.error) return String(output.error).slice(0, 40);
  if (output.version_commit) return `提交 ${String(output.version_commit).slice(0, 8)}`;
  if (output.theta_after) {
    const t = output.theta_after;
    const key = Object.keys(t)[0];
    return key ? `${key}=${t[key]}` : "θ 已更新";
  }
  if (output.rho_pending === 1) return "闸口关闭";
  if (output.rho_pending === 0) return "闸口开放";
  if (output.ok === false) return "被拦截";
  if (output.ok === true) return "已放行";
  if (output.best?.label) return output.best.label;
  if (output.drawing_id) return "工程图已生成";
  if (output.restored) return `检出 ${output.restored.length} 个文件`;
  if (output.modified) return `变更 ${output.modified.length} 项`;
  if (output.commit_count != null) return `${output.commit_count} 个版本`;
  if (output.commits?.length) return `${output.commits.length} 条提交`;
  if (output.entry_count != null) return `${output.entry_count} 条审计`;
  if (output.task_id) return "任务已绑定";
  return "完成";
}

function setStepState(caseId, stepId, state, output) {
  const pill = document.querySelector(`#timeline-${caseId} [data-step-id="${stepId}"]`);
  if (!pill) return;
  pill.dataset.state = state;
  if (output !== undefined && state === "done") {
    const sum = summarizeStep(stepId, output);
    if (sum) pill.title = sum;
  }
}

function resetCase(caseId) {
  const def = getCaseDef(caseId);
  if (!def) return;
  for (const step of def.steps) setStepState(caseId, step.id, "pending");
  const out = $(`#io-out-${caseId}`);
  if (out) out.textContent = "{}";
  const art = $(`#artifacts-${caseId}`);
  if (art) art.innerHTML = "";
  const stage = $(`#stage-${caseId}`);
  if (stage) stage.innerHTML = '<p class="demoVizPlaceholder">点击「运行完整案例」观看可视化结果；运行后可点击上方步骤回看…</p>';
  const hint = $(`#step-hint-${caseId}`);
  if (hint) {
    hint.hidden = true;
    hint.innerHTML = "";
  }
  delete caseStepStore[caseId];
  updateGateForCase(caseId, null);
}

function updateGateForCase(caseId, rho) {
  const vis = $(`#gate-${caseId}`);
  const lab = $(`#gate-label-${caseId}`);
  if (!vis || !lab) return;
  if (rho === null) {
    vis.dataset.state = "idle";
    lab.textContent = "相位闸 · 待命";
    return;
  }
  vis.dataset.state = rho ? "blocked" : "open";
  lab.textContent = rho ? "ρₚ = 1 · 闸口关闭" : "ρₚ = 0 · 可前进";
}

function mergeOutput(caseId, chunk) {
  const el = $(`#io-out-${caseId}`);
  if (!el) return;
  let cur = {};
  try {
    cur = JSON.parse(el.textContent || "{}");
  } catch {
    cur = {};
  }
  Object.assign(cur, chunk);
  el.textContent = JSON.stringify(cur, null, 2);
}

function kvRows(obj) {
  if (!obj || typeof obj !== "object") return "<p class=\"demoVizPlaceholder\" style=\"padding:20px\">无数据</p>";
  return Object.entries(obj)
    .slice(0, 8)
    .map(([k, v]) => `<div class="demoKv"><span>${esc(k)}</span><strong>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</strong></div>`)
    .join("");
}

function setStageHtml(caseId, html, opts = {}) {
  const stage = $(`#stage-${caseId}`);
  if (!stage) return;
  stage.classList.remove("is-enter");
  stage.innerHTML = html;
  // force reflow for enter animation
  void stage.offsetWidth;
  stage.classList.add("is-enter");
  if (opts.snapshotStep) {
    rememberStepSnapshot(caseId, opts.snapshotStep, html, opts.summary || "");
  }
}

const caseStepStore = Object.create(null);

function rememberStepSnapshot(caseId, stepId, html, summary) {
  if (!caseStepStore[caseId]) caseStepStore[caseId] = {};
  caseStepStore[caseId][stepId] = {
    html,
    summary: summary || "",
    at: Date.now(),
  };
}

function restoreStepSnapshot(caseId, stepId) {
  const snap = caseStepStore[caseId]?.[stepId];
  if (!snap) {
    toast("该步骤尚无快照，请先运行案例");
    return;
  }
  document.querySelectorAll(`#timeline-${caseId} .demoStepPill`).forEach((p) => {
    p.classList.toggle("is-focused", p.dataset.stepId === stepId);
  });
  const stage = $(`#stage-${caseId}`);
  if (!stage) return;
  stage.classList.add("is-leave");
  window.setTimeout(() => {
    stage.innerHTML = snap.html;
    stage.classList.remove("is-leave");
    stage.classList.add("is-enter");
    bindStageInteractions(caseId);
  }, 160);
  const hint = $(`#step-hint-${caseId}`);
  if (hint) {
    hint.hidden = false;
    hint.innerHTML = `<strong>回看步骤</strong> · ${esc(snap.summary || stepId)} <button type="button" class="demoHintClear" data-case="${esc(caseId)}">清除高亮</button>`;
  }
}

function stepPauseMs(caseId, opts = {}) {
  if (opts.instantJourney && (caseId === "case3" || caseId === "case5")) return 900;
  if (caseId === "case3" || caseId === "case5") return 2200;
  if (caseId === "case4") return 500;
  if (caseId === "case6") return 1100;
  return 750;
}

function formatWorkspacePreview(name, text) {
  const lower = String(name || "").toLowerCase();
  try {
    if (lower.endsWith(".json") || text.trim().startsWith("{") || text.trim().startsWith("[")) {
      const data = JSON.parse(text);
      if (data && typeof data === "object" && !Array.isArray(data)) {
        const rows = Object.entries(data)
          .slice(0, 24)
          .map(([k, v]) => {
            const val = typeof v === "object" ? JSON.stringify(v) : String(v);
            return `<div class="demoWsKvCard"><div class="demoWsKvKey">${esc(k)}</div><div class="demoWsKvVal">${esc(val)}</div></div>`;
          })
          .join("");
        return {
          kind: "kv",
          html: `<div class="demoWsKvGrid">${rows || "<p class='demoWsPreviewEmpty'>空对象</p>"}</div>`,
        };
      }
      return {
        kind: "code",
        html: `<pre class="demoWsPreviewBody">${esc(JSON.stringify(data, null, 2))}</pre>`,
      };
    }
  } catch {
    /* fall through */
  }
  const clipped = text.length > 14000 ? `${text.slice(0, 14000)}\n…` : text;
  return { kind: "code", html: `<pre class="demoWsPreviewBody">${esc(clipped)}</pre>` };
}

function openWorkspaceExplorer({ baseUrl, destDir, destUrl, files }) {
  let overlay = $("#demoWorkspaceOverlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "demoWorkspaceOverlay";
    overlay.className = "demoWsOverlay";
    overlay.hidden = true;
    document.body.appendChild(overlay);
  }
  const rootUrl = destUrl
    ? destUrl.startsWith("http")
      ? destUrl
      : `${baseUrl}${destUrl.startsWith("/") ? "" : "/"}${destUrl}`
    : "";
  const fileList = (files || [])
    .map((f) => {
      const href = rootUrl ? `${rootUrl.replace(/\/$/, "")}/${f}` : "#";
      const ext = String(f).includes(".") ? String(f).split(".").pop().toLowerCase() : "bin";
      return `<button type="button" class="demoWsFile" data-href="${esc(href)}" data-name="${esc(f)}" data-ext="${esc(ext)}">
        <span class="demoWsFileIcon" aria-hidden="true"></span>
        <span class="demoWsFileName">${esc(f)}</span>
        <span class="demoWsFileAction">预览</span>
      </button>`;
    })
    .join("");
  overlay.hidden = false;
  overlay.innerHTML = `
    <div class="demoWsBackdrop" data-close="1"></div>
    <div class="demoWsPanel" role="dialog" aria-modal="true" aria-label="工作区">
      <header class="demoWsHead">
        <div>
          <p class="demoWsKicker">Workspace</p>
          <h3>检出工作区</h3>
          <p class="demoWsPath">${esc(destDir || "")}</p>
        </div>
        <button type="button" class="demoWsClose" data-close="1" aria-label="关闭">×</button>
      </header>
      <div class="demoWsBody">
        <aside class="demoWsSidebar">
          <h4>文件</h4>
          <div class="demoWsFileList">${fileList || "<p class='demoWsEmpty'>暂无文件</p>"}</div>
        </aside>
        <section class="demoWsPreview">
          <div class="demoWsPreviewHead" hidden>
            <p class="demoWsPreviewTitle" id="demoWsPreviewTitle"></p>
            <span class="demoWsPreviewBadge" id="demoWsPreviewBadge">VIEW</span>
          </div>
          <div class="demoWsPreviewScroll">
            <div class="demoWsPreviewEmpty">选择左侧文件查看结构化预览</div>
            <div class="demoWsPreviewContent" hidden></div>
          </div>
        </section>
      </div>
      <footer class="demoWsFoot">
        <a class="btn btnSoft" id="demoWsOpenTab" href="${esc(rootUrl || "#")}" target="_blank" rel="noopener">在新标签打开目录</a>
        <button type="button" class="btn btnPrimary" data-close="1">完成</button>
      </footer>
    </div>`;

  overlay.onclick = async (e) => {
    if (e.target.closest("[data-close]")) {
      overlay.hidden = true;
      return;
    }
    const fileBtn = e.target.closest(".demoWsFile");
    if (!fileBtn) return;
    const href = fileBtn.dataset.href;
    const name = fileBtn.dataset.name;
    overlay.querySelectorAll(".demoWsFile").forEach((b) => b.classList.toggle("is-active", b === fileBtn));
    const empty = overlay.querySelector(".demoWsPreviewEmpty");
    const content = overlay.querySelector(".demoWsPreviewContent");
    const head = overlay.querySelector(".demoWsPreviewHead");
    const title = overlay.querySelector("#demoWsPreviewTitle");
    const badge = overlay.querySelector("#demoWsPreviewBadge");
    if (!content || !href || href === "#") return;
    try {
      if (empty) empty.hidden = true;
      content.hidden = false;
      if (head) head.hidden = false;
      if (title) title.textContent = name;
      content.innerHTML = `<p class="demoWsPreviewEmpty" style="padding:24px">加载中…</p>`;
      const r = await fetch(href, { cache: "no-store" });
      const text = await r.text();
      const formatted = formatWorkspacePreview(name, text);
      if (badge) badge.textContent = formatted.kind === "kv" ? "STRUCTURE" : "TEXT";
      content.innerHTML = formatted.html;
    } catch (err) {
      content.innerHTML = `<p class="demoWsPreviewEmpty">无法预览 ${esc(name)}：${esc(err?.message || err)}</p>`;
    }
  };
}

function bindStageInteractions(caseId) {
  const stage = $(`#stage-${caseId}`);
  if (!stage) return;
  stage.querySelectorAll("[data-enter-workspace]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      openWorkspaceExplorer({
        baseUrl: apiBase(),
        destDir: btn.dataset.destDir || "",
        destUrl: btn.dataset.destUrl || "",
        files: String(btn.dataset.files || "")
          .split("|")
          .map((s) => s.trim())
          .filter(Boolean),
      });
    });
  });
  stage.querySelectorAll("[data-preview-url]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const url = btn.dataset.previewUrl;
      if (!url) return;
      openWorkspaceExplorer({
        baseUrl: apiBase(),
        destDir: btn.dataset.destDir || "审计清单",
        destUrl: url.includes("/") ? url.replace(/\/[^/]+$/, "") : url,
        files: [btn.dataset.fileName || "audit_manifest.json"],
      });
      window.setTimeout(() => {
        const overlay = $("#demoWorkspaceOverlay");
        const first = overlay?.querySelector(".demoWsFile");
        first?.click();
      }, 80);
    });
  });
}

async function runFullCase(caseId, opts = {}) {
  const def = getCaseDef(caseId);
  if (!def) return;

  const ctx = {
    taskId: getTaskId() || newTaskId(),
    baseUrl: apiBase(),
    instantJourney: Boolean(opts.instantJourney),
    lastReplan: null,
    cadPath: "",
    ensureTaskId() {
      if (!ctx.taskId) ctx.taskId = newTaskId();
      const inp = $("#demoTaskId");
      if (inp) inp.value = ctx.taskId;
      return ctx.taskId;
    },
    async api(path, options) {
      const url = path.startsWith("http") ? path : `${ctx.baseUrl}${path}`;
      const r = await fetch(url, options);
      let data = {};
      try {
        data = await r.json();
      } catch {
        /* ignore */
      }
      if (!r.ok) {
        const detail = typeof data.detail === "string" ? data.detail : r.statusText;
        throw new Error(detail || "请求失败");
      }
      logResponse(`${caseId} ${path}`, data);
      return data;
    },
    updateGate(rho) {
      updateGateForCase(caseId, rho);
    },
    async playJourneyInStage(raw) {
      const stage = $(`#stage-${caseId}`);
      if (!stage) return;
      const before = raw?.result?.theta_before || raw?.theta_before || {};
      const after = raw?.result?.theta_after || raw?.theta_after || {};
      const compare = `
        <div class="demoCompareRow">
          <div class="demoCompareCard" data-tone="before"><h4>重规划前 θ</h4>${kvRows(before)}</div>
          <div class="demoCompareArrow">→</div>
          <div class="demoCompareCard" data-tone="after"><h4>重规划后 θ</h4>${kvRows(after)}</div>
        </div>`;
      const norm = normalizeReplanJourneyData(raw);
      if (!norm) {
        setStageHtml(caseId, compare);
        return;
      }
      const card = replanDataToJourneyPayload(norm);
      setStageHtml(caseId, `${compare}<div class="rpJourneyHost" style="margin-top:14px">${card.html}</div>`);
      const host = stage.querySelector(".rpJourneyHost");
      await playReplanJourney(host, norm, {
        baseUrl: ctx.baseUrl,
        instant: Boolean(ctx.instantJourney),
      }).done;
    },
    renderHaltResult(gate) {
      if (!gate) return;
      const existing = $(`#stage-${caseId} .demoHaltBanner`);
      const banner = `<div class="demoHaltBanner ${gate.ok ? "is-pass" : "is-fail"}">${esc(
        gate.reason || (gate.ok ? "终止门通过 · 可进入归档" : "终止门未通过"),
      )}</div>`;
      const stage = $(`#stage-${caseId}`);
      if (!stage) return;
      if (existing) existing.outerHTML = banner;
      else stage.insertAdjacentHTML("beforeend", banner);
    },
    renderCandidateList(items, highlightId) {
      const arr = items || [];
      const max = Math.max(...arr.map((c) => Number(c.overall_score) || 0), 1);
      const dimLabels = {
        capacity: "单机容量",
        steel: "钢耗强度",
        cost: "单位造价",
        construction: "建造周期",
        fatigue: "疲劳寿命",
      };
      const rows = arr
        .map((c, i) => {
          const score = Number(c.overall_score) || 0;
          const pct = Math.round((score / max) * 100);
          const best = highlightId ? c.candidate_id === highlightId : i === 0;
          const basis = Array.isArray(c.score_basis) ? c.score_basis : [];
          const rationale = c.rationale || c.notes || "";
          const basisLines = basis.length
            ? `<ul class="demoRankBasis">${basis
                .map(
                  (b) =>
                    `<li><em>${esc(b.label || dimLabels[b.dim] || b.dim)}</em> ${esc(String(b.score))}：` +
                    `${esc(b.metric || "—")} · ${esc(b.evidence || "—")}</li>`,
                )
                .join("")}</ul>`
            : "";
          return `<li class="demoRankItem ${best ? "is-best" : ""}">
            <span class="demoRankBadge">${best ? "★" : i + 1}</span>
            <div class="demoRankMeta">
              <div class="name">${esc(c.label || c.candidate_id)}</div>
              <div class="demoRankBar"><i style="width:${pct}%"></i></div>
              ${rationale ? `<p class="demoRankWhy">${esc(rationale)}</p>` : ""}
              ${basisLines}
            </div>
            <span class="demoRankScore" title="AI 智能体预测分">预测 ${score.toFixed(1)}</span>
          </li>`;
        })
        .join("");
      const aiNote =
        arr[0]?.prediction_label ||
        "分数为 AI Review 智能体预测分（非 Phase V 实测验证分）";
      setStageHtml(
        caseId,
        `<p class="demoCandAiLabel">${esc(aiNote)}</p><ul class="demoRankList">${rows || "<li>暂无候选</li>"}</ul>`,
      );
      bindStageInteractions(caseId);
    },
    renderAuditManifest(data) {
      const n = Number(data?.entry_count) || 0;
      const url = data?.audit_manifest_url || "";
      const full = url ? (url.startsWith("http") ? url : `${ctx.baseUrl}${url}`) : "";
      const fileName = String(url || "audit_manifest.json").split("/").pop() || "audit_manifest.json";
      setStageHtml(
        caseId,
        `<div class="demoAuditCard">
          <div class="demoAuditSeal">SHA-256</div>
          <div class="demoAuditBody">
            <h4>审计清单已生成</h4>
            <p>共 <strong>${n}</strong> 条文件指纹，用于归档与可追溯性。</p>
            <div class="demoAuditActions">
              <button type="button" class="btn btnPrimary" data-preview-url="${esc(full)}" data-file-name="${esc(fileName)}" data-dest-dir="审计清单">打开清单内容</button>
              <a class="btn btnSoft" href="${esc(full || "#")}" target="_blank" rel="noopener">下载 JSON</a>
            </div>
          </div>
        </div>`,
      );
      bindStageInteractions(caseId);
    },
    renderVersionList(items) {
      ctx.renderVersionGraph([{ process_id: "versions", label: "版本", commits: items }]);
    },
    renderVersionGraph(lanes) {
      const html = (lanes || [])
        .map((lane) => {
          const commits = lane.commits || [];
          const ordered = [...commits].reverse();
          const nodes = ordered
            .map((c, i) => {
              const id = c.commit_id || "";
              const handlers = (c.handlers || c.handlers_applied || [])
                .map((h) => `<span class="demoHandlerTag">${esc(h)}</span>`)
                .join("");
              const isHead = i === ordered.length - 1;
              const node = `<div class="demoVerNode ${isHead ? "is-head" : ""}" tabindex="0">
                <div class="tag">${isHead ? "HEAD" : `v${i + 1}`}</div>
                <div class="hash">${esc(String(id).slice(0, 10))}</div>
                <div class="msg">${esc(c.message || "")}</div>
                <div class="handlers">${handlers}</div>
              </div>`;
              const arrow = i < ordered.length - 1 ? `<span class="demoVerArrow">→</span>` : "";
              return node + arrow;
            })
            .join("");
          return `<div class="demoVerLane">
            <h4 class="demoVerLaneTitle">${esc(lane.label || lane.process_id || "进程")}</h4>
            <div class="demoVerChain">${nodes || "<span class='demoVizPlaceholder'>暂无提交</span>"}</div>
          </div>`;
        })
        .join("");
      setStageHtml(caseId, `<div class="demoVerGraph">${html}</div>`);
      bindStageInteractions(caseId);
    },
    renderHandlersCatalog(replanHandlers, candHandlers) {
      const block = (title, list) =>
        `<div style="margin-bottom:14px"><h4 class="demoVerLaneTitle">${esc(title)}</h4>
        <div class="demoHandlerCatalog">${(list || [])
          .map(
            (h) =>
              `<div class="demoHandlerCard"><div class="id">${esc(h.id || h)}</div><div class="when">${esc(
                h.label || h.when || "",
              )}</div></div>`,
          )
          .join("")}</div></div>`;
      setStageHtml(
        caseId,
        block("重规划 handlers", replanHandlers) + block("方案选择 handlers", candHandlers),
      );
      bindStageInteractions(caseId);
    },
    renderDiff(diff) {
      if (!diff) return;
      setStageHtml(
        caseId,
        `<div class="demoDiffBoard">
          <div class="demoDiffCol" data-tone="mod"><h4>已修改</h4><ul>${(diff.modified || [])
            .map((f) => `<li>${esc(f)}</li>`)
            .join("") || "<li>（无）</li>"}</ul></div>
          <div class="demoDiffCol" data-tone="add"><h4>新增 / 删除</h4><ul>
            ${(diff.added || []).map((f) => `<li>+ ${esc(f)}</li>`).join("")}
            ${(diff.removed || []).map((f) => `<li>− ${esc(f)}</li>`).join("")}
            ${!(diff.added || []).length && !(diff.removed || []).length ? "<li>（无）</li>" : ""}
          </ul></div>
        </div>`,
      );
      bindStageInteractions(caseId);
    },
    renderCheckout(data) {
      const files = data?.restored || [];
      const chips = files.map((f) => `<span class="demoFileChip">${esc(f)}</span>`).join("");
      setStageHtml(
        caseId,
        `<div class="demoCheckoutCard is-interactive">
          <div class="demoFolderIcon" aria-hidden="true"></div>
          <div class="demoCheckoutMain">
            <h4>已检出到工作区</h4>
            <p>${esc(data?.dest_dir || "")}</p>
            <div class="demoFileChips">${chips}</div>
            <div class="demoCheckoutActions">
              <button type="button" class="btn btnPrimary"
                data-enter-workspace="1"
                data-dest-dir="${esc(data?.dest_dir || "")}"
                data-dest-url="${esc(data?.dest_url || "")}"
                data-files="${esc(files.join("|"))}">进入工作区</button>
            </div>
          </div>
        </div>`,
      );
      bindStageInteractions(caseId);
    },
    renderBeso7Launch(href, all) {
      const boot = all?.bootstrap || {};
      const mesh = all?.mesh_replan || {};
      const orch = all?.orchestrate || {};
      const sol = all?.solver_replan || {};
      const theta = all?.finalize?.beso_theta || {};
      setStageHtml(
        caseId,
        `<div class="demoBeso7Launch">
          <p class="demoBeso7Kicker">资产 · BESO7.FCStd</p>
          <h3>服务端链路已跑通</h3>
          <ul class="demoBeso7Facts">
            <li>清单 θ · mg=${esc(String(theta.mass_goal_ratio ?? "—"))} · ${esc(String(theta.source || ""))}</li>
            <li>mesh version · ${esc(String(mesh.version?.commit?.commit_id || mesh.version_commit || "—").slice(0, 12))}</li>
            <li>job · ${esc(String(orch.job_id || "—").slice(0, 12))}… · checklist 已写入</li>
            <li>solver version · ${esc(String(sol.version?.commit?.commit_id || sol.version_commit || "—").slice(0, 12))}</li>
          </ul>
          <a class="btn btnPrimary demoBeso7OpenBtn" href="${esc(href)}" target="_blank" rel="noopener">在主工作台观看逐步引导</a>
          <p class="demoBeso7Hint">将打开现有拓扑优化界面（设计域 / 编排），播放同一套故事线。</p>
          <p class="mono demoBeso7Path">${esc(boot.fcstd_rel || "examples/beso/beso7/BESO7.FCStd")}</p>
        </div>`,
      );
    },
    renderFlowIoBoard(opts = {}) {
      const step = Number(opts.step) || 1;
      const total = Number(opts.total) || 6;
      const accent = opts.accent || "cyan";
      const io = opts.io || {};
      const inputs = io.inputs || [];
      const outputs = io.outputs || [];
      const meta = opts.meta || [];
      const fmtSize = (n) => {
        const v = Number(n);
        if (!Number.isFinite(v) || v < 0) return "";
        if (v < 1024) return `${v} B`;
        if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
        return `${(v / (1024 * 1024)).toFixed(2)} MB`;
      };
      const fileCard = (f, tone) => {
        const miss = f.exists === false ? " is-missing" : "";
        const size = fmtSize(f.size_bytes);
        return `<div class="demoIoFile ${tone}${miss}" title="${esc(f.path || f.rel || "")}">
          <span class="demoIoRole">${esc(f.role || "file")}</span>
          <strong class="demoIoName">${esc(f.name || f.rel || "—")}</strong>
          <span class="demoIoPath mono">${esc(String(f.rel || f.path || "").slice(0, 64))}</span>
          ${size ? `<span class="demoIoSize">${esc(size)}</span>` : ""}
        </div>`;
      };
      const metaHtml = meta
        .map(([k, v]) => `<div class="demoFlowMetaItem"><span>${esc(k)}</span><strong>${esc(v == null ? "—" : String(v))}</strong></div>`)
        .join("");
      const rail = Array.from({ length: total }, (_, i) => {
        const n = i + 1;
        const cls = n < step ? "is-done" : n === step ? "is-active" : "";
        return `<span class="demoFlowRailDot ${cls}" title="步骤 ${n}"></span>`;
      }).join('<span class="demoFlowRailLine"></span>');
      const theta = opts.journey?.result?.theta_after || opts.journey?.theta_after;
      const thetaBefore = opts.journey?.result?.theta_before || opts.journey?.theta_before;
      let compare = "";
      if (theta || thetaBefore) {
        compare = `<div class="demoCompareRow demoFlowCompare">
          <div class="demoCompareCard" data-tone="before"><h4>θ 前</h4>${kvRows(thetaBefore || {})}</div>
          <div class="demoCompareArrow">→</div>
          <div class="demoCompareCard" data-tone="after"><h4>θ 后</h4>${kvRows(theta || {})}</div>
        </div>`;
      }
      setStageHtml(
        caseId,
        `<div class="demoFlowBoard" data-accent="${esc(accent)}">
          <div class="demoFlowRail">${rail}</div>
          <div class="demoFlowHead">
            <span class="demoFlowStepBadge">步骤 ${step}/${total}</span>
            <h3>${esc(opts.title || "")}</h3>
            <p class="demoFlowDetail">${esc(opts.detail || "")}</p>
          </div>
          ${metaHtml ? `<div class="demoFlowMeta">${metaHtml}</div>` : ""}
          <div class="demoIoColumns">
            <section class="demoIoCol">
              <h4>输入</h4>
              <div class="demoIoList">${inputs.map((f) => fileCard(f, "is-in")).join("") || "<p class='demoVizPlaceholder'>（无）</p>"}</div>
            </section>
            <div class="demoIoArrow" aria-hidden="true">→</div>
            <section class="demoIoCol">
              <h4>产出</h4>
              <div class="demoIoList">${outputs.map((f) => fileCard(f, "is-out")).join("") || "<p class='demoVizPlaceholder'>（无）</p>"}</div>
            </section>
          </div>
          ${compare}
          ${opts.note ? `<p class="demoFlowNote">${esc(opts.note)}</p>` : ""}
          ${opts.done ? `<p class="demoFlowDone">✓ 全流程演示完成</p>` : ""}
          <div class="demoFlowActions">
            <a class="btn btnSoft" href="./index.html" target="_blank" rel="noopener">打开主工作台</a>
          </div>
        </div>`,
        { snapshotStep: `c6-s${step}`, summary: opts.title || `步骤 ${step}` },
      );
    },
    renderDrawingSheet(data) {
      if (!data?.sheet_url) return;
      const url = data.sheet_url.startsWith("http") ? data.sheet_url : `${ctx.baseUrl}${data.sheet_url}`;
      setStageHtml(
        caseId,
        `<div class="demoDrawingWrap"><img class="demoDrawingImg" src="${esc(url)}" alt="工程图" /><p class="demoDrawingCap">${esc(
          data.source_path || "四视图工程图预览",
        )}</p></div>`,
      );
    },
    addArtifact(name, url) {
      const box = $(`#artifacts-${caseId}`);
      if (!box || !url) return;
      const full = url.startsWith("http") ? url : `${ctx.baseUrl}${url}`;
      const a = document.createElement("a");
      a.className = "demoArtifactLink";
      a.href = full;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = name;
      box.appendChild(a);
    },
  };

  resetCase(caseId);
  toast(`开始：${def.title}`);

  for (const step of def.steps) {
    setStepState(caseId, step.id, "running");
    document.querySelectorAll(`#timeline-${caseId} .demoStepPill`).forEach((p) => {
      p.classList.toggle("is-focused", p.dataset.stepId === step.id);
    });
    try {
      const out = await step.run(ctx);
      setStepState(caseId, step.id, "done", out);
      mergeOutput(caseId, { [step.id]: out });
      const stage = $(`#stage-${caseId}`);
      if (stage) {
        rememberStepSnapshot(caseId, step.id, stage.innerHTML, summarizeStep(step.id, out) || step.label);
      }
      bindStageInteractions(caseId);
      await new Promise((r) => setTimeout(r, stepPauseMs(caseId, opts)));
    } catch (e) {
      setStepState(caseId, step.id, "error", { error: String(e.message || e) });
      toast(`失败：${e.message || e}`);
      return;
    }
  }
  document.querySelectorAll(`#timeline-${caseId} .demoStepPill`).forEach((p) => p.classList.remove("is-focused"));
  toast(`完成：${def.title} · 可点击步骤回看`);
}

async function runAllCases() {
  newTaskId();
  for (const def of CASE_DEFS) {
    showPanel(def.panel);
    await runFullCase(def.id, { instantJourney: true });
    await new Promise((r) => setTimeout(r, 400));
  }
  showPanel("overview");
  toast("全部案例演示完成");
}

async function checkHealth() {
  const conn = $("#demoConn");
  const base = apiBase();
  try {
    localStorage.setItem(BASE_URL_KEY, base);
  } catch {
    /* ignore */
  }
  try {
    const r = await fetch(`${base}/health`, { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    if (conn) {
      conn.dataset.state = "ok";
      conn.textContent = "后端已连接";
    }
  } catch {
    if (conn) {
      conn.dataset.state = "err";
      conn.textContent = "未连接";
    }
  }
}

function fixMotionTags() {
  document.querySelectorAll("motion").forEach((bad) => {
    const d = document.createElement("div");
    d.className = bad.className;
    if (bad.id) d.id = bad.id;
    if (bad.hidden) d.hidden = true;
    d.innerHTML = bad.innerHTML;
    for (const k of Object.keys(bad.dataset)) d.dataset[k] = bad.dataset[k];
    bad.replaceWith(d);
  });
}

function bindUi() {
  $("#demoNav")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".demoHubNavBtn");
    if (!btn) return;
    showPanel(btn.dataset.panel || "overview");
  });

  document.body.addEventListener("click", (e) => {
    const runBtn = e.target.closest(".demoRunCaseBtn");
    if (runBtn?.dataset.case) {
      const def = getCaseDef(runBtn.dataset.case);
      if (def) showPanel(def.panel);
      void runFullCase(runBtn.dataset.case);
      return;
    }
    const goto = e.target.closest(".demoCasePickBtn");
    if (goto?.dataset.goto) showPanel(goto.dataset.goto);
    const reset = e.target.closest(".demoResetCaseBtn");
    if (reset?.dataset.case) resetCase(reset.dataset.case);
    const pill = e.target.closest(".demoStepPill");
    if (pill?.dataset.caseId && pill?.dataset.stepId && pill.dataset.state === "done") {
      restoreStepSnapshot(pill.dataset.caseId, pill.dataset.stepId);
      return;
    }
    const clearHint = e.target.closest(".demoHintClear");
    if (clearHint?.dataset.case) {
      const cid = clearHint.dataset.case;
      document.querySelectorAll(`#timeline-${cid} .demoStepPill`).forEach((p) => p.classList.remove("is-focused"));
      const hint = $(`#step-hint-${cid}`);
      if (hint) {
        hint.hidden = true;
        hint.innerHTML = "";
      }
    }
  });

  $("#demoNewTaskId")?.addEventListener("click", () => {
    newTaskId();
    toast("已生成新任务 ID");
  });
  $("#demoRunAllCases")?.addEventListener("click", () => void runAllCases());
  $("#demoClearLog")?.addEventListener("click", () => {
    logLines = [];
    const el = $("#demoLogBody");
    if (el) el.textContent = "// 已清空";
  });
  $("#demoApiBase")?.addEventListener("change", () => void checkHealth());

  const layout = document.querySelector(".demoHubLayout");
  const logAside = $("#demoHubLog");
  const logToggle = $("#demoLogToggle");
  logToggle?.addEventListener("click", () => {
    const open = layout?.classList.toggle("is-log-open");
    if (logAside) {
      if (open) logAside.removeAttribute("hidden");
      else logAside.setAttribute("hidden", "");
    }
    logToggle.setAttribute("aria-expanded", open ? "true" : "false");
    logToggle.textContent = open ? "隐藏 API 日志" : "显示 API 日志";
  });
}

function init() {
  const apiInp = $("#demoApiBase");
  if (apiInp) {
    const stored = localStorage.getItem(BASE_URL_KEY) || "";
    apiInp.value = stored || (window.location.origin?.startsWith("http") ? window.location.origin : "http://127.0.0.1:8000");
  }
  const tidInp = $("#demoTaskId");
  if (tidInp) tidInp.value = localStorage.getItem(TASK_KEY) || `demo-${Date.now().toString(36)}`;
  buildCasePanels();
  fixMotionTags();
  bindUi();
  void checkHealth();

  const hash = String(window.location.hash || "").replace(/^#/, "").trim().toLowerCase();
  if (hash === "case6" || hash === "full-flow" || hash === "全流程") {
    showPanel("case6");
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("autorun") === "1" || params.get("run") === "1") {
      window.setTimeout(() => void runFullCase("case6"), 400);
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
