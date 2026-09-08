import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { parseLegacyAsciiUnstructuredGridTets } from "./flow_main.vtkLegacyAscii.js";

function meshUrlExt(url) {
  const path = String(url || "").split("?")[0].split("#")[0];
  const m = /\.([a-z0-9]+)$/i.exec(path);
  return m ? `.${m[1].toLowerCase()}` : "";
}

function fileNameFromUrl(url) {
  const path = String(url || "").split("?")[0].split("#")[0];
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] || path || "";
}

export function createViewer(deps) {
  const { refs, state, normalizedBaseUrl, checkStep3Ready, onMeshMeta } = deps;
  const container = refs.container;
  if (!container) {
    return {
      loadMesh: async () => {},
      upsertImage: () => {},
      setAutoRotate: () => {},
      getAutoRotate: () => false,
      resetPreviewState: () => {},
      getLastMeshUrl: () => "",
      getStatus: () => ({ phase: "idle", url: "", error: "" }),
    };
  }

  container.classList.add("flowVtkHost");
  let statusEl = container.querySelector(".flowVtkStatus");
  if (!statusEl) {
    statusEl = document.createElement("div");
    statusEl.className = "flowVtkStatus";
    statusEl.setAttribute("aria-live", "polite");
    container.appendChild(statusEl);
  }

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x020a2b);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
  camera.position.set(0, 0, 3);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  container.appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  let hasAutoFittedOnce = false;
  /** 首次适配后锁定网格根节点世界坐标，避免每次迭代因包围盒中心漂移导致画面抽动 */
  let frozenMeshRootPosition = null;
  scene.add(new THREE.AmbientLight(0xffffff, 0.42));
  const d = new THREE.DirectionalLight(0xffffff, 1.05);
  d.position.set(2, 2, 2);
  scene.add(d);
  const d2 = new THREE.DirectionalLight(0xa5f3fc, 0.35);
  d2.position.set(-2, 1, -1);
  scene.add(d2);
  const loader = new OBJLoader();
  let currentObj = null;
  const spinAxis = new THREE.Vector3(0, 1, 0);
  const spinStep = new THREE.Quaternion().setFromAxisAngle(spinAxis, 0.0015);
  let spinEnabled = true;
  const grid = new THREE.GridHelper(4, 16, 0x274472, 0x1e3a5f);
  grid.position.y = -1.2;
  scene.add(grid);

  let lastW = 0;
  let lastH = 0;
  let debounceMeshTimer = null;
  let loadSeq = 0;
  let pendingMeshUrl = "";
  /** 加载进行中时后来的「跟最新」请求合并到此，避免每帧打断解析导致永远黑屏 */
  let coalesceMeshUrl = "";
  let lastMeshUrl = "";
  let lastMeshLoadAt = 0;
  let statusPhase = "idle";
  let statusError = "";
  const imageLastUrlByName = new Map();
  const imageLastRefreshAtByName = new Map();
  const LIVE_PREVIEW_MAX_CELLS = 48000;

  function paintStatus() {
    if (!statusEl) return;
    if (statusPhase === "loading") {
      statusEl.className = "flowVtkStatus flowVtkStatus--loading";
      statusEl.textContent = `加载中 · ${fileNameFromUrl(pendingMeshUrl || lastMeshUrl) || "网格"}`;
      statusEl.classList.remove("hidden");
      return;
    }
    if (statusPhase === "error") {
      statusEl.className = "flowVtkStatus flowVtkStatus--error";
      statusEl.textContent = statusError || "网格加载失败";
      statusEl.classList.remove("hidden");
      return;
    }
    if (statusPhase === "empty" || !currentObj) {
      statusEl.className = "flowVtkStatus flowVtkStatus--empty";
      statusEl.textContent = "等待 VTK 帧序列 · 优化开始后将自动刷新";
      statusEl.classList.remove("hidden");
      return;
    }
    statusEl.className = "flowVtkStatus hidden";
    statusEl.textContent = "";
  }

  function setStatus(phase, error = "") {
    statusPhase = phase;
    statusError = String(error || "");
    paintStatus();
    try {
      onMeshMeta?.({
        phase: statusPhase,
        url: lastMeshUrl || pendingMeshUrl,
        name: fileNameFromUrl(lastMeshUrl || pendingMeshUrl),
        error: statusError,
        ready: Boolean(currentObj),
      });
    } catch {
      /* ignore */
    }
  }

  function resize() {
    const r = container.getBoundingClientRect();
    const w = Math.max(1, Math.floor(r.width));
    const h = Math.max(1, Math.floor(r.height));
    if (w === lastW && h === lastH) return;
    lastW = w;
    lastH = h;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }
  new ResizeObserver(() => resize()).observe(container);
  function animate() {
    requestAnimationFrame(animate);
    if (spinEnabled && currentObj) currentObj.quaternion.multiply(spinStep);
    controls.update();
    renderer.render(scene, camera);
  }
  resize();
  animate();
  setStatus("empty");

  function applyMeshSwap(obj) {
    const prev = currentObj;
    const prevQuat = prev ? prev.quaternion.clone() : null;
    obj.traverse((c) => {
      if (c.isMesh) {
        c.material = new THREE.MeshStandardMaterial({
          color: 0x7dd3fc,
          metalness: 0.08,
          roughness: 0.48,
          side: THREE.DoubleSide,
          flatShading: true,
        });
      }
    });
    if (prev) {
      scene.remove(prev);
      prev.traverse((c) => {
        if (c.isMesh) {
          c.geometry?.dispose?.();
          if (c.material?.dispose) c.material.dispose();
        }
      });
    }
    currentObj = obj;
    if (prevQuat) obj.quaternion.copy(prevQuat);
    scene.add(obj);

    const box = new THREE.Box3().setFromObject(obj);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z, 1e-6) * 0.5;
    const centered = center.clone().negate();

    if (hasAutoFittedOnce && frozenMeshRootPosition) {
      obj.position.copy(frozenMeshRootPosition);
    } else {
      obj.position.copy(centered);
    }

    if (!hasAutoFittedOnce) {
      const fov = (camera.fov * Math.PI) / 180;
      const distance = Math.max(radius / Math.sin(fov / 2), 1.8);
      camera.position.set(distance * 0.95, distance * 0.65, distance * 1.05);
      camera.near = Math.max(radius / 5000, distance / 400);
      camera.far = Math.max(1000, distance * 40);
      camera.updateProjectionMatrix();
      controls.minDistance = Math.max(0.2, distance * 0.12);
      controls.maxDistance = Math.max(10, distance * 12);
      controls.target.set(0, 0, 0);
      controls.update();
      const gScale = Math.max(radius * 0.55, 1);
      grid.scale.set(gScale / 2, 1, gScale / 2);
      grid.position.y = -radius * 0.42;
      hasAutoFittedOnce = true;
      frozenMeshRootPosition = obj.position.clone();
    }
    resize();
    state.meshReady = true;
    checkStep3Ready();
    setStatus("ready");
  }

  function objectFromVtkText(text, preview = true) {
    const hdr = /CELLS\s+(\d+)/i.exec(text);
    const nCellsHint = hdr ? parseInt(hdr[1], 10) : 0;
    let stride = 1;
    if (preview && Number.isFinite(nCellsHint) && nCellsHint > LIVE_PREVIEW_MAX_CELLS) {
      stride = Math.max(1, Math.ceil(nCellsHint / LIVE_PREVIEW_MAX_CELLS));
    }
    const { geometry, usedCells, numCells } = parseLegacyAsciiUnstructuredGridTets(text, {
      stride,
      maxCells: preview ? LIVE_PREVIEW_MAX_CELLS : 0,
    });
    const mesh = new THREE.Mesh(geometry);
    mesh.userData.vtkMeta = { usedCells, numCells, stride };
    const root = new THREE.Group();
    root.add(mesh);
    return root;
  }

  function loadMesh(url, opts = {}) {
    const force = Boolean(opts.force);
    const now = Date.now();
    if (!url) return;
    if (url === pendingMeshUrl && !force) return;
    if (!force && url === lastMeshUrl && now - lastMeshLoadAt < 2000) return;
    // 正在解析大 VTK 时，自动跟帧只记下最新 URL，等当前完成后一次跳到最新（避免永久黑屏）
    if (!force && pendingMeshUrl && statusPhase === "loading") {
      coalesceMeshUrl = url;
      return;
    }
    pendingMeshUrl = url;
    coalesceMeshUrl = "";
    const seq = ++loadSeq;
    clearTimeout(debounceMeshTimer);
    setStatus("loading");
    debounceMeshTimer = setTimeout(() => {
      void (async () => {
        try {
          const resp = await fetch(`${normalizedBaseUrl()}${url}`, { cache: "no-store" });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const text = await resp.text();
          if (seq !== loadSeq) return;
          const ext = meshUrlExt(url);
          let obj;
          if (ext === ".vtk") {
            obj = objectFromVtkText(text, opts.fullQuality !== true);
          } else if (ext === ".obj" || text.trimStart().startsWith("v ") || text.includes("\nv ")) {
            obj = loader.parse(text);
          } else if (text.includes("DATASET UNSTRUCTURED_GRID") || text.includes("# vtk DataFile")) {
            obj = objectFromVtkText(text, opts.fullQuality !== true);
          } else {
            throw new Error(`不支持的网格格式（${ext || "未知"}）`);
          }
          if (seq !== loadSeq) return;
          applyMeshSwap(obj);
          lastMeshUrl = url;
          lastMeshLoadAt = Date.now();
          const meta = obj?.children?.[0]?.userData?.vtkMeta;
          if (meta && meta.stride > 1) {
            statusEl.className = "flowVtkStatus flowVtkStatus--loading";
            statusEl.textContent = `已显示 · ${fileNameFromUrl(url)}（抽样 ${meta.usedCells}/${meta.numCells}）`;
            statusEl.classList.remove("hidden");
            setTimeout(() => {
              if (lastMeshUrl === url && statusPhase === "ready") paintStatus();
            }, 2200);
          }
        } catch (e) {
          if (seq === loadSeq) {
            setStatus("error", e?.message || String(e));
          }
        }
        if (seq === loadSeq) {
          pendingMeshUrl = "";
          const next = coalesceMeshUrl;
          coalesceMeshUrl = "";
          if (next && next !== lastMeshUrl) {
            loadMesh(next);
          }
        }
      })();
    }, force ? 0 : 120);
  }

  function upsertImage(name, url) {
    if (!refs.imgGrid) return;
    const emptyCard = refs.imgGrid.querySelector(".imgEmptyState");
    if (emptyCard) emptyCard.remove();
    let card = refs.imgGrid.querySelector(`[data-img='${name}']`);
    if (!card) {
      card = document.createElement("div");
      card.className = "imgCard";
      card.dataset.img = name;
      card.innerHTML = `<div class="imgCardHd"><span>${name}</span><a target="_blank">打开</a></div><img />`;
      refs.imgGrid.appendChild(card);
      state.imageCount += 1;
      checkStep3Ready();
    }
    const a = card.querySelector("a");
    const img = card.querySelector("img");
    const full = `${normalizedBaseUrl()}${url}`;
    a.href = full;
    const lastUrl = imageLastUrlByName.get(name) || "";
    const lastAt = imageLastRefreshAtByName.get(name) || 0;
    const now = Date.now();
    if (lastUrl !== full || now - lastAt > 3500) {
      img.src = `${full}?t=${now}`;
      imageLastUrlByName.set(name, full);
      imageLastRefreshAtByName.set(name, now);
    }
  }

  function setAutoRotate(v) {
    spinEnabled = Boolean(v);
  }

  function getAutoRotate() {
    return spinEnabled;
  }

  function resetPreviewState() {
    hasAutoFittedOnce = false;
    frozenMeshRootPosition = null;
    lastMeshUrl = "";
    lastMeshLoadAt = 0;
    pendingMeshUrl = "";
    coalesceMeshUrl = "";
    loadSeq += 1;
    if (debounceMeshTimer) {
      clearTimeout(debounceMeshTimer);
      debounceMeshTimer = null;
    }
    if (currentObj) {
      scene.remove(currentObj);
      currentObj.traverse((c) => {
        if (c.isMesh) {
          c.geometry?.dispose?.();
          if (c.material?.dispose) c.material.dispose();
        }
      });
      currentObj = null;
    }
    grid.scale.set(1, 1, 1);
    grid.position.y = -1.2;
    state.meshReady = false;
    checkStep3Ready();
    setStatus("empty");
  }

  return {
    loadMesh,
    upsertImage,
    setAutoRotate,
    getAutoRotate,
    resetPreviewState,
    getLastMeshUrl: () => lastMeshUrl,
    getStatus: () => ({ phase: statusPhase, url: lastMeshUrl, error: statusError }),
  };
}
