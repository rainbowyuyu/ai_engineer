import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export function createViewer(deps) {
  const { refs, state, normalizedBaseUrl, checkStep3Ready } = deps;
  const container = refs.container;
  if (!container) {
    return {
      loadMesh: async () => {},
      upsertImage: () => {},
      setAutoRotate: () => {},
      getAutoRotate: () => false,
      resetPreviewState: () => {},
    };
  }

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x020a2b);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
  camera.position.set(0, 0, 3);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  container.appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  let hasAutoFittedOnce = false;
  /** 首次适配后锁定网格根节点世界坐标，避免每次 OBJ 更新因包围盒中心漂移导致画面抽动 */
  let frozenMeshRootPosition = null;
  scene.add(new THREE.AmbientLight(0xffffff, 0.35));
  const d = new THREE.DirectionalLight(0xffffff, 1);
  d.position.set(2, 2, 2);
  scene.add(d);
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
  let lastMeshUrl = "";
  let lastMeshLoadAt = 0;
  const imageLastUrlByName = new Map();
  const imageLastRefreshAtByName = new Map();

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

  function applyMeshSwap(obj) {
    const prev = currentObj;
    const prevQuat = prev ? prev.quaternion.clone() : null;
    obj.traverse((c) => {
      if (c.isMesh) {
        c.material = new THREE.MeshStandardMaterial({ color: 0x93c5fd, metalness: 0.05, roughness: 0.5, side: THREE.DoubleSide });
      }
    });
    if (prev) {
      scene.remove(prev);
      prev.traverse((c) => {
        if (c.isMesh && c.material && c.material.dispose) c.material.dispose();
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

    // 首次加载时适配相机；后续迭代不再改相机与网格根位置，仅换几何，避免包围盒中心变化引起抽动
    if (!hasAutoFittedOnce) {
      const fov = (camera.fov * Math.PI) / 180;
      const distance = Math.max(radius / Math.sin(fov / 2), 1.8);
      camera.position.set(distance * 0.95, distance * 0.65, distance * 1.05);
      camera.near = Math.max(0.001, distance / 200);
      camera.far = Math.max(1000, distance * 20);
      camera.updateProjectionMatrix();
      controls.minDistance = Math.max(0.2, distance * 0.2);
      controls.maxDistance = Math.max(10, distance * 8);
      controls.target.set(0, 0, 0);
      controls.update();
      hasAutoFittedOnce = true;
      frozenMeshRootPosition = obj.position.clone();
    }
    resize();
    state.meshReady = true;
    checkStep3Ready();
  }

  function loadMesh(url) {
    const now = Date.now();
    if (url === pendingMeshUrl) return;
    // Poll/snapshot 会重复推送同一 mesh，限制同 URL 的重载频率，避免画面持续抽动
    if (url === lastMeshUrl && now - lastMeshLoadAt < 2000) return;
    pendingMeshUrl = url;
    const seq = ++loadSeq;
    clearTimeout(debounceMeshTimer);
    debounceMeshTimer = setTimeout(() => {
      void (async () => {
        try {
          const text = await (await fetch(`${normalizedBaseUrl()}${url}`, { cache: "no-store" })).text();
          if (seq !== loadSeq) return;
          const obj = loader.parse(text);
          applyMeshSwap(obj);
          lastMeshUrl = url;
          lastMeshLoadAt = Date.now();
        } catch {}
        if (seq === loadSeq) pendingMeshUrl = "";
      })();
    }, 100);
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
    // 同一图片在 polling 下会被高频重复上报；仅在 URL 变化或超过间隔时刷新，避免页面“持续刷新感”
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
    loadSeq += 1;
    if (debounceMeshTimer) {
      clearTimeout(debounceMeshTimer);
      debounceMeshTimer = null;
    }
    if (currentObj) {
      scene.remove(currentObj);
      currentObj.traverse((c) => {
        if (c.isMesh && c.material && c.material.dispose) c.material.dispose();
      });
      currentObj = null;
    }
    state.meshReady = false;
    checkStep3Ready();
  }

  return {
    loadMesh,
    upsertImage,
    setAutoRotate,
    getAutoRotate,
    resetPreviewState,
  };
}
