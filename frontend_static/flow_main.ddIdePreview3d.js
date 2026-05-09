/**
 * 设计域中栏单画布：会话内 OBJ / STEP（OpenCascade WASM）预览。
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

/**
 * @param {{ mountEl: HTMLElement | null, normalizedBaseUrl: () => string }} deps
 */
export function createDdIdePreview3d(deps) {
  const { mountEl, normalizedBaseUrl } = deps;
  if (!mountEl) {
    return {
      loadObjFromUrl: async () => {},
      loadStepFromUrl: async () => {},
      resize: () => {},
      capturePngDataUrl: () => null,
      dispose: () => {},
    };
  }

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf1f5f9);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 2000);
  camera.position.set(2.2, 1.6, 2.4);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const wrap = document.createElement("div");
  wrap.className = "designDomainCanvasInner";
  wrap.style.cssText = "position:absolute;inset:0;";
  mountEl.appendChild(wrap);
  wrap.appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.85);
  d1.position.set(4, 6, 5);
  scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xa5b4fc, 0.35);
  d2.position.set(-3, 2, -4);
  scene.add(d2);

  const objLoader = new OBJLoader();
  /** @type {THREE.Object3D | null} */
  let current = null;
  let fitted = false;
  let lastW = 0;
  let lastH = 0;
  const ro = new ResizeObserver(() => resize());
  ro.observe(mountEl);

  function resize() {
    const vp = typeof mountEl.closest === "function" ? mountEl.closest(".designDomainViewport") : null;
    const r = (vp || mountEl).getBoundingClientRect();
    const w = Math.max(1, Math.floor(r.width));
    const h = Math.max(1, Math.floor(r.height));
    if (w === lastW && h === lastH) return;
    lastW = w;
    lastH = h;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }

  function invalidateAndResize() {
    lastW = 0;
    lastH = 0;
    resize();
  }

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  resize();
  animate();

  function disposeCurrent() {
    if (!current) return;
    scene.remove(current);
    current.traverse((c) => {
      if (c.isMesh) {
        c.geometry?.dispose?.();
        if (Array.isArray(c.material)) c.material.forEach((m) => m.dispose?.());
        else c.material?.dispose?.();
      }
    });
    current = null;
  }

  function applyRoot(obj, meshColor) {
    disposeCurrent();
    obj.traverse((c) => {
      if (c.isMesh) {
        c.material = new THREE.MeshStandardMaterial({
          color: meshColor,
          metalness: 0.08,
          roughness: 0.42,
          side: THREE.DoubleSide,
        });
      }
    });
    current = obj;
    scene.add(obj);
    const box = new THREE.Box3().setFromObject(obj);
    if (!box.isEmpty()) {
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxS = Math.max(size.x, size.y, size.z, 1e-6);
      obj.position.copy(center.clone().multiplyScalar(-1));
      if (!fitted) {
        const radius = maxS * 0.5;
        const fov = (camera.fov * Math.PI) / 180;
        const dist = Math.max(radius / Math.sin(fov / 2), 1.2);
        camera.position.set(dist * 0.92, dist * 0.62, dist * 0.95);
        camera.near = Math.max(0.001, dist / 400);
        camera.far = Math.max(4000, dist * 30);
        camera.updateProjectionMatrix();
        controls.target.set(0, 0, 0);
        controls.minDistance = Math.max(0.05, dist * 0.08);
        controls.maxDistance = Math.max(8, dist * 12);
        controls.update();
        fitted = true;
      }
    }
    resize();
  }

  function absUrl(path) {
    const p = String(path || "").trim();
    const base = String(normalizedBaseUrl?.() || "").replace(/\/+$/, "");
    if (!p) return "";
    return p.startsWith("http") ? p : `${base}${p.startsWith("/") ? p : `/${p}`}`;
  }

  async function loadObjFromUrl(relOrAbs) {
    fitted = false;
    const url = absUrl(relOrAbs);
    if (!url) return;
    const OBJ_FETCH_MS = 240000;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), OBJ_FETCH_MS);
    let resp;
    try {
      resp = await fetch(url, { cache: "no-store", signal: ctrl.signal });
    } finally {
      clearTimeout(timer);
    }
    if (!resp.ok) throw new Error(`OBJ 请求失败 ${resp.status}：${url}`);
    const text = await resp.text();
    if (!text || text.length < 40) throw new Error("OBJ 内容异常（过短或空）");
    const obj = objLoader.parse(text);
    applyRoot(obj, 0x60a5fa);
  }

  async function loadStepFromUrl(relOrAbs) {
    fitted = false;
    const url = absUrl(relOrAbs);
    if (!url) return;
    const occt = await loadOcctImportJs();
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 300000);
    let resp;
    try {
      resp = await fetch(url, { cache: "no-store", signal: ctrl.signal });
    } finally {
      clearTimeout(timer);
    }
    if (!resp.ok) throw new Error(`STEP 请求失败 ${resp.status}：${url}`);
    const buf = new Uint8Array(await resp.arrayBuffer());
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
    if (!list?.length) throw new Error("STEP 中未解析出网格");
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
    if (!group.children.length) throw new Error("STEP 三角化后无可显示网格");
    applyRoot(group, 0x60a5fa);
  }

  function capturePngDataUrl() {
    try {
      invalidateAndResize();
      controls.update();
      renderer.render(scene, camera);
      return renderer.domElement.toDataURL("image/png");
    } catch {
      return null;
    }
  }

  return {
    loadObjFromUrl,
    loadStepFromUrl,
    resize: invalidateAndResize,
    capturePngDataUrl,
    dispose() {
      ro.disconnect();
      disposeCurrent();
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
      if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    },
  };
}
