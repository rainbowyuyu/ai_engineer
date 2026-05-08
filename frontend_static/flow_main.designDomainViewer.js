import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/**
 * 双视口 OC4 预览：左右各一套 Scene / Renderer / OrbitControls，避免相机耦合。
 * @param {{ leftContainer: HTMLElement | null, rightContainer: HTMLElement | null, normalizedBaseUrl: () => string }} deps
 */
export function createDesignDomainViewer(deps) {
  const { leftContainer, rightContainer, normalizedBaseUrl } = deps;

  function makeSide(container, meshColor) {
    if (!container) {
      return {
        loadUrl: async () => {},
        disposeSide: () => {},
        resize: () => {},
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
    container.appendChild(wrap);
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
    const loader = new OBJLoader();
    let current = null;
    let fitted = false;
    let lastW = 0;
    let lastH = 0;
    const ro = new ResizeObserver(() => resize());
    ro.observe(container);

    function resize() {
      const vp = typeof container.closest === "function" ? container.closest(".designDomainViewport") : null;
      const r = (vp || container).getBoundingClientRect();
      const w = Math.max(1, Math.floor(r.width));
      const h = Math.max(1, Math.floor(r.height));
      if (w === lastW && h === lastH) return;
      lastW = w;
      lastH = h;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }

    /** 在父级从 display:none 变为可见后强制按视口重算尺寸 */
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

    function applyObj(obj) {
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
      if (current) {
        scene.remove(current);
        current.traverse((c) => {
          if (c.isMesh && c.material?.dispose) c.material.dispose();
        });
      }
      current = obj;
      scene.add(obj);
      const box = new THREE.Box3().setFromObject(obj);
      if (!box.isEmpty()) {
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxS = Math.max(size.x, size.y, size.z, 1e-6);
        const offset = center.clone().multiplyScalar(-1);
        obj.position.copy(offset);
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

    async function loadUrl(relOrAbs) {
      const path = String(relOrAbs || "").trim();
      if (!path) return;
      fitted = false;
      const base = normalizedBaseUrl();
      const url = path.startsWith("http") ? path : `${base}${path.startsWith("/") ? path : `/${path}`}`;
      const OBJ_FETCH_MS = 240000;
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), OBJ_FETCH_MS);
      let resp;
      try {
        resp = await fetch(url, { cache: "no-store", signal: ctrl.signal });
      } catch (e) {
        if (e?.name === "AbortError") {
          throw new Error(`OBJ 下载超时（${Math.round(OBJ_FETCH_MS / 1000)}s），请检查 /runs 是否可访问或文件过大：${url}`);
        }
        throw e;
      } finally {
        clearTimeout(timer);
      }
      if (!resp.ok) {
        throw new Error(`OBJ 请求失败 ${resp.status}：${url}`);
      }
      const text = await resp.text();
      if (!text || text.length < 80) {
        throw new Error(`OBJ 内容异常（过短或空）：${url}`);
      }
      let obj;
      try {
        obj = loader.parse(text);
      } catch (e) {
        throw new Error(`OBJ 解析失败：${e?.message || e}`);
      }
      applyObj(obj);
    }

    function disposeSide() {
      ro.disconnect();
      if (current) {
        scene.remove(current);
        current.traverse((c) => {
          if (c.isMesh && c.material?.dispose) c.material.dispose();
        });
        current = null;
      }
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
      if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    }

    return { loadUrl, disposeSide, resize: invalidateAndResize };
  }

  const left = makeSide(leftContainer, 0x60a5fa);
  const right = makeSide(rightContainer, 0x34d399);

  return {
    loadLeft: (u) => left.loadUrl(u),
    loadRight: (u) => right.loadUrl(u),
    resizeAll: () => {
      left.resize?.();
      right.resize?.();
    },
    dispose: () => {
      left.disposeSide();
      right.disposeSide();
    },
  };
}
