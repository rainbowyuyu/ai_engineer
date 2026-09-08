/**
 * 全流程演示 — 在主工作台真实进入设计域 / 编排，并引导大模型操作。
 * 启动：index.html?demo=beso7-pipeline  或  demo_hub「全流程演示」跳转
 */
import {
  buildChecklistCardPayload,
  setActiveDesignChecklistId,
  setChecklistPendingState,
  clearChecklistPendingState,
} from "./flow_main.design_brief.js";
import { createFloatDock, createPanelOverview, mountMeshCards } from "./flow_main.beso7_panels.js";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 全流程演示：待确认参数（与设计清单澄清字段对齐） */
function buildDemoPendingClarifications(checklist) {
  const proj = checklist?.project || {};
  const site = checklist?.site || {};
  const perf = checklist?.performance_targets || {};
  const row = (field_id, question, value, unit) => {
    const v = value != null && value !== "" ? value : null;
    if (v == null) return null;
    const num = Number(v);
    const display = Number.isFinite(num)
      ? `${Number.isInteger(num) ? num.toFixed(1) : String(num)} ${unit}`.trim()
      : `${v} ${unit}`.trim();
    return { field_id, question, default_value: num, default_display: display, section: "" };
  };
  return [
    row("target_capacity_mw", "目标单机容量是多少 MW？", proj.target_capacity_mw ?? 20, "MW"),
    row("Hs_m", "场址设计有效波高 Hs 是多少？", site.Hs_m ?? 12, "m"),
    row("Tp_s", "谱峰周期 Tp 是多少？", site.Tp_s ?? 14, "s"),
    row("water_depth_m", "场址设计水深是多少？", site.water_depth_m ?? 45, "m"),
    row("wind_ref_m_s", "参考风速（轮毂高度）是多少？", site.wind_ref_m_s ?? 11.4, "m/s"),
    row("steel_intensity_t_per_MW", "钢耗强度目标是多少 t/MW？", perf.steel_intensity_t_per_MW ?? 300, "t/MW"),
    row("unit_cost_cny_per_MW", "单位造价目标是多少（万元/MW）？", perf.unit_cost_cny_per_MW ?? 2500, "万元/MW"),
    row("pitch_limit_deg", "静倾角限值是多少度？", perf.pitch_limit_deg ?? 5, "°"),
  ].filter(Boolean);
}

/** 在澄清卡片上逐项流式改写建议默认 → 已确认 */
async function streamClarifyParamEdits(cardRoot, edits) {
  if (!cardRoot) return;
  for (const edit of edits) {
    const li = cardRoot.querySelector(`.dcClarifyItem[data-field-id="${edit.field_id}"]`);
    if (!li) continue;
    li.classList.add("is-editing");
    li.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    const def = li.querySelector('[data-role="def"]');
    if (!def) {
      li.classList.remove("is-editing");
      continue;
    }
    const prefix = "已确认：";
    const target = `${prefix}${edit.display}`;
    def.classList.add("dcClarifyDef--live");
    def.textContent = "";
    for (let i = 0; i < target.length; i += 1) {
      def.textContent = target.slice(0, i + 1);
      await sleep(22 + (i % 3) * 6);
    }
    def.classList.add("dcClarifyDef--confirmed");
    li.classList.remove("is-editing");
    li.classList.add("is-confirmed");
    await sleep(220);
  }
}

async function typeLandingUserBubble(ctx, text, { cps = 28 } = {}) {
  const full = String(text || "");
  if (!full) return;
  if (ctx.refs?.msgLanding) {
    await typeInto(ctx.refs.msgLanding, full, { cps, clear: true });
    await sleep(280);
  }
  ctx.layout.addLandingBubble("user", full);
  if (ctx.refs?.msgLanding) ctx.refs.msgLanding.value = "";
}

/** @type {ReturnType<typeof createPanelOverview> | null} */
let _panels = null;

function ensureOverview() {
  if (!_panels) _panels = createPanelOverview();
  return _panels;
}

function ensureManagedDock(domId, regId, { title, badge, width = 400, order = 50, placeholder = "" } = {}) {
  const overview = ensureOverview();
  let dock = document.getElementById(domId)?.__dock;
  if (!dock) {
    dock = createFloatDock({
      id: domId,
      title: title || regId,
      side: "right",
      storageKey: `beso.ui.${domId}`,
      width,
      defaultMinimized: true,
      managed: true,
    });
    const el = document.getElementById(domId);
    if (el) el.__dock = dock;
    if (placeholder) dock.body.innerHTML = placeholder;
  }
  overview.register(regId, { title: title || regId, dock, badge, order });
  return dock;
}

/** 演示开始即注册全部可管理窗口，避免总览里只有「可视化」 */
function primeAllDemoWindows(ctx) {
  const overview = ensureOverview();
  ensureManagedDock("beso7VizGallery", "viz", {
    title: "可视化",
    badge: "3D",
    width: 400,
    order: 10,
    placeholder: `<p class="beso7FloatHint">Phase I–III 几何 / 拓扑 / 重构预览将显示在此。</p>`,
  });
  ensureManagedDock("beso7CandPanel", "candidates", {
    title: "方案选择",
    badge: "IV",
    width: 420,
    order: 20,
    placeholder: `<p class="beso7FloatHint">Phase IV · Automated Reviewer 多候选评分与选优（稍后出现）。</p>`,
  });
  ensureManagedDock("beso7VersionTree", "tree", {
    title: "版本树",
    badge: "git",
    width: 440,
    order: 30,
    placeholder: `<p class="beso7FloatHint">类 git 审计树：重规划 / 编排提交将出现在此。</p>`,
  });
  ensureManagedDock("beso7ValidatePanel", "validate", {
    title: "验证",
    badge: "V",
    width: 440,
    order: 35,
    placeholder: `<p class="beso7FloatHint">Phase V · Automated Reviewer 验证图表将显示在此。</p>`,
  });
  ensureManagedDock("beso7DrawingPanel", "drawing", {
    title: "工程图",
    badge: "VI",
    width: 460,
    order: 36,
    placeholder: `<p class="beso7FloatHint">Phase VI · 总布置式工程图预览。</p>`,
  });
  ensureManagedDock("beso7DeliverPanel", "deliverables", {
    title: "交付总览",
    badge: "Σ",
    width: 520,
    order: 8,
    placeholder: `<p class="beso7FloatHint">全流程关键文件与可视化总览（闭环收尾）。</p>`,
  });
  const params = ensureManagedDock("beso7ParamsPanel", "params", {
    title: "参数",
    badge: "θ",
    width: 360,
    order: 40,
    placeholder: `<p class="beso7FloatHint">拓扑参数（mass_goal / filter / save_every）。</p>`,
  });
  const syncParams = () => {
    const mg = ctx?.refs?.massGoal?.value ?? "—";
    const fr = ctx?.refs?.filterR?.value || "自动";
    const se = ctx?.refs?.saveEvery?.value ?? "—";
    const scan = ctx?.refs?.scanDirInput?.value || ctx?.state?.uploadedSourceDir || "—";
    const file = ctx?.state?.currentFileName || ctx?.refs?.landingPendingAttachName?.textContent || "—";
    params.body.innerHTML = `
      <dl class="beso7ParamsDl">
        <div><dt>源文件</dt><dd><code>${String(file).replace(/</g, "")}</code></dd></div>
        <div><dt>扫描目录</dt><dd class="beso7ParamsScan">${String(scan).replace(/</g, "")}</dd></div>
        <div><dt>mass_goal_ratio</dt><dd><strong>${String(mg)}</strong></dd></div>
        <div><dt>filter_radius</dt><dd>${String(fr)}</dd></div>
        <div><dt>save_every</dt><dd>${String(se)}</dd></div>
      </dl>
      <p class="beso7FloatHint">演示中会在设置抽屉里流式改写这些值；此处为总览快照。</p>`;
  };
  params.onFocus = syncParams;
  syncParams();

  const guide = ensureManagedDock("beso7GuidePanel", "guide", {
    title: "演示引导",
    badge: "demo",
    width: 340,
    order: 5,
    placeholder: `<p class="beso7FloatHint">全流程演示步骤说明。</p>`,
  });
  guide.onFocus = () => {
    const step = document.getElementById("beso7DemoCoachStep")?.textContent || "准备中…";
    guide.body.innerHTML = `
      <p class="beso7GuideStep">${step}</p>
      <p class="beso7FloatHint">顶部「全流程演示」条同步本步骤；底部窗口条可左右滑动切换可视化 / 参数 / 方案 / 版本树。</p>`;
  };
  guide.onFocus();

  // 任务日志：并入窗口总览，隐藏原站悬浮日志（避免重复）
  const logEl = ctx?.refs?.logFloatDock || document.getElementById("logFloatDock");
  if (logEl) {
    logEl.classList.add("hidden", "beso7LogDock--suppressed");
    logEl.setAttribute("aria-hidden", "true");
    try {
      logEl.classList.add("minimized");
    } catch {
      /* ignore */
    }
  }
  if (!document.getElementById("beso7LogProxy")?.__dock) {
    const logDock = ensureManagedDock("beso7LogProxy", "logs", {
      title: "任务日志",
      badge: "log",
      width: 400,
      order: 50,
      placeholder: `<p class="beso7FloatHint">编排阶段日志摘要。</p>`,
    });
    logDock.onFocus = () => {
      const body = ctx?.refs?.logFloatBody || document.getElementById("logFloatBody");
      const html = body?.innerHTML?.trim();
      logDock.body.innerHTML = html
        ? `<div class="beso7LogMirror mdBox">${html}</div>`
        : `<p class="beso7FloatHint">尚无日志。进入编排执行后将在此显示摘要。</p>`;
    };
  }

  overview.setBadge("viz", "3D");
  overview.setBadge("candidates", "IV");
  overview.setBadge("tree", "git");
  overview.setBadge("validate", "V");
  overview.setBadge("drawing", "VI");
  overview.setBadge("deliverables", "Σ");
  return overview;
}

async function typeInto(el, text, { cps = 32, clear = true } = {}) {
  if (!el) return;
  try {
    el.focus?.({ preventScroll: true });
  } catch {
    el.focus?.();
  }
  if (clear) el.value = "";
  const s = String(text ?? "");
  const delay = Math.max(12, Math.round(1000 / Math.max(8, cps)));
  for (let i = 1; i <= s.length; i++) {
    el.value = s.slice(0, i);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(delay);
  }
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

/** 主页模拟：选文件 → 流式填路径/参数/对话，再进入后端 bootstrap */
async function simulateLandingUserInput(ctx, { fcstdRel = "examples/beso/beso7/BESO7.FCStd" } = {}) {
  setCoach("① 模拟用户选择文件…");
  ctx.layout.showStage?.("landing");

  /* 清空主页对话，避免与上一轮演示/残留气泡叠成杂乱 */
  try {
    if (ctx.refs?.chatLanding) ctx.refs.chatLanding.innerHTML = "";
    if (ctx.state) {
      ctx.state.assistantThread = [];
      ctx.state.landingSessionDigest = [];
    }
  } catch {
    /* ignore */
  }
  await sleep(350);

  if (ctx.state) {
    ctx.state.landingAttachmentPending = {
      file_id: "demo-beso7-fcstd",
      file_name: "BESO7.FCStd",
      file_size: 2_400_000,
    };
    ctx.state.currentFileName = "BESO7.FCStd";
  }
  try {
    ctx.syncLandingPendingAttachBar?.();
  } catch {
    const bar = document.getElementById("landingPendingAttachBar");
    const n = document.getElementById("landingPendingAttachName");
    const meta = document.getElementById("landingPendingAttachMeta");
    bar?.classList.remove("hidden");
    if (n) n.textContent = "BESO7.FCStd";
    if (meta) meta.textContent = "FCStd · 演示资产";
  }
  if (ctx.refs?.fileSummaryInline) {
    ctx.refs.fileSummaryInline.textContent = "已选择：BESO7.FCStd（演示资产，待绑定会话）";
  }
  await sleep(700);

  setCoach("① 模拟输入工程路径与拓扑参数…");
  const scanHint = `…/${fcstdRel.replace(/\\/g, "/")}`;
  if (ctx.refs?.scanDirInput) {
    await typeInto(ctx.refs.scanDirInput, scanHint, { cps: 48 });
  }
  await sleep(280);
  if (ctx.refs?.massGoal) await typeInto(ctx.refs.massGoal, "0.15", { cps: 10 });
  if (ctx.refs?.filterR) await typeInto(ctx.refs.filterR, "2.0", { cps: 10 });
  try {
    ctx.persistTopologySettingsImmediate?.();
  } catch {
    /* ignore */
  }
  ensureOverview().setBadge("params", "θ");
  await sleep(400);

  setCoach("① 模拟输入设计意图…");
  const prompt =
    "请基于已上传的 BESO7.FCStd 做拓扑优化：mass_goal_ratio=0.15，先完成设计域检查，再进入逐步 BESO。";
  if (ctx.refs?.msgLanding) {
    await typeInto(ctx.refs.msgLanding, prompt, { cps: 40 });
  }
  ctx.layout.addLandingBubble?.("user", prompt);
  if (ctx.state) {
    ctx.state.assistantThread = [
      ...(ctx.state.assistantThread || []),
      { role: "user", content: prompt, format: "plain" },
    ];
  }
  if (ctx.refs?.msgLanding) ctx.refs.msgLanding.value = "";
  await sleep(500);
}

function showVizGallery(baseUrl, { title, items, focus = true }) {
  const overview = ensureOverview();
  const dock = ensureManagedDock("beso7VizGallery", "viz", {
    title: "可视化",
    badge: "3D",
    width: 400,
    order: 10,
  });
  dock._baseUrl = baseUrl;
  dock.setTitle(title || "可视化产物");
  overview.setTitle("viz", "可视化");
  overview.setBadge("viz", "3D");
  const cards = (items || [])
    .map((it) => {
      const raw = String(it.url || "");
      const png = String(it.png || "");
      const abs = (u) => {
        const s = String(u || "");
        if (!s) return "";
        return s.startsWith("http") || s.startsWith("#") || s.startsWith("data:") ? s : `${baseUrl}${s}`;
      };
      if (it.kind === "img") {
        return `<figure class="beso7VizCard"><img src="${abs(raw)}" alt="${it.label || ""}" loading="lazy"/><figcaption>${it.label || ""}</figcaption></figure>`;
      }
      // Prefer server-side PNG silhouette (avoids multi-WebGL black screens)
      if (png) {
        return `<figure class="beso7VizCard"><img class="beso7MiniThumb" src="${abs(png)}" alt="${it.label || ""}" loading="lazy"/><figcaption>${it.label || ""}</figcaption></figure>`;
      }
      if (raw.startsWith("#") || !raw) {
        return `<figure class="beso7VizCard beso7VizCard--mesh"><div class="beso7VizMeshHint">INFO</div><figcaption>${it.label || ""}</figcaption></figure>`;
      }
      return `<figure class="beso7VizCard beso7VizCard--mesh">
        <div class="beso7MiniCanvas" data-mini-obj="${raw}"></div>
        <figcaption>${it.label || "3D"}</figcaption>
      </figure>`;
    })
    .join("");
  dock.body.innerHTML = `<div class="beso7VizGrid">${cards}</div>
    <p class="beso7FloatHint">右侧「窗口」总览可切换面板（按 <kbd>N</kbd> 缩略/展开）；同一时间只展开一个。</p>`;
  if (focus) overview.focus("viz");
  // Ensure mesh thumbs mount even if overview remount timing misses
  setTimeout(() => mountMeshCards(dock.body, baseUrl), 80);
  return dock;
}

function demoQueryActive() {
  try {
    const q = new URLSearchParams(window.location.search || "");
    const v = String(q.get("demo") || "").trim().toLowerCase();
    return v === "beso7-pipeline" || v === "beso7" || v === "beso7-live" || v === "full-flow";
  } catch {
    return false;
  }
}

function ensureCoach() {
  let bar = document.getElementById("beso7DemoCoach");
  if (bar) return bar;
  bar = document.createElement("div");
  bar.id = "beso7DemoCoach";
  bar.className = "beso7DemoCoach";
  bar.innerHTML = `
    <div class="beso7DemoCoachInner">
      <span class="beso7DemoCoachMark">全流程演示</span>
      <span class="beso7DemoCoachStep" id="beso7DemoCoachStep">准备中…</span>
      <div class="beso7DemoCoachIo" id="beso7DemoCoachIo" hidden></div>
    </div>`;
  document.body.appendChild(bar);
  return bar;
}

function setCoach(text, io) {
  ensureCoach();
  const el = document.getElementById("beso7DemoCoachStep");
  if (el) el.textContent = text;
  const ioEl = document.getElementById("beso7DemoCoachIo");
  if (ioEl) {
    if (!io) {
      ioEl.hidden = true;
      ioEl.innerHTML = "";
    } else {
      const chip = (f, tone) =>
        `<span class="beso7IoChip ${tone}" title="${String(f.path || f.rel || "").replace(/"/g, "")}">${String(f.name || f.rel || "file")}</span>`;
      const ins = (io.inputs || []).map((f) => chip(f, "in")).join("");
      const outs = (io.outputs || []).map((f) => chip(f, "out")).join("");
      ioEl.hidden = false;
      ioEl.innerHTML = `<span class="beso7IoLab">入</span>${ins || "—"}<span class="beso7IoLab">出</span>${outs || "—"}`;
    }
  }
  try {
    document.getElementById("beso7GuidePanel")?.__dock?.onFocus?.();
  } catch {
    /* ignore */
  }
}

function stripDemoQuery() {
  try {
    const u = new URL(window.location.href);
    u.searchParams.delete("demo");
    u.searchParams.delete("autorun");
    window.history.replaceState({}, "", u.pathname + u.search + u.hash);
  } catch {
    /* ignore */
  }
}

function clearMetricsEmpty() {
  try {
    document.querySelector(".imgEmptyState")?.remove();
  } catch {
    /* ignore */
  }
}

/** Force Mass/FI curves into #imgGrid (demo seed path). */
function loadDemoMetrics(ctx, jobId, curveUrls = []) {
  clearMetricsEmpty();
  const base = String(ctx.baseUrl?.() || "").replace(/\/+$/, "");
  const names = ["Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png", "energy_density_mean.png"];
  const fromSeed = (curveUrls || [])
    .map((u) => String(u || ""))
    .filter(Boolean);
  const urls = fromSeed.length
    ? fromSeed
    : names.map((n) => `/runs/${jobId}/${n}`);
  for (const u of urls) {
    const name = String(u).split("/").pop();
    if (!name) continue;
    try {
      ctx.viewer?.upsertImage?.(name, u.startsWith("http") ? u.replace(base, "") : u);
    } catch {
      /* ignore */
    }
  }
  // Ensure imageCount reflects cards even if empty-state lingered
  try {
    const n = document.querySelectorAll("#imgGrid .imgCard").length;
    if (ctx.state && n > 0) ctx.state.imageCount = n;
  } catch {
    /* ignore */
  }
}

function setDemoLiveBesoBlocked(blocked) {
  window.__beso7DemoActive = Boolean(blocked);
  if (blocked && !window.__beso7DemoSeededJobId) {
    window.__beso7DemoSeededJobId = "pending";
  }
  const ids = ["executePlannedTask", "acceptStep1", "startBtn"];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) el.disabled = Boolean(blocked);
  }
}

function refsDdAgentReady(ctx) {
  return Boolean(ctx?.refs?.ddAgentRunLog || document.getElementById("ddAgentRunLog"));
}

/**
 * 交互式候选面板：用户点击「选择此方案」；超时则采纳推荐。
 */
function showCandidatePanelInteractive(baseUrl, data, { api, timeoutMs = 90000 } = {}) {
  const overview = ensureOverview();
  const dock = ensureManagedDock("beso7CandPanel", "candidates", {
    title: "方案选择",
    badge: "IV",
    width: 420,
    order: 20,
  });
  dock._baseUrl = baseUrl;
  dock.setTitle("Phase IV · Automated Reviewer");
  overview.setTitle("candidates", "方案选择");
  overview.setBadge("candidates", "IV");
  const list = data.candidates || data.registered || [];
  const recommendedId = data.recommended_id || list[0]?.candidate_id;
  const gate = data.halt_gate || {};
  const dimLabels = {
    capacity: "单机容量",
    steel: "钢耗强度",
    cost: "单位造价",
    construction: "建造周期",
    fatigue: "疲劳寿命",
  };

  const render = (selectedId, phase) => {
    const rows = list
      .map((c) => {
        const score = Number(c.overall_score) || 0;
        const best = selectedId && c.candidate_id === selectedId;
        const rec = c.candidate_id === recommendedId;
        const dims = c.score_dims || {};
        const basis = Array.isArray(c.score_basis) ? c.score_basis : [];
        const basisByDim = Object.fromEntries(basis.map((b) => [b.dim, b]));
        const dimHtml = Object.entries(dims)
          .map(([k, v]) => {
            const b = basisByDim[k];
            const tip = b
              ? `${b.metric || ""} · ${b.evidence || ""} · ${b.formula_ref || ""}`
              : "";
            return `<span class="beso7CandDim" title="${tip.replace(/"/g, "&quot;")}"><em>${dimLabels[k] || k}</em>${v}</span>`;
          })
          .join("");
        const basisHtml = basis.length
          ? `<details class="beso7CandBasis"><summary>给分理由与依据</summary><ul>${basis
              .map(
                (b) =>
                  `<li><strong>${b.label || dimLabels[b.dim] || b.dim}</strong>（${b.score}）：` +
                  `${b.metric || "—"}。依据：${b.evidence || "—"}。规则：${b.formula_ref || "—"}</li>`,
              )
              .join("")}</ul></details>`
          : "";
        const rationale = c.rationale
          ? `<p class="beso7CandRationale"><strong>综合理由：</strong>${c.rationale}</p>`
          : "";
        const preview = c.preview_url
          ? String(c.preview_url).endsWith(".png") || String(c.preview_png || "").length
            ? `<div class="beso7CandPreview"><img class="beso7MiniThumb" src="${baseUrl}${c.preview_png || c.preview_url}" alt="preview" loading="lazy"/></div>`
            : `<div class="beso7CandPreview"><div class="beso7MiniCanvas" data-mini-obj="${c.preview_url}"></div></div>`
          : "";
        const curve = c.curve_url
          ? `<img class="beso7CandCurve" src="${baseUrl}${c.curve_url}" alt="curve" loading="lazy"/>`
          : "";
        return `<li class="beso7CandRow ${best ? "is-best" : ""} ${rec && !selectedId ? "is-rec" : ""}" data-cid="${c.candidate_id}">
          <div class="beso7CandTop">
            <span class="beso7CandBadge">${best ? "已选" : rec ? "推荐" : "候选"}</span>
            <strong class="beso7CandScore">预测 S=${score.toFixed(1)}</strong>
          </div>
          <div class="beso7CandName">${c.label || c.candidate_id}</div>
          <div class="beso7CandBar"><i style="width:${Math.min(100, score)}%"></i></div>
          <div class="beso7CandMedia">${preview}${curve}</div>
          <div class="beso7CandDims">${dimHtml}</div>
          ${rationale}
          ${basisHtml}
          <p class="beso7CandNotes">${c.notes || ""}</p>
          ${
            phase === "pick"
              ? `<button type="button" class="beso7CandPick" data-pick="${c.candidate_id}">选择此方案</button>`
              : ""
          }
        </li>`;
      })
      .join("");
    const status =
      phase === "pick"
        ? `请选择方案（推荐已标出）。终止门 S≥85：${gate.ok ? "可终止探索" : gate.reason || "未通过"} · ${Math.round(timeoutMs / 1000)}s 内未选将采纳推荐`
        : selectedId
          ? "已确认选定方案并写入 versions"
          : "等待选择…";
    const aiLabel =
      list[0]?.prediction_label ||
      "以下分数为 AI Review 智能体预测分（基于拓扑/指标启发式），非 Phase V 实测验证分";
    dock.body.innerHTML = `
      <p class="beso7CandAiLabel">${aiLabel}</p>
      <p class="beso7CandGate ${gate.ok ? "is-pass" : "is-fail"}">${status}</p>
      <ul class="beso7CandList beso7CandList--rich">${rows}</ul>
      <p class="beso7CandNote">论文：多候选 → AI 五维预测 → 终止门 → 用户选优。用右侧「窗口」切换其它面板。</p>`;
    overview.focus("candidates");
    setTimeout(() => mountMeshCards(dock.body, baseUrl), 80);
  };

  render(null, "pick");

  return new Promise((resolve) => {
    let done = false;
    const finish = async (cid, via) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      let confirmed = { selected: list.find((c) => c.candidate_id === cid) || null };
      if (api && cid) {
        try {
          confirmed = await api("/api/demo/beso7-live-pipeline/select-candidate", {
            method: "POST",
            body: JSON.stringify({ task_id: data.task_id || "", candidate_id: cid }),
          });
        } catch {
          /* keep local */
        }
      }
      render(cid, "done");
      resolve({
        ...confirmed,
        via,
        selected: confirmed.selected || list.find((c) => c.candidate_id === cid),
      });
    };

    const timer = setTimeout(() => {
      finish(recommendedId, "timeout-recommend");
    }, timeoutMs);

    dock.body.addEventListener("click", (e) => {
      const btn = e.target.closest?.("[data-pick]");
      if (!btn) return;
      finish(btn.getAttribute("data-pick"), "user");
    });
  });
}

function showVersionTreePanel(baseUrl, tree) {
  const overview = ensureOverview();
  const dock = ensureManagedDock("beso7VersionTree", "tree", {
    title: "版本树",
    badge: "git",
    width: 440,
    order: 30,
  });
  dock._baseUrl = baseUrl;
  dock.setTitle("版本树 · 类 git 审计");
  overview.setTitle("tree", "版本树");
  overview.setBadge("tree", "git");
  const branches = tree.branches || [];
  const structure = tree.structure || {};
  const lanes = branches
    .map((b) => {
      const commits = (b.commits || [])
        .map((c, i) => {
          const files = (c.files || [])
            .map((f) => `<li><code>${f.path}</code> <span class="beso7Sha">${f.sha256 || ""}</span></li>`)
            .join("");
          const viz = (c.viz || [])
            .map((v) =>
              v.kind === "img"
                ? `<img class="beso7TreeThumb" src="${baseUrl}${v.url}" alt="${v.name}"/>`
                : `<div class="beso7MiniCanvas beso7TreeMini" data-mini-obj="${v.url}"></div>`,
            )
            .join("");
          const branchLine = i === 0 ? "●" : "│";
          return `<div class="beso7TreeCommit">
            <div class="beso7TreeRail">${branchLine}</div>
            <div class="beso7TreeCard">
              <div class="beso7TreeMsg"><code>${String(c.commit_id || "").slice(0, 8)}</code> ${c.message || ""}</div>
              <div class="beso7TreeMeta">${(c.tags || []).join(" · ") || "—"} · ${c.file_count || 0} files</div>
              <ul class="beso7TreeFiles">${files || "<li>(inline / empty)</li>"}</ul>
              ${viz ? `<div class="beso7TreeViz">${viz}</div>` : ""}
            </div>
          </div>`;
        })
        .join("");
      return `<section class="beso7TreeLane">
        <h4>${b.label || b.process_id} <em>${b.process_type || ""}</em></h4>
        <div class="beso7TreeCommits">${commits || "<p class='beso7FloatHint'>暂无提交</p>"}</div>
      </section>`;
    })
    .join("");
  dock.body.innerHTML = `
    <p class="beso7TreeSummary">${structure.note || ""} · 车道 ${structure.lanes?.length || 0} · 提交 ${structure.total_commits || 0}</p>
    <div class="beso7TreeBranches">${lanes}</div>
    <p class="beso7FloatHint">用右侧「窗口」总览切换；点「全部收起」可清屏。</p>`;
  overview.focus("tree");
  return dock;
}

function showValidationPanel(baseUrl, data) {
  const overview = ensureOverview();
  const dock = ensureManagedDock("beso7ValidatePanel", "validate", {
    title: "验证",
    badge: "V",
    width: 440,
    order: 35,
  });
  dock._baseUrl = baseUrl;
  dock.setTitle("Phase V · Automated Reviewer 验证");
  overview.setBadge("validate", "V");
  const figs = (data.figures || [])
    .map((f) => {
      const u = String(f.url || "");
      const src = u.startsWith("http") ? u : `${baseUrl}${u}`;
      return `<figure class="beso7VizCard"><img src="${src}" alt="${f.label || ""}" loading="lazy"/><figcaption>${f.label || ""}</figcaption></figure>`;
    })
    .join("");
  const gate = data.halt_gate || {};
  const next = data.next_action || (gate.ok ? "halt_and_archive" : "review_replan");
  dock.body.innerHTML = `
    <p class="beso7CandGate ${gate.ok ? "is-pass" : "is-fail"}">
      综合分 <strong>S=${data.overall_score ?? "—"}</strong>
      · 等级 <strong>${data.grade || "—"}</strong>
      · 终止门 S≥${gate.S_min ?? 85}：${gate.ok ? "可终止探索" : gate.reason || "未通过"}
    </p>
    ${
      gate.ok
        ? `<p class="beso7FloatHint">下一步：归档 / 工程图交付（next=${next}）。</p>`
        : `<p class="beso7FloatHint">未达终止门 → 触发 <strong>review 重规划</strong>（对齐容量与弱项 θ，ρₚ=1，再复验）。</p>`
    }
    <div class="beso7VizGrid">${figs || "<p class='beso7FloatHint'>暂无图表</p>"}</div>
    <p class="beso7FloatHint">报告：
      ${data.report_md_url ? `<a href="${baseUrl}${data.report_md_url}" target="_blank" rel="noopener">validation_report.md</a>` : "—"}
      ·
      ${data.score_json_url ? `<a href="${baseUrl}${data.score_json_url}" target="_blank" rel="noopener">score.json</a>` : "—"}
    </p>`;
  overview.focus("validate");
  return dock;
}

function showDrawingPanel(baseUrl, data) {
  const overview = ensureOverview();
  const dock = ensureManagedDock("beso7DrawingPanel", "drawing", {
    title: "工程图",
    badge: "VI",
    width: 460,
    order: 36,
  });
  dock._baseUrl = baseUrl;
  dock.setTitle("Phase VI · 工程图出图");
  overview.setBadge("drawing", "VI");
  const sheet = String(data.sheet_url || "");
  const src = sheet ? (sheet.startsWith("http") ? sheet : `${baseUrl}${sheet}`) : "";
  dock.body.innerHTML = `
    <p class="beso7FloatHint">源：<code>${data.source_path || "—"}</code> · 引擎 ${data.engine || "mesh"}</p>
    ${
      src
        ? `<figure class="beso7DrawingSheet"><img src="${src}" alt="工程图" loading="lazy"/><figcaption>总布置式四视图预览</figcaption></figure>`
        : `<p class="beso7FloatHint">未生成图纸</p>`
    }
    <p class="beso7FloatHint">drawing_id=${data.drawing_id || "—"}</p>`;
  overview.focus("drawing");
  return dock;
}

function showDeliverablesPanel(baseUrl, data) {
  const overview = ensureOverview();
  const dock = ensureManagedDock("beso7DeliverPanel", "deliverables", {
    title: "交付总览",
    badge: "Σ",
    width: 540,
    order: 8,
  });
  dock._baseUrl = baseUrl;
  dock.setTitle("交付总览 · 全流程闭环");
  overview.setBadge("deliverables", "Σ");
  const phases = (data.phases || [])
    .map(
      (p) =>
        `<li class="beso7PhaseChip is-${p.status || "done"}"><strong>${p.id}</strong><span>${p.title}</span></li>`,
    )
    .join("");
  const gallery = (data.gallery || [])
    .slice(0, 18)
    .map((g) => {
      const u = String(g.url || "");
      const png = String(g.png || "");
      const kind = String(g.kind || "img").toLowerCase();
      const abs = (path) => {
        const s = String(path || "");
        if (!s) return "";
        return s.startsWith("http") || s.startsWith("data:") ? s : `${baseUrl}${s}`;
      };
      const label = g.label || "";
      // Prefer PNG for mesh entries; never put .obj/.stl into <img>
      if (kind === "mesh" || /\.(obj|stl|vtk)(\?|$)/i.test(u)) {
        if (png) {
          return `<figure class="beso7VizCard"><img class="beso7MiniThumb" src="${abs(png)}" alt="${label}" loading="lazy"/><figcaption>${label}</figcaption></figure>`;
        }
        if (/\.preview\.png(\?|$)/i.test(u) || /\.png(\?|$)/i.test(u)) {
          return `<figure class="beso7VizCard"><img class="beso7MiniThumb" src="${abs(u)}" alt="${label}" loading="lazy"/><figcaption>${label}</figcaption></figure>`;
        }
        return `<figure class="beso7VizCard beso7VizCard--mesh">
          <div class="beso7MiniCanvas" data-mini-obj="${u}"></div>
          <figcaption>${label}</figcaption>
        </figure>`;
      }
      const src = abs(u);
      return `<figure class="beso7VizCard"><img src="${src}" alt="${label}" loading="lazy"/><figcaption>${label}</figcaption></figure>`;
    })
    .join("");
  const files = (data.files || [])
    .map((f) => {
      const u = f.url ? (String(f.url).startsWith("http") ? f.url : `${baseUrl}${f.url}`) : "";
      const name = f.name || "file";
      const link = u
        ? `<a href="${u}" target="_blank" rel="noopener"><code>${name}</code></a>`
        : `<code>${name}</code>`;
      return `<tr><td>${f.phase || "—"}</td><td>${f.role || "—"}</td><td>${link}</td></tr>`;
    })
    .join("");
  dock.body.innerHTML = `
    <p class="beso7TreeSummary">选定方案：<strong>${data.selected_label || "—"}</strong>
      · 验证 S=${data.validation_score ?? "—"}（${data.validation_grade || "—"}）
      · 工程图 ${data.drawing_id ? String(data.drawing_id).slice(0, 8) + "…" : "—"}
    </p>
    <ul class="beso7PhaseRow">${phases}</ul>
    <h4 class="beso7DeliverHd">可视化产物</h4>
    <div class="beso7VizGrid beso7VizGrid--dense">${gallery || "<p class='beso7FloatHint'>暂无预览</p>"}</div>
    <h4 class="beso7DeliverHd">关键文件清单</h4>
    <div class="beso7FileTableWrap"><table class="beso7FileTable">
      <thead><tr><th>阶段</th><th>角色</th><th>文件</th></tr></thead>
      <tbody>${files || "<tr><td colspan='3'>暂无</td></tr>"}</tbody>
    </table></div>
    <p class="beso7FloatHint">此页汇总 Phase I–VI 主要产物，形成从设计域到验证与出图的闭环。</p>`;
  overview.focus("deliverables");
  setTimeout(() => mountMeshCards(dock.body, baseUrl), 80);
  return dock;
}

/**
 * @param {object} ctx — wired from flow_main.js
 */
export async function maybeRunBeso7LiveDemo(ctx) {
  if (!demoQueryActive()) return false;
  if (!ctx?.state || !ctx?.layout) return false;
  if (window.__beso7DemoRunning) return false;
  window.__beso7DemoRunning = true;
  setDemoLiveBesoBlocked(true);

  const base = () => String(ctx.baseUrl() || "").replace(/\/+$/, "");
  const api = async (path, options = {}) => {
    const r = await fetch(`${base()}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = typeof data.detail === "string" ? data.detail : r.statusText;
      throw new Error(detail || "请求失败");
    }
    return data;
  };

  ensureCoach();
  ensureOverview();
  primeAllDemoWindows(ctx);
  setCoach("① 准备主页交互模拟…");
  await sleep(400);

  try {
    // Prefer task_id from demo_hub jump URL so sidebar entry matches
    try {
      const qTid = new URLSearchParams(window.location.search || "").get("task_id");
      if (qTid) ctx.state.currentTaskId = qTid;
    } catch {
      /* ignore */
    }
    ctx.ensureDesignDomainIde?.();
    ctx.layout.showStage("landing");

    await simulateLandingUserInput(ctx, {
      fcstdRel: "examples/beso/beso7/BESO7.FCStd",
    });

    setCoach("① 创建任务与设计清单（后端 bootstrap）…");
    const boot = await api("/api/demo/beso7-live-pipeline/bootstrap", {
      method: "POST",
      body: JSON.stringify({ task_id: ctx.state.currentTaskId || null }),
    });

    const tid = boot.task_id;
    const cid = boot.checklist_id;
    const sid = boot.session_id;

    ctx.state.currentTaskId = tid;
    ctx.state.currentFileName = "BESO7.FCStd";
    ctx.state.currentFileId = ctx.state.currentFileId || "";
    ctx.state.uploadedSourceDir = boot.scan_dir || "";
    ctx.state.oc4DesignDomainSessionId = sid;
    ctx.state.oc4DesignDomainSessionIdForResume = sid;
    ctx.state.oc4DesignDomainFinalized = false;
    if (ctx.refs?.scanDirInput) {
      await typeInto(ctx.refs.scanDirInput, boot.scan_dir || "", { cps: 55, clear: true });
    }
    if (ctx.refs?.fileSummaryInline) {
      ctx.refs.fileSummaryInline.textContent =
        `全流程演示资产：BESO7.FCStd\n会话：${sid.slice(0, 8)}…\n目录：${boot.scan_dir || ""}`;
    }
    document.getElementById("beso7ParamsPanel")?.__dock?.onFocus?.();
    if (Number.isFinite(Number(boot.beso_theta?.mass_goal_ratio)) && ctx.refs?.massGoal) {
      const mg = String(boot.beso_theta.mass_goal_ratio);
      if (String(ctx.refs.massGoal.value) !== mg) {
        await typeInto(ctx.refs.massGoal, mg, { cps: 10 });
      }
    }

    setActiveDesignChecklistId(cid);
    const pending = buildDemoPendingClarifications(boot.checklist);
    setChecklistPendingState({ checklistId: cid, pending });
    const pendingCardData = {
      checklist_id: cid,
      checklist: boot.checklist,
      pending_clarifications: pending,
      clarification_complete: false,
      parser: boot.checklist?.meta?.parser || "rule_fallback",
      context_summary: `BESO7 全流程 · θ mg=${boot.beso_theta?.mass_goal_ratio}`,
    };
    ctx.commitChecklistTurnForTask?.(tid, pendingCardData, base());
    ctx.layout.addLandingBubble(
      "agent",
      "已绑定 **BESO7.FCStd**。请确认上方待确认参数，随后进入：设计域 → BESO → Automated Reviewer → 验证 → 工程图。",
      { format: "md" },
    );

    await ctx.taskManager?.upsertTask?.(
      {
        title: "全流程演示 · BESO7",
        file_name: "BESO7.FCStd",
        scan_dir: boot.scan_dir,
        status: "uploaded",
        progress: 12,
        step: 1,
        ui_stage: "landing",
        oc4_design_domain_session_id: sid,
      },
      { taskId: tid, allowSidebarReorder: true },
    );
    await ctx.taskManager?.loadTasks?.().catch(() => {});
    ctx.persistLandingAssistantThread?.(tid);
    setCoach("① 任务+清单就绪 · 待您确认参数", boot.io);
    await sleep(1600);

    /* 流式模拟：用户适当修改部分参数后确认（容量保持 20 MW，与几何资产对齐） */
    setCoach("①b 模拟用户确认并微调参数…");
    const userReply =
      "Hs 改为 11.5，水深 50，钢耗 280；容量保持 20 MW，其余用默认。";
    await typeLandingUserBubble(ctx, userReply, { cps: 26 });
    await sleep(400);

    const clarifyRoot = ctx.refs?.chatLanding?.querySelector(".dcCard .dcClarify");
    const paramEdits = [
      { field_id: "Hs_m", display: "11.5 m", value: 11.5 },
      { field_id: "water_depth_m", display: "50.0 m", value: 50 },
      { field_id: "steel_intensity_t_per_MW", display: "280.0 t/MW", value: 280 },
    ];
    await streamClarifyParamEdits(clarifyRoot, paramEdits);

    /* 其余项快速标为采用默认 */
    if (clarifyRoot) {
      for (const li of clarifyRoot.querySelectorAll(".dcClarifyItem:not(.is-confirmed)")) {
        const def = li.querySelector('[data-role="def"]');
        if (!def) continue;
        li.classList.add("is-confirmed");
        const raw = String(def.textContent || "").replace(/^建议默认：/, "").trim();
        def.textContent = `采用默认：${raw}`;
        def.classList.add("dcClarifyDef--confirmed");
        await sleep(90);
      }
    }
    await sleep(500);

    /* 持久化到后端清单，避免 Phase V 仍用未更新的默认值 */
    try {
      await api(`/api/design-requirements/${encodeURIComponent(cid)}/clarify`, {
        method: "POST",
        body: JSON.stringify({ reply: userReply, mode: "clarify" }),
      });
    } catch (e) {
      try {
        await api(`/api/design-requirements/${encodeURIComponent(cid)}/clarify`, {
          method: "POST",
          body: JSON.stringify({
            reply: "Hs 11.5，水深 50，钢耗 280 t/MW，容量 20 MW",
            mode: "edit",
          }),
        });
      } catch (e2) {
        ctx.layout.addLandingBubble?.("agent", `清单澄清持久化跳过：${e2?.message || e?.message || e2}`);
      }
    }

    const clPatched = structuredClone
      ? structuredClone(boot.checklist || {})
      : JSON.parse(JSON.stringify(boot.checklist || {}));
    if (!clPatched.project) clPatched.project = {};
    if (!clPatched.site) clPatched.site = {};
    if (!clPatched.performance_targets) clPatched.performance_targets = {};
    clPatched.project.target_capacity_mw = 20;
    clPatched.site.Hs_m = 11.5;
    clPatched.site.water_depth_m = 50;
    clPatched.performance_targets.steel_intensity_t_per_MW = 280;

    clearChecklistPendingState();
    const lockedCardData = {
      checklist_id: cid,
      checklist: clPatched,
      pending_clarifications: [],
      clarification_complete: true,
      parser: boot.checklist?.meta?.parser || "rule_fallback",
      updated_fields: paramEdits.map((e) => ({
        field_id: e.field_id,
        value: e.value,
        unit: String(e.display).replace(/^[\d.]+\s*/, ""),
      })),
      context_summary: `BESO7 全流程 · θ mg=${boot.beso_theta?.mass_goal_ratio}`,
    };
    const lockedCard = buildChecklistCardPayload(lockedCardData, base());
    /* 原地更新同一张清单卡，避免再插一张重复卡片 */
    if (lockedCard?.html) {
      ctx.layout.replaceLandingChecklistCard?.(lockedCard, base());
    }
    setActiveDesignChecklistId(cid);
    clearChecklistPendingState();
    if (ctx.state) {
      ctx.state.designChecklistPending = null;
      const thread = ctx.state.assistantThread || [];
      const idx = [...thread].map((m, i) => ({ m, i })).reverse().find(({ m }) => m?.kind === "design_checklist")?.i;
      if (idx != null) {
        thread[idx] = {
          role: "assistant",
          content: lockedCard.plainSummary,
          format: "checklist",
          checklist_payload: lockedCard,
          design_checklist_id: cid,
          kind: "design_checklist",
          clarification_complete: true,
        };
      }
    }
    ctx.layout.addLandingBubble(
      "agent",
      "参数已锁定：**容量 20 MW** · Hs 11.5 · 水深 50 · 钢耗 280。进入设计域。",
      { format: "md" },
    );
    await sleep(1200);

    /* 跳过额外助手往返，避免主页再堆一轮重复说明 */

    setCoach("② 进入设计域功能区 · 加载 3D 预览…", boot.io);
    await ctx.taskManager?.upsertTask?.(
      {
        title: "全流程演示 · BESO7",
        ui_stage: "design_domain",
        progress: 28,
        step: 2,
        status: "running",
      },
      { taskId: tid },
    );
    ctx.state.currentTaskUiStage = "design_domain";
    await ctx.layout.playLandingSubflowBridge?.({ kind: "design_domain", minMs: 1400, instant: false });
    await ctx.enterOc4DesignDomainStage?.({ softResume: true, forceNewSession: false });
    await ctx.linkOc4SessionToCurrentTask?.();
    ctx.ensureDesignDomainIde?.();
    await ctx.syncDesignDomainSessionProgress?.().catch(() => {});
    ctx.applyDesignDomainStepUi?.();
    // Homepage workflow cards so demo steps are visible on landing
    try {
      if (!ctx.landingThreadHasDesignDomainCard?.()) {
        ctx.pushDesignDomainWorkflowCardToLandingThread?.({ status: "进行中", step: 2, progress: 28 });
      }
      ctx.persistLandingAssistantThread?.(tid);
    } catch {
      /* ignore */
    }
    await sleep(800);
    try {
      await ctx.refreshDesignDomainPreviewsFromSession?.();
    } catch {
      /* ignore */
    }
    await sleep(1200);
    const designObjUrl =
      boot.design_obj_url || `/runs/_design_domain/${sid}/design_preview.obj`;
    const sourceObjUrl =
      boot.source_obj_url || `/runs/_design_domain/${sid}/source_preview.obj`;
    const designPngUrl =
      boot.design_png_url || `/runs/_design_domain/${sid}/design_preview.preview.png`;
    const sourcePngUrl =
      boot.source_png_url || `/runs/_design_domain/${sid}/source_preview.preview.png`;
    showVizGallery(base(), {
      title: "Phase I · 设计域几何",
      items: [
        { label: "设计域 design_preview.obj", url: designObjUrl, png: designPngUrl, kind: "mesh" },
        { label: "源几何 source_preview.obj", url: sourceObjUrl, png: sourcePngUrl, kind: "mesh" },
      ],
      focus: true,
    });
    ctx.appendDesignDomainChat?.(
      "agent",
      "已进入设计域并加载 **design_preview.obj**（中栏预览页签）。" +
        "静力工况默认：**顶面中心环载**（黄箭头）+ **三底角底圆弧固定**（红点）；Build 时可改力方向。" +
        "右侧「窗口」总览已登记可视化 / 参数 / 方案 / 版本树；点「可视化」可重看 3D。",
    );
    setCoach("② 设计域已就绪 · 请看右侧 3D 与中栏预览", boot.io);
    await sleep(4800);
    try {
      ensureOverview().hideAll();
    } catch {
      /* ignore */
    }

    setCoach("②b 引导设计域智能体盘点文件…");
    const agentPrompt =
      "【全流程演示 · 请执行】这是 BESO7 演示会话。请：\n" +
      "1) 列出会话目录关键文件；\n" +
      "2) 打开或摘要 03_for_beso.inp / build_plan.md；\n" +
      "3) 用中文说明设计域已就绪，下一步可能出现网格质量失败并触发重规划。\n" +
      "不要删除文件，不要重新跑完整 FreeCAD 网格（产物已就绪）。";
    try {
      const sent = await ctx.designDomainAgentUi?.sendMessage?.(agentPrompt);
      if (!sent) {
        ctx.appendDesignDomainChat?.("agent", "（智能体发送接口未就绪，继续流程演示）");
      } else {
        await sleep(6500);
      }
    } catch (e) {
      ctx.appendDesignDomainChat?.("agent", `智能体引导：${e?.message || e}`);
    }
    await sleep(2000);

    setCoach("③ 设计域内部 · 网格质量异常 → ρₚ 重规划…");
    await sleep(800);
    // 重规划期间清屏悬浮窗，聚焦设计域 Plan + 智能体旅程（贴合论文：内部发现→内部处置）
    try {
      ensureOverview().hideAll();
    } catch {
      /* ignore */
    }
    ctx.ensureDdPlanRailStepsIfEmpty?.();
    ctx.appendDesignDomainChat?.(
      "agent",
      "**内部监测**：体网格诊断发现翻转单元 / 质量过低（`mesh_quality_min=0.12`, `error_code=-5`）。" +
        "将在本设计域 Plan 第 3 步与智能体时间线中走完「检测→诊断→重规划→恢复」闭环，而不是跳到外部页面。",
    );
    await sleep(1800);
    const mesh = await api("/api/demo/beso7-live-pipeline/mesh-replan", {
      method: "POST",
      body: JSON.stringify({ task_id: tid, session_id: sid }),
    });
    setCoach("③ 正在设计域内播放重规划旅程…", mesh.io);
    const presented = ctx.presentReplanJourney?.(mesh, {
      animate: true,
      persist: true,
      host: "design_domain",
    });
    try {
      await presented?.done;
    } catch {
      await sleep(6000);
    }
    ctx.appendDesignDomainChat?.(
      "agent",
      `重规划闭环完成：ρₚ=1` +
        (mesh.version?.commit?.commit_id ? ` · version=${String(mesh.version.commit.commit_id).slice(0, 8)}…` : "") +
        "。Plan 第 3 步已同步为恢复态。",
    );
    setCoach("③ 网格重规划完成 · 内部 Plan 已同步", mesh.io);
    await sleep(2800);

    const gate = await api("/api/demo/beso7-live-pipeline/check-gate", {
      method: "POST",
      body: JSON.stringify({ task_id: tid }),
    });
    ctx.appendDesignDomainChat?.(
      "agent",
      gate.ok
        ? "相位闸意外通过。"
        : `相位闸拦截 finalize：${gate.verdict?.reason || "ρₚ≠0"}（演示下一步会清 ρ 后收尾）。`,
    );
    setCoach("③b 相位闸拦截 finalize（论文安全闸）", gate.io);
    await sleep(3500);

    setCoach("④ finalize · 从清单灌入 BESO θ…");
    const fin = await api("/api/demo/beso7-live-pipeline/finalize", {
      method: "POST",
      body: JSON.stringify({ task_id: tid, session_id: sid, clear_rho: true }),
    });
    ctx.state.uploadedSourceDir = fin.scan_dir || ctx.state.uploadedSourceDir;
    ctx.state.oc4DesignDomainFinalized = true;
    if (ctx.refs?.scanDirInput) ctx.refs.scanDirInput.value = ctx.state.uploadedSourceDir || "";
    const bt = fin.beso_theta || {};
    if (Number.isFinite(Number(bt.mass_goal_ratio)) && ctx.refs?.massGoal) {
      ctx.refs.massGoal.value = String(bt.mass_goal_ratio);
    }
    if (Number.isFinite(Number(bt.filter_radius)) && ctx.refs?.filterR) {
      ctx.refs.filterR.value = String(bt.filter_radius);
    }
    try {
      ctx.persistTopologySettingsImmediate?.();
    } catch {
      /* ignore */
    }
    ctx.appendDesignDomainChat?.(
      "agent",
      `finalize 完成 · θ from ${bt.source || "checklist"}（mg=${bt.mass_goal_ratio}）。即将进入编排台。`,
    );
    setCoach("④ finalize 完成 · θ 已写入", fin.io);
    await sleep(3200);

    setCoach("⑤ 进入编排功能区（流式说明）…");
    try {
      await api(`/api/workflow/clear-rho?task_id=${encodeURIComponent(tid)}`, { method: "POST" });
    } catch {
      /* ignore */
    }
    await ctx.layout.playLandingSubflowBridge?.({ kind: "orchestrate", minMs: 1600 });
    if (typeof ctx.beginOrchestrationAfterLanding === "function") {
      await ctx.beginOrchestrationAfterLanding({
        skipUserBubble: true,
        suppressExecutePrompt: true,
        taskTitle: "全流程演示 · BESO7",
        userMessage:
          "【全流程演示】BESO7 设计域已收尾。请按编排四步扫描清单、生成 BESO 配置、绑定预览后等待执行。",
      });
    } else {
      ctx.layout.showStage("orchestrate");
    }
    // Keep sidebar title correct even if orchestration stream races
    await ctx.taskManager?.upsertTask?.(
      {
        title: "全流程演示 · BESO7",
        file_name: "BESO7.FCStd",
        ui_stage: "orchestrate",
        status: "orchestrating",
        progress: 55,
        step: 2,
      },
      { taskId: tid, allowSidebarReorder: true },
    );
    await ctx.taskManager?.loadTasks?.().catch(() => {});
    setDemoLiveBesoBlocked(true);
    await sleep(1800);

    const orch = await api("/api/demo/beso7-live-pipeline/orchestrate", {
      method: "POST",
      body: JSON.stringify({
        task_id: tid,
        checklist_id: cid,
        scan_dir: fin.scan_dir,
        mass_goal_ratio: bt.mass_goal_ratio ?? 0.15,
        filter_radius: bt.filter_radius ?? 2.0,
      }),
    });
    const seed = orch.seed || {};
    if (seed.ok === false) {
      throw new Error(`演示拓扑种子失败：${seed.error || "unknown"}`);
    }
    ctx.state.jobId = orch.job_id;
    window.__beso7DemoSeededJobId = orch.job_id;
    setDemoLiveBesoBlocked(true);
    if (ctx.refs?.jobIdEl) ctx.refs.jobIdEl.textContent = orch.job_id;
    if (ctx.refs?.statusEl) ctx.refs.statusEl.textContent = "completed";
    ctx.state.currentTaskStatus = "completed";
    await ctx.taskManager?.upsertTask?.(
      {
        title: "全流程演示 · BESO7",
        job_id: orch.job_id,
        status: "completed",
        progress: 90,
        step: 3,
        ui_stage: "flow",
        scan_dir: fin.scan_dir,
      },
      { taskId: tid },
    );
    setCoach("⑤ 逐步优化回放：file001_state0 → …（非终态直出）", seed.io || orch.io);

    try {
      ctx.layout.setStep?.(3);
      ctx.layout.showStage?.("flow");
    } catch {
      ctx.layout.showStage?.("orchestrate");
    }
    clearMetricsEmpty();
    try {
      ctx.connectWs?.();
    } catch {
      /* ignore */
    }
    await sleep(400);
    loadDemoMetrics(ctx, orch.job_id, seed.curve_urls || []);
    try {
      await ctx.hydrateDefaultImages?.();
    } catch {
      /* ignore */
    }
    // Re-apply seed curves after hydrate (guards against failed-job empty state)
    loadDemoMetrics(ctx, orch.job_id, seed.curve_urls || []);
    const evolution = Array.isArray(seed.evolution) ? seed.evolution : [];
    const meshUrl = seed.latest_mesh_url || `/runs/${orch.job_id}/latest.obj`;
    const finalMesh = seed.final_mesh_url || meshUrl;
    try {
      await ctx.viewer?.loadMesh?.(meshUrl);
      ctx.state.meshReady = true;
      ctx.checkStep3Ready?.();
    } catch {
      /* ignore */
    }
    // Play topology evolution frames step by step (file001 → …)
    if (evolution.length) {
      setCoach(`⑤ 拓扑逐步演化（1/${evolution.length}）…`);
      for (let i = 0; i < evolution.length; i++) {
        const fr = evolution[i];
        setCoach(`⑤ ${fr.label || `帧 ${i + 1}`}（${i + 1}/${evolution.length}）`);
        try {
          await ctx.viewer?.loadMesh?.(fr.obj);
        } catch {
          /* ignore */
        }
        await sleep(i === 0 ? 1600 : 900);
      }
      try {
        await ctx.viewer?.loadMesh?.(finalMesh);
      } catch {
        /* ignore */
      }
    }
    const evoItems = evolution.slice(0, 6).map((fr) => ({
      label: fr.label || `iter ${fr.iter}`,
      url: fr.obj,
      png: fr.png || "",
      kind: "mesh",
    }));
    showVizGallery(base(), {
      title: "Phase II · 自 file001 逐步优化",
      items: [
        {
          label: "设计域 · BESO7.FCStd",
          url: designObjUrl,
          png: designPngUrl,
          kind: "mesh",
        },
        { label: "Mass 曲线（全历程）", url: `/runs/${orch.job_id}/Mass.png`, kind: "img" },
        { label: "FI_mean", url: `/runs/${orch.job_id}/FI_mean.png`, kind: "img" },
        ...evoItems,
      ],
    });
    ctx.layout.addBubble?.(
      "agent",
      "**逐步优化回放**：设计域来自 `BESO7.FCStd`；FEM 输入为 FCStd→`Analysis-beso.inp`；" +
        "拓扑从 `file001_state0.inp` 起逐步演化（非直接终态 dump）。",
      { format: "md" },
    );
    await sleep(2800);

    // ⑤b Phase III · 拓扑结果重构（参数化）
    setCoach("⑤b Phase III · 拓扑结果 → 参数化重构…");
    const recon = await api("/api/demo/beso7-live-pipeline/reconstruct", {
      method: "POST",
      body: JSON.stringify({ task_id: tid, job_id: orch.job_id }),
    });
    setCoach("⑤b 参数化重构完成", recon.io);
    if (recon.reconstructed_mesh_url) {
      try {
        await ctx.viewer?.loadMesh?.(recon.reconstructed_mesh_url);
      } catch {
        /* ignore */
      }
    }
    showVizGallery(base(), {
      title: "Phase III · 拓扑 → 参数化重构",
      items: [
        {
          label: "拓扑终态",
          url: recon.topology_mesh_url || finalMesh,
          png: recon.topology_png_url || "",
          kind: "mesh",
        },
        {
          label: "参数化重构（柱+顶盘）",
          url: recon.reconstructed_mesh_url || finalMesh,
          png: recon.reconstructed_png_url || "",
          kind: "mesh",
        },
        {
          label: "Mass 曲线",
          url: `/runs/${orch.job_id}/Mass.png`,
          kind: "img",
        },
      ],
    });
    ctx.layout.addBubble?.(
      "agent",
      `**几何重构**：拓扑保留相拟合为变径柱 + 顶盘参数体（mode=\`${recon.mode || "—"}\`），` +
        "写入 `measurements.json`，作为尺寸优化输入。",
      { format: "md" },
    );
    await sleep(3200);

    // ⑤c Phase III · 尺寸优化（壳用钢 + 平台库 restruction）
    setCoach("⑤c Phase III · 尺寸优化（壳用钢 + 平台库收尾 · pitch≤5°）…");
    const sizing = await api("/api/demo/beso7-live-pipeline/sizing", {
      method: "POST",
      body: JSON.stringify({ task_id: tid, job_id: orch.job_id, target_power_mw: 20 }),
    });
    const prest = sizing.platform_restruction || {};
    setCoach(
      `⑤c 尺寸优化完成 · 壳用钢 ${sizing.steel_intensity_t_per_MW ?? "—"} t/MW · ` +
        `平台库(${prest.base_name || "—"}) x=${prest.extra_scale_x ?? "—"} · pitch ${sizing.pitch_angle_deg ?? "—"}°`,
      sizing.io,
    );
    if (sizing.reconstructed_mesh_url) {
      try {
        await ctx.viewer?.loadMesh?.(sizing.reconstructed_mesh_url);
      } catch {
        /* ignore */
      }
    }
    showVizGallery(base(), {
      title: "Phase III · 尺寸优化（用钢 + 平台库）",
      items: [
        {
          label: "参数化几何",
          url: sizing.reconstructed_mesh_url || recon.reconstructed_mesh_url || finalMesh,
          png: sizing.reconstructed_png_url || recon.reconstructed_png_url || "",
          kind: "mesh",
        },
        {
          label: "钢耗–尺度曲线",
          url: sizing.curve_url || `/runs/${orch.job_id}/sizing_curve.png`,
          kind: "img",
        },
        {
          label: "FI_mean",
          url: `/runs/${orch.job_id}/FI_mean.png`,
          kind: "img",
        },
      ],
    });
    const optCols = prest.scaled_optimized || {};
    ctx.layout.addBubble?.(
      "agent",
      `**尺寸优化（双路径）**\n` +
        `- 壳用钢：pitch≤5° 下 \`${sizing.optimizer || "SLSQP"}\` → **${sizing.steel_intensity_t_per_MW ?? "—"} t/MW**` +
        `（x=${sizing.extra_scale_x ?? "—"}，结构 ${sizing.struct_mass_t ?? "—"} t）\n` +
        `- 平台库收尾（OC4/DTU/VolturnUS）：基型 **${prest.base_name || "—"}**，min x³ → x=${prest.extra_scale_x ?? "—"}，` +
        `柱径≈${optCols.offset_col_dia != null ? Number(optCols.offset_col_dia).toFixed(2) : "—"} m，` +
        `间距≈${optCols.spacing != null ? Number(optCols.spacing).toFixed(1) : "—"} m，` +
        `库估钢耗 ${prest.steel_intensity_t_per_MW ?? "—"} t/MW。`,
      { format: "md" },
    );
    await sleep(3500);

    // ⑤d Phase III · Zwind 时域校核（尺寸优化后）
    setCoach("⑤d Phase III · Zwind 时域校核（zwind_newmodel · Fig. 2b–e）…");
    const zwind = await api("/api/demo/beso7-live-pipeline/zwind", {
      method: "POST",
      body: JSON.stringify({ task_id: tid, job_id: orch.job_id, platform: "ai" }),
    });
    const zhl = zwind.highlights || {};
    const zchk = zwind.pass_checks || {};
    setCoach(
      `⑤d Zwind 完成 · FA ${zhl.tower_1st_fa_hz ?? "—"} Hz · DLC6.1 pitch ${zhl.extreme_pitch_deg ?? "—"}°`,
      zwind.io,
    );
    const zwindItems = (zwind.panel_urls || []).map((p) => ({
      label: p.label || "Fig.2",
      url: p.url,
      kind: "img",
    }));
    if (zwindItems.length) {
      showVizGallery(base(), {
        title: "Phase III · Zwind 时域校核（AI vs TuQiang）",
        items: zwindItems,
      });
    }
    ctx.layout.addBubble?.(
      "agent",
      `**Zwind 时域校核**：尺寸优化后接入 \`third_party/zwind_newmodel\`（\`${zwind.mode || "paper_fig2_import"}\`）。\n\n` +
        `| 指标 | 数值 |\n|---|---|\n` +
        `| 塔架 1st FA | **${zhl.tower_1st_fa_hz ?? "—"} Hz** |\n` +
        `| 发电工况 pitch | ${zhl.operating_pitch_deg ?? "—"}°（限 ${zhl.pitch_limit_operating_deg ?? "—"}°） |\n` +
        `| 极限 DLC6.1 pitch | **${zhl.extreme_pitch_deg ?? "—"}°**（限 ${zhl.pitch_limit_extreme_deg ?? "—"}° · ${zchk.extreme_pitch_within_limit ? "通过" : "复核"}） |\n` +
        `| 系泊峰值张力 | **${zhl.max_mooring_tension_kn ?? "—"} kN**（${zchk.mooring_within_limit ? "通过" : "复核"}） |\n` +
        `| 塔基 My | ${zhl.tower_base_my_mnm ?? "—"} MN·m |\n\n` +
        `报告：\`${zwind.report_url || `/runs/${orch.job_id}/zwind_report.json`}\``,
      { format: "md" },
    );
    await sleep(4000);

    setCoach("⑥ 求解侧 Fₚ 信号 → 弹窗播放 replan 旅程…");
    try {
      ensureOverview().hideAll();
    } catch {
      /* ignore */
    }
    // Stay on flow stage; show modal so animation is visible
    try {
      ctx.layout.setStep?.(3);
      ctx.layout.showStage?.("flow");
    } catch {
      /* ignore */
    }
    const solver = await api("/api/demo/beso7-live-pipeline/solver-replan", {
      method: "POST",
      body: JSON.stringify({ task_id: tid, job_id: orch.job_id }),
    });
    const solverPresented = ctx.presentReplanJourney?.(solver, {
      animate: true,
      persist: false,
      host: "modal",
      title: "求解失败 → 重规划旅程",
      holdMs: 1600,
    });
    try {
      await solverPresented?.done;
    } catch {
      await sleep(4500);
    }
    // Keep Mass/FI visible after modal
    loadDemoMetrics(ctx, orch.job_id, seed.curve_urls || []);
    try {
      await api(`/api/workflow/clear-rho?task_id=${encodeURIComponent(tid)}`, { method: "POST" });
    } catch {
      /* ignore */
    }
    await sleep(1200);

    setCoach("⑦ Phase IV · 五方案对比 · 请在左侧面板选择…");
    const cands = await api("/api/demo/beso7-live-pipeline/candidates", {
      method: "POST",
      body: JSON.stringify({ task_id: tid, auto_select: false }),
    });
    cands.task_id = tid;
    const pick = await showCandidatePanelInteractive(base(), cands, { api, timeoutMs: 75000 });
    const selected = pick.selected || {};
    if (selected.preview_url) {
      try {
        await ctx.viewer?.loadMesh?.(selected.preview_url);
      } catch {
        try {
          await ctx.viewer?.loadMesh?.(meshUrl);
        } catch {
          /* ignore */
        }
      }
    }
    setCoach(`⑦ 已选定：${selected.label || "方案"}`, pick.io || cands.io);
    ctx.layout.addLandingBubble?.(
      "agent",
      `**Phase IV · Automated Reviewer**：登记五方案；您${pick.via === "user" ? "手动" : "超时后按推荐"}选定 **${selected.label || "—"}**` +
        `（S=${selected.overall_score ?? "—"}）。已写入 versions。`,
      { format: "md" },
    );
    await sleep(3500);

    setCoach("⑧ 生成类 git 版本树…");
    const tree = await api(
      `/api/demo/beso7-live-pipeline/version-tree?task_id=${encodeURIComponent(tid)}`,
    );
    showVersionTreePanel(base(), tree);
    setCoach("⑧ 版本树就绪 · 进入验证…", tree.process);
    ctx.layout.addLandingBubble?.(
      "agent",
      `**版本审计树**已生成：${tree.structure?.total_commits || 0} 个提交，车道：${(tree.structure?.lanes || []).join(" / ")}。`,
      { format: "md" },
    );
    await sleep(2200);

    setCoach("⑨ Phase V · Automated Reviewer 验证打分…");
    let validation = null;
    try {
      validation = await api("/api/demo/beso7-live-pipeline/validate", {
        method: "POST",
        body: JSON.stringify({
          task_id: tid,
          checklist_id: cid,
          candidate_label: selected.label || "BESO7 · 选定方案",
        }),
      });
      showValidationPanel(base(), validation);
      setCoach(
        `⑨ 验证完成 · S=${validation.overall_score ?? "—"} · ${validation.grade || ""}`,
        validation.io,
      );
      try {
        ctx.layout.showStage?.("landing");
      } catch {
        /* ignore */
      }
      ctx.layout.addLandingValidationCard?.(validation, base());
      ctx.layout.addLandingBubble?.(
        "agent",
        `**Phase V · Automated Reviewer**：S=**${validation.overall_score ?? "—"}**（${validation.grade || "—"}）。` +
          `终止门：${validation.halt_gate?.ok ? "可终止探索" : validation.halt_gate?.reason || "未通过"}。`,
        { format: "md" },
      );
      await sleep(1800);

      if (!validation.halt_gate?.ok) {
        setCoach("⑨b 未达终止门 → AI Review 修正并复验…");
        const replanned = await api("/api/demo/beso7-live-pipeline/review-replan", {
          method: "POST",
          body: JSON.stringify({
            task_id: tid,
            checklist_id: cid,
            candidate_label: `${selected.label || "BESO7"} · 修正`,
            previous_validation: {
              overall_score: validation.overall_score,
              grade: validation.grade,
              halt_gate: validation.halt_gate,
              ai_review_scores: validation.ai_review_scores || {},
            },
          }),
        });
        const after = replanned.validation || replanned;
        showValidationPanel(base(), {
          ...after,
          next_action: after.halt_gate?.ok ? "halt_and_archive" : "continue_explore",
        });
        validation = {
          ...after,
          overall_score: after.overall_score ?? replanned.overall_score,
          grade: after.grade ?? replanned.grade,
          halt_gate: after.halt_gate || replanned.halt_gate,
          figures: after.figures || replanned.figures,
          report_md_url: after.report_md_url || replanned.report_md_url,
          score_json_url: after.score_json_url || replanned.score_json_url,
          ai_review_scores: after.ai_review_scores || replanned.ai_review_scores,
        };
        ctx.layout.addLandingValidationCard?.(validation, base());
        setCoach(
          `⑨b 复验 · S=${validation.overall_score ?? "—"} · ${validation.halt_gate?.ok ? "通过" : "仍未过门"}`,
          replanned.io,
        );
        ctx.layout.addLandingBubble?.(
          "agent",
          `**弱项修正后复验**：S=**${validation.overall_score ?? "—"}**（${validation.grade || "—"}）；` +
            `终止门：${validation.halt_gate?.ok ? "已通过" : validation.halt_gate?.reason || "仍未通过"}。`,
          { format: "md" },
        );
        await sleep(2000);
      } else {
        await sleep(900);
      }
    } catch (e) {
      ctx.layout.addLandingBubble?.("agent", `验证步骤跳过：${e?.message || e}`);
      await sleep(800);
    }

    setCoach("⑩ Phase VI · 生成总布置式工程图…");
    let drawing = null;
    try {
      drawing = await api("/api/demo/beso7-live-pipeline/drawing", {
        method: "POST",
        body: JSON.stringify({ task_id: tid, job_id: orch.job_id, session_id: sid }),
      });
      showDrawingPanel(base(), drawing);
      try {
        ctx.layout.showStage?.("landing");
        ctx.layout.addLandingCadDrawingCard?.(drawing, base());
      } catch {
        /* ignore */
      }
      setCoach("⑩ 工程图已生成（原始柱体+光滑优化结构）", drawing.io);
      ctx.layout.addLandingBubble?.(
        "agent",
        `**Phase VI · 工程图**：原始边柱/桩靴 + 优化光滑斜撑/顶盘实体轮廓出图` +
          `（drawing_id=${String(drawing.drawing_id || "").slice(0, 8)}…）。`,
        { format: "md" },
      );
      await sleep(2800);
    } catch (e) {
      ctx.layout.addLandingBubble?.("agent", `工程图步骤跳过：${e?.message || e}`);
      await sleep(800);
    }

    setCoach("⑪ 汇总交付总览 · 闭环可视化…");
    try {
      const deliver = await api("/api/demo/beso7-live-pipeline/deliverables", {
        method: "POST",
        body: JSON.stringify({
          task_id: tid,
          job_id: orch.job_id,
          session_id: sid,
          selected_label: selected.label || null,
          validation: validation
            ? {
                overall_score: validation.overall_score,
                grade: validation.grade,
                figures: validation.figures,
                score_json_url: validation.score_json_url,
                report_md_url: validation.report_md_url,
              }
            : null,
          drawing: drawing
            ? {
                drawing_id: drawing.drawing_id,
                sheet_url: drawing.sheet_url,
                manifest_url: drawing.manifest_url,
              }
            : null,
        }),
      });
      showDeliverablesPanel(base(), deliver);
      setCoach("✓ 全流程闭环完成 · I–VI + 交付总览", deliver.process);
      ensureCoach().classList.add("is-done");
      ctx.layout.addLandingBubble?.(
        "agent",
        `**交付总览**：共 **${(deliver.files || []).length}** 个关键文件、**${(deliver.gallery || []).length}** 项可视化。` +
          `右侧「交付总览」可浏览设计域→优化→验证→工程图全链路产物。`,
        { format: "md" },
      );
      await sleep(3500);
    } catch (e) {
      setCoach("✓ 全流程完成（交付总览未生成）");
      ensureCoach().classList.add("is-done");
      ctx.layout.addLandingBubble?.("agent", `交付总览跳过：${e?.message || e}`);
      await sleep(1200);
    }

    if (ctx.refs?.msgLanding) {
      try {
        ctx.layout.showStage?.("landing");
        await sleep(400);
        /* 直接写收尾摘要，勿走 sendLandingAssistantChat（会误触发「网格重规划」演示） */
        ctx.layout.addLandingBubble?.(
          "agent",
          `**全流程演示完成（Phase I–VI）**\n\n` +
            `- 设计清单已锁定（容量 20 MW）\n` +
            `- 设计域检查与 BESO 逐步回放完成\n` +
            `- 拓扑重构 + 尺寸优化（壳用钢 ${sizing?.steel_intensity_t_per_MW ?? "—"} t/MW` +
            ` · 平台库 x=${sizing?.platform_restruction?.extra_scale_x ?? "—"}）\n` +
            `- Zwind 时域（DLC6.1 pitch ${zwind?.highlights?.extreme_pitch_deg ?? "—"}° · 系泊 ${zwind?.highlights?.max_mooring_tension_kn ?? "—"} kN）\n` +
            `- Automated Reviewer 选定 **${selected.label || "方案"}**\n` +
            `- 验证 S=**${validation?.overall_score ?? "—"}**（${validation?.grade || "—"}）` +
            `${validation?.halt_gate?.ok ? "，终止门通过" : ""}\n` +
            `- 工程图已生成并同步主页\n\n` +
            `底部「窗口」可切换可视化 / 验证 / 工程图 / 交付总览。`,
          { format: "md" },
        );
        ctx.persistLandingAssistantThread?.(tid);
      } catch {
        /* ignore */
      }
      await sleep(1200);
      try {
        ensureOverview().focus("deliverables", { remount: false, keepCollapsed: false });
      } catch {
        /* ignore */
      }
    }

    stripDemoQuery();
    return true;
  } catch (e) {
    setCoach(`演示失败：${e?.message || e}`);
    try {
      ctx.layout.addLandingBubble("agent", `全流程演示失败：${e?.message || e}`);
    } catch {
      /* ignore */
    }
    return false;
  } finally {
    window.__beso7DemoRunning = false;
    // Keep seeded job id so createAndRun stays blocked for this job;
    // clear the global "active" lock so other tasks can run.
    window.__beso7DemoActive = false;
    const ids = ["executePlannedTask", "acceptStep1", "startBtn"];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el && window.__beso7DemoSeededJobId !== "pending") {
        // leave accept/start enabled for UX but createAndRun still guards
        if (id === "executePlannedTask") el.disabled = false;
      }
    }
  }
}
