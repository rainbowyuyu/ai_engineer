// Minimal UI without npm build (ESM via CDN).
// Use three.js + OBJLoader to render latest.obj produced by backend.
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const $ = (id) => document.getElementById(id);
const LS_TOPOLOGY = "beso.settings.topology.v1";
function hydrateTopoMain() {
  try {
    const o = JSON.parse(localStorage.getItem(LS_TOPOLOGY) || "null");
    const m = $("massGoal");
    const s = $("saveEvery");
    const f = $("filterR");
    if (m) m.value = o?.mg != null && String(o.mg).trim() !== "" ? String(o.mg) : "0.25";
    if (s) s.value = o?.se != null && String(o.se).trim() !== "" ? String(o.se) : "1";
    if (f) f.value = o && o.fr != null ? String(o.fr) : "";
  } catch {
    /* ignore */
  }
}
function persistTopoMain() {
  try {
    localStorage.setItem(
      LS_TOPOLOGY,
      JSON.stringify({
        mg: $("massGoal")?.value ?? "",
        fr: $("filterR")?.value ?? "",
        se: $("saveEvery")?.value ?? "",
      }),
    );
  } catch {
    /* ignore */
  }
}
const chatEl = $("chat");
const jobLogsEl = $("jobLogs");
const vtkLink = $("vtkLink");
const statusEl = $("status");
const jobIdEl = $("jobId");
const cancelBtn = $("cancelBtn");
const fileInput = $("fileInput");
const pickBtn = $("pickBtn");
const settingsBtn = $("settingsBtn");
const settingsShell = $("settingsShell");
const settingsBackdrop = $("settingsBackdrop");
const settingsPanel = $("settingsPanel");
const settingsClose = $("settingsClose");
const baseUrlInput = $("baseUrl");
const baseUrlText = $("baseUrlText");
const fileSummary = $("fileSummary");
const fileSummaryInline = $("fileSummaryInline");
const filePreview = $("filePreview");
const imgGrid = $("imgGrid");
const qwenBaseUrl = $("qwenBaseUrl");
const qwenModel = $("qwenModel");
const qwenKey = $("qwenKey");
const qwenSave = $("qwenSave");
const qwenStatus = $("qwenStatus");
const codeTabs = $("codeTabs");
const codePreview = $("codePreview");
const scanDirInput = $("scanDir");
const scanBtn = $("scanBtn");
const mappingPreview = $("mappingPreview");

let currentFileId = null;
let parsedParams = null;
let currentJobLogBox = null;
let generatedCodeMap = new Map();

let ws = null;
let jobId = null;
let lastVtkUrl = null;

function normalizedBaseUrl() {
  let base = (baseUrlInput.value || "").trim();
  if (!base) return window.location.origin;
  if (!/^https?:\/\//i.test(base)) base = `http://${base}`;
  return base.replace(/\/+$/, "");
}

const container = $("vtk");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b1020);
const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
camera.position.set(0, 0, 3);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio || 1);
container.appendChild(renderer.domElement);
renderer.domElement.style.cursor = "grab";

const light1 = new THREE.DirectionalLight(0xffffff, 1.0);
light1.position.set(2, 2, 2);
scene.add(light1);
scene.add(new THREE.AmbientLight(0xffffff, 0.35));

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.enablePan = true;
controls.enableZoom = true;
controls.zoomSpeed = 1.1;
controls.rotateSpeed = 0.8;
controls.target.set(0, 0, 0);
controls.update();

let currentObj = null;
const loader = new OBJLoader();

function resize() {
  const r = container.getBoundingClientRect();
  const w = Math.max(1, Math.floor(r.width));
  const h = Math.max(1, Math.floor(r.height));
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
}

// Ensure 3D canvas always matches container
new ResizeObserver(() => resize()).observe(container);

function animate() {
  requestAnimationFrame(animate);
  if (currentObj) currentObj.rotation.y += 0.0015;
  controls.update();
  renderer.render(scene, camera);
}
resize();
animate();

function appendLog(line) {
  if (!currentJobLogBox) {
    // fallback
    addBubble("agent", line, true);
    return;
  }
  currentJobLogBox.textContent += line + "\n";
  currentJobLogBox.scrollTop = currentJobLogBox.scrollHeight;
}

function renderSelectedInputs(selected) {
  if (!selected) {
    mappingPreview.textContent = "(暂无输入映射)";
    return;
  }
  const primary = selected.primary_inp || "(未识别)";
  const aux = selected.aux_inps || {};
  const loadCase = (aux.load_case || []).join(", ") || "(none)";
  const setDef = (aux.set_definition || []).join(", ") || "(none)";
  const other = (aux.other_inp || []).join(", ") || "(none)";
  const step = selected.step_mapping || {};
  const stepLines = Object.keys(step).length
    ? Object.entries(step).map(([k, v]) => `${k} -> step ${v}`).join("\n")
    : "(none)";
  mappingPreview.textContent = `primary: ${primary}\nload_case: ${loadCase}\nset_definition: ${setDef}\nother_inp: ${other}\nstep_mapping:\n${stepLines}`;
}

async function showCodeFile(name, url) {
  try {
    const full = `${normalizedBaseUrl()}${url}`;
    const text = await (await fetch(full, { cache: "no-store" })).text();
    codePreview.textContent = text;
    [...codeTabs.querySelectorAll("button")].forEach((b) => {
      b.classList.toggle("btnPrimary", b.dataset.codeName === name);
    });
  } catch (e) {
    codePreview.textContent = `读取代码失败: ${e}`;
  }
}

function upsertCode(name, url, group = "generated") {
  generatedCodeMap.set(name, { url, group });
  let tab = codeTabs.querySelector(`button[data-code-name="${name}"]`);
  if (!tab) {
    tab = document.createElement("button");
    tab.className = "btn";
    tab.dataset.codeName = name;
    tab.textContent = `[${group}] ${name}`;
    tab.addEventListener("click", () => {
      const item = generatedCodeMap.get(name);
      showCodeFile(name, item && item.url ? item.url : url);
    });
    codeTabs.appendChild(tab);
  } else {
    tab.textContent = `[${group}] ${name}`;
  }
  if (generatedCodeMap.size === 1) {
    showCodeFile(name, url);
  }
}

function addBubble(role, text, isLog = false) {
  const b = document.createElement("div");
  b.className = `bubble ${role}`;
  b.textContent = text;
  if (isLog) {
    const m = document.createElement("div");
    m.className = "meta";
    m.textContent = "log";
    b.appendChild(m);
  }
  chatEl.appendChild(b);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function loadMesh(url) {
  try {
    const full = `${normalizedBaseUrl()}${url}`;
    const resp = await fetch(full, { cache: "no-store" });
    const text = await resp.text();
    const obj = loader.parse(text);
    // center to origin so rotation/camera is stable
    const box0 = new THREE.Box3().setFromObject(obj);
    const center0 = new THREE.Vector3();
    box0.getCenter(center0);
    obj.position.sub(center0);
    obj.traverse((c) => {
      if (c.isMesh) {
        c.material = new THREE.MeshStandardMaterial({
          color: 0x93c5fd,
          metalness: 0.05,
          roughness: 0.55,
          side: THREE.DoubleSide,
        });
      }
    });
    if (currentObj) scene.remove(currentObj);
    currentObj = obj;
    scene.add(obj);

    // auto fit camera
    const box = new THREE.Box3().setFromObject(obj);
    const size = new THREE.Vector3();
    const center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const dist = maxDim * 1.8;
    camera.position.set(0, 0, dist);
    camera.lookAt(0, 0, 0);
    controls.target.set(0, 0, 0);
    controls.update();
  } catch (e) {
    appendLog(`[UI] 网格渲染失败：${e}`);
  }
}

function upsertImage(name, url) {
  let card = document.querySelector(`[data-img='${name}']`);
  if (!card) {
    card = document.createElement("div");
    card.className = "imgCard";
    card.dataset.img = name;
    card.innerHTML = `
      <div class="imgCardHd"><span>${name}</span><a target="_blank">打开</a></div>
      <img />
    `;
    imgGrid.appendChild(card);
  }
  const a = card.querySelector("a");
  const img = card.querySelector("img");
  const full = `${normalizedBaseUrl()}${url}`;
  a.href = full;
  // bust cache
  img.src = `${full}?t=${Date.now()}`;
}

function connectWs() {
  const base = normalizedBaseUrl().replace(/^http/i, "ws");
  ws = new WebSocket(`${base}/ws/jobs/${jobId}`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "snapshot") {
      statusEl.textContent = msg.job.status;
      jobIdEl.textContent = msg.job.id;
      if (Array.isArray(msg.job.artifacts)) {
        msg.job.artifacts.forEach((evt) => {
          if (evt.kind === "code" || evt.kind === "manifest") upsertCode(evt.name, evt.url, (evt.meta && evt.meta.group) || evt.kind);
        });
      }
      renderSelectedInputs(msg.job.selected_inputs || null);
      if (msg.job.latest_vtk_url) {
        lastVtkUrl = msg.job.latest_vtk_url;
        vtkLink.href = `${normalizedBaseUrl()}${lastVtkUrl}`;
        vtkLink.textContent = lastVtkUrl;
        loadMesh(lastVtkUrl);
      }
      return;
    }
    if (msg.type === "log") appendLog(msg.line);
    if (msg.type === "status") statusEl.textContent = msg.status;
    if (msg.type === "vtk") {
      lastVtkUrl = msg.url;
      vtkLink.href = `${normalizedBaseUrl()}${lastVtkUrl}`;
      vtkLink.textContent = lastVtkUrl;
      loadMesh(lastVtkUrl);
    }
    if (msg.type === "artifact") {
      if (msg.kind === "mesh") {
        // show source vtk if provided
        const label = (msg.meta && msg.meta.source_vtk) ? msg.meta.source_vtk : msg.name;
        vtkLink.href = `${normalizedBaseUrl()}${msg.url}`;
        vtkLink.textContent = label;
        loadMesh(msg.url);
      } else if (msg.kind === "image") {
        upsertImage(msg.name, msg.url);
      } else if (msg.kind === "code" || msg.kind === "manifest") {
        upsertCode(msg.name, msg.url, (msg.meta && msg.meta.group) || msg.kind);
      }
    }
  };
  ws.onclose = () => {
    appendLog("[UI] WebSocket 已断开");
  };
}

async function uploadSelectedFile(file) {
  const base = normalizedBaseUrl();
  const fd = new FormData();
  fd.append("file", file);
  const resp = await fetch(`${base}/api/files/upload`, { method: "POST", body: fd });
  const data = await resp.json();
  currentFileId = data.file_id;
  addBubble("agent", `已选择文件：${data.name}`);

  const p = await (await fetch(`${base}/api/files/${currentFileId}/preview`)).json();
  if (p.ext === ".inp") {
    const elsets = (p.preview.elsets || []).join(", ") || "(未识别)";
    fileSummary.textContent = `文件：${p.name}\nELSET：${elsets}`;
    fileSummaryInline.textContent = fileSummary.textContent;
    filePreview.textContent = (p.preview.lines || []).join("\n");
  } else {
    fileSummary.textContent = `文件：${p.name}\n类型：${p.ext}`;
    fileSummaryInline.textContent = fileSummary.textContent;
    filePreview.textContent = "";
  }

  // 在桌面运行时（如 Electron/WebView）通常可拿到 file.path，自动同步扫描目录，避免手动输入。
  const rawPath = file && typeof file.path === "string" ? file.path : "";
  if (rawPath) {
    const normalized = rawPath.replace(/\//g, "\\");
    const idx = normalized.lastIndexOf("\\");
    if (idx > 0) scanDirInput.value = normalized.slice(0, idx);
  }
}

async function createAndRun() {
  addBubble("user", $("msg").value);
  statusEl.textContent = "-";
  jobIdEl.textContent = "(启动中...)";

  const base = normalizedBaseUrl();
  const body = { message: $("msg").value, auto_start: true };
  const scanDir = scanDirInput.value.trim();
  if (scanDir) body.scan_dir = scanDir;

  if (currentFileId) body.file_id = currentFileId;

  // optional manual overrides (settings panel)
  const mg = Number($("massGoal")?.value);
  const fr = Number($("filterR")?.value);
  const se = Number($("saveEvery")?.value);
  body.mass_goal_ratio = Number.isFinite(mg) && mg > 0 && mg < 1 ? mg : 0.25;
  body.save_every = Number.isFinite(se) && se > 0 ? Math.floor(se) : 1;
  if (Number.isFinite(fr) && fr > 0) body.filter_radius = fr;

  const resp = await fetch(`${base}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (!resp.ok) {
    addBubble("agent", `启动失败：${data.detail || JSON.stringify(data)}`);
    return;
  }
  jobId = data.job_id;
  generatedCodeMap = new Map();
  codeTabs.innerHTML = "";
  codePreview.textContent = "(尚未生成代码)";
  mappingPreview.textContent = "(暂无输入映射)";
  // create a dedicated log window per job
  const wrap = document.createElement("div");
  wrap.className = "imgCard"; // reuse card style
  wrap.style.height = "200px";
  wrap.innerHTML = `
    <div class="imgCardHd"><span>Job ${jobId.slice(0, 8)}</span><a target="_blank">打开目录</a></div>
    <pre class="previewBox" style="margin:10px; height:140px; max-height:none; overflow:auto;"></pre>
  `;
  const pre = wrap.querySelector("pre");
  const a = wrap.querySelector("a");
  a.href = `${normalizedBaseUrl()}/runs/${jobId}/`;
  jobLogsEl.prepend(wrap);
  currentJobLogBox = pre;

  parsedParams = data.parsed_params || null;
  if (parsedParams) {
    $("massGoal").value = String(parsedParams.mass_goal_ratio ?? "");
    $("filterR").value = String(parsedParams.filter_radius ?? "");
    $("saveEvery").value = String(parsedParams.save_every ?? "");
    persistTopoMain();
  }
  if (Array.isArray(data.generated_code)) {
    data.generated_code.forEach((f) => upsertCode(f.name, f.url, f.group || "generated"));
  }
  renderSelectedInputs(data.selected_inputs || null);
  if (data.reasoning_summary) addBubble("agent", `参数解析：${data.reasoning_summary}`);
  cancelBtn.disabled = false;
  connectWs();
}

async function scanDirectory() {
  const scanDir = scanDirInput.value.trim();
  if (!scanDir) {
    addBubble("agent", "请先输入扫描目录绝对路径。");
    return;
  }
  const base = normalizedBaseUrl();
  const url = `${base}/api/scan-directory?scan_dir=${encodeURIComponent(scanDir)}`;
  const resp = await fetch(url);
  const data = await resp.json();
  if (!resp.ok) {
    addBubble("agent", `扫描失败：${data.detail || JSON.stringify(data)}`);
    return;
  }
  const files = (data.files || []).slice(0, 12).map((x) => `- ${x.name} [${x.role}]`).join("\n");
  const notes = (data.notes || []).join("；") || "无";
  addBubble("agent", `扫描完成，主输入：${data.primary_inp || "(未识别)"}\n${files}\n备注：${notes}`);
  fileSummaryInline.textContent = `扫描目录：${data.scan_dir}\n主输入：${data.primary_inp || "(未识别)"}`;
}

async function cancel() {
  if (!jobId) return;
  const base = normalizedBaseUrl();
  await fetch(`${base}/api/jobs/${jobId}/cancel`, { method: "POST" });
  appendLog("[UI] 已请求取消");
}

$("startBtn").addEventListener("click", createAndRun);
scanBtn.addEventListener("click", scanDirectory);
cancelBtn.addEventListener("click", cancel);

window.addEventListener("resize", resize);

pickBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  await uploadSelectedFile(f);
});

function setSettingsDrawer(open) {
  const on = Boolean(open);
  if (settingsShell) {
    settingsShell.setAttribute("aria-hidden", on ? "false" : "true");
    settingsShell.classList.toggle("settingsShell--open", on);
    document.body.classList.toggle("settingsDrawerOpen", on);
  } else if (settingsPanel) {
    settingsPanel.classList.toggle("hidden", !on);
  }
}
settingsBtn.addEventListener("click", () => {
  hydrateTopoMain();
  void refreshQwenStatus();
  setSettingsDrawer(true);
});
settingsClose?.addEventListener("click", () => setSettingsDrawer(false));
settingsBackdrop?.addEventListener("click", () => setSettingsDrawer(false));
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !settingsShell?.classList.contains("settingsShell--open")) return;
  e.preventDefault();
  setSettingsDrawer(false);
});
baseUrlInput.addEventListener("input", () => {
  try {
    baseUrlText.textContent = baseUrlInput.value.replace(/^https?:\/\//, "");
  } catch {}
});

// init base url text
baseUrlText.textContent = baseUrlInput.value.replace(/^https?:\/\//, "");

async function refreshQwenStatus() {
  if (!qwenStatus) return;
  try {
    const base = normalizedBaseUrl();
    const data = await (await fetch(`${base}/api/config/qwen`, { cache: "no-store" })).json();
    qwenStatus.textContent = data.configured
      ? `已配置（${data.model || "qwen"}）`
      : "未配置：填写 API Key 或设置环境变量 QWEN_API_KEY";
    if (data.base_url) qwenBaseUrl.value = data.base_url;
    if (data.model) qwenModel.value = data.model;
  } catch {
    qwenStatus.textContent = "无法连接后端检测 Qwen";
  }
}

qwenSave.addEventListener("click", async () => {
  const base = normalizedBaseUrl();
  const body = {
    api_key: qwenKey.value.trim() || null,
    base_url: qwenBaseUrl.value.trim() || null,
    model: qwenModel.value.trim() || null,
  };
  const resp = await fetch(`${base}/api/config/qwen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  await refreshQwenStatus();
  // Persist for convenience on this machine/browser.
  localStorage.setItem("qwen_base_url", qwenBaseUrl.value || "");
  localStorage.setItem("qwen_model", qwenModel.value || "");
  localStorage.setItem("qwen_api_key", qwenKey.value || "");
  addBubble("agent", data.configured ? "已启用 Qwen 参数解析。" : "Qwen 未启用。");
});

hydrateTopoMain();
["massGoal", "filterR", "saveEvery"].forEach((id) => {
  const el = $(id);
  el?.addEventListener("input", () => persistTopoMain());
});
refreshQwenStatus();

// Restore locally-saved Qwen settings (never sent unless user clicks save)
try {
  const lsBase = localStorage.getItem("qwen_base_url");
  const lsModel = localStorage.getItem("qwen_model");
  const lsKey = localStorage.getItem("qwen_api_key");
  if (lsBase && !qwenBaseUrl.value) qwenBaseUrl.value = lsBase;
  if (lsModel && !qwenModel.value) qwenModel.value = lsModel;
  if (lsKey && !qwenKey.value) qwenKey.value = lsKey;
} catch {}

