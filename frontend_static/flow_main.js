import { createLayoutManager } from "./flow_main.layout.js";
import { createTaskManager } from "./flow_main.tasks.js";
import { createViewer } from "./flow_main.viewer.js";

const $ = (id) => document.getElementById(id);
const refs = {
  baseUrlText: $("baseUrlText"),
  statusEl: $("status"),
  jobIdEl: $("jobId"),
  pickBtn: $("pickBtn"),
  fileInput: $("fileInput"),
  pickBtnLanding: $("pickBtnLanding"),
  fileInputLanding: $("fileInputLanding"),
  scanBtn: $("scanBtn"),
  startBtn: $("startBtn"),
  cancelBtn: $("cancelBtn"),
  msgEl: $("msg"),
  chatEl: $("chat"),
  scanDirInput: $("scanDir"),
  mappingPreview: $("mappingPreview"),
  logSummary: $("logSummary"),
  codeTabs: $("codeTabs"),
  codePreview: $("codePreview"),
  codeStreamWrap: $("codeStreamWrap"),
  imgGrid: $("imgGrid"),
  spinToggleBtn: $("spinToggleBtn"),
  logFloatDock: $("logFloatDock"),
  logFloatToggle: $("logFloatToggle"),
  logFloatMin: $("logFloatMin"),
  logFloatBody: $("logFloatBody"),
  vtkLink: $("vtkLink"),
  acceptStep1: $("acceptStep1"),
  acceptStep2: $("acceptStep2"),
  acceptStep3: $("acceptStep3"),
  restartFlow: $("restartFlow"),
  runAgentFlow: $("runAgentFlow"),
  executePlannedTask: $("executePlannedTask"),
  backHomeFromOrchestrate: $("backHomeFromOrchestrate"),
  backHomeFromFlow: $("backHomeFromFlow"),
  chatLanding: $("chatLanding"),
  msgLanding: $("msgLanding"),
  landingMain: $("landingMain"),
  orchestrateMain: $("orchestrateMain"),
  flowMain: $("flowMain"),
  orchestrateStream: $("orchestrateStream"),
  fileSummaryInline: $("fileSummaryInline"),
  autoScanInfo: $("autoScanInfo"),
  autoScanTree: $("autoScanTree"),
  railStop1: $("railStop1"),
  railStop2: $("railStop2"),
  railStop3: $("railStop3"),
  railStop4: $("railStop4"),
  railConn1: $("railConn1"),
  railConn2: $("railConn2"),
  railConn3: $("railConn3"),
  flowStep1: $("flowStep1"),
  flowStep2: $("flowStep2"),
  flowStep3: $("flowStep3"),
  flowStep4: $("flowStep4"),
  panelStep1: $("panelStep1"),
  panelStep2: $("panelStep2"),
  panelStep3A: $("panelStep3A"),
  panelStep3B: $("panelStep3B"),
  panelStep4: $("panelStep4"),
  flowStageRight: $("flowStageRight"),
  backHomeFloating: $("backHomeFloating"),
  flowStepper: $("flowStepper"),
  taskListEl: $("taskList"),
  taskSidebarEl: document.querySelector("#landingMain .taskSidebar"),
  refreshTasksBtn: $("refreshTasksBtn"),
  toggleSidebarBtn: $("toggleSidebarBtn"),
  artifactSummary: $("artifactSummary"),
  container: $("vtk"),
  uploadPreviewCard: $("uploadPreviewCard"),
  uploadPreviewName: $("uploadPreviewName"),
  uploadPreviewRemove: $("uploadPreviewRemove"),
  settingsBtn: $("settingsBtn"),
  settingsPanel: $("settingsPanel"),
  settingsClose: $("settingsClose"),
  baseUrlInput: $("baseUrl"),
  qwenBaseUrl: $("qwenBaseUrl"),
  qwenModel: $("qwenModel"),
  qwenKey: $("qwenKey"),
  qwenSave: $("qwenSave"),
  qwenStatus: $("qwenStatus"),
  massGoal: $("massGoal"),
  filterR: $("filterR"),
  saveEvery: $("saveEvery"),
};

const state = {
  currentStep: 1,
  maxReachedStep: 1,
  currentTaskStatus: "",
  currentTaskId: null,
  currentFileId: null,
  currentFileName: "",
  uploadedSourceDir: "",
  ws: null,
  jobId: null,
  step1Ready: false,
  meshReady: false,
  imageCount: 0,
  logs: [],
  scanRevealTimer: null,
  codeItems: new Map(),
  codePending: new Set(),
  codeQueue: [],
  processingCodeQueue: false,
  streamedRequired: new Set(),
  requiredFiles: new Set(["task_manifest.json", "input_router.py", "strategy.py", "beso_conf.py", "run_generated.py"]),
  activeCodeName: "",
  jobPollTimer: null,
  summaryRefreshTimer: null,
  activeTaskKey: "",
};

function normalizedBaseUrl() {
  const v = String(refs.baseUrlInput?.value || "").trim();
  if (v) return v;
  if (typeof window !== "undefined" && window.location?.origin) return window.location.origin;
  return "http://localhost:8000";
}
refs.baseUrlText && (refs.baseUrlText.textContent = normalizedBaseUrl().replace(/^https?:\/\//, ""));

const layout = createLayoutManager({ refs, state });

function clearMetricsEmptyState() {
  const el = refs.imgGrid?.querySelector(".imgEmptyState");
  if (el) el.remove();
}

function showMetricsEmptyState(reason = "") {
  if (!refs.imgGrid || state.imageCount > 0) return;
  if (refs.imgGrid.querySelector(".imgEmptyState")) return;
  const card = document.createElement("div");
  card.className = "imgEmptyState";
  const reasonLine = reason ? `<div class="reason">${escapeHtml(reason)}</div>` : "";
  card.innerHTML = `
    <div class="title">任务尚未产出曲线</div>
    <div class="desc">当前任务可能已失败或提前结束，请先查看“日志摘要”定位原因。</div>
    ${reasonLine}
  `;
  refs.imgGrid.appendChild(card);
}

function canProceedFromStep3() {
  const s = String(state.currentTaskStatus || "").toLowerCase();
  if (state.meshReady || state.imageCount > 0) return true;
  if (s === "done" || s === "completed" || s === "failed" || s === "cancelled") return true;
  return false;
}

function checkStep3Ready() {
  if (refs.acceptStep3) refs.acceptStep3.disabled = !canProceedFromStep3();
}
const viewer = createViewer({ refs, state, normalizedBaseUrl, checkStep3Ready });

function updateSpinToggleUi() {
  if (!refs.spinToggleBtn) return;
  const on = !!viewer.getAutoRotate?.();
  refs.spinToggleBtn.classList.toggle("on", on);
  refs.spinToggleBtn.classList.toggle("off", !on);
  refs.spinToggleBtn.setAttribute("aria-pressed", on ? "true" : "false");
  const label = refs.spinToggleBtn.querySelector(".label");
  if (label) label.textContent = on ? "旋转中" : "已暂停";
}

function stopJobPolling() {
  if (state.jobPollTimer) {
    clearInterval(state.jobPollTimer);
    state.jobPollTimer = null;
  }
}

function stopSummaryRefresh() {
  if (state.summaryRefreshTimer) {
    clearInterval(state.summaryRefreshTimer);
    state.summaryRefreshTimer = null;
  }
}

function startSummaryRefresh() {
  if (!state.jobId || state.summaryRefreshTimer) return;
  state.summaryRefreshTimer = setInterval(async () => {
    const status = await buildSummary();
    const s = String(status || "").toLowerCase();
    if (["done", "completed", "failed", "cancelled"].includes(s)) {
      stopSummaryRefresh();
    }
  }, 3000);
}

async function pollJobSnapshotOnce() {
  if (!state.jobId) return;
  try {
    const resp = await fetch(`${normalizedBaseUrl()}/api/jobs/${state.jobId}`, { cache: "no-store" });
    if (!resp.ok) {
      if (resp.status === 404) {
        state.currentTaskStatus = "missing";
        refs.statusEl && (refs.statusEl.textContent = "missing");
        stopJobPolling();
      }
      return;
    }
    const data = await resp.json();
    state.currentTaskStatus = String(data.status || state.currentTaskStatus || "");
    refs.statusEl && (refs.statusEl.textContent = state.currentTaskStatus || "-");
    mergeLogsFromServer(data.logs);
    refreshLogSummaryViews();
    layout.renderSelectedInputs(data.selected_inputs || null);
    (data.artifacts || []).forEach((a) => {
      if (a.kind === "image") viewer.upsertImage(a.name, a.url);
      if (a.kind === "mesh") viewer.loadMesh(a.url);
      if (a.kind === "code" || a.kind === "manifest") enqueueCodeStream(a.name, a.url, (a.meta && a.meta.group) || a.kind);
    });
    checkStep3Ready();
    if (String(data.status || "").toLowerCase() === "failed" && state.imageCount === 0) {
      const hint = state.logs.slice(-1)[0] || "";
      showMetricsEmptyState(hint);
    }
    if (["done", "completed", "failed", "cancelled"].includes(String(data.status || "").toLowerCase())) {
      stopJobPolling();
    }
  } catch {}
}

function startJobPolling() {
  if (!state.jobId || state.jobPollTimer) return;
  state.jobPollTimer = setInterval(() => {
    pollJobSnapshotOnce().catch(() => {});
  }, 2500);
}

function resetTaskRuntimeView() {
  if (state.ws) {
    try { state.ws.close(); } catch {}
  }
  state.ws = null;
  stopJobPolling();
  stopSummaryRefresh();
  state.streamedRequired.clear();
  state.codeItems.clear();
  state.codePending.clear();
  state.codeQueue = [];
  state.processingCodeQueue = false;
  state.logs = [];
  refreshLogSummaryViews();
  updateLogDockVisibility();
  state.imageCount = 0;
  state.meshReady = false;
  refs.codeTabs && (refs.codeTabs.innerHTML = "");
  refs.codePreview && (refs.codePreview.innerHTML = '<div class="codePreviewHead">生成代码</div><pre class="codePreviewBody"><code>(等待代码生成)</code></pre>');
  refs.codeStreamWrap && (refs.codeStreamWrap.innerHTML = "");
  refs.imgGrid && (refs.imgGrid.innerHTML = "");
  clearMetricsEmptyState();
  checkStep3Ready();
}

let taskManager = null;
taskManager = createTaskManager({
  refs,
  state,
  normalizedBaseUrl,
  onOpenTask: async (task) => {
    const nextTaskKey = String(task?.id || task?.task_id || task?.job_id || "");
    if (state.activeTaskKey !== nextTaskKey) {
      resetTaskRuntimeView();
      state.activeTaskKey = nextTaskKey;
    }
    state.currentTaskStatus = String(task.status || "");
    if (state.currentTaskStatus === "completed") {
      state.maxReachedStep = 4;
    } else {
      const stepNum = Number(task.step || 1);
      state.maxReachedStep = Math.min(4, Math.max(1, Number.isFinite(stepNum) ? stepNum : 1));
    }
    if (refs.scanDirInput) refs.scanDirInput.value = state.uploadedSourceDir;
    if (refs.fileSummaryInline) {
      refs.fileSummaryInline.textContent = `已上传文件：${state.currentFileName || "(未知)"}\n扫描目录：${state.uploadedSourceDir || "(未知)"}`;
    }
    if (refs.msgLanding && task.title) refs.msgLanding.value = task.title;
    if (task.step && Number(task.step) >= 1 && Number(task.step) <= 4) {
      layout.showStage("flow");
      layout.setStep(Number(task.step));
    } else {
      layout.showStage("landing");
    }
    if (state.jobId) {
      refs.jobIdEl && (refs.jobIdEl.textContent = state.jobId);
      refs.statusEl && (refs.statusEl.textContent = task.status || "running");
      connectWs();
      try {
        const resp = await fetch(`${normalizedBaseUrl()}/api/jobs/${state.jobId}`);
        if (!resp.ok) {
          if (resp.status === 404) {
            state.currentTaskStatus = "missing";
            refs.statusEl && (refs.statusEl.textContent = "missing");
            stopJobPolling();
          }
          return;
        }
        const data = await resp.json();
        state.currentTaskStatus = String(data.status || state.currentTaskStatus || "");
        mergeLogsFromServer(data.logs);
        refreshLogSummaryViews();
        layout.renderSelectedInputs(data.selected_inputs || null);
        (data.artifacts || []).forEach((a) => {
          if (a.kind === "image") viewer.upsertImage(a.name, a.url);
          if (a.kind === "code" || a.kind === "manifest") enqueueCodeStream(a.name, a.url, (a.meta && a.meta.group) || a.kind);
        });
        checkStep3Ready();
        if (String(data.status || "").toLowerCase() === "failed" && state.imageCount === 0) {
          const hint = state.logs.slice(-1)[0] || "";
          showMetricsEmptyState(hint);
        }
      } catch {}
    }
  },
});

const setStepRaw = layout.setStep;
layout.setStep = (step) => {
  setStepRaw(step);
  state.currentStep = step;
  state.maxReachedStep = Math.max(state.maxReachedStep, step);
  state.currentTaskStatus = step >= 4 ? "completed" : (state.currentTaskStatus || "running");
  updateLogDockVisibility();
  updateStepperClickableState();
  if (state.currentTaskId) {
    const persistedStep = state.maxReachedStep;
    const persistedStatus = persistedStep >= 4 ? "completed" : "running";
    taskManager.upsertTask({
      step: persistedStep,
      progress: taskManager.taskProgressByStep(persistedStep),
      status: persistedStatus,
    }).then(() => taskManager.loadTasks()).catch(() => {});
  }
};

function updateStepperClickableState() {
  const allUnlocked = state.currentTaskStatus === "completed";
  const completedStep = Math.max(1, state.maxReachedStep - 1);
  const stepEls = [
    [refs.flowStep1, 1],
    [refs.flowStep2, 2],
    [refs.flowStep3, 3],
    [refs.flowStep4, 4],
  ];
  stepEls.forEach(([el, idx]) => {
    if (!el) return;
    const clickable = allUnlocked || idx <= completedStep || idx === state.currentStep;
    el.classList.toggle("stepDisabled", !clickable);
    el.classList.toggle("stepCurrent", idx === state.currentStep);
    el.setAttribute("aria-disabled", clickable ? "false" : "true");
    el.tabIndex = clickable ? 0 : -1;
  });
}

async function uploadSelectedFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const data = await (await fetch(`${normalizedBaseUrl()}/api/files/upload`, { method: "POST", body: fd })).json();
  state.currentFileId = data.file_id;
  state.currentFileName = data.name || file?.name || "";
  layout.addBubble("agent", `已上传文件：${data.name}`);
  const rawPath = file && typeof file.path === "string" ? file.path : "";
  if (rawPath) {
    const idx = rawPath.lastIndexOf("\\");
    if (idx > 0) {
      state.uploadedSourceDir = rawPath.slice(0, idx);
      refs.scanDirInput && (refs.scanDirInput.value = state.uploadedSourceDir);
    }
  }
  if (!state.uploadedSourceDir && data.suggested_scan_dir) {
    state.uploadedSourceDir = data.suggested_scan_dir;
    refs.scanDirInput && (refs.scanDirInput.value = state.uploadedSourceDir);
  }
  if (refs.fileSummaryInline) refs.fileSummaryInline.textContent = `已上传文件：${file.name}\n扫描目录：${refs.scanDirInput?.value || "(自动识别失败，请手动填写)"}`;
  if (refs.uploadPreviewName) refs.uploadPreviewName.textContent = state.currentFileName || file.name;
  refs.uploadPreviewCard?.classList.remove("hidden");
  layout.addLandingBubble("agent", state.uploadedSourceDir ? `已自动识别扫描目录：${state.uploadedSourceDir}` : "自动识别目录失败，请手动填写扫描目录。");
  await taskManager.upsertTask({ file_name: state.currentFileName, scan_dir: state.uploadedSourceDir, status: "uploaded", progress: 8, step: 1 });
  await taskManager.loadTasks();
}

async function scanDirectory() {
  const dir = (state.uploadedSourceDir || refs.scanDirInput?.value || "").trim();
  if (!dir) return layout.addBubble("agent", "未获取到上传文件目录，暂无法自动扫描。");
  const resp = await fetch(`${normalizedBaseUrl()}/api/scan-directory?scan_dir=${encodeURIComponent(dir)}`);
  const data = await resp.json();
  if (!resp.ok) return layout.addBubble("agent", `扫描失败：${data.detail || JSON.stringify(data)}`);
  const selected = { primary_inp: data.primary_inp ? data.primary_inp.split(/[\\/]/).pop() : null, aux_inps: data.aux_inps || {}, step_mapping: data.step_mapping || {} };
  layout.renderSelectedInputs(selected);
  if (refs.autoScanInfo) refs.autoScanInfo.textContent = `扫描目录：${data.scan_dir}\n主文件：${selected.primary_inp || "(none)"}\n状态：正在探索文件结构...`;
  if (refs.autoScanTree) {
    if (state.scanRevealTimer) clearInterval(state.scanRevealTimer);
    refs.autoScanTree.innerHTML = "";
    const rowMeta = (data.files || []).slice(0, 60).map((x) => ({ name: x.name, role: x.role, text: `${x.name} [${x.role}]` }));
    const iconByRole = { primary_candidate: "⭐", load_case: "⚡", set_definition: "🧩", inp_candidate: "📄", result_state: "🧪", result_frame: "🧱", code_file: "💻", log_file: "📝", viz_file: "🧊", other: "📦" };
    let idx = 0;
    state.scanRevealTimer = setInterval(() => {
      if (idx >= rowMeta.length) {
        clearInterval(state.scanRevealTimer);
        state.scanRevealTimer = null;
        refs.autoScanInfo && (refs.autoScanInfo.textContent = `扫描目录：${data.scan_dir}\n主文件：${selected.primary_inp || "(none)"}\n状态：探索完成，共识别 ${rowMeta.length} 个关联文件`);
        return;
      }
      const r = rowMeta[idx];
      const role = String(r.role || "other");
      const line = document.createElement("div");
      line.className = "scanRow";
      line.innerHTML = `<span class="scanIcon">${iconByRole[role] || "📁"}</span><span>${r.text}</span>`;
      if (r.name.toLowerCase().endsWith(".inp")) line.classList.add("inp");
      line.classList.add(role);
      if (r.name === (selected.primary_inp || "")) line.classList.add("primary");
      refs.autoScanTree.appendChild(line);
      refs.autoScanTree.scrollTop = refs.autoScanTree.scrollHeight;
      idx += 1;
    }, 95);
  }
  state.step1Ready = Boolean(data.primary_inp);
  refs.acceptStep1 && (refs.acceptStep1.disabled = !state.step1Ready);
  layout.addBubble("agent", state.step1Ready ? "文件搜索完成，可进入下一步。" : "未识别到主文件。");
}

function detectCodeLang(name = "") {
  const n = name.toLowerCase();
  if (n.endsWith(".py")) return "python";
  if (n.endsWith(".json")) return "json";
  return "plain";
}
function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
function renderSimpleMd(text) {
  const lines = String(text || "").split("\n");
  let html = "";
  let inList = false;
  const inline = (t) =>
    escapeHtml(t)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      continue;
    }
    if (line.startsWith("### ")) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<h4>${inline(line.slice(4))}</h4>`;
      continue;
    }
    if (line.startsWith("## ")) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<h3>${inline(line.slice(3))}</h3>`;
      continue;
    }
    if (line.startsWith("- ")) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(line.slice(2))}</li>`;
      continue;
    }
    if (inList) {
      html += "</ul>";
      inList = false;
    }
    html += `<p>${inline(line)}</p>`;
  }
  if (inList) html += "</ul>";
  return html || "<p>(无)</p>";
}

function mergeLogsFromServer(serverLogs) {
  if (!Array.isArray(serverLogs) || !serverLogs.length) return;
  if (serverLogs.length >= state.logs.length) {
    state.logs = serverLogs.slice();
  }
}

function refreshLogSummaryViews() {
  const statusLine = `- 当前任务状态：\`${state.currentTaskStatus || "unknown"}\``;
  const lastLogs = state.logs.slice(-80).map((x) => `- ${x}`).join("\n");
  const md = `## 日志摘要\n${statusLine}\n${lastLogs || "- (无)"}`;
  const html = renderSimpleMd(md);
  if (refs.logFloatBody) {
    refs.logFloatBody.innerHTML = html;
    refs.logFloatBody.scrollTop = refs.logFloatBody.scrollHeight;
  }
  if (refs.logSummary) {
    refs.logSummary.classList.add("mdBox");
    refs.logSummary.innerHTML = html;
  }
  if (refs.logFloatToggle) {
    const n = state.logs.length;
    refs.logFloatToggle.textContent = n ? `日志摘要 · ${n} 行` : "日志摘要";
  }
}

function updateLogDockVisibility() {
  if (!refs.logFloatDock) return;
  const inFlowStage = !!refs.flowMain && !refs.flowMain.classList.contains("hidden");
  const visible = inFlowStage && state.currentStep === 3 && !!state.jobId;
  refs.logFloatDock.classList.toggle("hidden", !visible);
}

function wireLogFloatDock() {
  if (!refs.logFloatDock || !refs.logFloatToggle || !refs.logFloatMin) return;
  const dock = refs.logFloatDock;
  // Portal to body so the dock is truly global/fixed and not affected by Step3 panel transforms/clipping.
  if (dock.parentElement !== document.body) {
    document.body.appendChild(dock);
  }
  const dragHandle = dock.querySelector(".logFloatDockHd");
  const dockPanel = dock.querySelector(".logFloatDockPanel");
  const minimizedHandle = refs.logFloatToggle;
  let dragState = null;
  let suppressToggleClick = false;

  const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
  const clearDockInlinePos = () => {
    dock.style.left = "";
    dock.style.top = "";
    dock.style.right = "14px";
    dock.style.bottom = "14px";
  };
  const applyDockPos = (x, y) => {
    dock.style.left = `${x}px`;
    dock.style.top = `${y}px`;
    dock.style.right = "auto";
    dock.style.bottom = "auto";
  };
  const saveDockPos = (x, y) => {
    try {
      sessionStorage.setItem("beso.ui.logFloatPos", JSON.stringify({ x, y }));
    } catch {}
  };
  const restoreDockPos = () => {
    try {
      const raw = sessionStorage.getItem("beso.ui.logFloatPos");
      if (!raw) return;
      const p = JSON.parse(raw);
      if (!Number.isFinite(p?.x) || !Number.isFinite(p?.y)) return;
      applyDockPos(p.x, p.y);
    } catch {}
  };
  const getDockBox = () => {
    if (dock.classList.contains("minimized")) {
      return refs.logFloatToggle?.getBoundingClientRect() || dock.getBoundingClientRect();
    }
    return dockPanel?.getBoundingClientRect() || dock.getBoundingClientRect();
  };
  const clampDockIntoViewport = () => {
    const r = dock.getBoundingClientRect();
    const box = getDockBox();
    const w = Math.max(160, box.width || 220);
    const h = Math.max(48, box.height || 48);
    const maxX = Math.max(8, window.innerWidth - w - 8);
    const maxY = Math.max(8, window.innerHeight - h - 8);
    const x = clamp(r.left, 8, maxX);
    const y = clamp(r.top, 8, maxY);
    applyDockPos(x, y);
    saveDockPos(x, y);
  };

  try {
    const m = sessionStorage.getItem("beso.ui.logFloatMinimized");
    if (m === "0") dock.classList.remove("minimized");
    else dock.classList.add("minimized");
  } catch {
    dock.classList.add("minimized");
  }
  restoreDockPos();
  requestAnimationFrame(clampDockIntoViewport);
  refs.logFloatToggle.addEventListener("click", () => {
    if (suppressToggleClick) {
      suppressToggleClick = false;
      return;
    }
    dock.classList.remove("minimized");
    try {
      sessionStorage.setItem("beso.ui.logFloatMinimized", "0");
    } catch {}
    refreshLogSummaryViews();
    requestAnimationFrame(clampDockIntoViewport);
  });
  refs.logFloatMin.addEventListener("click", (e) => {
    e.stopPropagation();
    dock.classList.add("minimized");
    try {
      sessionStorage.setItem("beso.ui.logFloatMinimized", "1");
    } catch {}
  });

  const beginDrag = (e) => {
      const isMinimized = dock.classList.contains("minimized");
      if (isMinimized && e.currentTarget !== minimizedHandle) return;
      if (!isMinimized && e.currentTarget !== dragHandle) return;
      const target = e.target;
      if (target && target.closest && target.closest("#logFloatMin")) return;
      // Ensure we are in left/top coordinate mode before dragging.
      const r0 = dock.getBoundingClientRect();
      applyDockPos(r0.left, r0.top);
      const r = dock.getBoundingClientRect();
      dragState = {
        pointerId: e.pointerId,
        offsetX: e.clientX - r.left,
        offsetY: e.clientY - r.top,
        startX: e.clientX,
        startY: e.clientY,
        moved: false,
      };
      dock.classList.add("dragging");
      try { e.currentTarget?.setPointerCapture?.(e.pointerId); } catch {}
      e.preventDefault();
  };
  const onDragMove = (e) => {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    if (!dragState.moved) {
      const dx = e.clientX - dragState.startX;
      const dy = e.clientY - dragState.startY;
      if ((dx * dx + dy * dy) >= 16) dragState.moved = true;
    }
    const box = getDockBox();
    const w = Math.max(160, box.width || 220);
    const h = Math.max(48, box.height || 48);
    const maxX = Math.max(8, window.innerWidth - w - 8);
    const maxY = Math.max(8, window.innerHeight - h - 8);
    const x = clamp(e.clientX - dragState.offsetX, 8, maxX);
    const y = clamp(e.clientY - dragState.offsetY, 8, maxY);
    applyDockPos(x, y);
  };
  const endDrag = (e) => {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    const r = dock.getBoundingClientRect();
    const box = getDockBox();
    const w = Math.max(160, box.width || 220);
    const h = Math.max(48, box.height || 48);
    const maxX = Math.max(8, window.innerWidth - w - 8);
    const maxY = Math.max(8, window.innerHeight - h - 8);
    const x = clamp(r.left, 8, maxX);
    const y = clamp(r.top, 8, maxY);
    applyDockPos(x, y);
    saveDockPos(x, y);
    if (dragState.moved && dock.classList.contains("minimized")) {
      // 拖动最小化胶囊后，抑制本次 click 展开行为
      suppressToggleClick = true;
    }
    dock.classList.remove("dragging");
    dragState = null;
  };
  if (dragHandle) {
    dragHandle.addEventListener("pointerdown", beginDrag);
  }
  if (minimizedHandle) {
    minimizedHandle.addEventListener("pointerdown", beginDrag);
  }
  window.addEventListener("pointermove", onDragMove);
  window.addEventListener("pointerup", endDrag);
  window.addEventListener("pointercancel", endDrag);

  window.addEventListener("resize", () => {
    if (!dock) return;
    requestAnimationFrame(clampDockIntoViewport);
  });

  try {
    if (!sessionStorage.getItem("beso.ui.logFloatPos")) {
      clearDockInlinePos();
    }
  } catch {
    clearDockInlinePos();
  }
  updateLogDockVisibility();
}

function renderArtifactList(artifacts = []) {
  const iconByKind = { code: "💻", manifest: "🧾", image: "🖼️", mesh: "🧊" };
  // De-duplicate by kind+name, keep the latest one.
  const seen = new Map();
  artifacts.forEach((a) => {
    const kind = String(a.kind || "other");
    const name = String(a.name || a.url || "(unknown)");
    seen.set(`${kind}::${name}`, { kind, name });
  });
  const rows = Array.from(seen.values()).slice(-120).map((a) => {
    const kind = a.kind;
    const name = a.name;
    return { kind, text: `[${kind}] ${name}`, icon: iconByKind[kind] || "📦" };
  });
  return rows;
}
function highlightCode(text, lang) {
  let out = escapeHtml(text);
  if (lang === "python") {
    out = out
      .replace(/\b(def|class|return|if|elif|else|for|while|try|except|finally|import|from|as|with|lambda|pass|raise|yield|in|is|not|and|or|None|True|False)\b/g, '<span class="tokKw">$1</span>')
      .replace(/(^|\s)(#.*)$/gm, '$1<span class="tokCmt">$2</span>');
  } else if (lang === "json") {
    out = out
      .replace(/(".*?")(\s*:)/g, '<span class="tokKey">$1</span>$2')
      .replace(/:\s*(".*?")/g, ': <span class="tokStr">$1</span>')
      .replace(/:\s*(-?\d+(\.\d+)?)/g, ': <span class="tokNum">$1</span>')
      .replace(/\b(true|false|null)\b/g, '<span class="tokKw">$1</span>');
  }
  return out;
}
function renderCodePreview(name, text, streamed = false) {
  if (!refs.codePreview) return;
  const lang = detectCodeLang(name);
  refs.codePreview.classList.add("codePreviewPane");
  refs.codePreview.innerHTML = `<div class="codePreviewHead">${name}${streamed ? " · 生成中..." : ""}</div><pre class="codePreviewBody"><code>${highlightCode(text, lang)}</code></pre>`;
  if (streamed) {
    const body = refs.codePreview.querySelector(".codePreviewBody");
    if (body) body.scrollTop = body.scrollHeight;
  }
}
function setActiveCodeTab(name) {
  state.activeCodeName = name;
  refs.codeTabs?.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("codeTabActive", btn.dataset.codeName === name);
  });
}
function setStreamingCodeTab(name) {
  refs.codeTabs?.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("codeTabStreaming", btn.dataset.codeName === name);
  });
}
function streamTextToPreview(name, text, onDone) {
  return new Promise((resolve) => {
    const total = text.length;
    const started = performance.now();
    const cps = 520; // faster stream while keeping readability
    const tick = (now) => {
      const elapsed = Math.max(0, now - started);
      const i = Math.min(total, Math.floor((elapsed / 1000) * cps));
      renderCodePreview(name, text.slice(0, i), i < total);
      if (i >= total) {
        onDone?.();
        resolve();
        return;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}
async function streamCodeNow(name, url, group = "generated") {
  if (!(group === "generated" || group === "manifest")) return;
  if (state.codeItems.has(name)) return;
  const text = await (await fetch(`${normalizedBaseUrl()}${url}`, { cache: "no-store" })).text();
  state.codeItems.set(name, { url, group, text });
  const tab = document.createElement("button");
  tab.className = "btn codeTabBtn";
  tab.dataset.codeName = name;
  tab.textContent = `[${group}] ${name}`;
  tab.addEventListener("click", () => {
    setActiveCodeTab(name);
    renderCodePreview(name, text, false);
  });
  refs.codeTabs?.appendChild(tab);
  setActiveCodeTab(name);
  setStreamingCodeTab(name);
  if (state.codeItems.size === 1) {
    renderCodePreview(name, "", true);
  }
  await streamTextToPreview(name, text, () => {
    setStreamingCodeTab("");
    if (state.activeCodeName === name) renderCodePreview(name, text, false);
    if (state.requiredFiles.has(name)) state.streamedRequired.add(name);
    if (state.streamedRequired.size === state.requiredFiles.size && refs.acceptStep2) refs.acceptStep2.disabled = false;
  });
}
async function processCodeQueue() {
  if (state.processingCodeQueue) return;
  state.processingCodeQueue = true;
  try {
    while (state.codeQueue.length > 0) {
      const next = state.codeQueue.shift();
      if (!next) continue;
      const key = `${next.group}:${next.name}`;
      if (!state.codePending.has(key)) continue;
      await streamCodeNow(next.name, next.url, next.group);
      state.codePending.delete(key);
    }
  } finally {
    state.processingCodeQueue = false;
  }
}
function enqueueCodeStream(name, url, group = "generated") {
  if (!(group === "generated" || group === "manifest")) return;
  const key = `${group}:${name}`;
  if (state.codeItems.has(name) || state.codePending.has(key)) return;
  state.codePending.add(key);
  state.codeQueue.push({ name, url, group });
  processCodeQueue();
}

async function hydrateDefaultImages() {
  if (!state.jobId) return;
  let names = [];
  try {
    const resp = await fetch(`${normalizedBaseUrl()}/api/jobs/${state.jobId}`, {
      cache: "no-store",
    });
    if (resp.ok) {
      const data = await resp.json();
      names = (Array.isArray(data.artifacts) ? data.artifacts : [])
        .filter((a) => a && a.kind === "image" && a.name)
        .map((a) => String(a.name));
    }
  } catch {}
  for (const name of names) {
    if (refs.imgGrid?.querySelector(`[data-img='${name}']`)) continue;
    try {
      viewer.upsertImage(name, `/runs/${state.jobId}/${name}`);
    } catch {}
  }
}

function connectWs() {
  if (!state.jobId) return;
  if (state.ws) state.ws.close();
  state.ws = new WebSocket(`${normalizedBaseUrl().replace(/^http/, "ws")}/ws/jobs/${state.jobId}`);
  startJobPolling();
  state.ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "snapshot") {
      refs.statusEl && (refs.statusEl.textContent = msg.job.status);
      refs.jobIdEl && (refs.jobIdEl.textContent = msg.job.id);
      state.currentTaskStatus = String(msg.job.status || state.currentTaskStatus || "");
      mergeLogsFromServer(msg.job.logs);
      refreshLogSummaryViews();
      layout.renderSelectedInputs(msg.job.selected_inputs || null);
      (msg.job.artifacts || []).forEach((a) => {
        if (a.kind === "code" || a.kind === "manifest") enqueueCodeStream(a.name, a.url, (a.meta && a.meta.group) || a.kind);
        if (a.kind === "image") viewer.upsertImage(a.name, a.url);
      });
      hydrateDefaultImages().catch(() => {});
      if (String(msg.job.status || "").toLowerCase() === "failed" && state.imageCount === 0) {
        const hint = state.logs.slice(-1)[0] || "";
        showMetricsEmptyState(hint);
      } else {
        clearMetricsEmptyState();
      }
      if (["done", "completed", "failed", "cancelled"].includes(String(msg.job.status || "").toLowerCase())) {
        stopJobPolling();
      }
      return;
    }
    if (msg.type === "status") {
      refs.statusEl && (refs.statusEl.textContent = msg.status);
      state.currentTaskStatus = String(msg.status || state.currentTaskStatus || "");
      checkStep3Ready();
      if (state.currentTaskId) taskManager.upsertTask({ status: msg.status, progress: msg.status === "done" ? 100 : undefined, step: msg.status === "done" ? 4 : undefined }).then(() => taskManager.loadTasks()).catch(() => {});
      if (String(msg.status || "").toLowerCase() === "failed" && state.imageCount === 0) {
        const hint = state.logs.slice(-1)[0] || "";
        showMetricsEmptyState(hint);
      }
    }
    if (msg.type === "log") state.logs.push(msg.line);
    if (msg.type === "vtk") {
      if (refs.vtkLink) { refs.vtkLink.href = `${normalizedBaseUrl()}${msg.url}`; refs.vtkLink.textContent = msg.url; }
      viewer.loadMesh(msg.url);
    }
    if (msg.type === "artifact") {
      if (msg.kind === "mesh") viewer.loadMesh(msg.url);
      if (msg.kind === "image") {
        clearMetricsEmptyState();
        viewer.upsertImage(msg.name, msg.url);
      }
      if (msg.kind === "code" || msg.kind === "manifest") enqueueCodeStream(msg.name, msg.url, (msg.meta && msg.meta.group) || msg.kind);
    }
    refreshLogSummaryViews();
  };
  state.ws.onerror = () => {
    startJobPolling();
  };
  state.ws.onclose = () => {
    startJobPolling();
  };
}

async function createAndRun() {
  layout.addBubble("user", refs.msgEl?.value || "");
  const body = { message: refs.msgEl?.value || "", auto_start: true };
  if (refs.scanDirInput?.value.trim()) body.scan_dir = refs.scanDirInput.value.trim();
  if (state.currentFileId) body.file_id = state.currentFileId;
  const mg = Number(refs.massGoal?.value);
  const fr = Number(refs.filterR?.value);
  const se = Number(refs.saveEvery?.value);
  if (Number.isFinite(mg) && mg > 0 && mg < 1) body.mass_goal_ratio = mg;
  if (Number.isFinite(fr) && fr > 0) body.filter_radius = fr;
  if (Number.isFinite(se) && se > 0) body.save_every = Math.floor(se);
  const resp = await fetch(`${normalizedBaseUrl()}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await resp.json();
  if (!resp.ok) return layout.addBubble("agent", `任务启动失败：${data.detail || JSON.stringify(data)}`);
  state.jobId = data.job_id;
  refs.jobIdEl && (refs.jobIdEl.textContent = state.jobId);
  refs.statusEl && (refs.statusEl.textContent = "running");
  state.streamedRequired.clear();
  state.codeItems.clear();
  state.codePending.clear();
  state.codeQueue = [];
  state.processingCodeQueue = false;
  refs.codeTabs && (refs.codeTabs.innerHTML = "");
  refs.codePreview && (refs.codePreview.innerHTML = '<div class="codePreviewHead">生成代码</div><pre class="codePreviewBody"><code>(等待代码生成)</code></pre>');
  refs.codeStreamWrap && (refs.codeStreamWrap.innerHTML = "");
  refs.imgGrid && (refs.imgGrid.innerHTML = "");
  clearMetricsEmptyState();
  state.imageCount = 0;
  state.meshReady = false;
  state.currentTaskStatus = "running";
  checkStep3Ready();
  state.logs = [];
  refreshLogSummaryViews();
  stopJobPolling();
  stopSummaryRefresh();
  layout.renderSelectedInputs(data.selected_inputs || null);
  (data.generated_code || []).forEach((f) => enqueueCodeStream(f.name, f.url, f.group || "generated"));
  await taskManager.upsertTask({ job_id: state.jobId, status: "running", progress: 55, step: 2 });
  await taskManager.loadTasks();
  connectWs();
}

async function buildSummary() {
  if (!state.jobId) return;
  try {
    const data = await (await fetch(`${normalizedBaseUrl()}/api/jobs/${state.jobId}`)).json();
    state.currentTaskStatus = String(data.status || state.currentTaskStatus || "");
    if (refs.artifactSummary) {
      refs.artifactSummary.classList.add("artifactSummaryList");
      const rows = renderArtifactList(data.artifacts || []);
      refs.artifactSummary.innerHTML = "";
      if (!rows.length) {
        refs.artifactSummary.innerHTML = '<div class="scanRow other"><span class="scanIcon">📦</span><span>(无)</span></div>';
      } else {
        let idx = 0;
        const timer = setInterval(() => {
          if (idx >= rows.length) {
            clearInterval(timer);
            return;
          }
          const r = rows[idx];
          const line = document.createElement("div");
          line.className = `scanRow ${r.kind}`;
          line.innerHTML = `<span class="scanIcon">${r.icon}</span><span>${escapeHtml(r.text)}</span>`;
          refs.artifactSummary.appendChild(line);
          refs.artifactSummary.scrollTop = refs.artifactSummary.scrollHeight;
          idx += 1;
        }, 24);
      }
    }
    if (refs.mappingPreview) {
      refs.mappingPreview.classList.add("mdBox");
      const mapLines = String(refs.mappingPreview.textContent || "")
        .split("\n")
        .filter((x) => x.trim())
        .map((x) => `- ${x}`)
        .join("\n");
      refs.mappingPreview.innerHTML = renderSimpleMd(`## 输入映射\n${mapLines || "- (无)"}`);
    }
    mergeLogsFromServer(data.logs);
    refreshLogSummaryViews();
    return state.currentTaskStatus;
  } catch {
    refreshLogSummaryViews();
    return state.currentTaskStatus;
  }
}

refs.acceptStep1?.addEventListener("click", async () => { layout.setStep(2); await createAndRun(); });
refs.acceptStep2?.addEventListener("click", () => layout.setStep(3));
refs.acceptStep2?.addEventListener("click", () => {
  hydrateDefaultImages().catch(() => {});
});
refs.acceptStep3?.addEventListener("click", async () => {
  layout.setStep(4);
  await buildSummary();
  startSummaryRefresh();
});
refs.restartFlow?.addEventListener("click", () => {
  const finishingTaskId = state.currentTaskId;
  const done = async () => {
    if (finishingTaskId) {
      await taskManager.upsertTask({ status: "completed", progress: 100, step: 4 });
    }
    state.currentTaskStatus = "";
    state.currentTaskId = null;
    state.jobId = null;
    state.activeTaskKey = "";
    stopJobPolling();
    stopSummaryRefresh();
    refs.jobIdEl && (refs.jobIdEl.textContent = "(未启动)");
    refs.statusEl && (refs.statusEl.textContent = "-");
    refs.acceptStep1 && (refs.acceptStep1.disabled = true);
    refs.acceptStep2 && (refs.acceptStep2.disabled = true);
    refs.acceptStep3 && (refs.acceptStep3.disabled = true);
    refs.mappingPreview && (refs.mappingPreview.textContent = "(尚未扫描)");
    layout.goHome();
    await taskManager.loadTasks();
  };
  done().catch(() => {
    layout.goHome();
    taskManager.loadTasks().catch(() => {});
  });
});

refs.pickBtn?.addEventListener("click", () => refs.fileInput?.click());
refs.fileInput?.addEventListener("change", async (e) => { const f = e.target.files && e.target.files[0]; if (f) await uploadSelectedFile(f); });
refs.scanBtn?.addEventListener("click", scanDirectory);
refs.startBtn?.addEventListener("click", async () => { if (!state.step1Ready) await scanDirectory(); if (state.step1Ready) { layout.setStep(2); await createAndRun(); } });
refs.cancelBtn?.addEventListener("click", async () => { if (!state.jobId) return; await fetch(`${normalizedBaseUrl()}/api/jobs/${state.jobId}/cancel`, { method: "POST" }); });

refs.pickBtnLanding?.addEventListener("click", () => refs.fileInputLanding?.click());
refs.fileInputLanding?.addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  await uploadSelectedFile(f);
  layout.addLandingBubble("agent", `已上传文件：${f.name}`);
});
refs.runAgentFlow?.addEventListener("click", async () => {
  if (!state.currentFileId) return layout.addLandingBubble("agent", "请先上传文件，再运行智能体流程。");
  if (!state.currentTaskId) state.currentTaskId = (crypto?.randomUUID?.() || `${Date.now()}`);
  state.currentTaskStatus = "orchestrating";
  refs.msgEl && (refs.msgEl.value = (refs.msgLanding?.value || "").trim() || refs.msgEl.value);
  layout.addLandingBubble("user", refs.msgEl?.value || "");
  await taskManager.upsertTask({ title: (refs.msgEl?.value || "").slice(0, 80), progress: 12, step: 1, status: "orchestrating", file_name: state.currentFileName, scan_dir: state.uploadedSourceDir });
  await taskManager.loadTasks();
  layout.showStage("orchestrate");
  refs.executePlannedTask && (refs.executePlannedTask.disabled = true);
  layout.streamOrchestration(async () => {
    refs.executePlannedTask && (refs.executePlannedTask.disabled = false);
    layout.addLandingBubble("agent", "编排完成，点击“执行任务”进入分步执行。");
    await taskManager.upsertTask({ progress: 20, step: 1, status: "ready_to_execute" });
    await taskManager.loadTasks();
  });
});
refs.executePlannedTask?.addEventListener("click", async () => { layout.showStage("flow"); layout.setStep(1); await scanDirectory(); });
refs.backHomeFromOrchestrate?.addEventListener("click", () => layout.goHome());
refs.backHomeFromFlow?.addEventListener("click", () => layout.goHome());
refs.backHomeFloating?.addEventListener("click", () => layout.goHome());
refs.refreshTasksBtn?.addEventListener("click", () => taskManager.loadTasks());
refs.toggleSidebarBtn?.addEventListener("click", () => layout.setSidebarCollapsed(!(refs.landingMain?.classList.contains("sidebarCollapsed"))));
refs.taskSidebarEl?.addEventListener("click", (e) => {
  if (!refs.landingMain?.classList.contains("sidebarCollapsed")) return;
  if (e.target?.id === "toggleSidebarBtn" || e.target?.closest?.("#toggleSidebarBtn")) {
    layout.setSidebarCollapsed(false);
    return;
  }
  layout.setSidebarCollapsed(false);
});
refs.settingsBtn?.addEventListener("click", () => refs.settingsPanel?.classList.remove("hidden"));
refs.settingsClose?.addEventListener("click", () => refs.settingsPanel?.classList.add("hidden"));
refs.baseUrlInput?.addEventListener("change", () => {
  refs.baseUrlText && (refs.baseUrlText.textContent = normalizedBaseUrl().replace(/^https?:\/\//, ""));
});
[refs.baseUrlInput, refs.qwenBaseUrl, refs.qwenModel].forEach((el) => {
  el?.addEventListener("change", () => {
    try {
      localStorage.setItem("beso.settings.baseUrl", String(refs.baseUrlInput?.value || ""));
      localStorage.setItem("beso.settings.qwenBaseUrl", String(refs.qwenBaseUrl?.value || ""));
      localStorage.setItem("beso.settings.qwenModel", String(refs.qwenModel?.value || ""));
    } catch {}
  });
});
refs.qwenSave?.addEventListener("click", async () => {
  const payload = {
    api_key: String(refs.qwenKey?.value || "").trim() || null,
    base_url: String(refs.qwenBaseUrl?.value || "").trim() || null,
    model: String(refs.qwenModel?.value || "").trim() || null,
  };
  try {
    const resp = await fetch(`${normalizedBaseUrl()}/api/config/qwen`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data?.detail || "保存失败");
    if (refs.qwenStatus) refs.qwenStatus.textContent = data.configured ? `已连接 (${data.model || "qwen"})` : "未配置";
    layout.addLandingBubble("agent", data.configured ? "Qwen 已启用，后续参数解析与生成将走大模型。" : "Qwen 未配置，将使用默认规则。");
  } catch (e) {
    if (refs.qwenStatus) refs.qwenStatus.textContent = "连接失败";
    layout.addLandingBubble("agent", `Qwen 配置失败：${e?.message || e}`);
  }
});
refs.uploadPreviewRemove?.addEventListener("click", () => {
  state.currentFileId = null;
  state.currentFileName = "";
  state.uploadedSourceDir = "";
  if (refs.scanDirInput) refs.scanDirInput.value = "";
  if (refs.fileSummaryInline) refs.fileSummaryInline.textContent = "(尚未选择文件)";
  if (refs.uploadPreviewName) refs.uploadPreviewName.textContent = "(暂无文件)";
  refs.uploadPreviewCard?.classList.add("hidden");
  layout.addLandingBubble("agent", "已移除当前上传文件。");
});
refs.spinToggleBtn?.addEventListener("click", () => {
  const next = !viewer.getAutoRotate?.();
  viewer.setAutoRotate?.(next);
  updateSpinToggleUi();
});
[refs.backHomeFromOrchestrate, refs.backHomeFromFlow, refs.backHomeFloating].forEach((el) => {
  el?.addEventListener("click", () => refs.settingsPanel?.classList.add("hidden"));
});
[refs.flowStep1, refs.flowStep2, refs.flowStep3, refs.flowStep4].forEach((el, i) => {
  if (!el) return;
  const target = i + 1;
  el.addEventListener("click", () => {
    const allUnlocked = state.currentTaskStatus === "completed";
    const completedStep = Math.max(1, state.maxReachedStep - 1);
    const clickable = allUnlocked || target <= completedStep || target === state.currentStep;
    if (!clickable) return;
    layout.setStep(target);
  });
});

layout.setStep(1);
layout.showStage("landing");
updateLogDockVisibility();
layout.addLandingBubble("agent", "先聊天并上传文件，点击“运行智能体流程”后开始流式编排。");
try {
  if (refs.baseUrlInput) refs.baseUrlInput.value = localStorage.getItem("beso.settings.baseUrl") || refs.baseUrlInput.value || (window.location?.origin || "http://localhost:8000");
  if (refs.qwenBaseUrl) refs.qwenBaseUrl.value = localStorage.getItem("beso.settings.qwenBaseUrl") || refs.qwenBaseUrl.value || "";
  if (refs.qwenModel) refs.qwenModel.value = localStorage.getItem("beso.settings.qwenModel") || refs.qwenModel.value || "";
  refs.baseUrlText && (refs.baseUrlText.textContent = normalizedBaseUrl().replace(/^https?:\/\//, ""));
} catch {}
fetch(`${normalizedBaseUrl()}/api/config/qwen`, { cache: "no-store" })
  .then((r) => r.json())
  .then((cfg) => {
    if (refs.qwenStatus) refs.qwenStatus.textContent = cfg.configured ? `已连接 (${cfg.model || "qwen"})` : "未配置";
    if (refs.qwenBaseUrl && cfg.base_url) refs.qwenBaseUrl.value = cfg.base_url;
    if (refs.qwenModel && cfg.model) refs.qwenModel.value = cfg.model;
  })
  .catch(() => {
    if (refs.qwenStatus) refs.qwenStatus.textContent = "未配置";
  });
try { layout.setSidebarCollapsed(localStorage.getItem("beso.sidebar.collapsed") === "1"); } catch {}
updateStepperClickableState();
wireLogFloatDock();
refreshLogSummaryViews();
updateSpinToggleUi();
taskManager.loadTasks().catch(() => {});
