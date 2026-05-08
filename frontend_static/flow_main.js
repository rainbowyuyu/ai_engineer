import { createLayoutManager } from "./flow_main.layout.js";
import { createTaskManager, formatTaskStatus } from "./flow_main.tasks.js";
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
  landingSendChatBtn: $("landingSendChatBtn"),
  newLandingTaskBtn: $("newLandingTaskBtn"),
  landingSubflowStrip: $("landingSubflowStrip"),
  landingEnterDesignDomainBtn: $("landingEnterDesignDomainBtn"),
  landingEnterOrchestrateBtn: $("landingEnterOrchestrateBtn"),
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
  backToOc4FromFlowBtn: $("backToOc4FromFlowBtn"),
  backToOc4FromOrchestrateBtn: $("backToOc4FromOrchestrateBtn"),
  flowStepper: $("flowStepper"),
  taskListEl: $("taskList"),
  taskSessionDigest: $("taskSessionDigest"),
  taskSidebarEl: document.querySelector("#landingMain .taskSidebar"),
  refreshTasksBtn: $("refreshTasksBtn"),
  toggleSidebarBtn: $("toggleSidebarBtn"),
  taskRenameDialog: $("taskRenameDialog"),
  taskRenameInput: $("taskRenameInput"),
  taskRenameSave: $("taskRenameSave"),
  taskRenameCancel: $("taskRenameCancel"),
  artifactSummary: $("artifactSummary"),
  container: $("vtk"),
  landingPendingAttachBar: $("landingPendingAttachBar"),
  landingPendingAttachName: $("landingPendingAttachName"),
  landingPendingAttachRemove: $("landingPendingAttachRemove"),
  settingsBtn: $("settingsBtn"),
  settingsShell: $("settingsShell"),
  settingsBackdrop: $("settingsBackdrop"),
  settingsPanel: $("settingsPanel"),
  settingsClose: $("settingsClose"),
  baseUrlInput: $("baseUrl"),
  qwenBaseUrl: $("qwenBaseUrl"),
  qwenModel: $("qwenModel"),
  qwenKey: $("qwenKey"),
  qwenSave: $("qwenSave"),
  qwenStatus: $("qwenStatus"),
  assistantPreferStream: $("assistantPreferStream"),
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
  designDomainToolbar: $("designDomainToolbar"),
  designDomainBackBtn: $("designDomainBackBtn"),
  designDomainCanvasLeft: $("designDomainCanvasLeft"),
  designDomainCanvasRight: $("designDomainCanvasRight"),
  designDomainLeftOverlay: $("designDomainLeftOverlay"),
  designDomainRightOverlay: $("designDomainRightOverlay"),
  designDomainLeftOverlayText: $("designDomainLeftOverlayText"),
  designDomainRightOverlayText: $("designDomainRightOverlayText"),
  ddCutCenter: $("ddCutCenter"),
  ddIncludeSource: $("ddIncludeSource"),
  ddMeshDensity: $("ddMeshDensity"),
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
  /** 与任务 JSON `oc4_activity` 同步：{ ts, role, text }[] */
  oc4ActivityLog: [],
  /** 设计域收尾后仍可用于「返回 OC4」恢复 session_id（与任务 oc4_design_domain_session_id 一致） */
  oc4DesignDomainSessionIdForResume: "",
  /** 主页多轮对话（POST /api/assistant/chat），仅 user/assistant；按任务切换时与 localStorage 同步 */
  assistantThread: [],
  landingAssistantPending: false,
  /** 当前流式请求：切换任务 / 离开主页 / 新发送 时中止，避免互相卡住主线程与 UI */
  landingChatFlight: null,
  /** 任务标题摘要 /api/assistant/chat 的 AbortController，避免与流式对话并行拖慢后端 */
  titleSummarizeAbort: null,
  /** 当前对话参与的子流程摘要（侧栏只读展示） */
  landingSessionDigest: [],
  /** 上传成功尚未随下一条用户消息发出的文件（仅用于输入区「待发送」与下一条气泡后的附件展示） */
  landingAttachmentPending: null,
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

/** 右侧设置抽屉：遮罩淡入 + 面板滑入；无 shell 时回退旧版 hidden。 */
function setSettingsDrawer(open) {
  const on = Boolean(open);
  if (!on) persistTopologySettingsImmediate();
  const shell = refs.settingsShell;
  if (!shell) {
    refs.settingsPanel?.classList.toggle("hidden", !on);
    return;
  }
  shell.setAttribute("aria-hidden", on ? "false" : "true");
  shell.classList.toggle("settingsShell--open", on);
  document.body.classList.toggle("settingsDrawerOpen", on);
}

const LS_TOPOLOGY = "beso.settings.topology.v1";
const DEFAULT_TOPO_MG = 0.25;
const DEFAULT_TOPO_SE = 1;
let _topologySaveTimer = null;

function persistTopologySettingsImmediate() {
  try {
    localStorage.setItem(
      LS_TOPOLOGY,
      JSON.stringify({
        mg: refs.massGoal?.value ?? "",
        fr: refs.filterR?.value ?? "",
        se: refs.saveEvery?.value ?? "",
      }),
    );
  } catch {
    /* ignore */
  }
}

function schedulePersistTopologySettings() {
  if (_topologySaveTimer != null) clearTimeout(_topologySaveTimer);
  _topologySaveTimer = setTimeout(() => {
    _topologySaveTimer = null;
    persistTopologySettingsImmediate();
  }, 220);
}

function hydrateTopologyInputsFromStorage() {
  let o = null;
  try {
    o = JSON.parse(localStorage.getItem(LS_TOPOLOGY) || "null");
  } catch {
    o = null;
  }
  if (refs.massGoal) {
    const v = o && o.mg != null && String(o.mg).trim() !== "" ? String(o.mg) : String(DEFAULT_TOPO_MG);
    refs.massGoal.value = v;
  }
  if (refs.saveEvery) {
    const v = o && o.se != null && String(o.se).trim() !== "" ? String(o.se) : String(DEFAULT_TOPO_SE);
    refs.saveEvery.value = v;
  }
  if (refs.filterR) refs.filterR.value = o && o.fr != null ? String(o.fr) : "";
}

/** 与 POST /api/chat 对齐：质量比与保存步长始终带默认值；滤波半径仅在有有效正数时发送。 */
function readTopologyOverridesForChat() {
  const mg = Number(refs.massGoal?.value);
  const fr = Number(refs.filterR?.value);
  const se = Number(refs.saveEvery?.value);
  const out = {
    mass_goal_ratio: Number.isFinite(mg) && mg > 0 && mg < 1 ? mg : DEFAULT_TOPO_MG,
    save_every: Number.isFinite(se) && se > 0 ? Math.floor(se) : DEFAULT_TOPO_SE,
  };
  if (Number.isFinite(fr) && fr > 0) out.filter_radius = fr;
  return out;
}

async function refreshQwenConfigStatus() {
  try {
    const cfg = await (await fetch(`${normalizedBaseUrl()}/api/config/qwen`, { cache: "no-store" })).json();
    if (refs.qwenStatus) {
      refs.qwenStatus.textContent = cfg.configured
        ? `已配置（${cfg.model || "qwen"}）`
        : "未配置：填写 API Key 或设置环境变量 QWEN_API_KEY";
    }
    if (refs.qwenBaseUrl && cfg.base_url) refs.qwenBaseUrl.value = cfg.base_url;
    if (refs.qwenModel && cfg.model) refs.qwenModel.value = cfg.model;
    if (cfg.configured) fireAndForgetQwenWarmup();
    return cfg;
  } catch {
    if (refs.qwenStatus) refs.qwenStatus.textContent = "无法连接后端检测 Qwen";
    return null;
  }
}

const layout = createLayoutManager({ refs, state });

function landingThreadStorageKey(tid) {
  return `beso.landingThread.${String(tid || "").trim()}`;
}

let _landingThreadServerTimer = null;
let _landingThreadServerTid = null;

function cancelPendingLandingThreadServerPersist(forTaskId) {
  const tid = String(forTaskId || "").trim();
  if (_landingThreadServerTimer && tid && _landingThreadServerTid === tid) {
    clearTimeout(_landingThreadServerTimer);
    _landingThreadServerTimer = null;
    _landingThreadServerTid = null;
  }
}

/** 切换任务等场景下立即把当前内存中的对话写入服务端（带 taskId 覆盖，避免已切走 currentTaskId） */
async function flushLandingAssistantThreadServer(forTaskId) {
  const tid = String(forTaskId ?? state.currentTaskId ?? "").trim();
  if (!tid || !taskManager?.upsertTask) return;
  cancelPendingLandingThreadServerPersist(tid);
  const threadSnap = (state.assistantThread || []).slice(-120);
  const digestSnap = (state.landingSessionDigest || []).slice(-40);
  await taskManager.upsertTask(
    { assistant_thread: threadSnap, landing_session_digest: digestSnap },
    { taskId: tid },
  );
}

function persistLandingAssistantThread(forTaskId) {
  const tid = String(forTaskId ?? state.currentTaskId ?? "").trim();
  if (!tid) return;
  const threadSnap = (state.assistantThread || []).slice(-120);
  const digestSnap = (state.landingSessionDigest || []).slice(-40);
  try {
    localStorage.setItem(
      landingThreadStorageKey(tid),
      JSON.stringify({
        v: 2,
        thread: threadSnap.slice(-80),
        digest: digestSnap.slice(-24),
      }),
    );
  } catch {
    /* ignore */
  }
  _landingThreadServerTid = tid;
  if (_landingThreadServerTimer) clearTimeout(_landingThreadServerTimer);
  _landingThreadServerTimer = setTimeout(() => {
    _landingThreadServerTimer = null;
    const tm = taskManager;
    if (!tm?.upsertTask) return;
    void tm.upsertTask(
      { assistant_thread: threadSnap, landing_session_digest: digestSnap },
      { taskId: tid },
    );
  }, 650);
}

function loadLandingAssistantThread(forTaskId) {
  const tid = String(forTaskId ?? "").trim();
  if (!tid) {
    state.assistantThread = [];
    state.landingSessionDigest = [];
    return;
  }
  try {
    const raw = localStorage.getItem(landingThreadStorageKey(tid));
    if (!raw) {
      state.assistantThread = [];
      state.landingSessionDigest = [];
      return;
    }
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && Number(parsed.v) === 2) {
      state.assistantThread = Array.isArray(parsed.thread) ? parsed.thread : [];
      state.landingSessionDigest = Array.isArray(parsed.digest) ? parsed.digest : [];
      return;
    }
    const arr = Array.isArray(parsed) ? parsed : [];
    state.assistantThread = arr;
    state.landingSessionDigest = [];
  } catch {
    state.assistantThread = [];
    state.landingSessionDigest = [];
  }
}

/** 中止当前主页流式对话（切换任务、离开主页、再次发送），避免请求与 UI 串扰、长时间占用主线程回调 */
function abortLandingChat(_reason) {
  try {
    state.titleSummarizeAbort?.abort();
  } catch {
    /* ignore */
  }
  state.titleSummarizeAbort = null;
  const f = state.landingChatFlight;
  state.landingChatFlight = null;
  state.landingAssistantPending = false;
  if (refs.landingSendChatBtn) refs.landingSendChatBtn.disabled = false;
  if (!f) return;
  try {
    f.ac?.abort();
  } catch {
    /* ignore */
  }
  try {
    if (f.streamCtrl?.wrap?.classList?.contains("landingTurn--streaming")) {
      f.streamCtrl.finalize("（已中断：切换对话或离开主页）");
    } else if (!f.streamCtrl && f.thinkingEl?.isConnected) {
      layout.removeLandingThinking(f.thinkingEl);
    }
  } catch {
    /* ignore */
  }
}

function appendLandingSessionDigest(entry) {
  if (!entry || !entry.label) return;
  if (!Array.isArray(state.landingSessionDigest)) state.landingSessionDigest = [];
  state.landingSessionDigest.push({
    kind: String(entry.kind || ""),
    label: String(entry.label || "").slice(0, 80),
    ts: Number(entry.ts) || Date.now(),
  });
  if (state.landingSessionDigest.length > 24) state.landingSessionDigest = state.landingSessionDigest.slice(-24);
  renderTaskSessionDigest();
}

function renderTaskSessionDigest() {
  const el = refs.taskSessionDigest;
  if (!el) return;
  const rows = state.landingSessionDigest || [];
  if (!rows.length) {
    el.innerHTML = `<div class="taskDigestEmpty" title="尚未从对话进入设计域或构型优化编排">暂无子流程摘要</div>`;
    return;
  }
  el.innerHTML = rows
    .map(
      (r) =>
        `<div class="taskDigestItem" title="${escapeHtml(r.label)}"><span class="taskDigestDot" data-kind="${escapeHtml(r.kind)}"></span><span class="taskDigestItemText">${escapeHtml(r.label)}</span></div>`,
    )
    .join("");
}

/** 用户是否在描述「编排 / 设计域」等可自动跳转的子流程 */
function detectLandingWorkflowIntent(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  const orch =
    /运行\s*智能体|智能体\s*流程|智能体\s*编排|构型\s*优化|运行\s*构型|构型\s*编排|开始\s*编排|编排\s*流程|一键\s*流程|执行任务|跑.*流程|进入\s*编排|打开\s*编排|拓扑\s*优化|结构\s*优化|形状\s*优化|形貌\s*优化|布局\s*优化|优化\s*设计|柔度|应变\s*能|灵敏度|材料\s*插值|密度\s*法|\bSIMP\b|\bBESO\b|beso\s|calculi?x|有限元\s*优化|\bAI\s*Engineering\b/i.test(raw);
  const dd = /设计域|进入\s*设计域|OC4|oc4|iges.*(流程|步骤)|几何.*设计域/i.test(raw);
  if (dd && !orch) return "design_domain";
  if (orch) return "orchestrate";
  return null;
}

/**
 * 消费 SSE 流；对 reader.read 与中止语义加固，避免 Abort / 切任务被误报为「对话失败」。
 * @returns {{ full: string, status: "complete"|"cancelled"|"error", error?: Error }}
 */
async function consumeAssistantChatStream(response, onDelta, opts = {}) {
  const shouldContinue = typeof opts.shouldContinue === "function" ? opts.shouldContinue : null;
  const signal = opts.signal;
  const isAbortLike = (e) =>
    Boolean(
      signal?.aborted ||
        e?.name === "AbortError" ||
        (typeof DOMException !== "undefined" && e instanceof DOMException && e.name === "AbortError") ||
        /aborted|abort|bodystreambuffer|user.?abort/i.test(String(e?.message || e || "")),
    );
  if (!response.ok) {
    const t = await response.text().catch(() => "");
    let msg = `HTTP ${response.status}`;
    try {
      const j = JSON.parse(t);
      const d = j.detail;
      msg =
        typeof d === "string"
          ? d
          : Array.isArray(d)
            ? d.map((x) => (typeof x === "string" ? x : x?.msg || JSON.stringify(x))).join("；")
            : t.slice(0, 400) || msg;
    } catch {
      if (t) msg = t.slice(0, 400);
    }
    return { full: "", status: "error", error: new Error(msg) };
  }
  const reader = response.body?.getReader();
  if (!reader) return { full: "", status: "error", error: new Error("无法读取模型流") };
  const dec = new TextDecoder();
  let carry = "";
  let full = "";
  /** 合并 token，减少主线程 layout（参考对话型智能体「批量刷新」思路） */
  let pendingDelta = "";
  let flushTimer = null;
  const DELTA_BATCH_MS = 20;
  const DELTA_MAX_CHARS = 1200;
  const fatal = { err: /** @type {Error|null} */ (null) };
  const flushDeltas = () => {
    flushTimer = null;
    if (!pendingDelta) return;
    if (shouldContinue && !shouldContinue()) {
      pendingDelta = "";
      return;
    }
    const chunk = pendingDelta;
    pendingDelta = "";
    onDelta?.(chunk);
  };
  const pushDelta = (piece) => {
    if (!piece) return;
    if (shouldContinue && !shouldContinue()) return;
    full += piece;
    pendingDelta += piece;
    if (pendingDelta.length >= DELTA_MAX_CHARS) {
      if (flushTimer != null) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
      flushDeltas();
      return;
    }
    if (flushTimer == null) {
      flushTimer = setTimeout(flushDeltas, DELTA_BATCH_MS);
    }
  };
  const processLine = (line) => {
    const s = String(line || "").trim();
    if (!s || s.startsWith(":") || !s.startsWith("data:")) return;
    const payload = s.slice(5).trim();
    if (payload === "[DONE]") return;
    try {
      const j = JSON.parse(payload);
      if (j.error) {
        fatal.err = new Error(String(j.error));
        return;
      }
      const piece = j.choices?.[0]?.delta?.content ?? j.choices?.[0]?.message?.content ?? "";
      pushDelta(piece);
    } catch (e) {
      if (!(e instanceof SyntaxError)) fatal.err = e instanceof Error ? e : new Error(String(e));
    }
  };
  let streamCancelled = false;
  while (true) {
    if (shouldContinue && !shouldContinue()) {
      streamCancelled = true;
      try {
        await reader.cancel();
      } catch {
        /* ignore */
      }
      break;
    }
    let readDone = false;
    let value;
    try {
      const chunk = await reader.read();
      readDone = chunk.done;
      value = chunk.value;
    } catch (readExc) {
      if (flushTimer != null) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
      if (pendingDelta && (!shouldContinue || shouldContinue())) onDelta?.(pendingDelta);
      pendingDelta = "";
      if (isAbortLike(readExc)) return { full, status: "cancelled" };
      if (shouldContinue && !shouldContinue()) return { full, status: "cancelled" };
      return {
        full,
        status: "error",
        error: readExc instanceof Error ? readExc : new Error(String(readExc)),
      };
    }
    if (fatal.err) {
      if (flushTimer != null) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
      if (pendingDelta && (!shouldContinue || shouldContinue())) onDelta?.(pendingDelta);
      pendingDelta = "";
      return { full, status: "error", error: fatal.err };
    }
    if (readDone) break;
    carry += dec.decode(value, { stream: true });
    for (;;) {
      const nl = carry.indexOf("\n");
      if (nl < 0) break;
      const line = carry.slice(0, nl).trim();
      carry = carry.slice(nl + 1);
      processLine(line);
      if (fatal.err) break;
    }
    if (fatal.err) break;
  }
  if (!streamCancelled) {
    carry += dec.decode();
    for (const line of carry.split("\n")) {
      processLine(line);
      if (fatal.err) break;
    }
  }
  if (flushTimer != null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (pendingDelta) {
    if (!shouldContinue || shouldContinue()) onDelta?.(pendingDelta);
  }
  pendingDelta = "";
  if (fatal.err) return { full, status: "error", error: fatal.err };
  return { full, status: streamCancelled ? "cancelled" : "complete" };
}

const LS_ASSISTANT_PREFER_STREAM = "beso.settings.assistantPreferStream";

function readAssistantPreferStream() {
  try {
    return localStorage.getItem(LS_ASSISTANT_PREFER_STREAM) === "1";
  } catch {
    return false;
  }
}

function syncAssistantPreferStreamUi() {
  try {
    if (refs.assistantPreferStream) refs.assistantPreferStream.checked = readAssistantPreferStream();
  } catch {
    /* ignore */
  }
}

/** 非流式整包对话（对齐 Wisdom：单次 JSON，抗代理断流） */
async function fetchAssistantChatOnce(messages, signal) {
  try {
    const r = await fetch(`${normalizedBaseUrl()}/api/assistant/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, temperature: 0.6 }),
      signal,
    });
    const raw = await r.text().catch(() => "");
    if (!r.ok) {
      let msg = `请求失败（${r.status}）`;
      try {
        const j = JSON.parse(raw);
        const d = j.detail;
        msg =
          typeof d === "string"
            ? d
            : Array.isArray(d)
              ? d.map((x) => (typeof x === "string" ? x : x?.msg || JSON.stringify(x))).join("；")
              : msg;
      } catch {
        if (raw) msg = raw.slice(0, 500);
      }
      return { ok: false, reply: "", errorText: msg, aborted: false };
    }
    try {
      const j = JSON.parse(raw);
      const reply = String(j.reply ?? "").trim();
      return { ok: true, reply: reply || "（无回复）", errorText: "", aborted: false };
    } catch {
      return { ok: false, reply: "", errorText: "响应不是合法 JSON", aborted: false };
    }
  } catch (e) {
    if (signal?.aborted) return { ok: false, reply: "", errorText: "", aborted: true };
    return { ok: false, reply: "", errorText: `网络错误：${e?.message || e}`, aborted: false };
  }
}

/** 拿到整包回复后在本地渐进输出（类比 Wisdom streamTextInto） */
async function replayAssistantProgressive(streamCtrl, fullText, signal, shouldContinue) {
  if (!streamCtrl?.appendDelta) return;
  const text = String(fullText || "");
  const units = [...text];
  const reduceMotion =
    typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const chunkSize = reduceMotion ? Math.max(32, Math.ceil(units.length / 6)) : 4;
  const tickMs = reduceMotion ? 0 : 16;
  let i = 0;
  while (i < units.length) {
    if (signal?.aborted || (shouldContinue && !shouldContinue())) return;
    const end = Math.min(i + chunkSize, units.length);
    streamCtrl.appendDelta(units.slice(i, end).join(""));
    i = end;
    if (tickMs > 0) await new Promise((res) => setTimeout(res, tickMs));
  }
}

function syncLandingWorkflowCardsFromTasks(items) {
  const tid = String(state.currentTaskId || "").trim();
  if (!tid || !refs.chatLanding) return;
  const t = (items || []).find((x) => String(x.task_id) === tid);
  if (!t) return;
  const st = formatTaskStatus(t.status);
  const stepNum = Number(t.step);
  const stepLabel = Number.isFinite(stepNum) && stepNum >= 1 && stepNum <= 4 ? `步骤 ${stepNum}/4` : "";
  const pct = Math.max(0, Math.min(100, Number(t.progress || 0)));
  const uiStage = String(t.ui_stage || "").toLowerCase();
  const hasDdSid = Boolean(String(t.oc4_design_domain_session_id || "").trim());
  for (const btn of refs.chatLanding.querySelectorAll(".landingWorkflowCard[data-task-id]")) {
    if (btn.getAttribute("data-task-id") !== tid) continue;
    const kind = String(btn.getAttribute("data-workflow-jump") || "");
    const pill = btn.querySelector(".landingWorkflowCardStatus");
    const stepEl = btn.querySelector(".landingWorkflowCardStep");
    const fill = btn.querySelector(".landingWorkflowBarFill");
    if (pill) {
      if (kind === "design_domain") {
        const inDd = uiStage === "design_domain" || hasDdSid;
        pill.textContent = inDd ? "进行中" : "待开始";
      } else {
        pill.textContent = st.label;
      }
    }
    if (stepEl && stepLabel) stepEl.textContent = stepLabel;
    if (fill) fill.style.width = `${pct}%`;
  }
}

function pushOrchestrateWorkflowCardToLandingThread() {
  const taskId = String(state.currentTaskId || "").trim();
  const card = {
    role: "card",
    kind: "orchestrate",
    title: "构型优化编排",
    status: "编排中",
    step: 1,
    progress: 12,
    taskId,
  };
  state.assistantThread.push(card);
  layout.addLandingWorkflowCard({ ...card });
  appendLandingSessionDigest({ kind: "orchestrate", label: "构型优化编排" });
}

function landingThreadHasDesignDomainCard() {
  return (state.assistantThread || []).some((m) => m.role === "card" && m.kind === "design_domain");
}

function pushDesignDomainWorkflowCardToLandingThread(patch = {}) {
  const taskId = String(state.currentTaskId || "").trim();
  const card = {
    role: "card",
    kind: "design_domain",
    title: "设计域（OC4）",
    status: patch.status || "进行中",
    step: Number.isFinite(Number(patch.step)) ? Number(patch.step) : 1,
    progress: Number.isFinite(Number(patch.progress)) ? Number(patch.progress) : 15,
    taskId,
  };
  state.assistantThread.push(card);
  layout.addLandingWorkflowCard({ ...card });
  appendLandingSessionDigest({ kind: "design_domain", label: "设计域（OC4）" });
}

/** 从主页进入设计域：写入对话卡片与侧栏摘要，再打开设计域舞台 */
async function openDesignDomainFromLanding(opts = {}) {
  const { autoPipeline = false, softResume = true, forceNewSession = false } = opts;
  if (!isOc4IgesFilename(state.currentFileName)) {
    layout.addLandingBubble("agent", "设计域仅支持已上传的 IGES 文件。");
    return;
  }
  await ensureLandingTaskForWork();
  await taskManager.loadTasks().catch(() => {});
  await ensureOc4DesignDomainSessionForResume();
  dismissLandingHero();
  if (!landingThreadHasDesignDomainCard()) {
    pushDesignDomainWorkflowCardToLandingThread({ status: "进行中", step: 1, progress: 14 });
    persistLandingAssistantThread();
  }
  await taskManager.upsertTask({ ui_stage: "design_domain" }).catch(() => {});
  await enterOc4DesignDomainStage({ autoPipeline, softResume, forceNewSession }).catch((e) => {
    layout.addLandingBubble("agent", `设计域：${e?.message || e}`);
  });
  await taskManager.loadTasks().catch(() => {});
}

function renderLandingChatFromThread() {
  if (!refs.chatLanding) return;
  refs.chatLanding.innerHTML = "";
  let userTurnIdx = 0;
  for (const m of state.assistantThread) {
    if (m.role === "user") {
      const att = m.attachment && String(m.attachment.file_name || "").trim() ? m.attachment : null;
      layout.addLandingBubble("user", m.content, {
        debut: userTurnIdx === 0,
        attachment: att || undefined,
      });
      userTurnIdx += 1;
    }
    else if (m.role === "assistant") {
      const fmt =
        m.format === "md" ||
        (!m.format &&
          /(\*\*|#{1,4}\s|\n[-*]\s|\n\d+\.\s|\x60{3}|^[-=*_]{3,}\s*$|\n\|[^\n]+\|[^\n]*\n\|)/m.test(String(m.content || "")))
          ? "md"
          : "plain";
      layout.addLandingBubble("agent", m.content, { format: fmt });
    } else if (m.role === "card") {
      layout.addLandingWorkflowCard({
        kind: m.kind,
        title: m.title,
        status: m.status,
        step: m.step,
        progress: m.progress,
        taskId: m.taskId,
      });
    }
  }
  renderTaskSessionDigest();
}

function landingThreadHasVisibleConversation() {
  const arr = state.assistantThread || [];
  return arr.some((m) => m.role === "user" || m.role === "assistant" || m.role === "card");
}

function landingChatSurfaceHasTurns() {
  return Boolean(refs.chatLanding?.querySelector(".landingTurn"));
}

/** 无对话气泡、无附件、输入框为空时展示首屏 Hero；否则隐藏并进入对话区 */
function syncLandingHeroVisibility() {
  if (!refs.landingMain) return;
  const draft = String(refs.msgLanding?.value || "").trim();
  const hasFile = Boolean(state.currentFileId || String(state.currentFileName || "").trim());
  const hasChat = landingThreadHasVisibleConversation() || landingChatSurfaceHasTurns();
  const idle = !hasChat && !hasFile && !draft;
  if (idle) refs.landingMain.classList.remove("landingHeroHidden");
  else refs.landingMain.classList.add("landingHeroHidden");
  updateLandingSubflowStrip();
}

function dismissLandingHero() {
  refs.landingMain?.classList.add("landingHeroHidden");
  updateLandingSubflowStrip();
}

function syncLandingPendingAttachBar() {
  const bar = refs.landingPendingAttachBar;
  const n = refs.landingPendingAttachName;
  const p = state.landingAttachmentPending;
  if (!bar) return;
  if (p && String(p.file_id || "").trim() && String(p.file_name || "").trim()) {
    bar.classList.remove("hidden");
    if (n) n.textContent = p.file_name;
  } else {
    bar.classList.add("hidden");
    if (n) n.textContent = "";
  }
}

/** 删除已绑定文件并清空任务侧记录（主页「待发送」移除与附件解绑共用） */
async function clearLandingUploadedFileFromTask() {
  const fid = state.currentFileId;
  if (fid) {
    try {
      await fetch(`${normalizedBaseUrl()}/api/files/${encodeURIComponent(fid)}`, { method: "DELETE" });
    } catch {
      /* 仍清除前端与任务绑定 */
    }
  }
  state.currentFileId = null;
  state.currentFileName = "";
  state.landingAttachmentPending = null;
  state.uploadedSourceDir = "";
  state.oc4DesignDomainSessionIdForResume = "";
  state.oc4DesignDomainSessionId = "";
  disposeDesignDomainViewer();
  resetOc4DesignDomainState();
  state.oc4DesignDomainFinalized = false;
  if (refs.scanDirInput) refs.scanDirInput.value = "";
  if (refs.fileSummaryInline) refs.fileSummaryInline.textContent = "(尚未选择文件)";
  syncLandingPendingAttachBar();
  await taskManager?.upsertTask?.({ file_id: "", file_name: "", scan_dir: "", oc4_design_domain_session_id: "" }).catch(() => {});
  await taskManager?.loadTasks?.().catch(() => {});
  persistLandingAssistantThread();
  syncLandingHeroVisibility();
  updateLandingSubflowStrip();
}

function updateLandingSubflowStrip() {
  const el = refs.landingSubflowStrip;
  if (!el) return;
  const show = Boolean(refs.landingMain?.classList.contains("landingHeroHidden"));
  el.classList.toggle("hidden", !show);
  const dd = refs.landingEnterDesignDomainBtn;
  const oc = refs.landingEnterOrchestrateBtn;
  const iges = isOc4IgesFilename(state.currentFileName);
  const sidAny = String(state.oc4DesignDomainSessionId || state.oc4DesignDomainSessionIdForResume || "").trim();
  /** 有 IGES 且（已绑定 file_id 或已有设计域会话）即可进入，避免任务 JSON 缺 file_id 时按钮永久灰显 */
  const canDesignDomain = Boolean(iges && (state.currentFileId || sidAny));
  if (dd) {
    dd.disabled = !canDesignDomain;
    if (!iges) dd.title = "设计域仅支持 IGES";
    else if (!state.currentFileId && !sidAny) dd.title = "请先上传 IGES，或从含设计域会话的任务进入";
    else dd.title = "进入设计域";
  }
  if (oc) {
    oc.disabled = !state.currentFileId;
    oc.title = state.currentFileId ? "进入构型优化编排" : "请先上传文件";
  }
}

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

function updateOc4ReturnNavVisibility() {
  const hasTask = Boolean(state.currentTaskId);
  const sidMem = String(state.oc4DesignDomainSessionIdForResume || "").trim();
  const sidLive = String(state.oc4DesignDomainSessionId || "").trim();
  const show = hasTask && Boolean(sidMem || sidLive);
  refs.backToOc4FromFlowBtn?.classList.toggle("hidden", !show);
  refs.backToOc4FromOrchestrateBtn?.classList.toggle("hidden", !show);
}

let _taskTitleSummarizeTimer = null;
/** 输入时合并 syncLandingHeroVisibility，减轻主线程压力、避免连续布局抖动 */
let _landingInputHeroRaf = null;

function scheduleTaskTitleSummarize() {
  if (_taskTitleSummarizeTimer) clearTimeout(_taskTitleSummarizeTimer);
  _taskTitleSummarizeTimer = setTimeout(() => {
    _taskTitleSummarizeTimer = null;
    void summarizeCurrentTaskTitleFromThread();
  }, 2600);
}

/** 根据最近用户输入调用助手生成短标题（失败则静默） */
async function summarizeCurrentTaskTitleFromThread() {
  const tid = String(state.currentTaskId || "").trim();
  if (!tid) return;
  try {
    state.titleSummarizeAbort?.abort();
  } catch {
    /* ignore */
  }
  const ac = new AbortController();
  state.titleSummarizeAbort = ac;
  const draft = String(refs.msgLanding?.value || "").trim();
  const users = state.assistantThread.filter((m) => m.role === "user").slice(-5);
  let blob = users
    .map((u) => String(u.content || "").trim())
    .filter(Boolean)
    .join("\n---\n")
    .slice(0, 960);
  if (draft && (!blob || blob.length < 48)) {
    blob = blob ? `${blob}\n---\n${draft}` : draft;
  }
  if (blob.length < 8) {
    if (state.titleSummarizeAbort === ac) state.titleSummarizeAbort = null;
    return;
  }
  try {
    const r = await fetch(`${normalizedBaseUrl()}/api/assistant/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [
          {
            role: "system",
            content:
              "你是「AI Engineering」对话的任务命名模块；角色为工程任务摘要助手。只输出一行简体中文标题，不超过18个字，概括用户在本对话中的核心诉求。不要引号、不要书名号包住全文、不要「任务：」等前缀、不要解释。",
          },
          { role: "user", content: `根据下列【用户输入】生成任务栏标题：\n${blob}` },
        ],
        temperature: 0.15,
      }),
      signal: ac.signal,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return;
    let t = String(data.reply || "")
      .trim()
      .split(/\n/)[0]
      .replace(/^[\"'「『]|["'」』]$/g, "")
      .replace(/^任务[是为：:]\s*/i, "")
      .replace(/\s+/g, " ")
      .slice(0, 72);
    if (t.length < 2) return;
    await taskManager.upsertTask({ title: t });
    await taskManager.loadTasks().catch(() => {});
  } catch {
    /* ignore */
  } finally {
    if (state.titleSummarizeAbort === ac) state.titleSummarizeAbort = null;
  }
}

/** 侧栏角标：进入设计域或构型优化编排（先同步该任务上下文） */
async function openTaskSubprocessFromBadge(task, kind) {
  const tid = String(task?.task_id || "").trim();
  if (!tid) return;
  const cur = String(state.currentTaskId || "").trim();
  if (cur && tid !== cur) {
    abortLandingChat("task-switch-badge");
    persistLandingAssistantThread(cur);
    await flushLandingAssistantThreadServer(cur);
    state.landingAttachmentPending = null;
    syncLandingPendingAttachBar();
  }
  const nextKey = tid;
  if (state.activeTaskKey !== nextKey) {
    resetTaskRuntimeView();
    state.activeTaskKey = nextKey;
  }
  state.currentTaskId = tid;
  state.jobId = task.job_id || null;
  state.uploadedSourceDir = String(task.scan_dir || "");
  state.currentFileName = String(task.file_name || "");
  state.currentFileId = task.file_id || null;
  const sid = String(task.oc4_design_domain_session_id || "").trim();
  state.oc4DesignDomainSessionIdForResume = sid;
  state.oc4DesignDomainSessionId = sid;
  state.currentTaskStatus = String(task.status || "");
  state.maxReachedStep = deriveMaxReachedStepFromTask(task);
  ingestTaskOc4Activity(task);
  if (refs.scanDirInput) refs.scanDirInput.value = state.uploadedSourceDir;
  if (refs.fileSummaryInline) {
    refs.fileSummaryInline.textContent = `已上传文件：${state.currentFileName || "(未知)"}\n扫描目录：${state.uploadedSourceDir || "(未知)"}`;
  }
  if (refs.msgLanding && task.title) refs.msgLanding.value = task.title;
  await hydrateLandingFromTask(task);
  const k = String(kind || "");
  if (k === "design_domain") {
    if (!isOc4IgesFilename(state.currentFileName)) {
      layout.addLandingBubble("agent", "该任务文件不是 IGES，无法进入设计域。");
      return;
    }
    if (!state.currentFileId) {
      layout.addLandingBubble("agent", "缺少有效上传文件，请在该对话中重新上传 IGES。");
      return;
    }
    await taskManager.upsertTask({ ui_stage: "design_domain" }).catch(() => {});
    await enterOc4DesignDomainStage({ softResume: true, forceNewSession: false }).catch((e) =>
      layout.addLandingBubble("agent", String(e?.message || e)),
    );
    await taskManager.loadTasks().catch(() => {});
    return;
  }
  if (k === "orchestrate") {
    if (!state.currentFileId) {
      layout.addLandingBubble("agent", "该对话没有已保存的上传文件，请先上传后再进入构型优化编排。");
      return;
    }
    if (isOc4IgesFilename(state.currentFileName) && !state.oc4DesignDomainFinalized) {
      layout.addLandingBubble("agent", "IGES 需先完成设计域；正在打开设计域。");
      await enterOc4DesignDomainStage({ softResume: true, autoPipeline: false }).catch((e) =>
        layout.addLandingBubble("agent", String(e?.message || e)),
      );
      return;
    }
    layout.showStage("orchestrate");
    const st = String(state.currentTaskStatus || "").toLowerCase();
    if (st === "orchestrating") {
      if (refs.executePlannedTask) refs.executePlannedTask.disabled = true;
      const preambleMd = buildOc4OrchestratePreambleMd();
      layout.streamOrchestration(async () => {
        if (refs.executePlannedTask) refs.executePlannedTask.disabled = false;
        layout.addLandingBubble("agent", "构型优化编排完成，点击「执行任务」进入分步执行。");
        await taskManager.upsertTask({ progress: 20, step: 1, status: "ready_to_execute" });
        await taskManager.loadTasks();
      }, { preambleMd });
    } else if (st === "ready_to_execute" || st === "completed" || st === "done") {
      if (refs.executePlannedTask) refs.executePlannedTask.disabled = false;
    } else if (refs.executePlannedTask) {
      refs.executePlannedTask.disabled = false;
    }
    await taskManager.upsertTask({ ui_stage: "orchestrate" }).catch(() => {});
    await taskManager.loadTasks().catch(() => {});
  }
}

let taskManager = null;
taskManager = createTaskManager({
  refs,
  state,
  normalizedBaseUrl,
  onTaskRemoved: (removedId) => {
    try {
      localStorage.removeItem(landingThreadStorageKey(removedId));
    } catch {
      /* ignore */
    }
  },
  onTasksListUpdated: (items) => {
    updateOc4ReturnNavVisibility();
    syncLandingWorkflowCardsFromTasks(items || []);
  },
  onBeforeSelectTask: async (nextTaskId) => {
    const cur = String(state.currentTaskId || "").trim();
    const next = String(nextTaskId || "").trim();
    /** 再次点击当前任务也会走此回调：不得中止正在进行的流式对话 */
    if (cur && next && cur !== next) {
      abortLandingChat("task-switch");
      persistLandingAssistantThread(cur);
      await flushLandingAssistantThreadServer(cur);
      state.landingAttachmentPending = null;
      syncLandingPendingAttachBar();
    }
  },
  onTaskBadgeClick: async (task, kind) => {
    await openTaskSubprocessFromBadge(task, kind);
  },
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
    ingestTaskOc4Activity(task);
    const sid = String(task?.oc4_design_domain_session_id || "").trim();
    state.oc4DesignDomainSessionIdForResume = sid;
    /** 无字段时清空，避免沿用上一条任务的 session 导致错绑或反复建会话 */
    state.oc4DesignDomainSessionId = sid;
    state.jobId = task?.job_id ?? null;
    state.uploadedSourceDir = String(task?.scan_dir || "");
    state.currentFileName = String(task?.file_name || "");
    state.currentFileId = String(task?.file_id || "").trim() || null;
    if (refs.scanDirInput) refs.scanDirInput.value = state.uploadedSourceDir;
    if (refs.fileSummaryInline) {
      refs.fileSummaryInline.textContent = `已上传文件：${state.currentFileName || "(未知)"}\n扫描目录：${state.uploadedSourceDir || "(未知)"}`;
    }
    if (refs.msgLanding && task.title) refs.msgLanding.value = task.title;

    /* 侧栏只切换「对话上下文」，不根据 ui_stage 跳入编排 / 设计域 / 分步流；子流程由对话内卡片或顶栏入口进入 */
    layout.showStage("landing");

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
    await hydrateLandingFromTask(task);
  },
});

async function ensureLandingTaskForWork() {
  if (state.currentTaskId) return;
  const tid = crypto?.randomUUID?.() || `${Date.now()}`;
  state.currentTaskId = tid;
  const title =
    String(refs.msgLanding?.value || "").trim().slice(0, 80) ||
    String(state.currentFileName || "").slice(0, 80) ||
    "新对话";
  await taskManager.upsertTask({ title, status: "pending", progress: 0, step: 1 });
  await taskManager.loadTasks().catch(() => {});
}

async function hydrateLandingFromTask(task) {
  const tid = String(task?.task_id || "").trim();
  /** 同任务流式进行中时重hydrate 会清空 chat DOM，导致「思考中」节点脱离文档，流式 UI 失效 */
  const inflightSameTask =
    Boolean(state.landingChatFlight) && String(state.landingChatFlight.taskId || "") === tid;
  if (!inflightSameTask) {
    let loadedFromServer = false;
    if (tid) {
      try {
        const r = await fetch(`${normalizedBaseUrl()}/api/tasks/${encodeURIComponent(tid)}`, { cache: "no-store" });
        if (r.ok) {
          const full = await r.json().catch(() => ({}));
          const th = full?.assistant_thread;
          if (Array.isArray(th) && th.length) {
            state.assistantThread = th.slice(-120);
            state.landingSessionDigest = Array.isArray(full?.landing_session_digest)
              ? full.landing_session_digest.slice(-40)
              : [];
            loadedFromServer = true;
            try {
              localStorage.setItem(
                landingThreadStorageKey(tid),
                JSON.stringify({
                  v: 2,
                  thread: state.assistantThread.slice(-80),
                  digest: (state.landingSessionDigest || []).slice(-24),
                }),
              );
            } catch {
              /* ignore */
            }
          }
        }
      } catch {
        /* ignore */
      }
    }
    if (!loadedFromServer && tid) {
      loadLandingAssistantThread(tid);
      if ((state.assistantThread || []).length && taskManager?.upsertTask) {
        void taskManager.upsertTask(
          {
            assistant_thread: state.assistantThread.slice(-120),
            landing_session_digest: (state.landingSessionDigest || []).slice(-40),
          },
          { taskId: tid },
        );
      }
    }
    if (!tid && !loadedFromServer) {
      state.assistantThread = [];
      state.landingSessionDigest = [];
    }
    renderLandingChatFromThread();
  }
  const fid = String(task?.file_id || "").trim();
  state.currentFileId = fid || null;
  state.currentFileName = String(task?.file_name || "").trim();
  state.landingAttachmentPending = null;
  syncLandingPendingAttachBar();
  state.uploadedSourceDir = String(task?.scan_dir || state.uploadedSourceDir || "");
  state.jobId = task?.job_id || state.jobId || null;
  syncLandingHeroVisibility();
  updateLandingSubflowStrip();
}

/** 仅含后端 /api/assistant/chat* 允许的 role，排除对话里持久化的 card 等结构 */
let _qwenWarmupLastAt = 0;
function fireAndForgetQwenWarmup() {
  try {
    const now = Date.now();
    if (now - _qwenWarmupLastAt < 40000) return;
    _qwenWarmupLastAt = now;
    const u = `${normalizedBaseUrl()}/api/assistant/qwen-warmup`;
    void fetch(u, { method: "GET", cache: "no-store" }).catch(() => {});
  } catch {
    /* ignore */
  }
}

/** 连续两帧再 resolve，确保「思考中」卡片已绘制再发请求 */
function nextPaintFrame2() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
}

function sliceAssistantThreadForApi(maxMsgs = 48) {
  const allowed = new Set(["system", "user", "assistant"]);
  const out = [];
  for (const m of (state.assistantThread || []).slice(-maxMsgs)) {
    const role = String(m?.role || "").trim();
    if (!allowed.has(role)) continue;
    const content = String(m?.content ?? "").trim();
    if (!content) continue;
    out.push({ role, content });
  }
  return out;
}

async function sendLandingAssistantChat() {
  const text = String(refs.msgLanding?.value || "").trim();
  if (!text) return;
  abortLandingChat("send");
  await ensureLandingTaskForWork();
  const myTaskId = String(state.currentTaskId || "").trim();
  dismissLandingHero();
  state.landingAssistantPending = true;
  if (refs.landingSendChatBtn) refs.landingSendChatBtn.disabled = true;
  const debutUser = !state.assistantThread.some((m) => String(m?.role || "") === "user");
  const pendingAtt = state.landingAttachmentPending;
  const userBubbleOpts = { debut: debutUser };
  if (pendingAtt?.file_id && String(pendingAtt.file_name || "").trim()) {
    userBubbleOpts.attachment = {
      file_id: pendingAtt.file_id,
      file_name: String(pendingAtt.file_name || "").trim(),
    };
  }
  layout.addLandingBubble("user", text, userBubbleOpts);
  const userMsg = { role: "user", content: text };
  if (pendingAtt?.file_id && String(pendingAtt.file_name || "").trim()) {
    userMsg.attachment = {
      file_id: String(pendingAtt.file_id).trim(),
      file_name: String(pendingAtt.file_name || "").trim(),
    };
  }
  state.assistantThread.push(userMsg);
  state.landingAttachmentPending = null;
  syncLandingPendingAttachBar();
  refs.msgLanding.value = "";
  persistLandingAssistantThread();
  const intent = detectLandingWorkflowIntent(text);

  try {
    if (intent === "design_domain" && !isOc4IgesFilename(state.currentFileName)) {
      const msg = "设计域仅支持 IGES：请先上传 IGES 文件。";
      layout.addLandingBubble("agent", msg);
      state.assistantThread.push({ role: "assistant", content: msg, format: "plain" });
      return;
    }

    const messages = sliceAssistantThreadForApi(48);
    const ac = new AbortController();
    const flight = { taskId: myTaskId, thinkingEl: null, streamCtrl: null, ac };
    state.landingChatFlight = flight;
    const thinkingEl = layout.addLandingThinking();
    flight.thinkingEl = thinkingEl;
    let streamCtrl = null;
    const stillMine = () => state.landingChatFlight === flight;
    const shouldContinue = () =>
      stillMine() && String(state.currentTaskId || "").trim() === myTaskId;

    const runOrchestrateFromIntent = async () => {
      if (!state.currentFileId) {
        const msg = "请先上传文件，再运行构型优化编排。";
        layout.addLandingBubble("agent", msg);
        state.assistantThread.push({ role: "assistant", content: msg, format: "plain" });
        return;
      }
      if (isOc4IgesFilename(state.currentFileName) && !state.oc4DesignDomainFinalized) {
        layout.addLandingBubble("agent", "IGES 需先完成设计域流程；已为您打开设计域。");
        state.assistantThread.push({
          role: "assistant",
          content: "IGES 需先完成设计域流程；已为您打开设计域。",
          format: "plain",
        });
        persistLandingAssistantThread();
        await layout.playLandingSubflowBridge({ kind: "design_domain", minMs: 1520 });
        if (!shouldContinue()) return;
        await openDesignDomainFromLanding({ autoPipeline: true, softResume: true });
        return;
      }
      await layout.playLandingSubflowBridge({ kind: "orchestrate", minMs: 1520 });
      if (!shouldContinue()) return;
      await beginOrchestrationAfterLanding({ skipUserBubble: true, userMessage: text });
    };

    const runDesignDomainBlock = async () => {
      if (intent !== "design_domain") return;
      try {
        if (!shouldContinue()) return;
        await layout.playLandingSubflowBridge({ kind: "design_domain", minMs: 1520 });
        if (!shouldContinue()) return;
        await openDesignDomainFromLanding({
          autoPipeline: /自动|一键|直接/.test(text),
          softResume: true,
          forceNewSession: false,
        });
        if (!shouldContinue()) return;
        const ack = "已根据您的描述打开设计域，可在右侧主区域继续各步。";
        layout.addLandingBubble("agent", ack);
        state.assistantThread.push({ role: "assistant", content: ack, format: "plain" });
        persistLandingAssistantThread();
      } catch (e2) {
        if (!shouldContinue()) return;
        const t = `模型已回复，但进入设计域时出错：${e2?.message || e2}`;
        layout.addLandingBubble("agent", t);
        state.assistantThread.push({ role: "assistant", content: t, format: "plain" });
      }
    };

    const thinkT0 = performance.now();
    await nextPaintFrame2();
    if (!stillMine()) return;
    try {
      const MIN_THINKING_MS = 520;
      const bumpThinkWait = async () => {
        const thinkWait = MIN_THINKING_MS - (performance.now() - thinkT0);
        if (thinkWait > 0 && stillMine()) await new Promise((res) => setTimeout(res, thinkWait));
      };
      const openStreamSurfaceOrBail = () => {
        streamCtrl = layout.beginLandingAgentStream({ reuseWrap: thinkingEl });
        flight.streamCtrl = streamCtrl;
        if (!streamCtrl) {
          layout.removeLandingThinking(thinkingEl);
          const msg = "对话区域不可用，无法显示流式回复。";
          layout.addLandingBubble("agent", msg);
          state.assistantThread.push({ role: "assistant", content: msg, format: "plain" });
          return false;
        }
        return true;
      };
      const runOrchestrateBlock = async () => {
        if (intent !== "orchestrate") return;
        try {
          if (!shouldContinue()) return;
          await runOrchestrateFromIntent();
          if (!shouldContinue()) return;
        } catch (e2) {
          if (!shouldContinue()) return;
          const t = `模型已回复，但进入构型优化编排时出错：${e2?.message || e2}`;
          layout.addLandingBubble("agent", t);
          state.assistantThread.push({ role: "assistant", content: t, format: "plain" });
        }
      };
      const finishExchange = async (replyRaw, viaProgressive) => {
        const reply = String(replyRaw || "").trim() || "（无回复）";
        if (!shouldContinue()) return;
        if (viaProgressive && streamCtrl) {
          await replayAssistantProgressive(streamCtrl, reply, ac.signal, shouldContinue);
          if (!shouldContinue()) return;
        }
        streamCtrl?.finalize(reply);
        state.assistantThread.push({ role: "assistant", content: reply, format: "md" });
        await runOrchestrateBlock();
        await runDesignDomainBlock();
      };

      const preferStream = readAssistantPreferStream();
      if (!preferStream) {
        const once = await fetchAssistantChatOnce(messages, ac.signal);
        if (!stillMine()) return;
        if (once.aborted || ac.signal.aborted) return;
        if (!once.ok) {
          layout.removeLandingThinking(thinkingEl);
          layout.addLandingBubble("agent", once.errorText || "请求失败");
          state.assistantThread.push({
            role: "assistant",
            content: once.errorText || "请求失败",
            format: "plain",
          });
          return;
        }
        await bumpThinkWait();
        if (!stillMine()) return;
        if (!openStreamSurfaceOrBail()) return;
        await finishExchange(once.reply, true);
        return;
      }

      let r;
      try {
        r = await fetch(`${normalizedBaseUrl()}/api/assistant/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages, temperature: 0.6 }),
          signal: ac.signal,
        });
      } catch (fe) {
        if (!stillMine()) return;
        if (ac.signal.aborted) return;
        layout.removeLandingThinking(thinkingEl);
        const msg = `网络错误：${fe?.message || fe}`;
        layout.addLandingBubble("agent", msg);
        state.assistantThread.push({ role: "assistant", content: msg, format: "plain" });
        return;
      }
      if (!stillMine()) return;
      if (!r.ok) {
        layout.removeLandingThinking(thinkingEl);
        const errText = await r.text().catch(() => "");
        let msg = `请求失败（${r.status}）`;
        try {
          const j = JSON.parse(errText);
          const d = j.detail;
          msg =
            typeof d === "string"
              ? d
              : Array.isArray(d)
                ? d.map((x) => (typeof x === "string" ? x : x?.msg || JSON.stringify(x))).join("；")
                : msg;
        } catch {
          if (errText) msg = errText.slice(0, 500);
        }
        layout.addLandingBubble("agent", msg);
        state.assistantThread.push({ role: "assistant", content: msg, format: "plain" });
        return;
      }
      await bumpThinkWait();
      if (!stillMine()) return;
      if (!openStreamSurfaceOrBail()) return;

      const consumed = await consumeAssistantChatStream(
        r,
        (delta) => {
          if (!shouldContinue()) return;
          streamCtrl.appendDelta(delta);
        },
        { shouldContinue, signal: ac.signal },
      );
      if (!stillMine()) return;
      if (consumed.status === "cancelled" || ac.signal.aborted) return;
      if (consumed.status === "error") {
        if (!shouldContinue()) return;
        const fb = await fetchAssistantChatOnce(messages, ac.signal);
        if (!stillMine() || fb.aborted || ac.signal.aborted) return;
        if (fb.ok) {
          await finishExchange(fb.reply, false);
          return;
        }
        const errLine = `对话失败：${fb.errorText || consumed.error?.message || "未知错误"}`;
        streamCtrl.finalize(errLine);
        state.assistantThread.push({ role: "assistant", content: errLine, format: "plain" });
        return;
      }
      await finishExchange(consumed.full, false);
    } catch (e) {
      if (!stillMine()) return;
      const aborted =
        e?.name === "AbortError" ||
        (typeof DOMException !== "undefined" && e instanceof DOMException && e.name === "AbortError") ||
        /aborted|abort/i.test(String(e?.message || ""));
      if (aborted || ac.signal.aborted) return;
      const errText = `对话失败：${e?.message || e}`;
      if (streamCtrl) streamCtrl.finalize(errText);
      else layout.removeLandingThinking(thinkingEl);
      if (!streamCtrl) layout.addLandingBubble("agent", errText);
      state.assistantThread.push({ role: "assistant", content: errText, format: "plain" });
    } finally {
      if (state.landingChatFlight === flight) state.landingChatFlight = null;
    }
  } catch (e) {
    const errText = `网络错误：${e?.message || e}`;
    layout.addLandingBubble("agent", errText);
    state.assistantThread.push({ role: "assistant", content: errText, format: "plain" });
  } finally {
    state.landingAssistantPending = false;
    if (refs.landingSendChatBtn) refs.landingSendChatBtn.disabled = false;
    persistLandingAssistantThread();
    updateLandingSubflowStrip();
    if (state.assistantThread.some((m) => m.role === "user")) scheduleTaskTitleSummarize();
    syncLandingHeroVisibility();
  }
}

async function startNewLandingTask() {
  abortLandingChat("new-task");
  if (_taskTitleSummarizeTimer) {
    clearTimeout(_taskTitleSummarizeTimer);
    _taskTitleSummarizeTimer = null;
  }
  persistLandingAssistantThread();
  const tid = crypto?.randomUUID?.() || `${Date.now()}`;
  state.currentTaskId = tid;
  state.currentFileId = null;
  state.currentFileName = "";
  state.uploadedSourceDir = "";
  state.jobId = null;
  state.assistantThread = [];
  state.landingSessionDigest = [];
  state.activeTaskKey = "";
  state.landingAttachmentPending = null;
  syncLandingPendingAttachBar();
  if (refs.msgLanding) refs.msgLanding.value = "";
  if (refs.chatLanding) refs.chatLanding.innerHTML = "";
  syncLandingHeroVisibility();
  renderTaskSessionDigest();
  updateLandingSubflowStrip();
  await taskManager.upsertTask({
    title: "新对话",
    status: "pending",
    progress: 0,
    step: 1,
  });
  await taskManager.loadTasks().catch(() => {});
}

(function wireLayoutTaskSync() {
  let uiStageTimer = null;
  function mapLayoutModeToUiStage(mode) {
    if (mode === "designDomain") return "design_domain";
    if (mode === "orchestrate") return "orchestrate";
    if (mode === "flow") return "flow";
    return String(mode || "landing");
  }
  const origShow = layout.showStage.bind(layout);
  layout.showStage = (mode) => {
    if (mode !== "landing") abortLandingChat("leave-landing");
    origShow(mode);
    queueMicrotask(() => updateOc4ReturnNavVisibility());
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
    queueMicrotask(() => {
      if (state.currentTaskId) {
        void hydrateLandingFromTask({
          task_id: state.currentTaskId,
          file_id: state.currentFileId,
          file_name: state.currentFileName,
          scan_dir: state.uploadedSourceDir,
          job_id: state.jobId,
        });
      }
    });
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

let _oc4ActivityDebounce = null;

function normalizeOc4ActivityEntry(x) {
  if (!x || typeof x !== "object") return null;
  const text = String(x.text ?? "").trim().slice(0, 2500);
  if (!text) return null;
  const role = x.role === "user" ? "user" : "agent";
  return { ts: Number.isFinite(Number(x.ts)) ? Number(x.ts) : Date.now(), role, text };
}

function ingestTaskOc4Activity(task) {
  const raw = task?.oc4_activity;
  state.oc4ActivityLog = (Array.isArray(raw) ? raw : []).map(normalizeOc4ActivityEntry).filter(Boolean).slice(-80);
}

function renderDesignDomainChatFromState() {
  const log = refs.designDomainFlowLog;
  if (!log) return;
  log.innerHTML = "";
  for (const e of state.oc4ActivityLog || []) {
    appendDesignDomainChatRow(e.role, e.text);
  }
  log.scrollTop = log.scrollHeight;
}

function appendDesignDomainChatRow(role, text) {
  const log = refs.designDomainFlowLog;
  if (!log) return;
  const wrap = document.createElement("div");
  wrap.className = `ddMsgWrap ddMsgWrap--${role === "user" ? "user" : "agent"}`;
  const badge = document.createElement("span");
  badge.className = "ddMsgBadge";
  badge.textContent = role === "user" ? "你" : "Agent";
  const row = document.createElement("div");
  row.className = `ddMsg ddMsg--${role === "user" ? "user" : "agent"}`;
  row.textContent = text;
  wrap.appendChild(badge);
  wrap.appendChild(row);
  log.appendChild(wrap);
  while (log.children.length > 48) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

function pushOc4ActivityPersist(role, text) {
  const entry = {
    ts: Date.now(),
    role: role === "user" ? "user" : "agent",
    text: String(text || "").trim().slice(0, 2500),
  };
  if (!entry.text) return;
  state.oc4ActivityLog = [...(state.oc4ActivityLog || []), entry].slice(-80);
  if (_oc4ActivityDebounce) clearTimeout(_oc4ActivityDebounce);
  _oc4ActivityDebounce = setTimeout(() => {
    _oc4ActivityDebounce = null;
    if (state.currentTaskId) taskManager.upsertTask({ oc4_activity: state.oc4ActivityLog }).catch(() => {});
  }, 450);
}

async function flushOc4ActivityPersist() {
  if (_oc4ActivityDebounce) {
    clearTimeout(_oc4ActivityDebounce);
    _oc4ActivityDebounce = null;
  }
  if (state.currentTaskId && Array.isArray(state.oc4ActivityLog) && state.oc4ActivityLog.length) {
    await taskManager.upsertTask({ oc4_activity: state.oc4ActivityLog }).catch(() => {});
  }
}

function buildOc4OrchestratePreambleMd() {
  const arr = state.oc4ActivityLog || [];
  if (!arr.length) return "";
  const lines = ["### 设计域记录", ""];
  for (const x of arr.slice(-16)) {
    const who = x.role === "user" ? "用户" : "Agent";
    const t = String(x.text || "").replace(/\s+/g, " ").trim().slice(0, 170);
    lines.push(`- **${who}**：${t}`);
  }
  return lines.join("\n");
}

function appendDesignDomainChat(role, text, opts = {}) {
  appendDesignDomainChatRow(role, text);
  if (!opts.skipPersist) pushOc4ActivityPersist(role, text);
}

function ddNlShortTopicLabel() {
  const t = state.ddNlTopic;
  if (t === "design") return "步骤1·构建";
  if (t === "preview") return "步骤2·OBJ";
  if (t === "mesh") return "步骤3·网格";
  if (t === "loads") return "步骤4·载荷";
  return "专步";
}

function appendDdNlLog(role, text) {
  const log = refs.ddStepNlLog;
  if (log) {
    const row = document.createElement("div");
    row.className = `ddMsg ${role === "user" ? "user" : "agent"}`;
    row.textContent = text;
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }
  appendDesignDomainChat(role, `[${ddNlShortTopicLabel()}] ${text}`);
}

const DD_NL_TOPIC_META = {
  design: { title: "AI Engineering · 步骤 1 · 设计域", intro: "选项讨论后点「1 构建设计域」。" },
  preview: { title: "AI Engineering · 步骤 2 · OBJ", intro: "可调三角化疏密；应用后点「2 导出 OBJ」。" },
  mesh: {
    title: "AI Engineering · 步骤 3 · 体网格",
    intro: "与主页相同 Plan 弹窗确认参数；char_max 可覆盖方案。步骤条可回溯。",
  },
  loads: {
    title: "AI Engineering · 步骤 4 · 载荷",
    intro: "描述载荷意图；可选自然语言。应用后点「4 划分载荷」。",
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

/** 当前会话已完成的最后一步序号（1～4），用于判断回溯时是否需作废后续产物 */
function deepestDdRailStepDone(p) {
  const x = p || readDdProgressFromPayload({});
  let d = 0;
  if (x.has_source_preview_obj) d = Math.max(d, 1);
  if (x.has_design_domain_step && x.has_design_preview_obj) d = Math.max(d, 2);
  if (x.has_mesh_body_inp) d = Math.max(d, 3);
  if (x.has_for_beso_inp) d = Math.max(d, 4);
  return d;
}

function computeDdStepHint(p) {
  if (!p.has_source_preview_obj) {
    return "点「1 构建设计域」生成左侧 OBJ。";
  }
  if (!p.has_design_domain_step) {
    return "左侧已就绪；点「1 构建设计域」生成 STEP 与右侧几何。";
  }
  if (!p.has_design_preview_obj) {
    return "STEP 已就绪；点「2 导出 OBJ」刷新右侧。";
  }
  if (!p.has_mesh_body_inp) {
    return "点「3 体网格」：先确认 Plan，再生成 02_mesh_body.inp。";
  }
  if (!p.has_for_beso_inp) {
    return "点「4 划分载荷」生成 03_for_beso.inp，再「完成并进入编排」。";
  }
  return "可点「完成并进入编排」。";
}

function applyDesignDomainStepUi() {
  const sid = state.oc4DesignDomainSessionId;
  const hintEl = refs.designDomainStepHint;
  const rail = refs.designDomainStepRail;
  const p = sid ? state.ddProgress ?? readDdProgressFromPayload({}) : readDdProgressFromPayload({});

  let ddCur = null;
  let ddDone = [false, false, false, false];
  let ddS4 = false;
  if (sid) {
    const s1 = p.has_source_preview_obj;
    const s2 = p.has_design_domain_step && p.has_design_preview_obj;
    const s3 = p.has_mesh_body_inp;
    const s4 = p.has_for_beso_inp;
    ddS4 = s4;
    ddDone = [s1, s2, s3, s4];
    let cur = 1;
    if (!s1) cur = 1;
    else if (!p.has_design_domain_step || !p.has_design_preview_obj) cur = 2;
    else if (!s3) cur = 3;
    else if (!s4) cur = 4;
    else cur = null;
    ddCur = cur;
  }

  if (hintEl) {
    hintEl.textContent = sid ? computeDdStepHint(p) : "上传 IGES 后开始；尚无会话。";
  }

  if (rail && sid) {
    for (let i = 0; i < 4; i += 1) {
      const el = rail.querySelector(`.ddStep[data-idx="${i + 1}"]`);
      if (!el) continue;
      el.classList.toggle("ddStepDone", ddDone[i]);
      el.classList.toggle("ddStepCurrent", ddCur === i + 1);
      el.setAttribute("aria-current", ddCur === i + 1 ? "step" : "false");
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

  const tb = refs.designDomainToolbar;
  const tbarSteps = [refs.ddBtnBuild, refs.ddBtnPreview, refs.ddBtnMesh, refs.ddBtnLoads];
  if (tb) {
    if (!sid) {
      tb.removeAttribute("data-dd-active-step");
      tb.removeAttribute("data-dd-all-done");
      for (const b of tbarSteps) {
        b?.classList.remove("ddTbarDone", "ddTbarCurrent");
      }
      refs.ddBtnFinalize?.classList.remove("ddTbarFinalizeReady");
    } else {
      tb.setAttribute("data-dd-active-step", ddCur === null ? "0" : String(ddCur));
      if (ddCur === null) tb.setAttribute("data-dd-all-done", "");
      else tb.removeAttribute("data-dd-all-done");
      tbarSteps.forEach((b, i) => {
        b?.classList.toggle("ddTbarDone", Boolean(ddDone[i]));
        b?.classList.toggle("ddTbarCurrent", ddCur === i + 1);
      });
      refs.ddBtnFinalize?.classList.toggle("ddTbarFinalizeReady", Boolean(ddS4));
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

async function focusDesignDomainRailStep(idx) {
  const rail = refs.designDomainStepRail;
  if (rail) rail.setAttribute("data-rail-focus", String(idx));
  const sid = String(state.oc4DesignDomainSessionId || "").trim();
  const p = state.ddProgress ?? readDdProgressFromPayload({});
  const deep = deepestDdRailStepDone(p);
  let didInvalidate = false;
  if (sid && idx < deep) {
    try {
      await oc4DesignDomainApi("/invalidate-from-step", { session_id: sid, rail_step: idx });
      didInvalidate = true;
      appendDesignDomainChat(
        "agent",
        `已回溯到第 ${idx} 步：已删除第 ${idx + 1}～4 步在服务端生成的中间文件，请从工具栏重新执行对应步骤。`,
      );
    } catch (e) {
      appendDesignDomainChat("agent", String(e?.message || e));
    }
    await syncDesignDomainSessionProgress().catch(() => {});
    await refreshDesignDomainPreviewsFromSession().catch(() => {});
    applyDesignDomainStepUi();
  }
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
  if (!didInvalidate) {
    const names = ["", "构建设计域 / 源预览", "导出 OBJ 预览", "FreeCAD 体网格", "划分载荷"];
    appendDesignDomainChat("agent", `步骤条：已定位到第 ${idx} 步「${names[idx] || ""}」，可在下方工具栏操作。`);
  }
}

async function fetchOc4DesignDomainSessionJson() {
  const sid = state.oc4DesignDomainSessionId;
  if (!sid) return { ok: false, data: {} };
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 45000);
  try {
    const resp = await fetch(
      `${normalizedBaseUrl()}/api/oc4/design-domain/session/${encodeURIComponent(sid)}`,
      { cache: "no-store", signal: ctrl.signal },
    );
    const data = await resp.json().catch(() => ({}));
    return { ok: resp.ok, data };
  } catch (e) {
    if (e?.name === "AbortError") {
      return { ok: false, data: { detail: "拉取设计域会话超时（45s），请检查后端或网络。" } };
    }
    return { ok: false, data: { detail: String(e?.message || e) } };
  } finally {
    clearTimeout(t);
  }
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
  let urls;
  try {
    urls = await oc4DesignDomainApi(
      "/export-source-preview",
      { session_id: sid },
      { timeoutMs: 900000 },
    );
  } finally {
    /** API 已返回即结束转圈；OBJ 拉取/解析若卡住不再挡住整页 */
    setDesignDomainOverlay("left", false);
  }
  await deferTwoFrames();
  const v = ensureDesignDomainViewer();
  if (v && urls?.source_obj) {
    try {
      await v.loadLeft(urls.source_obj);
      v.resizeAll?.();
    } catch (e) {
      appendDesignDomainChat("agent", `左侧 OBJ 预览加载失败：${e?.message || e}`);
    }
  }
  return urls;
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
    /** 无 OBJ 时不刷屏：顶部步骤条与 designDomainStepHint 已提示「1 构建设计域」 */
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
  } finally {
    setDesignDomainOverlay("right", false);
  }
  setDesignDomainOverlay("right", true, "正在导出设计域 OBJ 预览…");
  let urls;
  try {
    urls = await oc4DesignDomainApi(
      "/export-obj",
      { session_id: sid, design_only: true },
      { timeoutMs: 900000 },
    );
  } finally {
    setDesignDomainOverlay("right", false);
  }
  await deferTwoFrames();
  const v = ensureDesignDomainViewer();
  if (v && urls?.design_obj) {
    try {
      await v.loadRight(urls.design_obj);
      v.resizeAll?.();
    } catch (loadErr) {
      appendDesignDomainChat("agent", `右侧 OBJ 加载失败：${loadErr?.message || loadErr}`);
      throw loadErr;
    }
  }
  return urls;
}

/** 串行化进入设计域，避免「运行流程 + 点卡片」等并发触发双次 POST /session */
let _oc4EnterDdChain = Promise.resolve();

async function enterOc4DesignDomainStage(opts = {}) {
  const op = _oc4EnterDdChain.then(() => enterOc4DesignDomainStageImpl(opts));
  _oc4EnterDdChain = op.catch(() => {});
  return op;
}

async function enterOc4DesignDomainStageImpl(opts = {}) {
  const { autoPipeline = false, forceNewSession = false, softResume = false, resumeHint = "" } = opts;
  if (!forceNewSession) {
    await ensureOc4DesignDomainSessionForResume();
  }
  const sidHas = Boolean(String(state.oc4DesignDomainSessionId || "").trim());
  const canSoftResume = Boolean(softResume && sidHas && !forceNewSession);
  if (canSoftResume) {
    layout.showStage("designDomain");
    await deferTwoFrames();
    await refreshDesignDomainPreviewsFromSession();
    const hint = String(resumeHint || "").trim();
    if (hint) appendDesignDomainChat("agent", hint);
    return;
  }
  if (!state.currentFileId) {
    layout.addLandingBubble("agent", "请先上传 IGES 文件。");
    return;
  }
  if (!isOc4IgesFilename(state.currentFileName)) {
    layout.addLandingBubble("agent", "当前文件不是 IGES，设计域步骤不适用。");
    return;
  }
  const hadSession = Boolean(state.oc4DesignDomainSessionId) && !forceNewSession;
  if (!hadSession && refs.designDomainFlowLog) refs.designDomainFlowLog.innerHTML = "";
  if (!hadSession) {
    state.oc4ActivityLog = [];
    state.oc4LastSuggestedBuild = null;
    state.oc4LastSuggestedLoads = null;
    state.oc4PendingMesh = null;
    state.oc4PendingExport = null;
  }
  try {
    if (!state.oc4DesignDomainSessionId || forceNewSession) {
      if (!forceNewSession) {
        await taskManager.loadTasks().catch(() => {});
        await ensureOc4DesignDomainSessionForResume();
      }
      if (!state.oc4DesignDomainSessionId || forceNewSession) {
        const sess = await oc4DesignDomainApi("/session", { file_id: state.currentFileId });
        state.oc4DesignDomainSessionId = sess.session_id;
        state.oc4DesignDomainSessionIdForResume = state.oc4DesignDomainSessionId;
        appendDesignDomainChat("agent", `已创建设计域会话（${sess.session_id.slice(0, 8)}…）。几何摘要已写入服务端。`);
        if (state.currentTaskId) {
          await taskManager.upsertTask({ oc4_design_domain_session_id: state.oc4DesignDomainSessionId }).catch(() => {});
          await taskManager.loadTasks().catch(() => {});
        }
      } else {
        appendDesignDomainChat(
          "agent",
          `继续会话 ${state.oc4DesignDomainSessionId.slice(0, 8)}…（已从任务列表恢复，未新建会话）`,
        );
      }
    } else {
      appendDesignDomainChat("agent", `继续会话 ${state.oc4DesignDomainSessionId.slice(0, 8)}…（重新上传文件可开启新会话）`);
    }
    /** 会话就绪后再进入舞台，避免 /session 失败时卡在「无会话」空白页 */
    layout.showStage("designDomain");
    applyDesignDomainStepUi();
    await deferTwoFrames();
    if (autoPipeline) {
      appendDesignDomainChat("agent", "先生成源几何 STEP 预览（左侧）…");
      await runDdSourcePreviewOnly();
      appendDesignDomainChat("agent", "源预览已就绪；正在构建设计域并更新右侧预览…");
      await runDdBuildAndExportObj();
      appendDesignDomainChat("agent", "预览已更新。步骤条「AI」打开专步对话；体网格默认偏粗以控制 INP 体积。");
    } else {
      await refreshDesignDomainPreviewsFromSession();
      const p = state.ddProgress ?? readDdProgressFromPayload({});
      if (!p.has_source_preview_obj) {
        appendDesignDomainChat("agent", "下一步：点击工具栏「1 构建设计域」生成源预览与设计域几何。");
      }
    }
  } catch (e) {
    setDesignDomainOverlay("left", false);
    setDesignDomainOverlay("right", false);
    appendDesignDomainChat("agent", String(e?.message || e));
    layout.addLandingBubble("agent", `设计域：${e?.message || e}`);
    /** 仅会话未建立时退回主页，避免「尚无会话」空白卡死；已有会话则留在本页便于重试 */
    if (!String(state.oc4DesignDomainSessionId || "").trim()) {
      layout.showStage("landing");
    }
  } finally {
    await syncDesignDomainSessionProgress().catch(() => {});
  }
}

async function ensureOc4DesignDomainSessionForResume() {
  if (String(state.oc4DesignDomainSessionId || "").trim()) return true;
  const mem = String(state.oc4DesignDomainSessionIdForResume || "").trim();
  if (mem) {
    state.oc4DesignDomainSessionId = mem;
    return true;
  }
  if (!state.currentTaskId) return false;
  try {
    const resp = await fetch(`${normalizedBaseUrl()}/api/tasks`, { cache: "no-store" });
    const data = await resp.json();
    const t = (data.items || []).find((x) => x.task_id === state.currentTaskId);
    const sid = String(t?.oc4_design_domain_session_id || "").trim();
    if (sid) {
      state.oc4DesignDomainSessionId = sid;
      state.oc4DesignDomainSessionIdForResume = sid;
      if (t?.file_name && isOc4IgesFilename(t.file_name)) state.currentFileName = t.file_name;
      ingestTaskOc4Activity(t);
      renderDesignDomainChatFromState();
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}

async function goBackToOc4DesignDomainFromPipeline(opts = {}) {
  const { focusLoads = true } = opts || {};
  const ok = await ensureOc4DesignDomainSessionForResume();
  if (!ok) {
    layout.addLandingBubble(
      "agent",
      "没有可恢复的设计域会话。请重新上传 IGES 并进入设计域。",
    );
    return;
  }
  state.oc4DesignDomainFinalized = false;
  const hint =
    "已返回设计域。可重跑体网格或「4 划分载荷」，再「完成并进入编排」。";
  await enterOc4DesignDomainStage({ softResume: true, forceNewSession: false, resumeHint: hint });
  if (focusLoads) await focusDesignDomainRailStep(4);
  if (state.currentTaskId) await taskManager.upsertTask({ ui_stage: "design_domain" });
  await taskManager.loadTasks().catch(() => {});
}

async function beginOrchestrationAfterLanding(opts = {}) {
  const { skipUserBubble = false, userMessage = "" } = opts;
  if (!isOc4IgesFilename(state.currentFileName)) state.oc4ActivityLog = [];
  if (!state.currentTaskId) state.currentTaskId = crypto?.randomUUID?.() || `${Date.now()}`;
  const uMsg = String(userMessage || refs.msgLanding?.value || refs.msgEl?.value || "").trim();
  if (refs.msgEl) refs.msgEl.value = uMsg || refs.msgEl.value;
  if (!skipUserBubble) {
    const shown = String(uMsg || refs.msgEl?.value || "").trim();
    if (shown) {
      const pend = state.landingAttachmentPending;
      const bubbleOpts = {};
      const row = { role: "user", content: shown };
      if (pend?.file_id && String(pend.file_name || "").trim()) {
        bubbleOpts.attachment = {
          file_id: String(pend.file_id).trim(),
          file_name: String(pend.file_name || "").trim(),
        };
        row.attachment = { ...bubbleOpts.attachment };
      }
      layout.addLandingBubble("user", shown, bubbleOpts);
      state.assistantThread.push(row);
    }
    state.landingAttachmentPending = null;
    syncLandingPendingAttachBar();
  } else {
    state.landingAttachmentPending = null;
    syncLandingPendingAttachBar();
  }
  state.currentTaskStatus = "orchestrating";
  pushOrchestrateWorkflowCardToLandingThread();
  persistLandingAssistantThread();
  await taskManager.upsertTask({
    title: uMsg.slice(0, 80) || String(refs.msgEl?.value || "").slice(0, 80),
    progress: 12,
    step: 1,
    status: "orchestrating",
    file_name: state.currentFileName,
    scan_dir: state.uploadedSourceDir,
  });
  await taskManager.loadTasks();
  layout.showStage("orchestrate");
  if (refs.executePlannedTask) refs.executePlannedTask.disabled = true;
  const preambleMd = buildOc4OrchestratePreambleMd();
  layout.streamOrchestration(async () => {
    if (refs.executePlannedTask) refs.executePlannedTask.disabled = false;
    layout.addLandingBubble("agent", "构型优化编排完成，点击「执行任务」进入分步执行。");
    await taskManager.upsertTask({ progress: 20, step: 1, status: "ready_to_execute" });
    await taskManager.loadTasks();
  }, { preambleMd });
}

async function handleLandingWorkflowCardClick(kind) {
  const k = String(kind || "");
  if (k === "orchestrate") {
    if (!state.currentFileId) {
      layout.addLandingBubble("agent", "请先上传文件。");
      layout.showStage("landing");
      return;
    }
    if (isOc4IgesFilename(state.currentFileName) && !state.oc4DesignDomainFinalized) {
      layout.addLandingBubble("agent", "请先完成设计域流程，再进入构型优化编排。");
      return;
    }
    await layout.playLandingSubflowBridge({ kind: "orchestrate", minMs: 1280 });
    layout.showStage("orchestrate");
    return;
  }
  if (k === "design_domain") {
    if (!isOc4IgesFilename(state.currentFileName)) {
      layout.addLandingBubble("agent", "设计域需要 IGES 文件。");
      return;
    }
    /** 与顶栏「设计域」入口一致，避免漏 persist / 会话分支与重复逻辑导致点击无反应 */
    await layout.playLandingSubflowBridge({ kind: "design_domain", minMs: 1280 });
    await openDesignDomainFromLanding({ autoPipeline: false, softResume: true, forceNewSession: false }).catch((err) =>
      layout.addLandingBubble("agent", String(err?.message || err)),
    );
  }
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
    layout.addBubble("agent", "需先完成 IGES→INP 并生成主 INP。请点击「IGES → INP 格式转换」。");
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
  await ensureLandingTaskForWork();
  const prevFileId = state.currentFileId;
  state.currentFileId = data.file_id;
  state.currentFileName = data.name || file?.name || "";
  if (prevFileId && prevFileId !== state.currentFileId) {
    fetch(`${normalizedBaseUrl()}/api/files/${encodeURIComponent(prevFileId)}`, { method: "DELETE" }).catch(() => {});
  }
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
  state.landingAttachmentPending = {
    file_id: state.currentFileId,
    file_name: state.currentFileName || file.name || "",
  };
  syncLandingPendingAttachBar();
  dismissLandingHero();
  layout.addLandingBubble("agent", state.uploadedSourceDir ? `已自动识别扫描目录：${state.uploadedSourceDir}` : "自动识别目录失败，请手动填写扫描目录。");
  await taskManager.upsertTask({
    file_id: state.currentFileId,
    file_name: state.currentFileName,
    scan_dir: state.uploadedSourceDir,
    status: "uploaded",
    progress: 8,
    step: 1,
  });
  await taskManager.loadTasks();
  persistLandingAssistantThread();
  updateLandingSubflowStrip();
  if (isOc4IgesFilename(state.currentFileName)) {
    state.oc4DesignDomainSessionIdForResume = "";
    resetOc4DesignDomainState();
    state.oc4DesignDomainFinalized = false;
    disposeDesignDomainViewer();
    /** 新 IGES 与旧设计域会话解绑，否则 ensureOc4 会从任务 JSON 拉回已失效的 session_id，造成重复 POST /session */
    await taskManager.upsertTask({ oc4_design_domain_session_id: "" }).catch(() => {});
  } else {
    state.oc4DesignDomainSessionIdForResume = "";
    state.oc4DesignDomainFinalized = true;
    resetOc4DesignDomainState();
    disposeDesignDomainViewer();
    await taskManager.upsertTask({ oc4_design_domain_session_id: "" }).catch(() => {});
  }
  syncLandingHeroVisibility();
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
          "当前仅有几何（IGES）无主 INP：必须先完成格式转换得到 INP，才能点击「接受本步骤并继续」。请使用下方按钮（Esc 退出自动转换后也可在此重试）。";
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
  auto: { max: null, min: null, curvature: undefined },
  /** max 越大越粗；curvature 为 FreeCAD MeshSizeFromCurvature，越大曲面处越密 */
  fine: { max: 3000, min: 0.05, curvature: 28 },
  medium: { max: 12000, min: 0.1, curvature: 14 },
  coarse: { max: 40000, min: 1, curvature: 4 },
  xlarge: { max: 80000, min: 5, curvature: 0 },
};

const CAD_PLAN_SUBTITLE_IGES_HTML =
  "确认 FreeCAD + Gmsh 剖分参数后开始生成 <code>from_cad_gmsh.inp</code>。服务端需配置 <code>FREECAD_CMD</code>。";

function resetCadPlanModalChrome() {
  if (refs.cadPlanModalTitle) refs.cadPlanModalTitle.textContent = "网格转换方案";
  if (refs.cadPlanModalSubtitle) refs.cadPlanModalSubtitle.innerHTML = CAD_PLAN_SUBTITLE_IGES_HTML;
  if (refs.cadPlanSourceLabel) refs.cadPlanSourceLabel.textContent = "IGES 文件";
  if (refs.cadPlanStartBtn) refs.cadPlanStartBtn.textContent = "开始转换";
}

/** 设计域工具栏「疏密」→ Plan 弹窗：在 loadCadPlanDefaults 之后调用，覆盖默认以反映用户当前选择 */
function syncCadPlanFromDesignDomainToolbar() {
  const density = String(refs.ddMeshDensity?.value || "modal").trim();
  if (density && density !== "modal" && CAD_MESH_PRESETS[density] && refs.cadPlanPreset) {
    refs.cadPlanPreset.value = density;
  }
  const cm = String(refs.ddCharMax?.value || "").trim();
  if (cm && refs.cadPlanCharMax) refs.cadPlanCharMax.value = cm;
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
    syncMeshToolbarIntoCadPlan = false,
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
    if (syncMeshToolbarIntoCadPlan) syncCadPlanFromDesignDomainToolbar();
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
    modalTitle: "体网格方案",
    modalSubtitleText: "FreeCAD + Gmsh 生成 02_mesh_body.inp；char_max 越大越粗。需 FREECAD_CMD。",
    primaryButtonText: "开始体网格",
    syncMeshToolbarIntoCadPlan: true,
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
  } else if (preset !== "auto" && pr.curvature !== undefined && pr.curvature !== null) {
    mesh_size_from_curvature = pr.curvature;
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
      "IGES 尚无主 INP：服务端用 FreeCAD+Gmsh 生成 from_cad_gmsh.inp（需本机 FreeCAD / FREECAD_CMD）。完成后将自动扫描。";
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
  const topo = readTopologyOverridesForChat();
  body.mass_goal_ratio = topo.mass_goal_ratio;
  body.save_every = topo.save_every;
  if (topo.filter_radius != null) body.filter_radius = topo.filter_radius;
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
  const pp = data.parsed_params;
  if (pp && typeof pp === "object") {
    if (refs.massGoal && pp.mass_goal_ratio != null) refs.massGoal.value = String(pp.mass_goal_ratio);
    if (refs.filterR && pp.filter_radius != null) refs.filterR.value = String(pp.filter_radius);
    if (refs.saveEvery && pp.save_every != null) refs.saveEvery.value = String(pp.save_every);
    persistTopologySettingsImmediate();
  }
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
});
refs.landingSendChatBtn?.addEventListener("click", () => {
  void sendLandingAssistantChat();
});
refs.msgLanding?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (e.shiftKey) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.isComposing) return;
  e.preventDefault();
  void sendLandingAssistantChat();
});
refs.msgLanding?.addEventListener("input", () => {
  const v = String(refs.msgLanding?.value || "").trim();
  if (state.currentTaskId && v.length >= 12) scheduleTaskTitleSummarize();
  if (_landingInputHeroRaf != null) cancelAnimationFrame(_landingInputHeroRaf);
  _landingInputHeroRaf = requestAnimationFrame(() => {
    _landingInputHeroRaf = null;
    syncLandingHeroVisibility();
  });
});
refs.runAgentFlow?.addEventListener("click", async () => {
  if (!state.currentFileId) return layout.addLandingBubble("agent", "请先上传文件，再运行构型优化流程。");
  try {
    if (isOc4IgesFilename(state.currentFileName) && !state.oc4DesignDomainFinalized) {
      layout.addLandingBubble("agent", "IGES 需先完成设计域流程；已打开设计域。");
      await layout.playLandingSubflowBridge({ kind: "design_domain", minMs: 1280 });
      await openDesignDomainFromLanding({ autoPipeline: true, softResume: true }).catch((e) => {
        layout.addLandingBubble("agent", `设计域步骤：${e?.message || e}`);
      });
      return;
    }
    await layout.playLandingSubflowBridge({ kind: "orchestrate", minMs: 1280 });
    await beginOrchestrationAfterLanding();
  } catch (e) {
    layout.addLandingBubble("agent", String(e?.message || e));
  }
});
refs.landingMain?.addEventListener("click", (e) => {
  const chip = e.target.closest?.("[data-landing-prompt]");
  if (!chip || !refs.landingMain?.contains(chip)) return;
  const p = chip.getAttribute("data-landing-prompt");
  if (!p || !refs.msgLanding) return;
  refs.msgLanding.value = p;
  refs.msgLanding.dispatchEvent(new Event("input", { bubbles: true }));
  refs.msgLanding.focus();
  syncLandingHeroVisibility();
});
/** 在 chatLanding 上捕获委托：确保点在卡片上时一定命中（避免 landingMain 子层叠或 pointer-events 影响） */
refs.chatLanding?.addEventListener(
  "click",
  (e) => {
    const wf = e.target.closest?.(".landingWorkflowCard[data-workflow-jump]");
    if (!wf || !refs.chatLanding?.contains(wf)) return;
    e.preventDefault();
    e.stopPropagation();
    const kind = wf.getAttribute("data-workflow-jump");
    if (!kind) return;
    void handleLandingWorkflowCardClick(kind);
  },
  true,
);

refs.designDomainBackBtn?.addEventListener("click", () => {
  setDesignDomainOverlay("left", false);
  setDesignDomainOverlay("right", false);
  closeDdNlModal();
  disposeDesignDomainViewer();
  layout.goHome();
});
refs.ddMeshDensity?.addEventListener("change", () => {
  const v = String(refs.ddMeshDensity?.value || "modal");
  if (v === "modal" || !refs.ddCharMax) return;
  const pr = CAD_MESH_PRESETS[v];
  if (pr && pr.max != null) refs.ddCharMax.value = String(pr.max);
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
    setDesignDomainOverlay("left", false);
    setDesignDomainOverlay("right", false);
    const v = ensureDesignDomainViewer();
    if (v) {
      try {
        if (urls.source_obj) await v.loadLeft(urls.source_obj);
        if (urls.design_obj) await v.loadRight(urls.design_obj);
      } catch (loadErr) {
        appendDesignDomainChat("agent", `OBJ 预览加载失败：${loadErr?.message || loadErr}`);
      }
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
      "体网格进行中：FreeCAD + Gmsh 由 STEP 生成 02_mesh_body.inp，大模型可能需数分钟。",
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
    loadsBtn?.setAttribute("aria-busy", "true");
    if (loadsBtn) loadsBtn.disabled = true;
    const overlayMsg = nl
      ? "划分载荷：大模型解析与 INP 写入中…"
      : "划分载荷：正在划分 design / nondesign 并写入 INP…";
    setDesignDomainOverlay("right", true, overlayMsg);
    if (nl) {
      appendDesignDomainChat(
        "agent",
        "正在调用 Qwen 解析载荷自然语言，随后划分 design/nondesign 并写入 *STEP / *CLOAD …",
      );
    } else {
      appendDesignDomainChat("agent", "正在划分 design / nondesign 单元集并追加 *STEP（无自然语言时跳过 Qwen）…");
    }
    const data = await oc4DesignDomainApi("/loads", buildOc4LoadsRequestBody());
    if (data.nl_reply) appendDesignDomainChat("agent", String(data.nl_reply));
    const warns = data.validation_warnings || data.stats?.validation_warnings;
    if (Array.isArray(warns) && warns.length) {
      for (const w of warns) appendDesignDomainChat("agent", String(w));
    }
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
      const tip = "请先完成 1→3→4 步并生成 03_for_beso.inp，再进入构型优化编排。";
      appendDesignDomainChat("agent", tip);
      layout.addLandingBubble("agent", tip);
      return;
    }
    const data = await oc4DesignDomainApi("/finalize", { session_id: state.oc4DesignDomainSessionId });
    state.uploadedSourceDir = String(data.scan_dir || "").trim();
    if (refs.scanDirInput) refs.scanDirInput.value = state.uploadedSourceDir;
    state.oc4DesignDomainFinalized = true;
    const sidKeep = String(state.oc4DesignDomainSessionId || "").trim();
    state.oc4DesignDomainSessionIdForResume = sidKeep;
    appendDesignDomainChat(
      "agent",
      `设计域收尾完成。工作目录：${state.uploadedSourceDir || "(未知)"}，随后进入编排流水线。`,
    );
    await flushOc4ActivityPersist();
    resetOc4DesignDomainState();
    disposeDesignDomainViewer();
    if (refs.fileSummaryInline) {
      refs.fileSummaryInline.textContent = `已上传文件：${state.currentFileName}\n扫描目录：${state.uploadedSourceDir || "(未知)"}`;
    }
    layout.addLandingBubble("agent", `设计域完成。目录：${state.uploadedSourceDir}`);
    await taskManager.upsertTask({
      file_name: state.currentFileName,
      scan_dir: state.uploadedSourceDir,
      status: "uploaded",
      progress: 10,
      step: 1,
      ...(sidKeep ? { oc4_design_domain_session_id: sidKeep } : {}),
    });
    await taskManager.loadTasks();
    await layout.playLandingSubflowBridge({ kind: "orchestrate", minMs: 1480 });
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
  void focusDesignDomainRailStep(idx);
});
refs.designDomainStepRail?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const stepEl = e.target?.closest?.(".ddStep");
  if (!stepEl || !stepEl.classList.contains("ddStepNavigable")) return;
  e.preventDefault();
  const idx = parseInt(stepEl.getAttribute("data-idx") || "0", 10);
  if (!Number.isFinite(idx) || idx < 1 || idx > 4) return;
  void focusDesignDomainRailStep(idx);
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

refs.executePlannedTask?.addEventListener("click", async () => {
  layout.showStage("flow");
  layout.setStep(1);
  queueMicrotask(() => updateOc4ReturnNavVisibility());
  await scanDirectory();
});
refs.backToOc4FromOrchestrateBtn?.addEventListener("click", () => {
  goBackToOc4DesignDomainFromPipeline({ focusLoads: true }).catch((e) =>
    layout.addLandingBubble("agent", String(e?.message || e)),
  );
});
refs.backToOc4FromFlowBtn?.addEventListener("click", () => {
  goBackToOc4DesignDomainFromPipeline({ focusLoads: true }).catch((e) =>
    layout.addBubble("agent", String(e?.message || e)),
  );
});
refs.backHomeFromOrchestrate?.addEventListener("click", () => layout.goHome());
refs.backHomeFromFlow?.addEventListener("click", () => layout.goHome());
refs.backHomeFloating?.addEventListener("click", () => layout.goHome());
refs.refreshTasksBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  taskManager.loadTasks();
});
refs.toggleSidebarBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  layout.setSidebarCollapsed(!refs.landingMain?.classList.contains("sidebarCollapsed"));
});
refs.newLandingTaskBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  void startNewLandingTask();
});
refs.taskSidebarEl?.addEventListener("click", (e) => {
  if (e.target?.closest?.("#taskSessionDigest")) return;
  if (
    e.target?.closest?.("#refreshTasksBtn") ||
    e.target?.closest?.("#toggleSidebarBtn") ||
    e.target?.closest?.("#newLandingTaskBtn")
  ) {
    return;
  }
  if (!refs.landingMain?.classList.contains("sidebarCollapsed")) return;
  layout.setSidebarCollapsed(false);
});
refs.landingEnterDesignDomainBtn?.addEventListener("click", async () => {
  try {
    await layout.playLandingSubflowBridge({ kind: "design_domain", minMs: 1280 });
    await openDesignDomainFromLanding({ autoPipeline: false, softResume: true, forceNewSession: false });
  } catch (err) {
    layout.addLandingBubble("agent", String(err?.message || err));
  }
});
refs.landingEnterOrchestrateBtn?.addEventListener("click", async () => {
  if (!state.currentFileId) return layout.addLandingBubble("agent", "请先上传文件。");
  try {
    if (isOc4IgesFilename(state.currentFileName) && !state.oc4DesignDomainFinalized) {
      layout.addLandingBubble("agent", "IGES 需先完成设计域流程；正在打开设计域。");
      await layout.playLandingSubflowBridge({ kind: "design_domain", minMs: 1280 });
      await openDesignDomainFromLanding({ autoPipeline: true, softResume: true }).catch((e) => {
        layout.addLandingBubble("agent", `设计域步骤：${e?.message || e}`);
      });
      return;
    }
    await layout.playLandingSubflowBridge({ kind: "orchestrate", minMs: 1280 });
    await beginOrchestrationAfterLanding();
  } catch (e) {
    layout.addLandingBubble("agent", String(e?.message || e));
  }
});
refs.settingsBtn?.addEventListener("click", () => {
  syncAssistantPreferStreamUi();
  hydrateTopologyInputsFromStorage();
  void refreshQwenConfigStatus();
  setSettingsDrawer(true);
});
refs.settingsClose?.addEventListener("click", () => setSettingsDrawer(false));
refs.settingsBackdrop?.addEventListener("click", () => setSettingsDrawer(false));
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!refs.settingsShell?.classList.contains("settingsShell--open")) return;
  e.preventDefault();
  setSettingsDrawer(false);
});
refs.assistantPreferStream?.addEventListener("change", () => {
  try {
    localStorage.setItem(LS_ASSISTANT_PREFER_STREAM, refs.assistantPreferStream?.checked ? "1" : "0");
  } catch {
    /* ignore */
  }
});
[refs.massGoal, refs.filterR, refs.saveEvery].forEach((el) => {
  el?.addEventListener("input", () => schedulePersistTopologySettings());
  el?.addEventListener("change", () => persistTopologySettingsImmediate());
});
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
    await refreshQwenConfigStatus();
    layout.addLandingBubble(
      "agent",
      data.configured
        ? "Qwen 已启用：侧栏对话、意图/参数解析、设计域自然语言说明与任务标题摘要将优先使用大模型。"
        : "Qwen 未配置：上述能力将退回规则解析或受限模式（标题摘要等可能不可用）。",
    );
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

refs.landingPendingAttachRemove?.addEventListener("click", async () => {
  await clearLandingUploadedFileFromTask();
  layout.addLandingBubble("agent", "已移除文件：服务端已删除，本对话不再绑定该附件。");
});
refs.spinToggleBtn?.addEventListener("click", () => {
  const next = !viewer.getAutoRotate?.();
  viewer.setAutoRotate?.(next);
  updateSpinToggleUi();
});
[refs.backHomeFromOrchestrate, refs.backHomeFromFlow, refs.backHomeFloating].forEach((el) => {
  el?.addEventListener("click", () => setSettingsDrawer(false));
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
syncLandingHeroVisibility();
updateLandingSubflowStrip();
try {
  if (refs.baseUrlInput) {
    const stored = localStorage.getItem("beso.settings.baseUrl") || "";
    refs.baseUrlInput.value =
      stored || refs.baseUrlInput.value || (window.location?.origin || "http://127.0.0.1:8000");
    migrateCrossHostBaseUrl();
  }
  if (refs.qwenBaseUrl) refs.qwenBaseUrl.value = localStorage.getItem("beso.settings.qwenBaseUrl") || refs.qwenBaseUrl.value || "";
  if (refs.qwenModel) refs.qwenModel.value = localStorage.getItem("beso.settings.qwenModel") || refs.qwenModel.value || "";
  syncAssistantPreferStreamUi();
  refs.baseUrlText && (refs.baseUrlText.textContent = normalizedBaseUrl().replace(/^https?:\/\//, ""));
  hydrateTopologyInputsFromStorage();
} catch {}
void refreshQwenConfigStatus();
queueMicrotask(() => fireAndForgetQwenWarmup());
try {
  document.addEventListener(
    "visibilitychange",
    () => {
      if (document.visibilityState === "visible") fireAndForgetQwenWarmup();
    },
    { passive: true },
  );
  refs.msgLanding?.addEventListener("focus", () => fireAndForgetQwenWarmup(), { passive: true });
} catch {
  /* ignore */
}
try {
  const raw = localStorage.getItem("beso.sidebar.collapsed");
  const collapsed = raw === null ? true : raw === "1";
  layout.setSidebarCollapsed(collapsed);
} catch {}
updateStepperClickableState();
wireLogFloatDock();
refreshLogSummaryViews();
updateSpinToggleUi();
taskManager.loadTasks().catch(() => {});
queueMicrotask(() => applyDesignDomainStepUi());
queueMicrotask(() => updateOc4ReturnNavVisibility());

const resultsViewer = mountResultsViewer();
document.getElementById("resultsViewerBtn")?.addEventListener("click", () => {
  resultsViewer.open();
});
