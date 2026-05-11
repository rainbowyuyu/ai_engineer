/**
 * 本地结果查看器：导入文件夹，按类型筛选，预览 STEP / OBJ / INP / VTK 与四张指标 PNG；
 * 支持 BESO 多轨迭代序列：`fileNNN.vtk`、`fileNNN_state0.inp`、`fileNNN_state1.inp`、`fileNNN.inp` 分开，可在工具条选择要播放的序列。
 */
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { parseInpC3D4ToBufferGeometry } from "./flow_main.inpCcxAscii.js";
import { parseLegacyAsciiUnstructuredGridTets } from "./flow_main.vtkLegacyAscii.js";

const OCCT_IMPORT_JS_URL = "https://unpkg.com/occt-import-js@0.0.23/dist/occt-import-js.js";

/** @type {Promise<any> | null} */
let occtModulePromise = null;

function loadOcctImportJs() {
  if (occtModulePromise) return occtModulePromise;
  occtModulePromise = new Promise((resolve, reject) => {
    const start = () => {
      const fn = globalThis.occtimportjs;
      if (typeof fn !== "function") {
        reject(new Error("occt-import-js 未正确加载"));
        return;
      }
      fn()
        .then(resolve)
        .catch(reject);
    };
    if (typeof globalThis.occtimportjs === "function") {
      start();
      return;
    }
    const s = document.createElement("script");
    s.src = OCCT_IMPORT_JS_URL;
    s.async = true;
    s.onload = () => start();
    s.onerror = () => reject(new Error("无法加载 occt-import-js（检查网络或 CSP）"));
    document.head.appendChild(s);
  });
  return occtModulePromise;
}

function flattenNumberArray(arr) {
  if (!arr || !arr.length) return [];
  if (typeof arr[0] === "number") return arr;
  return arr.flat(Infinity);
}

const METRIC_NAMES = ["Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png"];

function extOf(name) {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function parseFileNumber(name, ext) {
  const m = new RegExp(`^file(\\d+)\\${ext}$`, "i").exec(name);
  return m ? parseInt(m[1], 10) : -1;
}

/**
 * @typedef {{ kind: 'vtk' | 'inp', file: File, n: number }} MeshFrame
 * @typedef {{ id: string, label: string, frames: MeshFrame[] }} MeshTrack
 */

function _mapIterFilesToFrames(/** @type {Map<number, File>} */ byN, /** @type {'vtk'|'inp'} */ kind) {
  const ns = [...byN.keys()].sort((a, b) => a - b);
  return ns.map((n) => ({ kind, file: /** @type {File} */ (byN.get(n)), n }));
}

/** 按 BESO 命名拆成多条独立序列（不按迭代合并 VTK/INP）。 */
function discoverMeshTracks(files) {
  const arr = Array.from(files || []);
  /** @type {Map<number, File>} */
  const vtkByN = new Map();
  /** @type {Map<number, File>} */
  const plainInpByN = new Map();
  /** @type {Map<string, Map<number, File>>} */
  const stateInpByKey = new Map();

  for (const f of arr) {
    let m = /^file(\d+)\.vtk$/i.exec(f.name);
    if (m) {
      vtkByN.set(parseInt(m[1], 10), f);
      continue;
    }
    m = /^file(\d+)_state(\d+)\.inp$/i.exec(f.name);
    if (m) {
      const n = parseInt(m[1], 10);
      const si = parseInt(m[2], 10);
      const key = `state${si}`;
      if (!stateInpByKey.has(key)) stateInpByKey.set(key, new Map());
      stateInpByKey.get(key).set(n, f);
      continue;
    }
    m = /^file(\d+)\.inp$/i.exec(f.name);
    if (m) {
      plainInpByN.set(parseInt(m[1], 10), f);
    }
  }

  /** @type {MeshTrack[]} */
  const tracks = [];
  if (vtkByN.size) {
    tracks.push({ id: "vtk", label: "VTK · fileNNN.vtk", frames: _mapIterFilesToFrames(vtkByN, "vtk") });
  }
  const stateKeys = [...stateInpByKey.keys()].sort((a, b) => {
    const na = parseInt(a.replace(/[^\d]/g, "") || "0", 10);
    const nb = parseInt(b.replace(/[^\d]/g, "") || "0", 10);
    return na - nb || a.localeCompare(b);
  });
  for (const key of stateKeys) {
    const mp = stateInpByKey.get(key);
    if (!mp?.size) continue;
    tracks.push({
      id: `inp_${key}`,
      label: `INP · fileNNN_${key}.inp`,
      frames: _mapIterFilesToFrames(mp, "inp"),
    });
  }
  if (plainInpByN.size) {
    tracks.push({ id: "inp_plain", label: "INP · fileNNN.inp", frames: _mapIterFilesToFrames(plainInpByN, "inp") });
  }
  return tracks.filter((t) => t.frames.length);
}

function pickDefaultMeshTrackId(/** @type {MeshTrack[]} */ tracks) {
  if (!tracks.length) return "";
  const vtk = tracks.find((t) => t.id === "vtk");
  if (vtk) return "vtk";
  return tracks[0].id;
}

function pickDefaultMeshFile(files) {
  const arr = Array.from(files || []);
  const tracks = discoverMeshTracks(arr);
  if (tracks.length) {
    const tid = pickDefaultMeshTrackId(tracks);
    const tr = tracks.find((t) => t.id === tid) || tracks[0];
    if (tr.frames.length) return tr.frames[0].file;
  }
  const objs = arr.filter((f) => extOf(f.name) === ".obj");
  if (objs.length) {
    const latest = objs.find((f) => f.name.toLowerCase() === "latest.obj");
    if (latest) return latest;
    let best = objs[0];
    let bestN = parseFileNumber(best.name, ".obj");
    for (const f of objs) {
      const n = parseFileNumber(f.name, ".obj");
      if (n > bestN) {
        best = f;
        bestN = n;
      }
    }
    return best;
  }
  const steps = arr.filter((f) => {
    const e = extOf(f.name);
    return e === ".step" || e === ".stp";
  });
  if (steps.length) {
    return [...steps].sort((a, b) => a.name.localeCompare(b.name))[0];
  }
  const inps = arr.filter((f) => extOf(f.name) === ".inp").sort((a, b) => a.name.localeCompare(b.name));
  return inps[0] || null;
}

function findFile(fileList, baseName) {
  const want = baseName.toLowerCase();
  return Array.from(fileList || []).find((f) => f.name?.toLowerCase() === want) || null;
}

/**
 * @param {{ normalizedBaseUrl?: () => string }} [opts]
 */
export function mountResultsViewer(opts = {}) {
  const getBaseUrl =
    typeof opts.normalizedBaseUrl === "function" ? opts.normalizedBaseUrl : () => "";

  const root = document.createElement("div");
  root.id = "resultsViewerModal";
  root.className = "resultsViewerModal hidden";
  root.setAttribute("aria-hidden", "true");
  root.innerHTML = `
    <div class="resultsViewerBackdrop" data-rv-close="1"></div>
    <div class="resultsViewerShell" role="dialog" aria-modal="true" aria-labelledby="resultsViewerTitle">
      <header class="resultsViewerHd">
        <div class="resultsViewerHdLeft">
          <span class="resultsViewerBadge"></span>
          <div>
            <div class="resultsViewerTitle" id="resultsViewerTitle">拓扑优化结果查看器</div>
            <div class="resultsViewerSub">导入 <span class="mono">runs/&lt;job&gt;/</span> 或 <span class="mono">examples/beso/</span> · 筛选后预览 <span class="mono">.vtk / .step / .obj / .inp</span>；<span class="mono">file*.vtk</span>、<span class="mono">file*_state0.inp</span>、<span class="mono">file*_state1.inp</span> 等为<strong>不同序列</strong>，可在工具条切换播放</div>
          </div>
        </div>
        <div class="resultsViewerHdRight">
          <button type="button" class="resultsViewerSpin rvSpinOn" id="rvSpinBtn" title="自动旋转（网格预览）">旋转</button>
          <button type="button" class="resultsViewerClose" id="rvCloseBtn" title="关闭">✕</button>
        </div>
      </header>
      <div class="resultsViewerToolbar">
        <button type="button" class="btn btnPrimary" id="rvPickBtn">导入文件夹</button>
        <input type="file" id="rvDirInput" class="hidden" webkitdirectory directory multiple />
        <span class="resultsViewerMeta" id="rvMeta">尚未导入</span>
      </div>
      <div class="resultsViewerVtkSeq hidden" id="rvVtkSeqBar" aria-label="迭代网格序列">
        <div class="resultsViewerVtkSeqHd">
          <span class="chip">迭代网格</span>
          <label class="resultsViewerMeshTrackLab hidden" id="rvMeshTrackLab">播放序列
            <select id="rvMeshTrackSelect" class="resultsViewerMeshTrackSelect" aria-label="选择迭代序列"></select>
          </label>
          <span class="resultsViewerVtkSeqHint" id="rvVtkSeqHint">各序列独立按 file 编号排序</span>
        </div>
        <div class="resultsViewerVtkSeqControls">
          <button type="button" class="btn" id="rvVtkFirst" title="第一帧">|◀</button>
          <button type="button" class="btn" id="rvVtkPrev" title="上一帧">◀</button>
          <button type="button" class="btn btnPrimary" id="rvVtkPlay" title="播放/暂停">▶</button>
          <button type="button" class="btn" id="rvVtkNext" title="下一帧">▶</button>
          <button type="button" class="btn" id="rvVtkLast" title="最后一帧">▶|</button>
          <input type="range" class="resultsViewerVtkSlider" id="rvVtkSlider" min="0" max="0" value="0" />
          <label class="resultsViewerVtkSpeedLab">间隔 (ms)
            <span class="resultsViewerIntervalSpin" title="播放每帧停留时间">
              <button type="button" class="btn resultsViewerIntervalBtn" id="rvIntervalDown" aria-label="减少间隔">−</button>
              <input type="number" id="rvIntervalMs" class="resultsViewerIntervalMs" min="50" max="120000" step="1" value="800" inputmode="numeric" />
              <button type="button" class="btn resultsViewerIntervalBtn" id="rvIntervalUp" aria-label="增加间隔">+</button>
            </span>
          </label>
          <span class="resultsViewerVtkSeqLabel mono" id="rvVtkSeqLabel">—</span>
        </div>
      </div>
      <div class="resultsViewerMainRow">
        <aside class="resultsViewerRail">
          <div class="resultsViewerFilters" id="rvFilters">
            <button type="button" class="rvFilter active" data-ext="all">全部</button>
            <button type="button" class="rvFilter" data-ext=".stp">STEP</button>
            <button type="button" class="rvFilter" data-ext=".obj">OBJ</button>
            <button type="button" class="rvFilter" data-ext=".inp">INP</button>
            <button type="button" class="rvFilter" data-ext=".vtk">VTK</button>
          </div>
          <input type="search" class="resultsViewerSearch" id="rvSearch" placeholder="筛选文件名…" autocomplete="off" />
          <div class="resultsViewerFileList" id="rvFileList"></div>
        </aside>
        <section class="resultsViewerPreviewCol">
          <div class="resultsViewerPaneHd">预览 <span class="chip" id="rvObjLabel">—</span></div>
          <div class="resultsViewerCanvasWrap" id="rvCanvasWrap">
            <pre class="resultsViewerTextPreview hidden" id="rvTextPreview" spellcheck="false"></pre>
            <div class="resultsViewerCanvasHint" id="rvCanvasHint">导入文件夹后，在左侧选择 .vtk / .step / .obj / .inp；含 file000.vtk、file000_state0.inp 等时可在上方选择序列并播放</div>
          </div>
        </section>
        <section class="resultsViewerPane resultsViewerPaneCharts">
          <div class="resultsViewerPaneHd">指标曲线 <span class="chip">Mass / FI</span></div>
          <div class="resultsViewerChartGrid" id="rvChartGrid"></div>
        </section>
      </div>
      <footer class="resultsViewerFt">STEP 使用 occt-import-js（OpenCascade WASM）三角化；VTK / INP(C3D4) 为四面体展开三角面；INP 三维优先走服务端 FreeCAD 转换（需本机后端与 FreeCAD）；VTK 与 state0/state1 等为独立序列。单帧大文件解析可能需数秒。</footer>
    </div>
  `;
  document.body.appendChild(root);

  const backdrop = root.querySelector(".resultsViewerBackdrop");
  const shell = root.querySelector(".resultsViewerShell");
  const btnClose = root.querySelector("#rvCloseBtn");
  const btnPick = root.querySelector("#rvPickBtn");
  const inpDir = root.querySelector("#rvDirInput");
  const meta = root.querySelector("#rvMeta");
  const hint = root.querySelector("#rvCanvasHint");
  const objLabel = root.querySelector("#rvObjLabel");
  const chartGrid = root.querySelector("#rvChartGrid");
  const wrap = root.querySelector("#rvCanvasWrap");
  const spinBtn = root.querySelector("#rvSpinBtn");
  const fileListEl = root.querySelector("#rvFileList");
  const searchEl = root.querySelector("#rvSearch");
  const filtersEl = root.querySelector("#rvFilters");
  const textPreview = root.querySelector("#rvTextPreview");
  const rvVtkSeqBar = root.querySelector("#rvVtkSeqBar");
  const rvVtkSlider = root.querySelector("#rvVtkSlider");
  const rvVtkSeqLabel = root.querySelector("#rvVtkSeqLabel");
  const rvVtkPlay = root.querySelector("#rvVtkPlay");
  const rvVtkFirst = root.querySelector("#rvVtkFirst");
  const rvVtkPrev = root.querySelector("#rvVtkPrev");
  const rvVtkNext = root.querySelector("#rvVtkNext");
  const rvVtkLast = root.querySelector("#rvVtkLast");
  const rvIntervalMs = root.querySelector("#rvIntervalMs");
  const rvIntervalDown = root.querySelector("#rvIntervalDown");
  const rvIntervalUp = root.querySelector("#rvIntervalUp");
  const rvMeshTrackLab = root.querySelector("#rvMeshTrackLab");
  const rvMeshTrackSelect = root.querySelector("#rvMeshTrackSelect");

  function clampPlaybackIntervalMs(v) {
    const n = Math.round(Number(v));
    if (!Number.isFinite(n)) return 800;
    return Math.max(50, Math.min(120000, n));
  }

  function readPlaybackIntervalMs() {
    return clampPlaybackIntervalMs(rvIntervalMs?.value);
  }

  function syncIntervalInputDisplay() {
    if (!rvIntervalMs) return;
    rvIntervalMs.value = String(readPlaybackIntervalMs());
  }

  let blobUrls = [];
  let threeDispose = null;
  let spinEnabled = true;
  let allFiles = [];
  let activeExtFilter = "all";
  let searchDebounce = null;
  let selectedRelPath = "";
  /** @type {MeshTrack[]} */
  let allMeshTracks = [];
  let activeMeshTrackId = "";
  /** @type {{ kind: 'vtk' | 'inp', file: File, n: number }[]} */
  let meshSeqFrames = [];
  let meshSeqIndex = 0;
  let vtkPlaying = false;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let vtkPlayTimer = null;
  let vtkLoadBusy = false;

  const objLoader = new OBJLoader();

  METRIC_NAMES.forEach((name) => {
    const card = document.createElement("div");
    card.className = "resultsViewerImgCard";
    card.dataset.metric = name;
    card.innerHTML = `
      <div class="resultsViewerImgHd"><span>${name.replace(".png", "")}</span></div>
      <div class="resultsViewerImgBody">
        <img alt="" />
        <div class="resultsViewerImgPlaceholder">未找到 ${name}</div>
      </div>`;
    chartGrid.appendChild(card);
  });

  function revokeBlobs() {
    blobUrls.forEach((u) => {
      try {
        URL.revokeObjectURL(u);
      } catch {
        /* ignore */
      }
    });
    blobUrls = [];
  }

  function destroyThree() {
    if (typeof threeDispose === "function") {
      threeDispose();
      threeDispose = null;
    }
    threeApi = null;
    wrap.querySelectorAll("canvas").forEach((c) => c.remove());
  }

  function hideTextPreview() {
    textPreview.classList.add("hidden");
    textPreview.textContent = "";
  }

  function showTextPreview(text, title) {
    destroyThree();
    textPreview.textContent = text;
    textPreview.classList.remove("hidden");
    hint.classList.add("hidden");
    objLabel.textContent = title || "INP";
  }

  let threeApi = null;

  function initThree() {
    destroyThree();
    hideTextPreview();
    hint.classList.add("hidden");
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x061426);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.02, 5000);
    camera.position.set(2.2, 1.6, 2.8);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    wrap.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    scene.add(new THREE.AmbientLight(0xffffff, 0.38));
    const dl = new THREE.DirectionalLight(0xffffff, 0.95);
    dl.position.set(4, 6, 3);
    scene.add(dl);
    const grid = new THREE.GridHelper(3.5, 18, 0x334155, 0x1e293b);
    grid.position.y = -0.85;
    scene.add(grid);
    let meshRoot = null;
    const spinAxis = new THREE.Vector3(0, 1, 0);
    const spinQuat = new THREE.Quaternion().setFromAxisAngle(spinAxis, 0.0022);
    let raf = 0;
    let w = 1;
    let h = 1;

    function fit() {
      const r = wrap.getBoundingClientRect();
      w = Math.max(120, Math.floor(r.width));
      h = Math.max(120, Math.floor(r.height));
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }
    const ro = new ResizeObserver(() => fit());
    ro.observe(wrap);
    fit();

    function tick() {
      raf = requestAnimationFrame(tick);
      if (spinEnabled && meshRoot) meshRoot.quaternion.multiply(spinQuat);
      controls.update();
      renderer.render(scene, camera);
    }
    tick();

    threeDispose = () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      if (meshRoot) {
        scene.remove(meshRoot);
        meshRoot.traverse((c) => {
          if (c.isMesh) {
            c.geometry?.dispose?.();
            if (Array.isArray(c.material)) c.material.forEach((m) => m.dispose?.());
            else c.material?.dispose?.();
          }
        });
        meshRoot = null;
      }
      renderer.domElement.remove();
    };

    /**
     * @param {THREE.Object3D} rootObj
     * @param {{ preserveView?: boolean }} [opts]
     */
    function frameObject(rootObj, opts = {}) {
      const preserveView = Boolean(opts.preserveView);
      const box = new THREE.Box3().setFromObject(rootObj);
      if (box.isEmpty()) return;
      const c = box.getCenter(new THREE.Vector3());
      const s = box.getSize(new THREE.Vector3());
      const r = Math.max(s.x, s.y, s.z, 1e-6) * 0.5;
      rootObj.position.sub(c);
      if (preserveView) {
        controls.update();
        fit();
        return;
      }
      const dist = Math.max(r * 2.4, 1.5);
      camera.position.set(dist * 0.9, dist * 0.55, dist * 0.95);
      camera.near = Math.max(0.01, dist / 400);
      camera.far = Math.max(2000, dist * 30);
      camera.updateProjectionMatrix();
      controls.target.set(0, 0, 0);
      controls.minDistance = Math.max(0.15, dist * 0.08);
      controls.maxDistance = Math.max(6, dist * 12);
      controls.update();
      fit();
    }

    /**
     * @param {THREE.Object3D} rootObj
     * @param {{ preserveView?: boolean }} [opts] preserveView：序列播放时保持相机与旋转角，仅换网格
     */
    function setRoot(rootObj, opts = {}) {
      const preserveView = Boolean(opts.preserveView);
      /** @type {THREE.Quaternion | null} */
      let prevQuat = null;
      if (preserveView && meshRoot) {
        prevQuat = meshRoot.quaternion.clone();
      }
      if (meshRoot) {
        scene.remove(meshRoot);
        meshRoot.traverse((c) => {
          if (c.isMesh) {
            c.geometry?.dispose?.();
            if (Array.isArray(c.material)) c.material.forEach((m) => m.dispose?.());
            else c.material?.dispose?.();
          }
        });
      }
      meshRoot = rootObj;
      scene.add(meshRoot);
      frameObject(meshRoot, { preserveView });
      if (preserveView && prevQuat) {
        meshRoot.quaternion.copy(prevQuat);
      }
    }

    return { setRoot, scene, camera, controls, renderer };
  }

  async function previewObj(file) {
    hideTextPreview();
    const text = await file.text();
    if (!threeApi) threeApi = initThree();
    const obj = objLoader.parse(text);
    applyMaterialToTree(obj);
    threeApi.setRoot(obj);
    objLabel.textContent = file.name;
    hint.classList.add("hidden");
  }

  function applyMaterialToTree(rootObj) {
    rootObj.traverse((c) => {
      if (c.isMesh) {
        c.material = new THREE.MeshStandardMaterial({
          color: 0x7dd3fc,
          metalness: 0.12,
          roughness: 0.42,
          side: THREE.DoubleSide,
        });
      }
    });
  }

  async function previewStep(file) {
    hideTextPreview();
    hint.textContent = "正在加载 STEP（OpenCascade WASM）…";
    hint.classList.remove("hidden");
    await new Promise((r) => requestAnimationFrame(r));

    const occt = await loadOcctImportJs();
    const buf = new Uint8Array(await file.arrayBuffer());
    const params = {
      linearUnit: "millimeter",
      linearDeflectionType: "bounding_box_ratio",
      linearDeflection: 0.004,
      angularDeflection: 0.35,
    };
    const result = occt.ReadStepFile(buf, params);
    if (!result?.success) {
      throw new Error((result && (result.error || result.message)) || "STEP 解析失败");
    }
    const list = result.meshes;
    if (!list?.length) {
      throw new Error("STEP 中未解析出网格");
    }

    if (!threeApi) threeApi = initThree();
    const group = new THREE.Group();
    for (const rm of list) {
      const posRaw = rm?.attributes?.position?.array;
      if (!posRaw?.length) continue;
      const posFlat = flattenNumberArray(posRaw);
      if (posFlat.length < 9) continue;

      const geom = new THREE.BufferGeometry();
      geom.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(posFlat), 3));

      const nRaw = rm?.attributes?.normal?.array;
      if (nRaw?.length) {
        const nFlat = flattenNumberArray(nRaw);
        if (nFlat.length === posFlat.length) {
          geom.setAttribute("normal", new THREE.Float32BufferAttribute(new Float32Array(nFlat), 3));
        } else {
          geom.computeVertexNormals();
        }
      } else {
        geom.computeVertexNormals();
      }

      const idxRaw = rm?.index?.array;
      if (idxRaw?.length) {
        const idxFlat = flattenNumberArray(idxRaw);
        geom.setIndex(new THREE.BufferAttribute(new Uint32Array(idxFlat), 1));
      }

      const col = rm.color;
      const mat = new THREE.MeshStandardMaterial({
        color: col && col.length >= 3 ? new THREE.Color(col[0], col[1], col[2]) : 0x93c5fd,
        metalness: 0.1,
        roughness: 0.45,
        side: THREE.DoubleSide,
      });
      group.add(new THREE.Mesh(geom, mat));
    }
    if (!group.children.length) {
      throw new Error("STEP 三角化后无可显示网格");
    }
    threeApi.setRoot(group);
    objLabel.textContent = file.name;
    hint.classList.add("hidden");
  }

  async function previewInpTextOnly(file) {
    const maxBytes = Math.min(file.size, 480_000);
    const slice = file.slice(0, maxBytes);
    const text = await slice.text();
    const more = file.size > maxBytes ? `\n\n… （文件共 ${file.size} 字节，仅展示前 ${maxBytes} 字节）` : "";
    showTextPreview(text + more, file.name);
  }

  /** @param {{ preserveView?: boolean }} [opts] */
  async function previewInpAsMesh3d(file, opts = {}) {
    hideTextPreview();
    const quietLoad = Boolean(opts.suppressLoadingUi);
    if (quietLoad) hint.classList.add("hidden");
    if (!quietLoad) {
      hint.textContent = "正在加载 INP 网格（FreeCAD 或本地解析）…";
      hint.classList.remove("hidden");
      await new Promise((r) => requestAnimationFrame(r));
    }

    const base = (getBaseUrl() || "").replace(/\/+$/, "");
    if (base) {
      try {
        const fd = new FormData();
        fd.append("file", file, file.name);
        const r = await fetch(`${base}/api/preview/inp-mesh-vtk`, {
          method: "POST",
          body: fd,
        });
        if (r.ok) {
          const vtkText = await r.text();
          const { geometry } = parseLegacyAsciiUnstructuredGridTets(vtkText);
          if (!threeApi) threeApi = initThree();
          const mat = new THREE.MeshStandardMaterial({
            color: 0x34d399,
            metalness: 0.08,
            roughness: 0.42,
            side: THREE.DoubleSide,
          });
          threeApi.setRoot(new THREE.Mesh(geometry, mat), { preserveView: Boolean(opts.preserveView) });
          objLabel.textContent = `${file.name}（服务端 VTK）`;
          if (!quietLoad) hint.classList.add("hidden");
          return;
        }
      } catch {
        /* 回退本地解析 */
      }
    }

    try {
      const text = await file.text();
      const { geometry } = parseInpC3D4ToBufferGeometry(text);
      if (!threeApi) threeApi = initThree();
      const mat = new THREE.MeshStandardMaterial({
        color: 0x6ee7b7,
        metalness: 0.08,
        roughness: 0.42,
        side: THREE.DoubleSide,
      });
      threeApi.setRoot(new THREE.Mesh(geometry, mat), { preserveView: Boolean(opts.preserveView) });
      objLabel.textContent = `${file.name}（本地 C3D4）`;
      if (!quietLoad) hint.classList.add("hidden");
    } catch (e) {
      hint.textContent = `INP 三维预览不可用：${e?.message || e}。可查看文本片段。`;
      hint.classList.remove("hidden");
      await previewInpTextOnly(file);
    }
  }

  function stopVtkPlayback() {
    vtkPlaying = false;
    if (vtkPlayTimer) {
      clearTimeout(vtkPlayTimer);
      vtkPlayTimer = null;
    }
    if (rvVtkPlay) rvVtkPlay.textContent = "▶";
  }

  function syncMeshSeqIndexFromFile(file) {
    const rel = file.webkitRelativePath || file.name;
    for (const track of allMeshTracks) {
      const j = track.frames.findIndex((fr) => (fr.file.webkitRelativePath || fr.file.name) === rel);
      if (j < 0) continue;
      if (track.id !== activeMeshTrackId) {
        stopVtkPlayback();
        activeMeshTrackId = track.id;
        meshSeqFrames = [...track.frames];
        if (rvMeshTrackSelect) rvMeshTrackSelect.value = track.id;
      }
      meshSeqIndex = j;
      return;
    }
  }

  function populateMeshTrackSelect() {
    if (!rvMeshTrackSelect || !rvMeshTrackLab) return;
    rvMeshTrackSelect.innerHTML = "";
    for (const t of allMeshTracks) {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.label;
      rvMeshTrackSelect.appendChild(opt);
    }
    if (activeMeshTrackId && allMeshTracks.some((x) => x.id === activeMeshTrackId)) {
      rvMeshTrackSelect.value = activeMeshTrackId;
    } else if (allMeshTracks[0]) {
      rvMeshTrackSelect.value = allMeshTracks[0].id;
      activeMeshTrackId = allMeshTracks[0].id;
    }
    const multi = allMeshTracks.length > 1;
    rvMeshTrackLab.classList.toggle("hidden", !multi);
    rvMeshTrackSelect.disabled = !multi;
  }

  function updateVtkSeqBarUi() {
    const n = meshSeqFrames.length;
    if (!rvVtkSeqBar) return;
    const hasMeshTracks = allMeshTracks.some((t) => t.frames.length > 0);
    if (!hasMeshTracks || n < 1) {
      rvVtkSeqBar.classList.add("hidden");
      return;
    }
    rvVtkSeqBar.classList.remove("hidden");
    if (rvMeshTrackSelect && activeMeshTrackId) {
      rvMeshTrackSelect.value = activeMeshTrackId;
    }
    if (rvMeshTrackLab) {
      rvMeshTrackLab.classList.toggle("hidden", allMeshTracks.length <= 1);
    }
    if (rvMeshTrackSelect) {
      rvMeshTrackSelect.disabled = allMeshTracks.length <= 1;
    }
    const maxI = Math.max(0, n - 1);
    if (rvVtkSlider) {
      rvVtkSlider.min = "0";
      rvVtkSlider.max = String(maxI);
      rvVtkSlider.value = String(Math.min(meshSeqIndex, maxI));
    }
    if (rvVtkSeqLabel) {
      const fr = meshSeqFrames[meshSeqIndex];
      const fn = fr ? `${fr.kind.toUpperCase()} · ${fr.file.name}` : "—";
      rvVtkSeqLabel.textContent = `${meshSeqIndex + 1} / ${n} · ${fn}`;
    }
    if (rvVtkFirst) rvVtkFirst.disabled = n < 1 || vtkLoadBusy;
    if (rvVtkPrev) rvVtkPrev.disabled = n < 1 || vtkLoadBusy;
    if (rvVtkNext) rvVtkNext.disabled = n < 1 || vtkLoadBusy;
    if (rvVtkLast) rvVtkLast.disabled = n < 1 || vtkLoadBusy;
    if (rvVtkSlider) rvVtkSlider.disabled = n < 1 || vtkLoadBusy;
    if (rvVtkPlay) {
      rvVtkPlay.disabled = n < 2;
      rvVtkPlay.textContent = vtkPlaying ? "❚❚" : "▶";
    }
  }

  function scheduleVtkAdvance() {
    if (vtkPlayTimer) clearTimeout(vtkPlayTimer);
    const delay = readPlaybackIntervalMs();
    vtkPlayTimer = setTimeout(async () => {
      vtkPlayTimer = null;
      if (!vtkPlaying || meshSeqFrames.length < 2) return;
      const next = (meshSeqIndex + 1) % meshSeqFrames.length;
      await showMeshFrameAtIndex(next, { silent: true });
      if (vtkPlaying) scheduleVtkAdvance();
    }, delay);
  }

  /** @param {{ preserveView?: boolean }} [opts] */
  async function previewVtk(file, opts = {}) {
    hideTextPreview();
    const quietLoad = Boolean(opts.suppressLoadingUi);
    if (quietLoad) hint.classList.add("hidden");
    if (!quietLoad) {
      hint.textContent = "正在解析 VTK（四面体网格）…";
      hint.classList.remove("hidden");
      await new Promise((r) => requestAnimationFrame(r));
    }
    const text = await file.text();
    const { geometry } = parseLegacyAsciiUnstructuredGridTets(text);
    if (!threeApi) threeApi = initThree();
    const mat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      metalness: 0.08,
      roughness: 0.42,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, mat);
    threeApi.setRoot(mesh, { preserveView: Boolean(opts.preserveView) });
    objLabel.textContent = file.name;
    if (!quietLoad) hint.classList.add("hidden");
  }

  /** @param {{ kind: 'vtk' | 'inp', file: File, n: number }} frame @param {{ preserveView?: boolean, suppressLoadingUi?: boolean }} [opts] */
  async function previewMeshFrame(frame, opts = {}) {
    const pass = {
      preserveView: Boolean(opts.preserveView),
      suppressLoadingUi: Boolean(opts.suppressLoadingUi),
    };
    if (frame.kind === "vtk") await previewVtk(frame.file, pass);
    else await previewInpAsMesh3d(frame.file, pass);
  }

  /** @param {number} idx @param {{ silent?: boolean }} [opts] */
  async function showMeshFrameAtIndex(idx, opts = {}) {
    const n = meshSeqFrames.length;
    if (n < 1) return;
    const i = Math.max(0, Math.min(n - 1, idx));
    meshSeqIndex = i;
    if (!opts.silent) stopVtkPlayback();
    updateVtkSeqBarUi();
    vtkLoadBusy = true;
    updateVtkSeqBarUi();
    try {
      const preserveView = Boolean(opts.silent && threeApi);
      await previewMeshFrame(meshSeqFrames[i], {
        preserveView,
        suppressLoadingUi: Boolean(opts.silent),
      });
      const f = meshSeqFrames[i].file;
      selectedRelPath = f.webkitRelativePath || f.name;
    } catch (e) {
      hint.textContent = `网格加载失败：${e?.message || e}`;
      hint.classList.remove("hidden");
    } finally {
      vtkLoadBusy = false;
      updateVtkSeqBarUi();
      refreshFileList();
    }
  }

  async function loadPreviewForFile(file) {
    if (!file) return;
    selectedRelPath = file.webkitRelativePath || file.name;
    const ex = extOf(file.name);
    try {
      if (ex === ".vtk") {
        stopVtkPlayback();
        syncMeshSeqIndexFromFile(file);
        updateVtkSeqBarUi();
        await previewVtk(file);
      } else if (ex === ".obj") {
        stopVtkPlayback();
        await previewObj(file);
      } else if (ex === ".step" || ex === ".stp") {
        stopVtkPlayback();
        await previewStep(file);
      } else if (ex === ".inp") {
        stopVtkPlayback();
        syncMeshSeqIndexFromFile(file);
        updateVtkSeqBarUi();
        await previewInpAsMesh3d(file);
      } else {
        hint.textContent = "不支持该扩展名预览";
        hint.classList.remove("hidden");
      }
    } catch (e) {
      hint.textContent = `加载失败：${e?.message || e}`;
      hint.classList.remove("hidden");
    }
    refreshFileList();
  }

  function isPreviewableFile(f) {
    const ex = extOf(f.name);
    return ex === ".step" || ex === ".stp" || ex === ".obj" || ex === ".inp" || ex === ".vtk";
  }

  function fileMatchesFilter(f) {
    if (!isPreviewableFile(f)) return false;
    const ex = extOf(f.name);
    if (activeExtFilter !== "all") {
      if (activeExtFilter === ".stp") {
        if (ex !== ".stp" && ex !== ".step") return false;
      } else if (ex !== activeExtFilter) {
        return false;
      }
    }
    const q = (searchEl?.value || "").trim().toLowerCase();
    if (!q) return true;
    const rel = (f.webkitRelativePath || f.name).toLowerCase();
    return rel.includes(q);
  }

  function refreshFileList() {
    if (!fileListEl) return;
    fileListEl.innerHTML = "";
    const filtered = allFiles.filter(fileMatchesFilter);
    filtered.sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name));
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "resultsViewerFileEmpty";
      empty.textContent = "无匹配文件";
      fileListEl.appendChild(empty);
      return;
    }
    for (const f of filtered) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "resultsViewerFileRow";
      const rel = f.webkitRelativePath || f.name;
      if (rel === selectedRelPath) row.classList.add("active");
      const exn = extOf(f.name);
      const icon =
        exn === ".step" || exn === ".stp"
          ? "⬡"
          : exn === ".obj"
            ? "◆"
            : exn === ".inp"
              ? "▤"
              : exn === ".vtk"
                ? "◇"
                : "·";
      row.innerHTML = `<span class="resultsViewerFileIcon">${icon}</span><span class="resultsViewerFileName">${escapeHtml(
        f.name,
      )}</span>`;
      row.title = rel;
      row.addEventListener("click", () => void loadPreviewForFile(f));
      fileListEl.appendChild(row);
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function applyPngs(fileList) {
    METRIC_NAMES.forEach((name) => {
      const card = chartGrid.querySelector(`[data-metric="${name}"]`);
      const img = card?.querySelector("img");
      const ph = card?.querySelector(".resultsViewerImgPlaceholder");
      const f = findFile(fileList, name);
      if (!img || !ph) return;
      if (f) {
        const url = URL.createObjectURL(f);
        blobUrls.push(url);
        img.src = url;
        img.classList.add("visible");
        ph.classList.add("hidden");
      } else {
        img.removeAttribute("src");
        img.classList.remove("visible");
        ph.classList.remove("hidden");
      }
    });
  }

  const RV_SCAN_MAX_FILES = 48;
  const RV_SCAN_MAX_BYTES = 42 * 1024 * 1024;

  /**
   * 与「导入文件夹」一致：用已有 File 列表刷新列表、序列轨与默认预览。
   * @param {File[]} fileList
   */
  function applyImportedFiles(fileList) {
    const fl = Array.isArray(fileList) ? fileList : [];
    stopVtkPlayback();
    revokeBlobs();
    destroyThree();
    hideTextPreview();
    threeApi = null;
    allFiles = fl;
    allMeshTracks = discoverMeshTracks(allFiles);
    activeMeshTrackId = pickDefaultMeshTrackId(allMeshTracks);
    const curTr = allMeshTracks.find((t) => t.id === activeMeshTrackId) || allMeshTracks[0];
    meshSeqFrames = curTr ? [...curTr.frames] : [];
    meshSeqIndex = 0;
    populateMeshTrackSelect();
    activeExtFilter = "all";
    filtersEl?.querySelectorAll(".rvFilter").forEach((b) => {
      b.classList.toggle("active", b.dataset.ext === "all");
    });
    if (searchEl) searchEl.value = "";
    const rootName = fl[0]?.webkitRelativePath?.split("/")[0] || fl[0]?.name || "(文件夹)";
    const nPrev = allFiles.filter(isPreviewableFile).length;
    meta.textContent = `${rootName} · ${allFiles.length} 个文件（可预览 ${nPrev}）`;
    applyPngs(fl);
    updateVtkSeqBarUi();
    refreshFileList();
    const def = pickDefaultMeshFile(fl);
    if (def) void loadPreviewForFile(def);
    else {
      hint.textContent = "未找到可预览的 .vtk / .step / .obj / .inp，可调整左侧筛选";
      hint.classList.remove("hidden");
      objLabel.textContent = "—";
    }
  }

  function onDirChange(ev) {
    const fl = ev.target?.files;
    if (!fl?.length) return;
    applyImportedFiles(Array.from(fl));
  }

  /**
   * 通过 /api/scan-directory + /runs/… 拉取工作区内目录下的已扫描文件，等价于编程方式「导入文件夹」。
   * @param {string} scanDir 绝对路径（与后端 scan_dir 一致）
   */
  async function openFromScanDir(scanDir) {
    const s = String(scanDir || "").trim();
    if (!s) throw new Error("scan_dir 为空");
    const base = String(getBaseUrl() || "").replace(/\/$/, "");
    const url = `${base}/api/scan-directory?scan_dir=${encodeURIComponent(s)}`;
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) {
      const t = await r.text().catch(() => "");
      throw new Error(`扫描目录失败 ${r.status}: ${t.slice(0, 240)}`);
    }
    const bundle = await r.json();
    const items = Array.isArray(bundle.files) ? bundle.files : [];
    /** @type {File[]} */
    const out = [];
    for (const it of items.slice(0, RV_SCAN_MAX_FILES)) {
      const abs = String(it.path || "").replace(/\\/g, "/");
      const low = abs.toLowerCase();
      const i = low.indexOf("/runs/");
      if (i < 0) continue;
      const rel = abs.slice(i + "/runs/".length);
      const segs = rel
        .split("/")
        .filter(Boolean)
        .map((x) => encodeURIComponent(x))
        .join("/");
      const fu = `${base}/runs/${segs}`;
      try {
        const fr = await fetch(fu, { cache: "no-store" });
        if (!fr.ok) continue;
        const buf = await fr.arrayBuffer();
        if (buf.byteLength > RV_SCAN_MAX_BYTES) continue;
        const name = String(it.name || rel.split("/").pop() || "file");
        const pseudo = `scan/${name}`;
        const file = new File([buf], name, { type: "application/octet-stream" });
        try {
          Object.defineProperty(file, "webkitRelativePath", { value: pseudo, configurable: true });
        } catch {
          /* ignore */
        }
        out.push(file);
      } catch {
        /* skip */
      }
    }
    open();
    if (!out.length) {
      applyImportedFiles([]);
      if (meta)
        meta.textContent = `已连接目录（扫描 ${items.length} 个输入项）但未能从 /runs/ 拉取可预览文件；请用「导入文件夹」或确认文件在 runs 下。`;
      return;
    }
    applyImportedFiles(out);
    const tail = s.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "scan";
    if (meta) meta.textContent = `${tail} · 自服务器拉取 ${out.length} 个文件`;
  }

  filtersEl?.addEventListener("click", (e) => {
    const btn = e.target.closest?.(".rvFilter");
    if (!btn) return;
    activeExtFilter = btn.dataset.ext || "all";
    filtersEl.querySelectorAll(".rvFilter").forEach((b) => b.classList.toggle("active", b === btn));
    refreshFileList();
  });

  searchEl?.addEventListener("input", () => {
    window.clearTimeout(searchDebounce);
    searchDebounce = window.setTimeout(() => refreshFileList(), 160);
  });

  function open() {
    root.classList.remove("hidden");
    root.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    root.classList.add("isOpen");
    shell?.classList.add("isOpen");
    requestAnimationFrame(() => {
      root.classList.add("isOpen");
      shell?.classList.add("isOpen");
    });
  }

  function close() {
    stopVtkPlayback();
    root.classList.remove("isOpen");
    shell?.classList.remove("isOpen");
    document.body.style.overflow = "";
    window.setTimeout(() => {
      root.classList.add("hidden");
      root.setAttribute("aria-hidden", "true");
      if (inpDir) inpDir.value = "";
    }, 320);
  }

  btnClose?.addEventListener("click", close);
  backdrop?.addEventListener("click", (e) => {
    if (e.target?.dataset?.rvClose) close();
  });
  btnPick?.addEventListener("click", () => inpDir?.click());
  inpDir?.addEventListener("change", onDirChange);
  spinBtn?.addEventListener("click", () => {
    spinEnabled = !spinEnabled;
    spinBtn.classList.toggle("rvSpinOn", spinEnabled);
    spinBtn.classList.toggle("rvSpinOff", !spinEnabled);
  });

  rvVtkPlay?.addEventListener("click", () => {
    if (meshSeqFrames.length < 2) return;
    if (vtkPlaying) {
      vtkPlaying = false;
      if (rvVtkPlay) rvVtkPlay.textContent = "▶";
      if (vtkPlayTimer) {
        clearTimeout(vtkPlayTimer);
        vtkPlayTimer = null;
      }
      updateVtkSeqBarUi();
      return;
    }
    if (vtkLoadBusy) return;
    vtkPlaying = true;
    if (rvVtkPlay) rvVtkPlay.textContent = "❚❚";
    scheduleVtkAdvance();
  });
  rvVtkFirst?.addEventListener("click", () => {
    stopVtkPlayback();
    void showMeshFrameAtIndex(0);
  });
  rvVtkPrev?.addEventListener("click", () => {
    stopVtkPlayback();
    void showMeshFrameAtIndex(meshSeqIndex - 1);
  });
  rvVtkNext?.addEventListener("click", () => {
    stopVtkPlayback();
    void showMeshFrameAtIndex(meshSeqIndex + 1);
  });
  rvVtkLast?.addEventListener("click", () => {
    stopVtkPlayback();
    void showMeshFrameAtIndex(meshSeqFrames.length - 1);
  });
  rvVtkSlider?.addEventListener("change", () => {
    stopVtkPlayback();
    const v = parseInt(rvVtkSlider.value, 10);
    if (Number.isFinite(v)) void showMeshFrameAtIndex(v);
  });
  function bumpIntervalMs(delta) {
    if (!rvIntervalMs) return;
    const v = readPlaybackIntervalMs() + delta;
    rvIntervalMs.value = String(clampPlaybackIntervalMs(v));
    if (vtkPlaying) {
      if (vtkPlayTimer) clearTimeout(vtkPlayTimer);
      scheduleVtkAdvance();
    }
  }

  rvIntervalDown?.addEventListener("click", () => bumpIntervalMs(-50));
  rvIntervalUp?.addEventListener("click", () => bumpIntervalMs(50));
  rvIntervalMs?.addEventListener("change", () => {
    syncIntervalInputDisplay();
    if (vtkPlaying) {
      if (vtkPlayTimer) clearTimeout(vtkPlayTimer);
      scheduleVtkAdvance();
    }
  });
  rvIntervalMs?.addEventListener("blur", () => syncIntervalInputDisplay());

  rvMeshTrackSelect?.addEventListener("change", () => {
    stopVtkPlayback();
    activeMeshTrackId = rvMeshTrackSelect.value;
    const tr = allMeshTracks.find((t) => t.id === activeMeshTrackId);
    meshSeqFrames = tr ? [...tr.frames] : [];
    meshSeqIndex = 0;
    updateVtkSeqBarUi();
    void showMeshFrameAtIndex(0);
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && root.classList.contains("isOpen")) close();
  });

  return {
    open,
    close,
    openFromScanDir,
    applyImportedFiles,
    destroy: () => {
      stopVtkPlayback();
      revokeBlobs();
      destroyThree();
      root.remove();
    },
  };
}
