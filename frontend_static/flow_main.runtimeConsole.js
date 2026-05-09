/**
 * 顶栏「运行控制台」：聚合主任务 / WebSocket / 轮询、侧栏流式、CAD 转换、设计域遮罩、编排等状态，
 * 并采样 JS 堆内存曲线与 /health 延迟（Chrome 下 memory 较完整）。
 */

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtBytes(n) {
  const x = Number(n);
  if (!Number.isFinite(x) || x < 0) return "—";
  if (x < 1024) return `${Math.round(x)} B`;
  if (x < 1024 * 1024) return `${(x / 1024).toFixed(1)} KB`;
  return `${(x / (1024 * 1024)).toFixed(1)} MB`;
}

function approxStorageEntryBytes(key, val) {
  try {
    return new Blob([String(key ?? ""), String(val ?? "")]).size;
  } catch {
    return (String(key).length + String(val).length) * 2;
  }
}

/**
 * @param {() => { task_id?: string; title?: string }[]} getCachedTaskItems
 */
function scanLocalStorageBreakdown(getCachedTaskItems) {
  /** @type {{ key: string; size: number }[]} */
  const besoItems = [];
  let totalAll = 0;
  try {
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (!key) continue;
      const val = localStorage.getItem(key) || "";
      const sz = approxStorageEntryBytes(key, val);
      totalAll += sz;
      if (key.startsWith("beso.")) besoItems.push({ key, size: sz });
    }
  } catch {
    return { totalAll: 0, besoItems: [], groups: [], besoOther: 0 };
  }
  const rows = typeof getCachedTaskItems === "function" ? getCachedTaskItems() : [];
  const titleOf = (id) => {
    const t = rows.find((r) => String(r?.task_id || "").trim() === id);
    const tt = String(t?.title || "").trim();
    return tt || `任务 ${id.slice(0, 8)}…`;
  };
  /** @type {Map<string, { taskId: string; label: string; size: number; chunks: { kind: string; size: number }[] }>} */
  const byTask = new Map();
  let besoOther = 0;
  const add = (taskId, kind, size) => {
    if (!byTask.has(taskId)) {
      byTask.set(taskId, { taskId, label: titleOf(taskId), size: 0, chunks: [] });
    }
    const g = byTask.get(taskId);
    if (!g) return;
    g.size += size;
    g.chunks.push({ kind, size });
  };
  for (const { key, size } of besoItems) {
    let m;
    if ((m = key.match(/^beso\.landingThread\.(.+)$/))) add(m[1], "侧栏对话", size);
    else if ((m = key.match(/^beso\.dd\.agentUi\.v1\.t\.(.+)$/))) add(m[1], "设计域智能体 / 工具与文件事件", size);
    else if ((m = key.match(/^beso\.dd\.ideTabs\.v1\.t\.(.+)$/))) add(m[1], "设计域已打开文件标签", size);
    else besoOther += size;
  }
  const groups = [...byTask.values()].sort((a, b) => b.size - a.size);
  return { totalAll, besoItems, groups, besoOther };
}

function isTaskScopedStorageKey(key) {
  const k = String(key || "");
  return (
    /^beso\.landingThread\./.test(k) || /^beso\.dd\.agentUi\.v1\.t\./.test(k) || /^beso\.dd\.ideTabs\.v1\.t\./.test(k)
  );
}

/**
 * 非「按任务归档」键：设置、侧栏、设计域临时会话等，按前缀聚合。
 */
function scanGlobalStorageBuckets() {
  let totalAll = 0;
  let taskScopedBytes = 0;
  /** @type {Map<string, number>} */
  const bucket = new Map();
  try {
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (!key) continue;
      const val = localStorage.getItem(key) || "";
      const sz = approxStorageEntryBytes(key, val);
      totalAll += sz;
      if (isTaskScopedStorageKey(key)) {
        taskScopedBytes += sz;
        continue;
      }
      if (key.startsWith("beso.")) {
        const segs = key.split(".");
        const buck = segs.length >= 2 ? `${segs[0]}.${segs[1]}` : "beso";
        bucket.set(buck, (bucket.get(buck) || 0) + sz);
      } else {
        const nk = "· 非 beso 键";
        bucket.set(nk, (bucket.get(nk) || 0) + sz);
      }
    }
  } catch {
    return { totalAll: 0, taskScopedBytes: 0, globalBytes: 0, rows: [] };
  }
  const rows = [...bucket.entries()]
    .map(([label, size]) => ({ label, size }))
    .sort((a, b) => b.size - a.size);
  const globalBytes = Math.max(0, totalAll - taskScopedBytes);
  return { totalAll, taskScopedBytes, globalBytes, rows };
}

function bucketLabelZh(buck) {
  const m = {
    "beso.settings": "偏好与连接",
    "beso.sidebar": "侧栏状态",
    "beso.ui": "界面状态",
    "beso.landingThread": "侧栏（非任务键名）",
    "beso.dd": "设计域通用（临时会话等）",
    "· 非 beso 键": "其他命名空间",
  };
  return m[buck] || `${buck} · 前缀汇总`;
}

/**
 * @param {HTMLElement | null | undefined} el
 * @param {{ headline: string; valueLine: string; subLine: string; pct: number; variant?: "mint" | "violet" }} o
 */
function renderStorageDonutHero(el, o) {
  if (!el) return;
  const innerMod =
    o.variant === "mint" ? " topConsoleStHeroInner--mint" : o.variant === "violet" ? " topConsoleStHeroInner--violet" : "";
  const progClass =
    o.variant === "mint" ? "topConsoleStDonutProg topConsoleStDonutProg--mint" : "topConsoleStDonutProg";
  const dash = Math.max(0, Math.min(100, Number(o.pct) || 0));
  el.innerHTML = `
    <div class="topConsoleStHeroInner${innerMod}">
      <div class="topConsoleStDonut" aria-hidden="true">
        <svg class="topConsoleStDonutSvg" viewBox="0 0 36 36">
          <g transform="rotate(-90 18 18)">
            <circle class="topConsoleStDonutTrack" cx="18" cy="18" r="14" fill="none" stroke-width="3" />
            <circle class="${progClass}" cx="18" cy="18" r="14" fill="none" stroke-width="3" stroke-linecap="round"
              pathLength="100" stroke-dasharray="100" stroke-dashoffset="${100 - dash}" />
          </g>
        </svg>
      </div>
      <div class="topConsoleStHeroTxt">
        <div class="topConsoleStHeroK">${esc(o.headline)}</div>
        <div class="topConsoleStHeroVal">${esc(o.valueLine)}</div>
        <div class="topConsoleStHeroSub">${esc(o.subLine)}</div>
      </div>
    </div>`;
}

/** @type {ReadonlySet<string>} */
const TRACK_TONES = new Set(["idle", "active", "working", "stream", "pending", "run", "paused", "orchestrate"]);

function trackToneClass(t) {
  const raw = String(t?.tone || (t?.busy ? "active" : "idle"));
  return TRACK_TONES.has(raw) ? raw : "idle";
}

function collectTracks(refs, state) {
  /** @type {{ id: string; label: string; meta: string; badge: string; busy: boolean; tone: string }[]} */
  const out = [];
  const st = String(state.currentTaskStatus || refs.statusEl?.textContent || "").toLowerCase();
  const jobBusy = Boolean(state.jobId && ["running", "queued", "pending"].includes(st));
  const wsLive = Boolean(typeof WebSocket !== "undefined" && state.ws && state.ws.readyState === WebSocket.OPEN);
  const pollLive = Boolean(state.jobPollTimer);
  const summaryLive = Boolean(state.summaryRefreshTimer);
  if (state.jobId || wsLive || pollLive || summaryLive) {
    const parts = [];
    if (state.jobId) parts.push(`Job ${String(state.jobId).slice(0, 12)}…`);
    parts.push(`状态 ${refs.statusEl?.textContent || state.currentTaskStatus || "—"}`);
    if (wsLive) parts.push("WS 已连接");
    if (pollLive) parts.push("轮询快照");
    if (summaryLive) parts.push("指标刷新");
    const busy = jobBusy || wsLive || pollLive || summaryLive;
    out.push({
      id: "job",
      label: "主计算链路",
      meta: parts.join(" · "),
      badge: busy ? "活动" : "空闲",
      busy,
      tone: busy ? "active" : "idle",
    });
  }
  if (state.landingChatFlight) {
    const tid = String(state.landingChatFlight.taskId || "").slice(0, 10);
    out.push({
      id: "landing",
      label: "侧栏对话（流式）",
      meta: tid ? `任务 ${tid}…` : "生成中",
      badge: "流式",
      busy: true,
      tone: "stream",
    });
  } else if (state.landingAssistantPending) {
    out.push({
      id: "landing-p",
      label: "侧栏对话",
      meta: "等待助手响应",
      badge: "等待",
      busy: true,
      tone: "pending",
    });
  }
  if (state.titleSummarizeAbort) {
    out.push({
      id: "title",
      label: "任务标题摘要",
      meta: "向模型请求短标题",
      badge: "请求",
      busy: true,
      tone: "pending",
    });
  }
  const cadModal = refs.cadConvertModal;
  const cadOpen = Boolean(cadModal && !cadModal.classList.contains("hidden"));
  if (cadOpen) {
    const stage = String(refs.cadConvertStage?.textContent || "").trim() || "CAD 转换进行中";
    out.push({
      id: "cad",
      label: "IGES → INP（CAD）",
      meta: state.cadPollPaused ? `${stage}（已暂停）` : stage,
      badge: state.cadPollPaused ? "暂停" : "运行",
      busy: !state.cadPollPaused,
      tone: state.cadPollPaused ? "paused" : "run",
    });
  }
  const leftBusy = Boolean(refs.designDomainLeftOverlay && !refs.designDomainLeftOverlay.classList.contains("hidden"));
  const rightBusy = Boolean(refs.designDomainRightOverlay && !refs.designDomainRightOverlay.classList.contains("hidden"));
  if (leftBusy || rightBusy) {
    const bits = [];
    if (leftBusy) bits.push("几何预览");
    if (rightBusy) bits.push("设计域网格");
    out.push({
      id: "dd",
      label: "设计域（OC4）",
      meta: bits.join(" · "),
      badge: "忙碌",
      busy: true,
      tone: "working",
    });
  }
  const orchVisible = Boolean(refs.orchestrateMain && !refs.orchestrateMain.classList.contains("hidden"));
  if (orchVisible && st === "orchestrating") {
    out.push({
      id: "orch",
      label: "构型优化编排",
      meta: "流式说明与轨道推进",
      badge: "编排",
      busy: true,
      tone: "orchestrate",
    });
  }
  return out;
}

/**
 * @param {{
 *   refs: Record<string, HTMLElement | null>;
 *   state: object;
 *   normalizedBaseUrl: () => string;
 *   getCachedTaskItems?: () => { task_id?: string; title?: string }[];
 *   onTrackActivate?: (track: { id: string }) => void;
 * }} ctx
 */
export function mountRuntimeConsole(ctx) {
  const { refs, state, normalizedBaseUrl, getCachedTaskItems = () => [] } = ctx;
  const trigger = refs.topConsoleTrigger;
  const backdrop = refs.topConsoleBackdrop;
  const panel = refs.topConsolePanel;
  const closeBtn = refs.topConsoleClose;
  const tracksEl = refs.topConsoleTracks;
  const memCanvas = refs.topConsoleMemCanvas;
  const memLegend = refs.topConsoleMemLegend;
  const netEl = refs.topConsoleNet;
  const pulse = refs.topConsolePulseRing;
  const subEl = refs.topConsoleTriggerSub;
  const mainTrack = refs.topConsoleMainTrack;
  const mainSeg = refs.topConsoleMainSeg;
  const storageTrack = refs.topConsoleStorageTrack;
  const storageSeg = refs.topConsoleStorageSeg;
  const heroTask = refs.topConsoleStorageHeroTask;
  const listTask = refs.topConsoleStorageListTask;
  const heroGlobal = refs.topConsoleStorageHeroGlobal;
  const listGlobal = refs.topConsoleStorageListGlobal;

  if (!trigger || !panel) return { dispose() {}, closePanel() {} };

  const memPoints = [];
  const MEM_CAP = 56;
  let open = false;
  let lastRtt = /** @type {number | null} */ (null);
  let lastHealthOk = /** @type {boolean | null} */ (null);
  let tickTimer = null;

  /** @type {"task" | "global"} */
  let storageTab = "task";

  /** @type {"monitor" | "storage"} */
  let mainConsoleTab = "monitor";

  const slideMonitorMainEl =
    mainTrack?.querySelector("#topConsoleMainSlideMonitor") ?? mainTrack?.children[0] ?? null;
  const slideStorageMainEl =
    mainTrack?.querySelector("#topConsoleMainSlideStorage") ?? mainTrack?.children[1] ?? null;

  const slideTaskEl = storageTrack?.querySelector("#topConsoleStorageSlideTask") ?? storageTrack?.children[0] ?? null;
  const slideGlobalEl =
    storageTrack?.querySelector("#topConsoleStorageSlideGlobal") ?? storageTrack?.children[1] ?? null;

  function setStorageTab(tab) {
    const t = tab === "global" ? "global" : "task";
    storageTab = t;
    storageTrack?.classList.toggle("topConsoleStorageTrack--global", t === "global");
    storageSeg?.querySelectorAll("[data-storage-tab]").forEach((el) => {
      if (!(el instanceof HTMLElement)) return;
      const on = el.getAttribute("data-storage-tab") === t;
      el.classList.toggle("topConsoleStorageSegBtn--active", on);
      el.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (slideTaskEl instanceof HTMLElement) slideTaskEl.setAttribute("aria-hidden", t === "task" ? "false" : "true");
    if (slideGlobalEl instanceof HTMLElement) slideGlobalEl.setAttribute("aria-hidden", t === "global" ? "false" : "true");
  }

  function onStorageSegClick(e) {
    const btn = e.target.closest("[data-storage-tab]");
    if (!btn || !storageSeg?.contains(btn)) return;
    const tab = btn.getAttribute("data-storage-tab");
    if (tab === "task" || tab === "global") setStorageTab(tab);
  }

  function setMainConsoleTab(tab) {
    const t = tab === "storage" ? "storage" : "monitor";
    mainConsoleTab = t;
    mainTrack?.classList.toggle("topConsoleMainTrack--storage", t === "storage");
    mainSeg?.querySelectorAll("[data-main-tab]").forEach((el) => {
      if (!(el instanceof HTMLElement)) return;
      const on = el.getAttribute("data-main-tab") === t;
      el.classList.toggle("topConsoleMainSegBtn--active", on);
      el.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (slideMonitorMainEl instanceof HTMLElement) {
      slideMonitorMainEl.setAttribute("aria-hidden", t === "monitor" ? "false" : "true");
    }
    if (slideStorageMainEl instanceof HTMLElement) {
      slideStorageMainEl.setAttribute("aria-hidden", t === "storage" ? "false" : "true");
    }
    if (t === "monitor") {
      queueMicrotask(() => drawMemChart());
    }
  }

  function onMainSegClick(e) {
    const btn = e.target.closest("[data-main-tab]");
    if (!btn || !mainSeg?.contains(btn)) return;
    const tab = btn.getAttribute("data-main-tab");
    if (tab === "monitor" || tab === "storage") setMainConsoleTab(tab);
  }

  function setOpen(next) {
    open = Boolean(next);
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
    panel.setAttribute("aria-hidden", open ? "false" : "true");
    backdrop?.setAttribute("aria-hidden", open ? "false" : "true");
    panel.classList.toggle("topConsolePanel--open", open);
    backdrop?.classList.toggle("topConsoleBackdrop--open", open);
    document.body.classList.toggle("topConsoleOpen", open);
    if (open) {
      closeBtn?.focus?.();
      void refreshFull();
    } else {
      trigger.focus?.();
    }
  }

  function toggle() {
    setOpen(!open);
  }

  function renderTracks(tracks) {
    if (!tracksEl) return;
    if (!tracks.length) {
      tracksEl.innerHTML = `<div class="topConsoleEmpty">当前无并发活动 · 子流程启动后将在此汇总</div>`;
      return;
    }
    tracksEl.innerHTML = tracks
      .map(
        (t) => `
      <button type="button" class="topConsoleTrack topConsoleTrack--${trackToneClass(t)}" data-track-id="${esc(t.id)}" title="进入对应活动">
        <div class="topConsoleTrackHd">
          <span class="topConsoleTrackDot" aria-hidden="true"></span>
          <span class="topConsoleTrackName">${esc(t.label)}</span>
          <span class="topConsoleTrackBadge">${esc(t.badge)}</span>
        </div>
        <div class="topConsoleTrackMeta">${esc(t.meta)}</div>
      </button>`,
      )
      .join("");
  }

  function onTracksClick(e) {
    const btn = e.target.closest("button[data-track-id]");
    if (!btn || !tracksEl?.contains(btn)) return;
    const id = btn.getAttribute("data-track-id");
    if (!id) return;
    ctx.onTrackActivate?.({ id });
  }

  function renderStoragePanel() {
    if (!mainTrack || !mainSeg || !storageTrack || !heroTask || !listTask || !heroGlobal || !listGlobal) return;
    const r = scanLocalStorageBreakdown(getCachedTaskItems);
    const g = scanGlobalStorageBuckets();

    const taskBytes = r.groups.reduce((a, x) => a + x.size, 0);
    const taskDonut = r.totalAll > 0 ? Math.min(100, Math.round((100 * taskBytes) / r.totalAll)) : 0;
    renderStorageDonutHero(heroTask, {
      headline: "任务维度缓存",
      valueLine: fmtBytes(taskBytes),
      subLine: `侧栏对话、设计域智能体与已打开文件 · 约占 localStorage ${taskDonut}%`,
      pct: taskDonut,
      variant: "violet",
    });
    const taskRows = r.groups.filter((x) => x.size > 0);
    if (!taskRows.length) {
      listTask.innerHTML = `<div class="topConsoleStorageEmpty">尚无按任务归档的条目 · 在侧栏对话或设计域中操作后会写入；切换「本体存储」可查看全局偏好等。</div>`;
    } else {
      const maxSz = Math.max(...taskRows.map((x) => x.size), 1);
      listTask.innerHTML = taskRows
        .map((gr) => {
          const w = Math.round((100 * gr.size) / maxSz);
          const chips = gr.chunks
            .slice()
            .sort((a, b) => b.size - a.size)
            .map((c) => `<span class="topConsoleStChip" title="${esc(c.kind)}">${esc(c.kind)} · ${esc(fmtBytes(c.size))}</span>`)
            .join("");
          return `<div class="topConsoleStRow">
            <div class="topConsoleStRowHd">
              <span class="topConsoleStRowTitle">${esc(gr.label)}</span>
              <span class="topConsoleStRowBytes mono">${esc(fmtBytes(gr.size))}</span>
            </div>
            <div class="topConsoleStBarWrap" aria-hidden="true"><div class="topConsoleStBar" style="width:${w}%"></div></div>
            <div class="topConsoleStChips">${chips}</div>
          </div>`;
        })
        .join("");
    }

    const globalDonut = g.totalAll > 0 ? Math.min(100, Math.round((100 * g.globalBytes) / g.totalAll)) : 0;
    renderStorageDonutHero(heroGlobal, {
      headline: "本体 / 全局存储",
      valueLine: fmtBytes(g.globalBytes),
      subLine: `不含按任务归档的三类键 · 全站 localStorage 约 ${fmtBytes(g.totalAll)} · 本体占 ${globalDonut}%`,
      pct: globalDonut,
      variant: "mint",
    });
    if (!g.rows.length || g.globalBytes <= 0) {
      listGlobal.innerHTML = `<div class="topConsoleStorageEmpty">暂无全局项或已全部归入任务缓存。</div>`;
    } else {
      const maxG = Math.max(...g.rows.map((x) => x.size), 1);
      listGlobal.innerHTML = g.rows
        .map((row) => {
          const title = bucketLabelZh(row.label);
          const w = Math.round((100 * row.size) / maxG);
          return `<div class="topConsoleStRow topConsoleStRow--global">
            <div class="topConsoleStRowHd">
              <span class="topConsoleStRowTitle">${esc(title)}</span>
              <span class="topConsoleStRowBytes topConsoleStRowBytes--mint mono">${esc(fmtBytes(row.size))}</span>
            </div>
            <div class="topConsoleStBarWrap" aria-hidden="true"><div class="topConsoleStBar topConsoleStBar--mint" style="width:${w}%"></div></div>
            <div class="topConsoleStHintMono mono">${esc(row.label)}</div>
          </div>`;
        })
        .join("");
    }

    setStorageTab(storageTab);
    setMainConsoleTab(mainConsoleTab);
  }

  function sampleMem() {
    try {
      const p = performance.memory;
      if (!p) return null;
      return { used: p.usedJSHeapSize, total: p.totalJSHeapSize, t: Date.now() };
    } catch {
      return null;
    }
  }

  function pushMemSample() {
    const m = sampleMem();
    if (!m) return;
    memPoints.push(m);
    while (memPoints.length > MEM_CAP) memPoints.shift();
  }

  function drawMemChart() {
    if (!memCanvas) return;
    const wrap = memCanvas.parentElement;
    const w = wrap ? wrap.clientWidth : 400;
    const h = 140;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    memCanvas.width = Math.max(1, Math.floor(w * dpr));
    memCanvas.height = Math.floor(h * dpr);
    memCanvas.style.width = `${w}px`;
    memCanvas.style.height = `${h}px`;
    const ctx = memCanvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const pad = { l: 8, r: 8, t: 10, b: 22 };
    const innerW = w - pad.l - pad.r;
    const innerH = h - pad.t - pad.b;
    ctx.fillStyle = "rgba(248,250,252,.95)";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(15,23,42,.08)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 3; i += 1) {
      const y = pad.t + (innerH * i) / 3;
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(w - pad.r, y);
      ctx.stroke();
    }
    if (memPoints.length < 2) {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "12px system-ui,Segoe UI,sans-serif";
      ctx.fillText("采样中…", pad.l + 6, pad.t + 18);
      return;
    }
    const used = memPoints.map((p) => p.used);
    const lo = Math.min(...used);
    const hi = Math.max(...used);
    const span = Math.max(1024 * 1024, hi - lo);
    const minV = lo - span * 0.04;
    const maxV = hi + span * 0.04;
    const n = memPoints.length;
    const xAt = (i) => pad.l + (innerW * i) / (n - 1);
    const yAt = (v) => pad.t + innerH * (1 - (v - minV) / (maxV - minV || 1));
    const grd = ctx.createLinearGradient(0, pad.t, 0, h - pad.b);
    grd.addColorStop(0, "rgba(37,99,235,.22)");
    grd.addColorStop(1, "rgba(16,185,129,.08)");
    ctx.beginPath();
    ctx.moveTo(xAt(0), yAt(memPoints[0].used));
    for (let i = 1; i < n; i += 1) ctx.lineTo(xAt(i), yAt(memPoints[i].used));
    ctx.lineTo(xAt(n - 1), h - pad.b);
    ctx.lineTo(xAt(0), h - pad.b);
    ctx.closePath();
    ctx.fillStyle = grd;
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(xAt(0), yAt(memPoints[0].used));
    for (let i = 1; i < n; i += 1) ctx.lineTo(xAt(i), yAt(memPoints[i].used));
    ctx.strokeStyle = "rgba(37,99,235,.85)";
    ctx.lineWidth = 2;
    ctx.stroke();
    const last = memPoints[n - 1];
    ctx.fillStyle = "#0f172a";
    ctx.font = "11px system-ui,Segoe UI,sans-serif";
    ctx.fillText(`${fmtBytes(last.used)} / ${fmtBytes(last.total)}`, pad.l + 4, h - 8);
  }

  function renderNet() {
    if (!netEl) return;
    const base = normalizedBaseUrl();
    const rtt = lastRtt != null ? `${lastRtt} ms` : "—";
    const ok = lastHealthOk === true ? "正常" : lastHealthOk === false ? "失败" : "未测";
    netEl.innerHTML = `
      <div class="topConsoleNetRow">
        <span class="topConsoleNetK">/health</span>
        <span class="topConsoleNetV">${esc(ok)} · RTT ${esc(rtt)}</span>
      </div>
      <div class="topConsoleNetRow topConsoleNetRow--dim">
        <span class="topConsoleNetK">端点</span>
        <span class="topConsoleNetV topConsoleMono">${esc(base.replace(/^https?:\/\//, ""))}</span>
      </div>`;
  }

  async function pingHealth() {
    try {
      const t0 = performance.now();
      const u = `${normalizedBaseUrl().replace(/\/$/, "")}/health`;
      const r = await fetch(u, { method: "GET", cache: "no-store" });
      lastRtt = Math.round(performance.now() - t0);
      lastHealthOk = r.ok;
    } catch {
      lastHealthOk = false;
      lastRtt = null;
    }
  }

  function refreshSummary() {
    const tracks = collectTracks(refs, state);
    const nBusy = tracks.filter((t) => t.busy).length;
    if (subEl) {
      if (!tracks.length) subEl.textContent = "无活动";
      else if (nBusy) subEl.textContent = `${nBusy} 项运行中`;
      else subEl.textContent = `${tracks.length} 条轨道 · 空闲`;
    }
    pulse?.classList.toggle("topConsolePulseRing--live", nBusy > 0);
  }

  async function refreshFull() {
    renderTracks(collectTracks(refs, state));
    pushMemSample();
    drawMemChart();
    const m = sampleMem();
    if (memLegend) {
      if (!m) {
        memLegend.textContent = "当前环境未暴露 performance.memory（可用 Chrome 桌面版查看 JS 堆曲线）。";
      } else {
        const pct = m.total ? Math.round((100 * m.used) / m.total) : 0;
        memLegend.textContent = `已用 ${fmtBytes(m.used)} · 上限 ${fmtBytes(m.total)} · 约 ${pct}%`;
      }
    }
    await pingHealth();
    renderNet();
    renderStoragePanel();
  }

  function onTick() {
    refreshSummary();
    if (open) void refreshFull();
  }

  function onResize() {
    if (open) drawMemChart();
  }

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle();
  });
  closeBtn?.addEventListener("click", () => setOpen(false));
  backdrop?.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && open) {
      e.preventDefault();
      setOpen(false);
    }
  });

  tickTimer = window.setInterval(onTick, 1300);
  window.addEventListener("resize", onResize);
  tracksEl?.addEventListener("click", onTracksClick);
  storageSeg?.addEventListener("click", onStorageSegClick);
  mainSeg?.addEventListener("click", onMainSegClick);

  refreshSummary();
  void pingHealth().then(() => renderNet());

  return {
    closePanel() {
      setOpen(false);
    },
    dispose() {
      if (tickTimer != null) window.clearInterval(tickTimer);
      tickTimer = null;
      window.removeEventListener("resize", onResize);
      tracksEl?.removeEventListener("click", onTracksClick);
      storageSeg?.removeEventListener("click", onStorageSegClick);
      mainSeg?.removeEventListener("click", onMainSegClick);
      document.body.classList.remove("topConsoleOpen");
    },
  };
}
