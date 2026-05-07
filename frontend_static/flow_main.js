import { createLayoutManager } from "./flow_main.layout.js";
import { createTaskManager } from "./flow_main.tasks.js";
import { createViewer } from "./flow_main.viewer.js";
import { createDesignDomainViewer } from "./flow_main.designDomainViewer.js";
import { mountResultsViewer } from "./flow_main.resultsViewer.js";

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
  taskRenameDialog: $("taskRenameDialog"),
  taskRenameInput: $("taskRenameInput"),
  taskRenameSave: $("taskRenameSave"),
  taskRenameCancel: $("taskRenameCancel"),
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
  cadConvertPlanModal: $("cadConvertPlanModal"),
  cadPlanIgesName: $("cadPlanIgesName"),
  cadPlanPreset: $("cadPlanPreset"),
  cadPlanCharMax: $("cadPlanCharMax"),
  cadPlanCharMin: $("cadPlanCharMin"),
  cadPlanElementOrder: $("cadPlanElementOrder"),
  cadPlanCurvature: $("cadPlanCurvature"),
  cadPlanPartStrategy: $("cadPlanPartStrategy"),
  cadPlanTimeout: $("cadPlanTimeout"),
  cadPlanStartBtn: $("cadPlanStartBtn"),
  cadPlanLaterBtn: $("cadPlanLaterBtn"),
  cadPlanCloseBtn: $("cadPlanCloseBtn"),
  cadPlanModalTitle: $("cadPlanModalTitle"),
  cadPlanModalSubtitle: $("cadPlanModalSubtitle"),
  cadPlanSourceLabel: $("cadPlanSourceLabel"),
  cadConvertModal: $("cadConvertModal"),
  cadConvertModalDesc: $("cadConvertModalDesc"),
  cadConvertBarFill: $("cadConvertBarFill"),
  cadConvertStage: $("cadConvertStage"),
  cadConvertPauseBtn: $("cadConvertPauseBtn"),
  cadConvertEscHint: $("cadConvertEscHint"),
  cadConvertBlock: $("cadConvertBlock"),
  cadConvertBlockHint: $("cadConvertBlockHint"),
  cadConvertManualBtn: $("cadConvertManualBtn"),
  designDomainMain: $("designDomainMain"),
  designDomainBackBtn: $("designDomainBackBtn"),
  designDomainCanvasLeft: $("designDomainCanvasLeft"),
  designDomainCanvasRight: $("designDomainCanvasRight"),
  designDomainLeftOverlay: $("designDomainLeftOverlay"),
  designDomainRightOverlay: $("designDomainRightOverlay"),
  designDomainLeftOverlayText: $("designDomainLeftOverlayText"),
  designDomainRightOverlayText: $("designDomainRightOverlayText"),
  ddCutCenter: $("ddCutCenter"),
  ddIncludeSource: $("ddIncludeSource"),
  ddCharMax: $("ddCharMax"),
  ddBtnBuild: $("ddBtnBuild"),
  ddBtnPreview: $("ddBtnPreview"),
  ddBtnMesh: $("ddBtnMesh"),
  ddBtnLoads: $("ddBtnLoads"),
  ddBtnFinalize: $("ddBtnFinalize"),
  designDomainFlowLog: $("designDomainFlowLog"),
  ddStepNlDialog: $("ddStepNlDialog"),
  ddStepNlDialogPanel: $("ddStepNlDialogPanel"),
  ddStepNlTitle: $("ddStepNlTitle"),
  ddStepNlIntro: $("ddStepNlIntro"),
  ddStepNlLog: $("ddStepNlLog"),
  ddStepNlInput: $("ddStepNlInput"),
  ddStepNlSend: $("ddStepNlSend"),
  ddStepNlClose: $("ddStepNlClose"),
  ddStepNlApply: $("ddStepNlApply"),
  ddNlLoadsTa: $("ddNlLoadsTa"),
  ddNlLoadsLbl: $("ddNlLoadsLbl"),
  designDomainStepHint: $("designDomainStepHint"),
  designDomainStepRail: $("designDomainStepRail"),
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
  cadPollPaused: false,
  cadUserExited: false,
  lastCadScanData: null,
  step1NeedsInp: false,
  oc4DesignDomainSessionId: "",
  oc4DesignDomainFinalized: false,
  oc4PendingLoads: null,
  oc4LastSuggestedBuild: null,
  oc4LastSuggestedLoads: null,
  oc4PendingMesh: null,
  oc4LastSuggestedMesh: null,
  oc4PendingExport: null,
  oc4LastSuggestedExport: null,
  /** 专步 AI 对话框当前 topic：design | preview | mesh | loads */
  ddNlTopic: "",
  ddNlLastPayload: null,
  /** OC4 设计域分步：由 GET session 的布尔字段填充 */
  ddProgress: null,
};

let designDomainViewer = null;

function _defaultPortForProtocol(proto) {
  return proto === "https:" ? "443" : "80";
}

/** 页面与 API 基址若仅为 localhost ↔ 127.0.0.1 差异，改为与当前页同源，避免浏览器按跨域处理。 */
function migrateCrossHostBaseUrl() {
  if (typeof window === "undefined" || !refs.baseUrlInput) return;
  const raw = String(refs.baseUrlInput.value || "").trim();
  if (!raw) return;
  const page = window.location;
  try {
    const api = new URL(/^https?:\/\//i.test(raw) ? raw : `${page.protocol}//${raw}`);
    const sameScheme = api.protocol === page.protocol;
    const pPort = page.port || _defaultPortForProtocol(page.protocol);
    const aPort = api.port || _defaultPortForProtocol(api.protocol);
    if (!sameScheme || aPort !== pPort) return;
    const cross =
      (page.hostname === "localhost" && api.hostname === "127.0.0.1") ||
      (page.hostname === "127.0.0.1" && api.hostname === "localhost");
    if (cross) {
      refs.baseUrlInput.value = page.origin;
      localStorage.setItem("beso.settings.baseUrl", page.origin);
    }
  } catch {
    /* ignore */
  }
}

function normalizedBaseUrl() {
  let u = String(refs.baseUrlInput?.value || "").trim();
  if (!u && typeof window !== "undefined" && window.location?.origin) {
    u = window.location.origin;
  }
  if (!u) u = "http://127.0.0.1:8000";
  try {
    const parsed = new URL(u);
    return (parsed.origin + (parsed.pathname === "/" ? "" : parsed.pathname.replace(/\/$/, ""))).replace(/\/$/, "");
  } catch {
    return u.replace(/\/$/, "");
  }
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
  viewer.resetPreviewState?.();
  refs.codeTabs && (refs.codeTabs.innerHTML = "");
  refs.codePreview && (refs.codePreview.innerHTML = '<div class="codePreviewHead">生成代码</div><pre class="codePreviewBody"><code>(等待代码生成)</code></pre>');
  refs.codeStreamWrap && (refs.codeStreamWrap.innerHTML = "");
  refs.imgGrid && (refs.imgGrid.innerHTML = "");
  clearMetricsEmptyState();
  checkStep3Ready();
}

function deriveMaxReachedStepFromTask(task) {
  const st = String(task?.status || "").toLowerCase();
  if (st === "completed" || st === "done") return 4;
  const stepNum = Number(task?.step);
  const hasValidStep = Number.isFinite(stepNum) && stepNum >= 1 && stepNum <= 4;
  if (st === "uploaded" || st === "orchestrating") return hasValidStep ? Math.min(1, stepNum) : 1;
  if (st === "ready_to_execute") return hasValidStep ? Math.min(4, Math.max(1, stepNum)) : 1;
  if (st === "running" || st === "queued" || st === "pending") {
    return hasValidStep ? Math.min(4, Math.max(1, stepNum)) : 1;
  }
  if (st === "failed" || st === "cancelled" || st === "missing") {
    return hasValidStep ? Math.min(4, Math.max(1, stepNum)) : 1;
  }
  return hasValidStep ? Math.min(4, Math.max(1, stepNum)) : 1;
}

let taskManager = null;
taskManager = createTaskManager({
  refs,
  state,
  normalizedBaseUrl,
  onOpenTask: async (task) => {
    const tid = String(task?.task_id || "").trim();
    const nextTaskKey = tid || String(task?.job_id || "").trim();
    if (tid) state.currentTaskId = tid;
    if (state.activeTaskKey !== nextTaskKey) {
      resetTaskRuntimeView();
      state.activeTaskKey = nextTaskKey;
    }
    state.currentTaskStatus = String(task.status || "");
    state.maxReachedStep = deriveMaxReachedStepFromTask(task);
    if (refs.scanDirInput) refs.scanDirInput.value = state.uploadedSourceDir;
    if (refs.fileSummaryInline) {
      refs.fileSummaryInline.textContent = `已上传文件：${state.currentFileName || "(未知)"}\n扫描目录：${state.uploadedSourceDir || "(未知)"}`;
    }
    if (refs.msgLanding && task.title) refs.msgLanding.value = task.title;

    const uiStage = String(task.ui_stage || "").toLowerCase();
    const routeByUi = async () => {
      if (uiStage === "orchestrate") {
        layout.showStage("orchestrate");
        const st = String(state.currentTaskStatus || "").toLowerCase();
        if (st === "ready_to_execute" || st === "completed" || st === "done") {
          if (refs.executePlannedTask) refs.executePlannedTask.disabled = false;
        } else if (st === "orchestrating") {
          if (refs.executePlannedTask) refs.executePlannedTask.disabled = true;
          layout.streamOrchestration(async () => {
            if (refs.executePlannedTask) refs.executePlannedTask.disabled = false;
            layout.addLandingBubble("agent", "编排完成，点击“执行任务”进入分步执行。");
            await taskManager.upsertTask({ progress: 20, step: 1, status: "ready_to_execute" });
            await taskManager.loadTasks();
          });
        } else if (refs.executePlannedTask) {
          refs.executePlannedTask.disabled = false;
        }
        return;
      }
      if (uiStage === "design_domain") {
        const sid = String(task.oc4_design_domain_session_id || "").trim();
        if (sid) state.oc4DesignDomainSessionId = sid;
        if (!state.currentFileId) {
          layout.showStage("landing");
          layout.addLandingBubble("agent", "该任务缺少已上传文件记录，无法恢复 OC4 设计域。已回到主页。");
          return;
        }
        await enterOc4DesignDomainStage({ softResume: Boolean(state.oc4DesignDomainSessionId) });
        return;
      }
      if (uiStage === "flow") {
        layout.showStage("flow");
        const sn = Number(task.step);
        layout.setStep(Number.isFinite(sn) && sn >= 1 && sn <= 4 ? sn : 1);
        return;
      }
      if (uiStage === "landing") {
        layout.showStage("landing");
        return;
      }
      const sn = Number(task.step);
      if (Number.isFinite(sn) && sn >= 1 && sn <= 4) {
        layout.showStage("flow");
        layout.setStep(sn);
      } else {
        layout.showStage("landing");
      }
    };
    await routeByUi();

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
    updateStepperClickableState();
  },
});

(function wireLayoutTaskSync() {
  let uiStageTimer = null;
  function mapLayoutModeToUiStage(mode) {
    if (mode === "designDomain") return "design_domain";
    return String(mode || "landing");
  }
  const origShow = layout.showStage.bind(layout);
  layout.showStage = (mode) => {
    origShow(mode);
    if (mode === "landing") taskManager.loadTasks().catch(() => {});
    if (!state.currentTaskId) return;
    clearTimeout(uiStageTimer);
    uiStageTimer = setTimeout(() => {
      taskManager.upsertTask({ ui_stage: mapLayoutModeToUiStage(mode) }).catch(() => {});
    }, 450);
  };
  const origGo = layout.goHome.bind(layout);
  layout.goHome = () => {
    origGo();
    taskManager.loadTasks().catch(() => {});
  };
})();
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") taskManager?.loadTasks().catch(() => {});
});

function isOc4IgesFilename(name) {
  return /\.(igs|iges)$/i.test(String(name || ""));
}

function disposeDesignDomainViewer() {
  try {
    designDomainViewer?.dispose();
  } catch {}
  designDomainViewer = null;
}

function ensureDesignDomainViewer() {
  if (designDomainViewer) {
    designDomainViewer.resizeAll?.();
    return designDomainViewer;
  }
  const L = refs.designDomainCanvasLeft;
  const R = refs.designDomainCanvasRight;
  if (!L || !R) return null;
  designDomainViewer = createDesignDomainViewer({
    leftContainer: L,
    rightContainer: R,
    normalizedBaseUrl,
  });
  queueMicrotask(() => {
    designDomainViewer?.resizeAll?.();
  });
  return designDomainViewer;
}

function resetOc4DesignDomainState() {
  state.oc4DesignDomainSessionId = "";
  state.oc4PendingLoads = null;
  state.oc4LastSuggestedBuild = null;
  state.oc4LastSuggestedLoads = null;
  state.oc4PendingMesh = null;
  state.oc4LastSuggestedMesh = null;
  state.oc4PendingExport = null;
  state.oc4LastSuggestedExport = null;
  state.ddNlTopic = "";
  state.ddNlLastPayload = null;
  state.ddProgress = null;
  closeDdNlModal();
  applyDesignDomainStepUi();
}

function deferTwoFrames() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });
}

async function oc4DesignDomainApi(path, body, options = {}) {
  const timeoutMs = options.timeoutMs ?? 900000;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let resp;
  try {
    resp = await fetch(`${normalizedBaseUrl()}/api/oc4/design-domain${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      signal: ctrl.signal,
    });
  } catch (e) {
    if (e?.name === "AbortError") {
      throw new Error(`请求超时（>${Math.round(timeoutMs / 60000)} 分钟）：${path}`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
  const raw = await resp.text();
  let data = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    data = { detail: raw.slice(0, 500) };
  }
  if (!resp.ok) {
    const d = data.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? JSON.stringify(d) : JSON.stringify(data);
    throw new Error(msg || `HTTP ${resp.status}`);
  }
  return data;
}

function appendDesignDomainChat(role, text) {
  const log = refs.designDomainFlowLog;
  if (!log) return;
  const row = document.createElement("div");
  row.className = `ddMsg ${role === "user" ? "user" : "agent"}`;
  row.textContent = text;
  log.appendChild(row);
  while (log.children.length > 40) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

function appendDdNlLog(role, text) {
  const log = refs.ddStepNlLog;
  if (!log) return;
  const row = document.createElement("div");
  row.className = `ddMsg ${role === "user" ? "user" : "agent"}`;
  row.textContent = text;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

const DD_NL_TOPIC_META = {
  design: { title: "步骤 1 · 设计域构建", intro: "讨论是否挖除中心柱、是否合并源几何；应用建议后请再点「1 构建设计域」。" },
  preview: { title: "步骤 2 · OBJ 预览", intro: "调整源/设计域三角化疏密（linear_deflection_*，与主页 CAD 转换无关）；应用后点「2 导出 OBJ 预览」。" },
  mesh: {
    title: "步骤 3 · FreeCAD 体网格",
    intro:
      "与主页「IGES→INP」相同管线：backend/tools/cad_iges_to_inp.py → scripts/freecad_iges_to_inp_runner.py。点击「3 FreeCAD 体网格」会先弹出与主页一致的 **Plan 方案窗** 供确认/调参；工具栏 char_max 若填写会覆盖方案中的 CharacteristicLengthMax。上方步骤条可点击回溯定位各步。",
  },
  loads: {
    title: "步骤 4 · 载荷与分区",
    intro: "描述力、边界意图；下方长框可写自然语言（与「4 划分载荷」一致）。应用建议后点「4 划分载荷」。",
  },
};

function syncDdNlInputVisibility() {
  const t = state.ddNlTopic;
  const loads = t === "loads";
  if (refs.ddNlLoadsTa) refs.ddNlLoadsTa.classList.toggle("hidden", !loads);
  if (refs.ddNlLoadsLbl) refs.ddNlLoadsLbl.classList.toggle("hidden", !loads);
  if (refs.ddStepNlInput) refs.ddStepNlInput.classList.toggle("hidden", loads);
}

function openDdNlModal(topic) {
  const dlg = refs.ddStepNlDialog;
  if (!dlg || !DD_NL_TOPIC_META[topic]) return;
  state.ddNlTopic = topic;
  state.ddNlLastPayload = null;
  if (refs.ddStepNlLog) refs.ddStepNlLog.innerHTML = "";
  if (refs.ddStepNlInput) refs.ddStepNlInput.value = "";
  if (topic !== "loads" && refs.ddNlLoadsTa) refs.ddNlLoadsTa.value = "";
  const meta = DD_NL_TOPIC_META[topic];
  if (refs.ddStepNlTitle) refs.ddStepNlTitle.textContent = meta.title;
  if (refs.ddStepNlIntro) refs.ddStepNlIntro.textContent = meta.intro;
  syncDdNlInputVisibility();
  refreshDdNlApplyEnabled();
  if (typeof dlg.showModal === "function") dlg.showModal();
  else dlg.setAttribute("open", "");
}

function closeDdNlModal() {
  const dlg = refs.ddStepNlDialog;
  if (!dlg) return;
  if (typeof dlg.close === "function") dlg.close();
  dlg.removeAttribute("open");
  state.ddNlTopic = "";
}

function refreshDdNlApplyEnabled() {
  const btn = refs.ddStepNlApply;
  if (!btn) return;
  const p = state.ddNlLastPayload;
  const t = state.ddNlTopic;
  if (!p || !t) {
    btn.disabled = true;
    return;
  }
  let ok = false;
  if (t === "design" && p.suggested_build && typeof p.suggested_build === "object") ok = true;
  if (t === "preview" && p.suggested_export && typeof p.suggested_export === "object") ok = true;
  if (t === "mesh" && p.suggested_mesh && typeof p.suggested_mesh === "object") ok = true;
  if (t === "loads" && p.suggested_loads && typeof p.suggested_loads === "object") ok = true;
  btn.disabled = !ok;
}

function applyDdNlSuggestions() {
  const p = state.ddNlLastPayload;
  const t = state.ddNlTopic;
  if (!p || !t) return;
  if (t === "design" && p.suggested_build && typeof p.suggested_build === "object") {
    const b = p.suggested_build;
    if (typeof b.cut_center_column === "boolean" && refs.ddCutCenter) refs.ddCutCenter.checked = b.cut_center_column;
    if (typeof b.include_source_geometry === "boolean" && refs.ddIncludeSource) refs.ddIncludeSource.checked = b.include_source_geometry;
    appendDdNlLog("agent", "已应用设计域选项到复选框。");
  }
  if (t === "preview" && p.suggested_export && typeof p.suggested_export === "object") {
    state.oc4PendingExport = { ...p.suggested_export };
    appendDdNlLog("agent", "已保存 OBJ 预览参数，请点击「2 导出 OBJ 预览」。");
  }
  if (t === "mesh" && p.suggested_mesh && typeof p.suggested_mesh === "object") {
    state.oc4PendingMesh = { ...p.suggested_mesh };
    const mx = Number(p.suggested_mesh.characteristic_length_max);
    if (refs.ddCharMax && Number.isFinite(mx) && mx > 0) refs.ddCharMax.value = String(mx);
    appendDdNlLog("agent", "已写入体网格建议（并同步 char_max 输入框，若模型给出）。可直接点「3 FreeCAD 体网格」。");
  }
  if (t === "loads" && p.suggested_loads && typeof p.suggested_loads === "object") {
    const l = p.suggested_loads;
    const next = { ...(state.oc4PendingLoads && typeof state.oc4PendingLoads === "object" ? state.oc4PendingLoads : {}) };
    const bs = Number(l.band_scale);
    const zf = Number(l.z_fix_band);
    const cm = Number(l.cload_mag);
    if (Number.isFinite(bs)) next.band_scale = bs;
    if (Number.isFinite(zf)) next.z_fix_band = zf;
    if (Number.isFinite(cm)) next.cload_mag = cm;
    if (typeof l.cload_mode === "string" && l.cload_mode.trim()) next.cload_mode = l.cload_mode.trim();
    const tc = Number(l.top_node_count ?? l.count);
    if (Number.isFinite(tc) && tc >= 1) next.top_node_count = tc;
    const tf = Number(l.top_fraction ?? l.fraction);
    if (Number.isFinite(tf)) next.top_fraction = tf;
    const ce = Number(l.cload_each);
    if (Number.isFinite(ce)) next.cload_each = ce;
    const cd = Number(l.cload_dof);
    if (Number.isFinite(cd) && (cd === 1 || cd === 2 || cd === 3)) next.cload_dof = cd;
    if (Array.isArray(l.explicit_cloads) && l.explicit_cloads.length) next.explicit_cloads = l.explicit_cloads;
    state.oc4PendingLoads = Object.keys(next).length ? next : null;
    appendDdNlLog("agent", "已合并载荷数值建议；自然语言框内容会在划分时一并提交。");
  }
  refreshDdNlApplyEnabled();
}

function buildOc4LoadsRequestBody() {
  const sid = state.oc4DesignDomainSessionId;
  const out = { session_id: sid, band_scale: 1.22, z_fix_band: 800.0, cload_mag: -5e6 };
  const o = state.oc4PendingLoads;
  if (o && typeof o === "object") {
    const bs = Number(o.band_scale);
    const zf = Number(o.z_fix_band);
    const cm = Number(o.cload_mag);
    if (Number.isFinite(bs) && bs >= 1 && bs <= 3) out.band_scale = bs;
    if (Number.isFinite(zf) && zf >= 10) out.z_fix_band = zf;
    if (Number.isFinite(cm)) out.cload_mag = cm;
    const lc = {};
    if (typeof o.cload_mode === "string" && o.cload_mode.trim()) lc.cload_mode = o.cload_mode.trim();
    const tc = Number(o.top_node_count ?? o.count);
    if (Number.isFinite(tc) && tc >= 1) lc.top_node_count = Math.min(500, Math.floor(tc));
    const tf = Number(o.top_fraction ?? o.fraction);
    if (Number.isFinite(tf) && tf > 0) lc.top_fraction = Math.min(0.5, Math.max(0.0001, tf));
    const ce = Number(o.cload_each);
    if (Number.isFinite(ce)) lc.cload_each = ce;
    const cd = Number(o.cload_dof);
    if (Number.isFinite(cd) && (cd === 1 || cd === 2 || cd === 3)) lc.cload_dof = cd;
    if (Array.isArray(o.explicit_cloads) && o.explicit_cloads.length) {
      lc.explicit_cloads = o.explicit_cloads
        .filter((x) => x && typeof x === "object")
        .slice(0, 500)
        .map((x) => ({
          node: Number(x.node ?? x.nid),
          dof: Number(x.dof) || 3,
          magnitude: Number(x.magnitude ?? x.mag ?? x.value),
        }))
        .filter((x) => Number.isFinite(x.node) && Number.isFinite(x.magnitude) && [1, 2, 3].includes(x.dof));
    }
    if (Object.keys(lc).length) out.load_case = lc;
  }
  const nl = String(refs.ddNlLoadsTa?.value || "").trim();
  if (nl) out.loads_natural_language = nl;
  return out;
}

function buildOc4MeshRequestBody(plan) {
  const sid = state.oc4DesignDomainSessionId;
  const body = { session_id: sid };
  const m = state.oc4PendingMesh;
  if (m && typeof m === "object") {
    if (typeof m.element_dimension === "string" && m.element_dimension.trim()) {
      body.element_dimension = m.element_dimension.trim();
    }
    const gt = Number(m.geometry_tolerance);
    if (Number.isFinite(gt)) body.geometry_tolerance = gt;
    if (typeof m.optimize_std === "boolean") body.optimize_std = m.optimize_std;
    if (typeof m.length_unit === "string" && m.length_unit.trim()) body.length_unit = m.length_unit.trim();
    if (!plan) {
      const mx = Number(m.characteristic_length_max);
      if (Number.isFinite(mx) && mx > 0) body.characteristic_length_max = mx;
      const mn = Number(m.characteristic_length_min);
      if (Number.isFinite(mn) && mn >= 0) body.characteristic_length_min = mn;
      if (typeof m.element_order === "string" && m.element_order.trim()) body.element_order = m.element_order.trim();
      const curv = Number(m.mesh_size_from_curvature);
      if (Number.isFinite(curv)) body.mesh_size_from_curvature = curv;
      if (typeof m.compound_part_strategy === "string" && m.compound_part_strategy.trim()) {
        body.compound_part_strategy = m.compound_part_strategy.trim();
      }
      const tm = Number(m.timeout_minutes);
      if (Number.isFinite(tm) && tm >= 5 && tm <= 720) body.timeout_minutes = tm;
    }
  }
  if (plan && typeof plan === "object") {
    if (plan.characteristic_length_max != null) body.characteristic_length_max = plan.characteristic_length_max;
    if (plan.characteristic_length_min != null) body.characteristic_length_min = plan.characteristic_length_min;
    if (plan.element_order) body.element_order = plan.element_order;
    if (plan.mesh_size_from_curvature !== undefined) body.mesh_size_from_curvature = plan.mesh_size_from_curvature;
    if (plan.compound_part_strategy) body.compound_part_strategy = plan.compound_part_strategy;
    if (plan.timeout_minutes != null) body.timeout_minutes = plan.timeout_minutes;
  }
  const raw = refs.ddCharMax?.value?.trim();
  if (raw) {
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) body.characteristic_length_max = n;
  }
  return body;
}

function setDesignDomainOverlay(side, visible, text) {
  const overlay = side === "left" ? refs.designDomainLeftOverlay : refs.designDomainRightOverlay;
  const textEl = side === "left" ? refs.designDomainLeftOverlayText : refs.designDomainRightOverlayText;
  if (!overlay) return;
  if (text != null && textEl) textEl.textContent = text;
  overlay.classList.toggle("hidden", !visible);
  overlay.setAttribute("aria-hidden", visible ? "false" : "true");
}

function readDdProgressFromPayload(data) {
  const d = data && typeof data === "object" ? data : {};
  return {
    has_source_preview_obj: Boolean(d.has_source_preview_obj),
    has_design_domain_step: Boolean(d.has_design_domain_step),
    has_design_preview_obj: Boolean(d.has_design_preview_obj),
    has_mesh_body_inp: Boolean(d.has_mesh_body_inp),
    has_for_beso_inp: Boolean(d.has_for_beso_inp),
  };
}

function computeDdStepHint(p) {
  if (!p.has_source_preview_obj) {
    return "下一步：点击「1 构建设计域」生成左侧源装配 OBJ（IGES→STEP→三角化）；自动进入本页时也会尝试执行。";
  }
  if (!p.has_design_domain_step) {
    return "左侧预览已就绪；下一步：完成「1 构建设计域」以生成 01_design_domain.step 与右侧几何。";
  }
  if (!p.has_design_preview_obj) {
    return "设计域 STEP 已就绪；下一步：点击「2 导出 OBJ 预览」刷新右侧三角化装配。";
  }
  if (!p.has_mesh_body_inp) {
    return "下一步：点击「3 FreeCAD 体网格」——将先弹出与主页一致的 Plan 方案窗，确认 FreeCAD+Gmsh 参数后再生成 02_mesh_body.inp。";
  }
  if (!p.has_for_beso_inp) {
    return "下一步：点击「4 划分载荷」生成 03_for_beso.inp，然后点击「完成并进入编排」。";
  }
  return "前置步骤已就绪：点击「完成并进入编排」写入扫描目录并进入智能体编排。";
}

function applyDesignDomainStepUi() {
  const sid = state.oc4DesignDomainSessionId;
  const hintEl = refs.designDomainStepHint;
  const rail = refs.designDomainStepRail;
  const p = sid ? state.ddProgress ?? readDdProgressFromPayload({}) : readDdProgressFromPayload({});

  if (hintEl) {
    hintEl.textContent = sid ? computeDdStepHint(p) : "上传 OC4 IGES 后将进入本流程；尚未建立设计域会话。";
  }

  if (rail && sid) {
    const s1 = p.has_source_preview_obj;
    const s2 = p.has_design_domain_step && p.has_design_preview_obj;
    const s3 = p.has_mesh_body_inp;
    const s4 = p.has_for_beso_inp;
    let cur = 1;
    if (!s1) cur = 1;
    else if (!p.has_design_domain_step || !p.has_design_preview_obj) cur = 2;
    else if (!s3) cur = 3;
    else if (!s4) cur = 4;
    else cur = null;
    const doneFlags = [s1, s2, s3, s4];
    for (let i = 0; i < 4; i += 1) {
      const el = rail.querySelector(`.ddStep[data-idx="${i + 1}"]`);
      if (!el) continue;
      el.classList.toggle("ddStepDone", doneFlags[i]);
      el.classList.toggle("ddStepCurrent", cur === i + 1);
      el.setAttribute("aria-current", cur === i + 1 ? "step" : "false");
      el.classList.toggle("ddStepNavigable", true);
      el.tabIndex = 0;
    }
  } else if (rail) {
    rail.removeAttribute("data-rail-focus");
    for (let i = 1; i <= 4; i += 1) {
      const el = rail.querySelector(`.ddStep[data-idx="${i}"]`);
      if (!el) continue;
      el.classList.remove("ddStepDone", "ddStepCurrent", "ddStepNavigable");
      el.setAttribute("aria-current", "false");
      el.tabIndex = -1;
    }
  }

  const noSess = !sid;
  const setBtn = (el, disabled, title) => {
    if (!el) return;
    el.disabled = Boolean(disabled);
    el.title = title || "";
  };
  setBtn(refs.ddBtnBuild, noSess, noSess ? "请先上传 IGES 并进入本页。" : "");
  setBtn(
    refs.ddBtnPreview,
    noSess || !p.has_design_domain_step,
    !p.has_design_domain_step ? "需先有 01_design_domain.step：请先点「1 构建设计域」。" : "刷新两侧 OBJ（不重新执行 build）。",
  );
  setBtn(
    refs.ddBtnMesh,
    noSess || !p.has_design_domain_step,
    !p.has_design_domain_step ? "请先完成设计域构建（步骤 1）。" : "",
  );
  setBtn(refs.ddBtnLoads, noSess || !p.has_mesh_body_inp, !p.has_mesh_body_inp ? "请先生成 02_mesh_body.inp（步骤 3）。" : "");
  setBtn(
    refs.ddBtnFinalize,
    noSess || !p.has_for_beso_inp,
    !p.has_for_beso_inp ? "请先生成 03_for_beso.inp（步骤 4）。" : "写入扫描目录并进入编排。",
  );
}

function mapDdRailIdxToToolbarBtn(idx) {
  if (idx === 1) return refs.ddBtnBuild;
  if (idx === 2) return refs.ddBtnPreview;
  if (idx === 3) return refs.ddBtnMesh;
  if (idx === 4) return refs.ddBtnLoads;
  return null;
}

function focusDesignDomainRailStep(idx) {
  const rail = refs.designDomainStepRail;
  if (rail) rail.setAttribute("data-rail-focus", String(idx));
  const btn = mapDdRailIdxToToolbarBtn(idx);
  if (btn) {
    try {
      btn.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch {
      btn.scrollIntoView();
    }
    try {
      btn.focus({ preventScroll: true });
    } catch {
      btn.focus();
    }
  }
  const names = ["", "构建设计域 / 源预览", "导出 OBJ 预览", "FreeCAD 体网格", "划分载荷"];
  appendDesignDomainChat("agent", `步骤条回溯：已定位到第 ${idx} 步「${names[idx] || ""}」，可在下方工具栏重试该步。`);
}

async function fetchOc4DesignDomainSessionJson() {
  const sid = state.oc4DesignDomainSessionId;
  if (!sid) return { ok: false, data: {} };
  const resp = await fetch(
    `${normalizedBaseUrl()}/api/oc4/design-domain/session/${encodeURIComponent(sid)}`,
    { cache: "no-store" },
  );
  const data = await resp.json().catch(() => ({}));
  return { ok: resp.ok, data };
}

function ingestDdSessionPayload(data) {
  state.ddProgress = readDdProgressFromPayload(data);
  applyDesignDomainStepUi();
}

async function syncDesignDomainSessionProgress() {
  const { ok, data } = await fetchOc4DesignDomainSessionJson();
  if (ok) ingestDdSessionPayload(data);
}

async function runDdSourcePreviewOnly() {
  const sid = state.oc4DesignDomainSessionId;
  if (!sid) throw new Error("缺少会话，请先上传 IGES 并进入本页。");
  setDesignDomainOverlay("left", true, "正在将源几何转为 STEP 并生成预览…");
  try {
    const urls = await oc4DesignDomainApi(
      "/export-source-preview",
      { session_id: sid },
      { timeoutMs: 900000 },
    );
    await deferTwoFrames();
    const v = ensureDesignDomainViewer();
    if (v && urls.source_obj) {
      await v.loadLeft(urls.source_obj);
      v.resizeAll?.();
    }
    return urls;
  } finally {
    setDesignDomainOverlay("left", false);
  }
}

async function refreshDesignDomainPreviewsFromSession() {
  const sid = state.oc4DesignDomainSessionId;
  if (!sid) return;
  try {
    const { ok, data } = await fetchOc4DesignDomainSessionJson();
    if (!ok) return;
    ingestDdSessionPayload(data);
    const v = ensureDesignDomainViewer();
    if (!v) return;
    await deferTwoFrames();
    v.resizeAll?.();
    const errs = [];
    if (data.source_obj_url) {
      try {
        await v.loadLeft(data.source_obj_url);
      } catch (e) {
        errs.push(`左侧：${e?.message || e}`);
      }
    }
    if (data.design_obj_url) {
      try {
        await v.loadRight(data.design_obj_url);
      } catch (e) {
        errs.push(`右侧：${e?.message || e}`);
      }
    }
    v.resizeAll?.();
    if (errs.length) appendDesignDomainChat("agent", errs.join("；"));
    if (!data.source_obj_url && !data.design_obj_url) {
      appendDesignDomainChat("agent", "会话中尚无 OBJ 预览，请先点击「1 构建设计域」。");
    }
  } catch (e) {
    appendDesignDomainChat("agent", `恢复预览失败：${e?.message || e}`);
  }
}

async function runDdBuildAndExportObj() {
  const sid = state.oc4DesignDomainSessionId;
  if (!sid) throw new Error("缺少会话，请先上传 IGES 并进入本页。");
  setDesignDomainOverlay("right", true, "正在生成设计域…");
  try {
    await oc4DesignDomainApi(
      "/build",
      {
        session_id: sid,
        cut_center_column: Boolean(refs.ddCutCenter?.checked),
        include_source_geometry: Boolean(refs.ddIncludeSource?.checked),
      },
      { timeoutMs: 900000 },
    );
    setDesignDomainOverlay("right", true, "正在导出设计域 OBJ 预览…");
    const urls = await oc4DesignDomainApi(
      "/export-obj",
      { session_id: sid, design_only: true },
      { timeoutMs: 900000 },
    );
    await deferTwoFrames();
    const v = ensureDesignDomainViewer();
    if (v) {
      try {
        if (urls.design_obj) await v.loadRight(urls.design_obj);
      } catch (loadErr) {
        appendDesignDomainChat("agent", `右侧 OBJ 加载失败：${loadErr?.message || loadErr}`);
        throw loadErr;
      }
      v.resizeAll?.();
    }
    return urls;
  } finally {
    setDesignDomainOverlay("right", false);
  }
}

async function enterOc4DesignDomainStage(opts = {}) {
  const { autoPipeline = false, forceNewSession = false, softResume = false } = opts;
  if (!state.currentFileId) {
    layout.addLandingBubble("agent", "请先上传 IGES 文件。");
    return;
  }
  if (!isOc4IgesFilename(state.currentFileName)) {
    layout.addLandingBubble("agent", "当前文件不是 IGES（.igs/.iges），OC4 设计域步骤不适用。");
    return;
  }
  if (softResume && state.oc4DesignDomainSessionId && !forceNewSession) {
    layout.showStage("designDomain");
    await deferTwoFrames();
    await refreshDesignDomainPreviewsFromSession();
    appendDesignDomainChat("agent", "请继续：完成体网格、载荷划分后点击「完成并进入编排」，或调整选项后重建设计域。");
    return;
  }
  layout.showStage("designDomain");
  const hadSession = Boolean(state.oc4DesignDomainSessionId) && !forceNewSession;
  if (!hadSession && refs.designDomainFlowLog) refs.designDomainFlowLog.innerHTML = "";
  if (!hadSession) {
    state.oc4LastSuggestedBuild = null;
    state.oc4LastSuggestedLoads = null;
    state.oc4PendingMesh = null;
    state.oc4PendingExport = null;
  }
  try {
    if (!state.oc4DesignDomainSessionId || forceNewSession) {
      const sess = await oc4DesignDomainApi("/session", { file_id: state.currentFileId });
      state.oc4DesignDomainSessionId = sess.session_id;
      appendDesignDomainChat("agent", `已创建设计域会话（${sess.session_id.slice(0, 8)}…）。几何摘要已写入服务端。`);
      if (state.currentTaskId) {
        taskManager.upsertTask({ oc4_design_domain_session_id: state.oc4DesignDomainSessionId }).catch(() => {});
      }
    } else {
      appendDesignDomainChat("agent", `继续会话 ${state.oc4DesignDomainSessionId.slice(0, 8)}…（重新上传文件可开启新会话）`);
    }
    await deferTwoFrames();
    if (autoPipeline) {
      appendDesignDomainChat("agent", "先生成源几何 STEP 预览（左侧）…");
      await runDdSourcePreviewOnly();
      appendDesignDomainChat("agent", "源预览已就绪；正在构建设计域并更新右侧预览…");
      await runDdBuildAndExportObj();
      appendDesignDomainChat("agent", "预览已更新。各步骤可点步骤条「AI」打开专步对话；体网格默认最粗以控制 INP 体积。");
    } else {
      await refreshDesignDomainPreviewsFromSession();
    }
  } catch (e) {
    setDesignDomainOverlay("left", false);
    setDesignDomainOverlay("right", false);
    appendDesignDomainChat("agent", String(e?.message || e));
    layout.addLandingBubble("agent", `OC4 设计域：${e?.message || e}`);
  } finally {
    await syncDesignDomainSessionProgress().catch(() => {});
  }
}

async function beginOrchestrationAfterLanding() {
  if (!state.currentTaskId) state.currentTaskId = (crypto?.randomUUID?.() || `${Date.now()}`);
  state.currentTaskStatus = "orchestrating";
  if (refs.msgEl) refs.msgEl.value = (refs.msgLanding?.value || "").trim() || refs.msgEl.value;
  layout.addLandingBubble("user", refs.msgEl?.value || "");
  await taskManager.upsertTask({
    title: (refs.msgEl?.value || "").slice(0, 80),
    progress: 12,
    step: 1,
    status: "orchestrating",
    file_name: state.currentFileName,
    scan_dir: state.uploadedSourceDir,
  });
  await taskManager.loadTasks();
  layout.showStage("orchestrate");
  if (refs.executePlannedTask) refs.executePlannedTask.disabled = true;
  layout.streamOrchestration(async () => {
    if (refs.executePlannedTask) refs.executePlannedTask.disabled = false;
    layout.addLandingBubble("agent", "编排完成，点击“执行任务”进入分步执行。");
    await taskManager.upsertTask({ progress: 20, step: 1, status: "ready_to_execute" });
    await taskManager.loadTasks();
  });
}

function focusCadConvertGuide() {
  const wrap = refs.cadConvertBlock;
  const btn = refs.cadConvertManualBtn;
  if (!btn || !wrap || wrap.classList.contains("hidden")) return;
  wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
  btn.scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    btn.focus({ preventScroll: true });
  } catch {
    btn.focus();
  }
}

function flowStepDisableReason(target) {
  if (state.step1NeedsInp && target > 1) {
    return "需先完成 IGES→INP 格式转换并生成主 INP，才能进入后续步骤。";
  }
  if (isFlowStepClickable(target)) return "";
  const completedStep = Math.max(1, state.maxReachedStep - 1);
  return `该步骤尚未解锁（当前流程最多推进到第 ${completedStep} 步之后）。`;
}

function isFlowStepClickable(target) {
  if (state.step1NeedsInp && target > 1) return false;
  const st = String(state.currentTaskStatus || "").toLowerCase();
  const allUnlocked = st === "completed" || st === "done";
  const completedStep = Math.max(1, state.maxReachedStep - 1);
  return allUnlocked || target <= completedStep || target === state.currentStep;
}

const setStepRaw = layout.setStep;
layout.setStep = (step) => {
  if (step > 1 && state.step1NeedsInp) {
    layout.addBubble(
      "agent",
      "需先完成 IGES→INP 格式转换并生成主 INP，才能进入后续步骤。请点击「IGES → INP 格式转换」（与后端 backend/tools/freecad_iges_to_inp 链路一致）。",
    );
    focusCadConvertGuide();
    return;
  }
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
  const stepEls = [
    [refs.flowStep1, 1],
    [refs.flowStep2, 2],
    [refs.flowStep3, 3],
    [refs.flowStep4, 4],
  ];
  stepEls.forEach(([el, idx]) => {
    if (!el) return;
    const clickable = isFlowStepClickable(idx);
    el.classList.toggle("stepDisabled", !clickable);
    el.classList.toggle("stepCurrent", idx === state.currentStep);
    el.setAttribute("aria-disabled", clickable ? "false" : "true");
    el.tabIndex = clickable ? 0 : -1;
    const reason = flowStepDisableReason(idx);
    el.title = clickable ? `第 ${idx} 步` : reason;
    el.setAttribute("aria-label", `流程第 ${idx} 步${clickable ? "" : `（不可用：${reason}）`}`);
  });
}

async function uploadSelectedFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const resp = await fetch(`${normalizedBaseUrl()}/api/files/upload`, { method: "POST", body: fd });
  const raw = await resp.text();
  let data = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    data = { detail: raw.slice(0, 400) };
  }
  if (!resp.ok) {
    const msg = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? JSON.stringify(data.detail) : raw.slice(0, 300);
    layout.addBubble("agent", `上传失败（${resp.status}）：${msg || "未知错误"}`);
    throw new Error(msg || `HTTP ${resp.status}`);
  }
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
  if (isOc4IgesFilename(state.currentFileName)) {
    resetOc4DesignDomainState();
    state.oc4DesignDomainFinalized = false;
    disposeDesignDomainViewer();
    layout.addLandingBubble("agent", "已识别为 IGES：进入 OC4 设计域前置步骤（构建设计域、预览、体网格与载荷）。");
    await enterOc4DesignDomainStage({ autoPipeline: true }).catch((e) => {
      layout.addLandingBubble("agent", `设计域步骤启动失败：${e?.message || e}`);
    });
  } else {
    state.oc4DesignDomainFinalized = true;
    resetOc4DesignDomainState();
    disposeDesignDomainViewer();
  }
}

function firstIgesNameFromScan(data) {
  const files = data.files || [];
  const hit = files.find((x) => /\.(igs|iges)$/i.test(String(x.name || "")));
  return hit ? String(hit.name) : null;
}

function scanNeedsCadConversion(data) {
  if (data.primary_inp) return false;
  return Boolean(firstIgesNameFromScan(data));
}

function refreshCadGateAfterScan(data) {
  state.lastCadScanData = data;
  state.step1Ready = Boolean(data.primary_inp);
  state.step1NeedsInp = scanNeedsCadConversion(data);
  if (refs.acceptStep1) {
    refs.acceptStep1.disabled = !state.step1Ready;
    refs.acceptStep1.title = state.step1NeedsInp
      ? "仅有 IGES、尚无主 INP：请先点击「IGES → INP 格式转换」。服务端使用 backend/tools/freecad_iges_to_inp（FreeCAD+Gmsh）生成 from_cad_gmsh.inp 后方可进入下一步。"
      : "";
  }
  const block = refs.cadConvertBlock;
  const btn = refs.cadConvertManualBtn;
  if (block && btn) {
    if (state.step1NeedsInp) {
      block.classList.remove("hidden");
      if (refs.cadConvertBlockHint) {
        refs.cadConvertBlockHint.textContent =
          "当前仅有几何（IGES）无主 INP：必须先完成格式转换得到 INP，才能点击「接受智能体本步骤」。请使用下方按钮（Esc 退出自动转换后也可在此重试）。";
      }
      btn.classList.add("cadConvertGuidePulse");
    } else {
      block.classList.add("hidden");
      btn.classList.remove("cadConvertGuidePulse");
    }
  }
  updateStepperClickableState();
}

function setCadConvertBar(pct) {
  if (refs.cadConvertBarFill) refs.cadConvertBarFill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
}

function showCadConvertModal() {
  if (!refs.cadConvertModal) return;
  refs.cadConvertModal.classList.remove("hidden");
  refs.cadConvertModal.setAttribute("aria-hidden", "false");
  setCadConvertBar(4);
}

function hideCadConvertModal() {
  if (!refs.cadConvertModal) return;
  refs.cadConvertModal.classList.add("hidden");
  refs.cadConvertModal.setAttribute("aria-hidden", "true");
  setCadConvertBar(0);
}

const CAD_MESH_PRESETS = {
  auto: { max: null, min: null },
  fine: { max: 3000, min: 0.05 },
  medium: { max: 12000, min: 0.1 },
  coarse: { max: 40000, min: 1 },
  xlarge: { max: 80000, min: 5 },
};

const CAD_PLAN_SUBTITLE_IGES_HTML =
  "确认 FreeCAD + Gmsh 剖分参数后开始生成 <code>from_cad_gmsh.inp</code>。服务端需配置 <code>FREECAD_CMD</code>。";

function resetCadPlanModalChrome() {
  if (refs.cadPlanModalTitle) refs.cadPlanModalTitle.textContent = "网格转换方案";
  if (refs.cadPlanModalSubtitle) refs.cadPlanModalSubtitle.innerHTML = CAD_PLAN_SUBTITLE_IGES_HTML;
  if (refs.cadPlanSourceLabel) refs.cadPlanSourceLabel.textContent = "IGES 文件";
  if (refs.cadPlanStartBtn) refs.cadPlanStartBtn.textContent = "开始转换";
}

function showCadPlanModal(config) {
  const {
    sourceLabel = "IGES 文件",
    sourceReadonly = "—",
    modalTitle = "网格转换方案",
    modalSubtitleText = null,
    modalSubtitleHtml = null,
    primaryButtonText = "开始转换",
    fallbackPlan = null,
  } = config;
  return new Promise((resolve) => {
    const modal = refs.cadConvertPlanModal;
    const fb =
      fallbackPlan ||
      (() => ({
        characteristic_length_max: null,
        characteristic_length_min: null,
        element_order: "1st",
        compound_part_strategy: "largest_volume",
        timeout_minutes: 120,
      }));
    if (!modal) {
      resolve(fb());
      return;
    }
    if (refs.cadPlanSourceLabel) refs.cadPlanSourceLabel.textContent = sourceLabel;
    if (refs.cadPlanIgesName) refs.cadPlanIgesName.textContent = sourceReadonly;
    if (refs.cadPlanModalTitle) refs.cadPlanModalTitle.textContent = modalTitle;
    if (refs.cadPlanModalSubtitle) {
      if (modalSubtitleHtml != null) refs.cadPlanModalSubtitle.innerHTML = modalSubtitleHtml;
      else if (modalSubtitleText != null) refs.cadPlanModalSubtitle.textContent = modalSubtitleText;
      else refs.cadPlanModalSubtitle.innerHTML = CAD_PLAN_SUBTITLE_IGES_HTML;
    }
    if (refs.cadPlanStartBtn) refs.cadPlanStartBtn.textContent = primaryButtonText;
    loadCadPlanDefaults();
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    const finish = (plan) => {
      document.removeEventListener("keydown", onKey);
      if (refs.cadPlanStartBtn) refs.cadPlanStartBtn.onclick = null;
      if (refs.cadPlanLaterBtn) refs.cadPlanLaterBtn.onclick = null;
      if (refs.cadPlanCloseBtn) refs.cadPlanCloseBtn.onclick = null;
      resetCadPlanModalChrome();
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
      resolve(plan);
    };
    const onKey = (e) => {
      if (e.key === "Escape") finish(null);
    };
    document.addEventListener("keydown", onKey);
    if (refs.cadPlanStartBtn) {
      refs.cadPlanStartBtn.onclick = () => {
        const plan = collectCadPlanOptions();
        saveCadPlanDefaultsFromPlan(plan);
        finish(plan);
      };
    }
    if (refs.cadPlanLaterBtn) refs.cadPlanLaterBtn.onclick = () => finish(null);
    if (refs.cadPlanCloseBtn) refs.cadPlanCloseBtn.onclick = () => finish(null);
  });
}

function showOc4MeshPlanModal() {
  const sid = String(state.oc4DesignDomainSessionId || "").trim();
  const short = sid.length > 12 ? `${sid.slice(0, 8)}…` : sid || "(无会话)";
  return showCadPlanModal({
    sourceLabel: "设计域 STEP",
    sourceReadonly: `01_design_domain.step（会话 ${short}）`,
    modalTitle: "体网格方案（OC4）",
    modalSubtitleText:
      "与主页「搜索文件 → IGES→INP」使用同一套 FreeCAD + Gmsh 参数；由此生成 02_mesh_body.inp。Gmsh 中 CharacteristicLengthMax 越大网格越粗。服务端需配置 FREECAD_CMD。",
    primaryButtonText: "开始体网格",
  });
}

function loadCadPlanDefaults() {
  try {
    const raw = localStorage.getItem("beso.cadPlan.v1");
    if (!raw) return;
    const o = JSON.parse(raw);
    if (o.preset && refs.cadPlanPreset) refs.cadPlanPreset.value = o.preset;
    if (refs.cadPlanElementOrder && o.element_order) refs.cadPlanElementOrder.value = o.element_order;
    if (refs.cadPlanPartStrategy && o.compound_part_strategy) refs.cadPlanPartStrategy.value = o.compound_part_strategy;
    if (refs.cadPlanTimeout && o.timeout_minutes != null) refs.cadPlanTimeout.value = String(o.timeout_minutes);
    if (o.char_max != null && refs.cadPlanCharMax) refs.cadPlanCharMax.value = String(o.char_max);
    if (o.char_min != null && refs.cadPlanCharMin) refs.cadPlanCharMin.value = String(o.char_min);
    if (o.curvature != null && refs.cadPlanCurvature) refs.cadPlanCurvature.value = String(o.curvature);
  } catch {}
}

function saveCadPlanDefaultsFromPlan(plan) {
  try {
    const preset = refs.cadPlanPreset?.value || "auto";
    localStorage.setItem(
      "beso.cadPlan.v1",
      JSON.stringify({
        preset,
        element_order: plan.element_order,
        compound_part_strategy: plan.compound_part_strategy,
        timeout_minutes: plan.timeout_minutes,
        char_max: refs.cadPlanCharMax?.value || "",
        char_min: refs.cadPlanCharMin?.value || "",
        curvature: refs.cadPlanCurvature?.value || "",
      }),
    );
  } catch {}
}

function collectCadPlanOptions() {
  const preset = refs.cadPlanPreset?.value || "auto";
  const pr = CAD_MESH_PRESETS[preset] || CAD_MESH_PRESETS.auto;
  const maxStr = String(refs.cadPlanCharMax?.value || "").trim();
  const minStr = String(refs.cadPlanCharMin?.value || "").trim();
  const manualMax = parseFloat(maxStr);
  const manualMin = parseFloat(minStr);
  let characteristic_length_max = null;
  if (maxStr !== "" && !Number.isNaN(manualMax)) characteristic_length_max = manualMax;
  else if (pr.max != null) characteristic_length_max = pr.max;
  let characteristic_length_min = null;
  if (minStr !== "" && !Number.isNaN(manualMin)) characteristic_length_min = manualMin;
  else if (pr.min != null && preset !== "auto") characteristic_length_min = pr.min;
  const curStr = String(refs.cadPlanCurvature?.value || "").trim();
  let mesh_size_from_curvature;
  if (curStr !== "") {
    const c = parseInt(curStr, 10);
    if (!Number.isNaN(c)) mesh_size_from_curvature = c;
  }
  const tRaw = parseFloat(String(refs.cadPlanTimeout?.value || "120"));
  const timeout_minutes = Number.isFinite(tRaw) ? Math.min(720, Math.max(5, tRaw)) : 120;
  return {
    characteristic_length_max,
    characteristic_length_min,
    element_order: refs.cadPlanElementOrder?.value || "1st",
    mesh_size_from_curvature,
    compound_part_strategy: refs.cadPlanPartStrategy?.value || "largest_volume",
    timeout_minutes,
  };
}

function buildCadConvertBody(scanDir, igesName, plan) {
  const body = { scan_dir: scanDir, iges_name: igesName };
  if (!plan) return body;
  if (plan.characteristic_length_max != null) body.characteristic_length_max = plan.characteristic_length_max;
  if (plan.characteristic_length_min != null) body.characteristic_length_min = plan.characteristic_length_min;
  body.element_order = plan.element_order;
  if (plan.mesh_size_from_curvature !== undefined) body.mesh_size_from_curvature = plan.mesh_size_from_curvature;
  body.compound_part_strategy = plan.compound_part_strategy;
  if (plan.timeout_minutes != null) body.timeout_minutes = plan.timeout_minutes;
  return body;
}

function showCadConvertPlanModal(_scanDir, data) {
  const igesName = firstIgesNameFromScan(data);
  if (!igesName) return Promise.resolve(null);
  return showCadPlanModal({
    sourceLabel: "IGES 文件",
    sourceReadonly: igesName,
    modalTitle: "网格转换方案",
    modalSubtitleHtml: CAD_PLAN_SUBTITLE_IGES_HTML,
    primaryButtonText: "开始转换",
  });
}

async function runCadConvertWithModal(scanDir, data, plan) {
  const igesName = firstIgesNameFromScan(data);
  if (!igesName) return;
  state.cadPollPaused = false;
  state.cadUserExited = false;
  if (refs.cadConvertPauseBtn) {
    refs.cadConvertPauseBtn.textContent = "暂停";
    refs.cadConvertPauseBtn.classList.remove("isPaused");
  }
  showCadConvertModal();
  if (refs.cadConvertModalDesc) {
    refs.cadConvertModalDesc.textContent =
      "已识别 IGES 几何，当前目录尚无主 INP。服务端通过 backend/tools/freecad_iges_to_inp（FreeCAD FEM + Gmsh）生成体网格并写出 from_cad_gmsh.inp。需本机安装 FreeCAD，并可设置 FREECAD_CMD。完成后会自动重新扫描目录。";
  }
  if (refs.cadConvertStage) refs.cadConvertStage.textContent = "正在提交转换任务…";
  setCadConvertBar(8);
  let taskId = "";
  const onProgressEsc = (e) => {
    if (e.key !== "Escape") return;
    if (!refs.cadConvertModal || refs.cadConvertModal.classList.contains("hidden")) return;
    e.preventDefault();
    state.cadUserExited = true;
    state.cadPollPaused = false;
    if (taskId) {
      fetch(`${normalizedBaseUrl()}/api/cad/convert-iges/${encodeURIComponent(taskId)}/cancel`, { method: "POST" }).catch(() => {});
    }
    hideCadConvertModal();
  };
  document.addEventListener("keydown", onProgressEsc);
  try {
    const body = buildCadConvertBody(scanDir, igesName, plan);
    const resp = await fetch(`${normalizedBaseUrl()}/api/cad/convert-iges`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const raw = await resp.text();
    let resBody = {};
    try {
      resBody = raw ? JSON.parse(raw) : {};
    } catch {
      resBody = { detail: raw.slice(0, 400) };
    }
    if (!resp.ok) {
      hideCadConvertModal();
      layout.addBubble("agent", `CAD 转换启动失败：${resBody.detail || JSON.stringify(resBody)}`);
      return;
    }
    taskId = resBody.task_id || "";
    if (!taskId) {
      hideCadConvertModal();
      layout.addBubble("agent", "CAD 转换启动失败：未返回 task_id。");
      return;
    }
    const timeoutMs = Math.min((Number(plan?.timeout_minutes) || 120) * 60 * 1000 + 120000, 26 * 60 * 60 * 1000);
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      while (state.cadPollPaused && !state.cadUserExited) {
        await new Promise((r) => setTimeout(r, 220));
      }
      if (state.cadUserExited) {
        hideCadConvertModal();
        layout.addBubble("agent", "已中止 CAD 转换（已请求服务端取消，FreeCAD 进程可能仍需数秒结束）。");
        return;
      }
      await new Promise((r) => setTimeout(r, 450));
      const stResp = await fetch(`${normalizedBaseUrl()}/api/cad/convert-iges/${encodeURIComponent(taskId)}`, { cache: "no-store" });
      const stRaw = await stResp.text();
      let st = {};
      try {
        st = stRaw ? JSON.parse(stRaw) : {};
      } catch {
        st = { error: stRaw.slice(0, 200) };
      }
      if (!stResp.ok) {
        hideCadConvertModal();
        layout.addBubble("agent", `转换状态查询失败：${st.detail || stRaw.slice(0, 200)}`);
        return;
      }
      if (!state.cadPollPaused) {
        const p = Number(st.progress) || 0;
        setCadConvertBar(Math.max(8, p));
        if (refs.cadConvertStage) refs.cadConvertStage.textContent = String(st.stage || "处理中…");
      }
      if (st.done) {
        if (st.cancelled) {
          hideCadConvertModal();
          layout.addBubble("agent", "CAD 转换已由服务端确认中止。");
          return;
        }
        if (st.error) {
          hideCadConvertModal();
          layout.addBubble("agent", `IGES 转换失败：${st.error}`);
          return;
        }
        setCadConvertBar(100);
        if (refs.cadConvertStage) refs.cadConvertStage.textContent = "完成，正在刷新扫描结果…";
        await new Promise((r) => setTimeout(r, 280));
        hideCadConvertModal();
        return;
      }
    }
    hideCadConvertModal();
    layout.addBubble(
      "agent",
      "CAD 转换等待超时，请检查是否已安装 FreeCAD、FREECAD_CMD 是否正确，或在方案中增大超时分钟数 / 放宽尺寸参数，稍后重试扫描。",
    );
  } catch (e) {
    hideCadConvertModal();
    layout.addBubble("agent", `CAD 转换异常：${e && e.message ? e.message : String(e)}`);
  } finally {
    document.removeEventListener("keydown", onProgressEsc);
  }
}

async function runManualCadConvert() {
  const dir = (state.uploadedSourceDir || refs.scanDirInput?.value || "").trim();
  if (!dir) return layout.addBubble("agent", "未获取到扫描目录。");
  let data = state.lastCadScanData;
  const norm = (s) =>
    String(s || "")
      .replace(/\\/g, "/")
      .trim()
      .toLowerCase();
  const needFetch = !data || norm(data.scan_dir) !== norm(dir);
  if (needFetch) {
    const resp = await fetch(`${normalizedBaseUrl()}/api/scan-directory?scan_dir=${encodeURIComponent(dir)}`);
    data = await resp.json();
    if (!resp.ok) return layout.addBubble("agent", `扫描失败：${data.detail || JSON.stringify(data)}`);
    state.lastCadScanData = data;
  }
  if (!scanNeedsCadConversion(data)) {
    layout.addBubble("agent", "当前目录已有主 INP，无需再转换。");
    applyScanDirectoryUI(data);
    return;
  }
  const plan = await showCadConvertPlanModal(dir, data);
  if (!plan) return;
  await runCadConvertWithModal(dir, data, plan);
  const resp2 = await fetch(`${normalizedBaseUrl()}/api/scan-directory?scan_dir=${encodeURIComponent(dir)}`);
  const data2 = await resp2.json();
  if (!resp2.ok) return layout.addBubble("agent", `转换后扫描失败：${data2.detail || JSON.stringify(data2)}`);
  applyScanDirectoryUI(data2);
  layout.addBubble(
    "agent",
    state.step1Ready ? "格式转换完成，主 INP 已就绪，可接受本步骤并继续。" : "转换已结束但未识别到主 INP，请检查几何/参数或查看服务端日志。",
  );
}

function applyScanDirectoryUI(data) {
  const selected = {
    primary_inp: data.primary_inp ? data.primary_inp.split(/[\\/]/).pop() : null,
    aux_inps: data.aux_inps || {},
    step_mapping: data.step_mapping || {},
  };
  layout.renderSelectedInputs(selected);
  if (refs.autoScanInfo) refs.autoScanInfo.textContent = `扫描目录：${data.scan_dir}\n主文件：${selected.primary_inp || "(none)"}\n状态：正在探索文件结构...`;
  if (refs.autoScanTree) {
    if (state.scanRevealTimer) clearInterval(state.scanRevealTimer);
    refs.autoScanTree.innerHTML = "";
    const rowMeta = (data.files || []).slice(0, 60).map((x) => ({ name: x.name, role: x.role, text: `${x.name} [${x.role}]` }));
    const iconByRole = {
      primary_candidate: "⭐",
      load_case: "⚡",
      set_definition: "🧩",
      inp_candidate: "📄",
      result_state: "🧪",
      result_frame: "🧱",
      code_file: "💻",
      log_file: "📝",
      viz_file: "🧊",
      cad_geometry: "📐",
      other: "📦",
    };
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
  refreshCadGateAfterScan(data);
}

async function scanDirectory() {
  const dir = (state.uploadedSourceDir || refs.scanDirInput?.value || "").trim();
  if (!dir) return layout.addBubble("agent", "未获取到上传文件目录，暂无法自动扫描。");
  let resp = await fetch(`${normalizedBaseUrl()}/api/scan-directory?scan_dir=${encodeURIComponent(dir)}`);
  let data = await resp.json();
  if (!resp.ok) return layout.addBubble("agent", `扫描失败：${data.detail || JSON.stringify(data)}`);
  state.lastCadScanData = data;

  if (scanNeedsCadConversion(data)) {
    const plan = await showCadConvertPlanModal(dir, data);
    if (!plan) {
      layout.addBubble(
        "agent",
        "已跳过 CAD→INP；当前目录无主 INP，可稍后在「扫描」中再次打开方案，或手动放入 from_cad_gmsh.inp。",
      );
      applyScanDirectoryUI(data);
      layout.addBubble("agent", "扫描结果已更新（未执行 CAD 转换）。");
      return;
    }
    await runCadConvertWithModal(dir, data, plan);
    resp = await fetch(`${normalizedBaseUrl()}/api/scan-directory?scan_dir=${encodeURIComponent(dir)}`);
    data = await resp.json();
    if (!resp.ok) return layout.addBubble("agent", `转换后扫描失败：${data.detail || JSON.stringify(data)}`);
  }

  applyScanDirectoryUI(data);
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
  const rawText = await resp.text();
  let data = {};
  try {
    data = rawText ? JSON.parse(rawText) : {};
  } catch {
    data = { detail: rawText ? rawText.slice(0, 400) : "(空响应)" };
  }
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
  viewer.resetPreviewState?.();
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

refs.acceptStep1?.addEventListener("click", async () => {
  if (state.step1NeedsInp) {
    layout.addBubble("agent", "需先完成 IGES→INP 并生成主 INP。请点击下方高亮的「格式转换」按钮。");
    focusCadConvertGuide();
    return;
  }
  if (!state.step1Ready) return;
  layout.setStep(2);
  await createAndRun();
});
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
    state.lastCadScanData = null;
    state.step1NeedsInp = false;
    refs.cadConvertBlock?.classList.add("hidden");
    refs.cadConvertManualBtn?.classList.remove("cadConvertGuidePulse");
    disposeDesignDomainViewer();
    resetOc4DesignDomainState();
    state.oc4DesignDomainFinalized = false;
    layout.goHome();
    await taskManager.loadTasks();
  };
  done().catch(() => {
    disposeDesignDomainViewer();
    resetOc4DesignDomainState();
    state.oc4DesignDomainFinalized = false;
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
  if (isOc4IgesFilename(state.currentFileName) && !state.oc4DesignDomainFinalized) {
    layout.addLandingBubble("agent", "OC4 IGES 需先完成设计域、体网格与载荷划分；已打开设计域步骤。");
    await enterOc4DesignDomainStage({ autoPipeline: true, softResume: true }).catch((e) => {
      layout.addLandingBubble("agent", `设计域步骤：${e?.message || e}`);
    });
    return;
  }
  await beginOrchestrationAfterLanding();
});

refs.designDomainBackBtn?.addEventListener("click", () => {
  setDesignDomainOverlay("left", false);
  setDesignDomainOverlay("right", false);
  closeDdNlModal();
  disposeDesignDomainViewer();
  layout.goHome();
});
refs.ddBtnBuild?.addEventListener("click", async () => {
  try {
    appendDesignDomainChat("agent", "刷新源几何预览并按选项重建设计域…");
    await runDdSourcePreviewOnly();
    await runDdBuildAndExportObj();
    appendDesignDomainChat("agent", "构建与预览已更新。");
  } catch (e) {
    appendDesignDomainChat("agent", String(e?.message || e));
  } finally {
    await syncDesignDomainSessionProgress().catch(() => {});
  }
});
refs.ddBtnPreview?.addEventListener("click", async () => {
  try {
    setDesignDomainOverlay("left", true, "正在更新 STEP 与 OBJ 预览…");
    setDesignDomainOverlay("right", true, "正在更新设计域预览…");
    const body = { session_id: state.oc4DesignDomainSessionId, design_only: false };
    const ex = state.oc4PendingExport;
    if (ex && typeof ex === "object") {
      const ls = Number(ex.linear_deflection_source);
      const ld = Number(ex.linear_deflection_design);
      if (Number.isFinite(ls) && ls >= 1) body.linear_deflection_source = ls;
      if (Number.isFinite(ld) && ld >= 1) body.linear_deflection_design = ld;
    }
    const urls = await oc4DesignDomainApi("/export-obj", body, { timeoutMs: 900000 });
    const v = ensureDesignDomainViewer();
    if (v) {
      if (urls.source_obj) await v.loadLeft(urls.source_obj);
      if (urls.design_obj) await v.loadRight(urls.design_obj);
    }
    appendDesignDomainChat("agent", "OBJ 预览已刷新（未重新执行 build）。");
  } catch (e) {
    appendDesignDomainChat("agent", String(e?.message || e));
  } finally {
    setDesignDomainOverlay("left", false);
    setDesignDomainOverlay("right", false);
    await syncDesignDomainSessionProgress().catch(() => {});
  }
});
refs.ddBtnMesh?.addEventListener("click", async () => {
  const meshBtn = refs.ddBtnMesh;
  try {
    const plan = await showOc4MeshPlanModal();
    if (!plan) {
      appendDesignDomainChat("agent", "已取消体网格（未在 Plan 方案窗中确认）。");
      return;
    }
    appendDesignDomainChat(
      "agent",
      "已开始体网格：服务端正在调用 FreeCAD + Gmsh（backend/tools/freecad_iges_to_inp → scripts/freecad_iges_to_inp_runner.py）由设计域 STEP 生成 02_mesh_body.inp；模型较大时可能需数分钟，请勿关闭页面。",
    );
    if (meshBtn) {
      meshBtn.disabled = true;
      meshBtn.setAttribute("aria-busy", "true");
    }
    setDesignDomainOverlay(
      "right",
      true,
      "正在生成体网格：FreeCAD + Gmsh 运行中，请稍候…",
    );
    const data = await oc4DesignDomainApi("/mesh", buildOc4MeshRequestBody(plan));
    let sizeLine = `体网格已生成：${data.mesh_inp_url || data.mesh_inp || ""}`;
    if (data.mesh_char_length_max_used != null) sizeLine += `（CharacteristicLengthMax≈${data.mesh_char_length_max_used}）`;
    appendDesignDomainChat("agent", sizeLine);
    if (data.mesh_inp_size_bytes != null) {
      const mb = data.mesh_inp_size_bytes / (1024 * 1024);
      appendDesignDomainChat("agent", `02_mesh_body.inp 约 ${mb.toFixed(2)} MB。`);
    }
    if (data.mesh_inp_size_warning) appendDesignDomainChat("agent", String(data.mesh_inp_size_warning));
  } catch (e) {
    appendDesignDomainChat("agent", String(e?.message || e));
  } finally {
    setDesignDomainOverlay("right", false);
    if (meshBtn) meshBtn.setAttribute("aria-busy", "false");
    await syncDesignDomainSessionProgress().catch(() => {});
  }
});
refs.ddBtnLoads?.addEventListener("click", async () => {
  const loadsBtn = refs.ddBtnLoads;
  const nl = String(refs.ddNlLoadsTa?.value || "").trim();
  try {
    if (nl) {
      appendDesignDomainChat("agent", "正在调用 Qwen 解析载荷自然语言，随后划分 design/nondesign 并写入 *STEP / *CLOAD …");
      loadsBtn?.setAttribute("aria-busy", "true");
      if (loadsBtn) loadsBtn.disabled = true;
      setDesignDomainOverlay("right", true, "划分载荷：大模型解析与 INP 写入中…");
    }
    const data = await oc4DesignDomainApi("/loads", buildOc4LoadsRequestBody());
    if (data.nl_reply) appendDesignDomainChat("agent", String(data.nl_reply));
    appendDesignDomainChat(
      "agent",
      `载荷划分完成：${data.final_inp_url || data.final_inp || ""}（统计：${JSON.stringify(data.stats || {})}）`,
    );
  } catch (e) {
    appendDesignDomainChat("agent", String(e?.message || e));
  } finally {
    setDesignDomainOverlay("right", false);
    loadsBtn?.setAttribute("aria-busy", "false");
    await syncDesignDomainSessionProgress().catch(() => {});
  }
});
refs.ddBtnFinalize?.addEventListener("click", async () => {
  try {
    const prog = state.ddProgress ?? readDdProgressFromPayload({});
    if (!prog.has_for_beso_inp) {
      const tip =
        "请先依次完成：1 构建设计域 → 3 体网格 → 4 划分载荷，待服务端生成 03_for_beso.inp 后再进入编排。";
      appendDesignDomainChat("agent", tip);
      layout.addLandingBubble("agent", tip);
      return;
    }
    const data = await oc4DesignDomainApi("/finalize", { session_id: state.oc4DesignDomainSessionId });
    state.uploadedSourceDir = String(data.scan_dir || "").trim();
    if (refs.scanDirInput) refs.scanDirInput.value = state.uploadedSourceDir;
    state.oc4DesignDomainFinalized = true;
    resetOc4DesignDomainState();
    disposeDesignDomainViewer();
    if (refs.fileSummaryInline) {
      refs.fileSummaryInline.textContent = `已上传文件：${state.currentFileName}\n扫描目录：${state.uploadedSourceDir || "(未知)"}`;
    }
    layout.addLandingBubble("agent", `OC4 设计域完成，工作目录：${state.uploadedSourceDir}`);
    await taskManager.upsertTask({
      file_name: state.currentFileName,
      scan_dir: state.uploadedSourceDir,
      status: "uploaded",
      progress: 10,
      step: 1,
    });
    await taskManager.loadTasks();
    await beginOrchestrationAfterLanding();
  } catch (e) {
    layout.addLandingBubble("agent", `无法完成收尾：${e?.message || e}`);
    appendDesignDomainChat("agent", String(e?.message || e));
  } finally {
    await syncDesignDomainSessionProgress().catch(() => {});
  }
});
refs.designDomainStepRail?.addEventListener("click", (e) => {
  if (!state.oc4DesignDomainSessionId) return;
  if (e.target?.closest?.(".ddStepAiBtn")) return;
  const stepEl = e.target?.closest?.(".ddStep");
  if (!stepEl || !stepEl.classList.contains("ddStepNavigable")) return;
  const idx = parseInt(stepEl.getAttribute("data-idx") || "0", 10);
  if (!Number.isFinite(idx) || idx < 1 || idx > 4) return;
  focusDesignDomainRailStep(idx);
});
refs.designDomainStepRail?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const stepEl = e.target?.closest?.(".ddStep");
  if (!stepEl || !stepEl.classList.contains("ddStepNavigable")) return;
  e.preventDefault();
  const idx = parseInt(stepEl.getAttribute("data-idx") || "0", 10);
  if (!Number.isFinite(idx) || idx < 1 || idx > 4) return;
  focusDesignDomainRailStep(idx);
});
refs.designDomainMain?.addEventListener("click", (e) => {
  const btn = e.target?.closest?.(".ddStepAiBtn");
  if (!btn) return;
  const topic = btn.getAttribute("data-dd-topic");
  if (!topic) return;
  openDdNlModal(topic);
});
refs.ddStepNlClose?.addEventListener("click", () => closeDdNlModal());
refs.ddStepNlDialog?.addEventListener("click", (e) => {
  if (e.target === refs.ddStepNlDialog) closeDdNlModal();
});
refs.ddStepNlDialogPanel?.addEventListener("click", (e) => e.stopPropagation());
refs.ddStepNlSend?.addEventListener("click", async () => {
  const topic = state.ddNlTopic;
  if (!topic || !state.oc4DesignDomainSessionId) return;
  const msg =
    topic === "loads"
      ? String(refs.ddNlLoadsTa?.value || "").trim()
      : String(refs.ddStepNlInput?.value || "").trim();
  if (!msg) return;
  if (topic === "loads" && refs.ddNlLoadsTa) refs.ddNlLoadsTa.value = "";
  else if (refs.ddStepNlInput) refs.ddStepNlInput.value = "";
  appendDdNlLog("user", msg);
  try {
    const data = await oc4DesignDomainApi(
      "/chat",
      { session_id: state.oc4DesignDomainSessionId, message: msg, topic },
      { timeoutMs: 120000 },
    );
    state.ddNlLastPayload = data;
    appendDdNlLog("agent", data.reply || "(无回复)");
    if (data.suggested_build && typeof data.suggested_build === "object") state.oc4LastSuggestedBuild = data.suggested_build;
    if (data.suggested_loads && typeof data.suggested_loads === "object") state.oc4LastSuggestedLoads = data.suggested_loads;
    if (data.suggested_mesh && typeof data.suggested_mesh === "object") state.oc4LastSuggestedMesh = data.suggested_mesh;
    if (data.suggested_export && typeof data.suggested_export === "object") state.oc4LastSuggestedExport = data.suggested_export;
    refreshDdNlApplyEnabled();
  } catch (err) {
    appendDdNlLog("agent", String(err?.message || err));
  }
});
refs.ddStepNlApply?.addEventListener("click", () => applyDdNlSuggestions());

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
refs.cadConvertManualBtn?.addEventListener("click", () => {
  runManualCadConvert().catch((e) => layout.addBubble("agent", `格式转换异常：${e?.message || e}`));
});

refs.cadConvertPauseBtn?.addEventListener("click", () => {
  state.cadPollPaused = !state.cadPollPaused;
  if (refs.cadConvertPauseBtn) {
    refs.cadConvertPauseBtn.textContent = state.cadPollPaused ? "继续" : "暂停";
    refs.cadConvertPauseBtn.classList.toggle("isPaused", state.cadPollPaused);
  }
  const st = refs.cadConvertStage;
  if (!st) return;
  if (state.cadPollPaused) {
    if (!st.dataset.cadStageFrozen) st.dataset.cadStageFrozen = st.textContent || "";
    st.textContent = "已暂停进度轮询（后端 FreeCAD 可能仍在运行），点击「继续」恢复显示。";
  } else if (st.dataset.cadStageFrozen) {
    st.textContent = st.dataset.cadStageFrozen;
    delete st.dataset.cadStageFrozen;
  }
});

refs.uploadPreviewRemove?.addEventListener("click", () => {
  state.currentFileId = null;
  state.currentFileName = "";
  state.uploadedSourceDir = "";
  disposeDesignDomainViewer();
  resetOc4DesignDomainState();
  state.oc4DesignDomainFinalized = false;
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
    if (state.step1NeedsInp && target > 1) {
      layout.addBubble(
        "agent",
        "需先完成 IGES→INP 格式转换并生成主 INP，才能进入该步骤。请点击「IGES → INP 格式转换」。",
      );
      focusCadConvertGuide();
      return;
    }
    if (!isFlowStepClickable(target)) return;
    layout.setStep(target);
  });
});

layout.setStep(1);
layout.showStage("landing");
updateLogDockVisibility();
layout.addLandingBubble("agent", "先聊天并上传文件，点击“运行智能体流程”后开始流式编排。");
try {
  if (refs.baseUrlInput) {
    const stored = localStorage.getItem("beso.settings.baseUrl") || "";
    refs.baseUrlInput.value =
      stored || refs.baseUrlInput.value || (window.location?.origin || "http://127.0.0.1:8000");
    migrateCrossHostBaseUrl();
  }
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
queueMicrotask(() => applyDesignDomainStepUi());

const resultsViewer = mountResultsViewer();
document.getElementById("resultsViewerBtn")?.addEventListener("click", () => {
  resultsViewer.open();
});
