/**
 * 本地结果查看器：导入文件夹，按类型筛选，预览 STEP / OBJ / INP 与四张指标 PNG。
 */
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

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

function pickDefaultMeshFile(files) {
  const arr = Array.from(files || []);
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

export function mountResultsViewer() {
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
            <div class="resultsViewerSub">导入 <span class="mono">runs/&lt;job&gt;/</span> · 筛选后点击文件即可预览 <span class="mono">.step / .stp / .obj / .inp</span></div>
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
      <div class="resultsViewerMainRow">
        <aside class="resultsViewerRail">
          <div class="resultsViewerFilters" id="rvFilters">
            <button type="button" class="rvFilter active" data-ext="all">全部</button>
            <button type="button" class="rvFilter" data-ext=".stp">STEP</button>
            <button type="button" class="rvFilter" data-ext=".obj">OBJ</button>
            <button type="button" class="rvFilter" data-ext=".inp">INP</button>
          </div>
          <input type="search" class="resultsViewerSearch" id="rvSearch" placeholder="筛选文件名…" autocomplete="off" />
          <div class="resultsViewerFileList" id="rvFileList"></div>
        </aside>
        <section class="resultsViewerPreviewCol">
          <div class="resultsViewerPaneHd">预览 <span class="chip" id="rvObjLabel">—</span></div>
          <div class="resultsViewerCanvasWrap" id="rvCanvasWrap">
            <pre class="resultsViewerTextPreview hidden" id="rvTextPreview" spellcheck="false"></pre>
            <div class="resultsViewerCanvasHint" id="rvCanvasHint">导入文件夹后，在左侧选择 .step / .stp / .obj / .inp</div>
          </div>
        </section>
        <section class="resultsViewerPane resultsViewerPaneCharts">
          <div class="resultsViewerPaneHd">指标曲线 <span class="chip">Mass / FI</span></div>
          <div class="resultsViewerChartGrid" id="rvChartGrid"></div>
        </section>
      </div>
      <footer class="resultsViewerFt">STEP 使用 occt-import-js（OpenCascade WASM）三角化预览；大文件首次加载较慢。</footer>
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

  let blobUrls = [];
  let threeDispose = null;
  let spinEnabled = true;
  let allFiles = [];
  let activeExtFilter = "all";
  let searchDebounce = null;
  let selectedRelPath = "";

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

    function frameObject(rootObj) {
      const box = new THREE.Box3().setFromObject(rootObj);
      if (box.isEmpty()) return;
      const c = box.getCenter(new THREE.Vector3());
      const s = box.getSize(new THREE.Vector3());
      const r = Math.max(s.x, s.y, s.z, 1e-6) * 0.5;
      rootObj.position.sub(c);
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

    function setRoot(rootObj) {
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
      frameObject(meshRoot);
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

  async function previewInp(file) {
    const maxBytes = Math.min(file.size, 480_000);
    const slice = file.slice(0, maxBytes);
    const text = await slice.text();
    const more = file.size > maxBytes ? `\n\n… （文件共 ${file.size} 字节，仅展示前 ${maxBytes} 字节）` : "";
    showTextPreview(text + more, file.name);
  }

  async function loadPreviewForFile(file) {
    if (!file) return;
    selectedRelPath = file.webkitRelativePath || file.name;
    const ex = extOf(file.name);
    try {
      if (ex === ".obj") {
        await previewObj(file);
      } else if (ex === ".step" || ex === ".stp") {
        await previewStep(file);
      } else if (ex === ".inp") {
        await previewInp(file);
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
    return ex === ".step" || ex === ".stp" || ex === ".obj" || ex === ".inp";
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
        exn === ".step" || exn === ".stp" ? "⬡" : exn === ".obj" ? "◆" : exn === ".inp" ? "▤" : "·";
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

  function onDirChange(ev) {
    const fl = ev.target?.files;
    if (!fl?.length) return;
    revokeBlobs();
    destroyThree();
    hideTextPreview();
    threeApi = null;
    allFiles = Array.from(fl);
    activeExtFilter = "all";
    filtersEl?.querySelectorAll(".rvFilter").forEach((b) => {
      b.classList.toggle("active", b.dataset.ext === "all");
    });
    if (searchEl) searchEl.value = "";
    const rootName = fl[0]?.webkitRelativePath?.split("/")[0] || "(文件夹)";
    const nPrev = allFiles.filter(isPreviewableFile).length;
    meta.textContent = `${rootName} · ${allFiles.length} 个文件（可预览 ${nPrev}）`;
    applyPngs(fl);
    refreshFileList();
    const def = pickDefaultMeshFile(fl);
    if (def) void loadPreviewForFile(def);
    else {
      hint.textContent = "未找到 .step / .stp / .obj / .inp，可调整左侧筛选";
      hint.classList.remove("hidden");
      objLabel.textContent = "—";
    }
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
    requestAnimationFrame(() => {
      root.classList.add("isOpen");
      shell?.classList.add("isOpen");
    });
  }

  function close() {
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

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && root.classList.contains("isOpen")) close();
  });

  return {
    open,
    close,
    destroy: () => {
      revokeBlobs();
      destroyThree();
      root.remove();
    },
  };
}
