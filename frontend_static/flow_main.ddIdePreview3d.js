/**
 * 设计域中栏单画布：会话内 OBJ / STEP（OpenCascade WASM）/ INP 体网格预览。
 * INP 含 *CLOAD 时叠加与结果查看器一致的黄箭头 / 红约束点。
 */
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  buildFemBcOverlayGroup,
  parseInpC3D4ToBufferGeometry,
  parseInpFemBc,
} from "./flow_main.inpCcxAscii.js";
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

/**
 * @param {ReturnType<typeof parseInpFemBc> | null} bc
 */
export function summarizeInpForceDirection(bc) {
  if (!bc?.steps?.length) {
    return { label: "无 *CLOAD", fx: 0, fy: 0, fz: 0, n: 0, primary: "" };
  }
  const st = bc.steps[bc.steps.length - 1];
  let fx = 0,
    fy = 0,
    fz = 0;
  for (const c of st.cloads || []) {
    if (c.dof === 1) fx += c.mag;
    else if (c.dof === 2) fy += c.mag;
    else if (c.dof === 3) fz += c.mag;
  }
  const abs = [
    { k: "X", v: fx },
    { k: "Y", v: fy },
    { k: "Z", v: fz },
  ].sort((a, b) => Math.abs(b.v) - Math.abs(a.v))[0];
  let primary = "";
  if (abs && Math.abs(abs.v) > 1e-9) {
    primary = `${abs.v < 0 ? "−" : "+"}${abs.k}`;
  }
  const label = primary
    ? `主方向 ${primary} · ΣFx=${fx.toExponential(2)} ΣFy=${fy.toExponential(2)} ΣFz=${fz.toExponential(2)} N`
    : "无有效集中力";
  return { label, fx, fy, fz, n: st.cloads?.length || 0, primary };
}

/**
 * @param {{
 *   mountEl: HTMLElement | null,
 *   normalizedBaseUrl: () => string,
 *   onBcSummary?: (s: ReturnType<typeof summarizeInpForceDirection> | null) => void,
 *   onLoadProgress?: (p: { title?: string, detail?: string } | null) => void,
 * }} deps
 */
export function createDdIdePreview3d(deps) {
  const { mountEl, normalizedBaseUrl, onBcSummary, onLoadProgress } = deps;
  if (!mountEl) {
    return {
      loadObjFromUrl: async () => {},
      loadStepFromUrl: async () => {},
      loadInpMesh: async () => {},
      setBcOverlayVisible: () => {},
      getBcOverlayVisible: () => false,
      getLastBcSummary: () => null,
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
  /** @type {THREE.Object3D | null} */
  let bcOverlay = null;
  let bcOverlayVisible = true;
  /** @type {ReturnType<typeof summarizeInpForceDirection> | null} */
  let lastBcSummary = null;
  let fitted = false;
  let lastW = 0;
  let lastH = 0;
  const ro = new ResizeObserver(() => resize());
  ro.observe(mountEl);

  function reportProgress(p) {
    try {
      onLoadProgress?.(p);
    } catch {
      /* ignore */
    }
  }

  /** 让出一帧，确保加载遮罩先画出来再进入重解析。 */
  function yieldToUi() {
    return new Promise((resolve) => {
      requestAnimationFrame(() => setTimeout(resolve, 0));
    });
  }

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

  function clearBcOverlay() {
    if (bcOverlay && current) {
      try {
        current.remove(bcOverlay);
      } catch {
        /* ignore */
      }
    }
    if (bcOverlay) {
      bcOverlay.traverse((c) => {
        if (c.geometry?.dispose) c.geometry.dispose();
        const mats = Array.isArray(c.material) ? c.material : c.material ? [c.material] : [];
        for (const m of mats) m.dispose?.();
      });
    }
    bcOverlay = null;
    lastBcSummary = null;
    try {
      onBcSummary?.(null);
    } catch {
      /* ignore */
    }
  }

  function disposeCurrent() {
    clearBcOverlay();
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
      if (c.isMesh && !c.userData?.ddSkipMaterial) {
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

  function applyMeshGeometry(geometry, colorHex) {
    const mat = new THREE.MeshStandardMaterial({
      color: colorHex,
      metalness: 0.08,
      roughness: 0.42,
      side: THREE.DoubleSide,
    });
    applyRoot(new THREE.Mesh(geometry, mat), colorHex);
  }

  function applyBcFromInpText(text) {
    clearBcOverlay();
    if (!current || !text) return null;
    try {
      const bc = parseInpFemBc(text);
      const summary = summarizeInpForceDirection(bc);
      lastBcSummary = summary;
      if (!bc?.steps?.length || !summary.n) {
        onBcSummary?.(summary);
        return summary;
      }
      const { group } = buildFemBcOverlayGroup(bc, { maxArrows: 120, maxMarkers: 800 });
      group.name = "ddIdeBcOverlay";
      group.visible = bcOverlayVisible;
      group.traverse((ch) => {
        if (ch.isMesh) ch.userData.ddSkipMaterial = true;
      });
      current.add(group);
      bcOverlay = group;
      onBcSummary?.(summary);
      return summary;
    } catch (e) {
      lastBcSummary = { label: `BC 解析失败：${e?.message || e}`, fx: 0, fy: 0, fz: 0, n: 0, primary: "" };
      onBcSummary?.(lastBcSummary);
      return lastBcSummary;
    }
  }

  function setBcOverlayVisible(v) {
    bcOverlayVisible = Boolean(v);
    if (bcOverlay) bcOverlay.visible = bcOverlayVisible;
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
    try {
      reportProgress({ title: "正在加载 OBJ 预览…", detail: "下载几何文件" });
      await yieldToUi();
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
      reportProgress({ title: "正在加载 OBJ 预览…", detail: "解析三角网格" });
      await yieldToUi();
      const text = await resp.text();
      if (!text || text.length < 40) throw new Error("OBJ 内容异常（过短或空）");
      const obj = objLoader.parse(text);
      applyRoot(obj, 0x60a5fa);
    } finally {
      reportProgress(null);
    }
  }

  async function loadStepFromUrl(relOrAbs) {
    fitted = false;
    const url = absUrl(relOrAbs);
    if (!url) return;
    try {
      reportProgress({ title: "正在加载 STEP 预览…", detail: "准备 OpenCascade 解析器" });
      await yieldToUi();
      const occt = await loadOcctImportJs();
      reportProgress({ title: "正在加载 STEP 预览…", detail: "下载 STEP 文件" });
      await yieldToUi();
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
      reportProgress({ title: "正在加载 STEP 预览…", detail: "三角化实体（较慢，请稍候）" });
      await yieldToUi();
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
    } finally {
      reportProgress(null);
    }
  }

  /**
   * 与结果查看器一致：优先服务端 INP→VTK，失败则本地 C3D4 解析。
   * VTK 与 INP 文本并行拉取；先上网格再叠约束，缩短「白屏」时间。
   * @param {{ sessionId?: string, relPath?: string, fileUrl?: string }} opts
   */
  async function loadInpMesh(opts = {}) {
    fitted = false;
    const sid = String(opts.sessionId || "").trim();
    const rel = String(opts.relPath || "").trim().replace(/\\/g, "/").replace(/^\/+/, "");
    const base = String(normalizedBaseUrl?.() || "").replace(/\/+$/, "");
    const errors = [];
    const fileUrl = absUrl(opts.fileUrl || "");

    try {
      reportProgress({ title: "正在加载网格预览…", detail: "并行下载体网格与约束数据" });
      await yieldToUi();

      /** @type {Promise<string>} */
      const inpTextPromise = (async () => {
        if (!fileUrl) return "";
        try {
          const fr = await fetch(fileUrl, { cache: "no-store" });
          if (fr.ok) return await fr.text();
        } catch {
          /* ignore */
        }
        return "";
      })();

      /** @type {Promise<{ ok: boolean, vtkText?: string, err?: string }>} */
      const vtkPromise = (async () => {
        if (!(sid && rel && base)) return { ok: false, err: "" };
        try {
          const api = `${base}/api/oc4/design-domain/session/${encodeURIComponent(sid)}/preview/inp-mesh-vtk?path=${encodeURIComponent(rel)}`;
          const r = await fetch(api, { cache: "no-store" });
          if (r.ok) return { ok: true, vtkText: await r.text() };
          const tx = await r.text().catch(() => "");
          return { ok: false, err: `服务端 VTK ${r.status}${tx ? `: ${tx.slice(0, 160)}` : ""}` };
        } catch (e) {
          return { ok: false, err: `服务端 VTK：${e?.message || e}` };
        }
      })();

      const [inpSettled, vtkSettled] = await Promise.all([inpTextPromise, vtkPromise]);
      let inpText = inpSettled || "";
      const vtkRes = vtkSettled;

      if (vtkRes.ok && vtkRes.vtkText) {
        try {
          reportProgress({ title: "正在加载网格预览…", detail: "构建三维网格场景" });
          await yieldToUi();
          const { geometry } = parseLegacyAsciiUnstructuredGridTets(vtkRes.vtkText);
          applyMeshGeometry(geometry, 0x34d399);
          if (inpText) {
            reportProgress({ title: "正在加载网格预览…", detail: "叠加约束与载荷箭头" });
            await yieldToUi();
            applyBcFromInpText(inpText);
          }
          return;
        } catch (e) {
          errors.push(`服务端 VTK 解析：${e?.message || e}`);
        }
      } else if (vtkRes.err) {
        errors.push(vtkRes.err);
      }

      if (fileUrl && base && inpText) {
        reportProgress({ title: "正在加载网格预览…", detail: "服务端转换 INP → VTK" });
        await yieldToUi();
        try {
          const blob = new Blob([inpText], { type: "text/plain" });
          const fd = new FormData();
          fd.append("file", blob, rel.split("/").pop() || "mesh.inp");
          const r = await fetch(`${base}/api/preview/inp-mesh-vtk`, { method: "POST", body: fd });
          if (r.ok) {
            const vtkText = await r.text();
            reportProgress({ title: "正在加载网格预览…", detail: "构建三维网格场景" });
            await yieldToUi();
            const { geometry } = parseLegacyAsciiUnstructuredGridTets(vtkText);
            applyMeshGeometry(geometry, 0x34d399);
            reportProgress({ title: "正在加载网格预览…", detail: "叠加约束与载荷箭头" });
            await yieldToUi();
            applyBcFromInpText(inpText);
            return;
          }
          errors.push(`上传转换 ${r.status}`);
        } catch (e) {
          errors.push(`上传转换：${e?.message || e}`);
        }
      }

      if (inpText) {
        reportProgress({ title: "正在加载网格预览…", detail: "本地解析 C3D4 单元（较慢）" });
        await yieldToUi();
        try {
          const { geometry } = parseInpC3D4ToBufferGeometry(inpText);
          applyMeshGeometry(geometry, 0x6ee7b7);
          applyBcFromInpText(inpText);
          return;
        } catch (e) {
          errors.push(`本地 C3D4：${e?.message || e}`);
        }
      }

      throw new Error(errors.filter(Boolean).join(" · ") || "INP 三维预览不可用");
    } finally {
      reportProgress(null);
    }
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
    loadInpMesh,
    setBcOverlayVisible,
    getBcOverlayVisible: () => bcOverlayVisible,
    getLastBcSummary: () => lastBcSummary,
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
